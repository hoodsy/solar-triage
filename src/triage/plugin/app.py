"""The plugin's HTTP surface, per the SolarQuant plugin spec:
GET /health and POST /measure. Run: uvicorn triage.plugin.app:app
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from triage.plugin import dayclose, store
from triage.plugin.backfill import backfill
from triage.plugin.bundle import load_bundle
from triage.plugin.config import load_settings


class MeasureBody(BaseModel):
    # datums stay untyped here: the spec wants per-datum accept/reject
    # counting, and a typed list would 400 the whole batch on one bad row
    datums: list[dict]


def _number(value) -> float | None:
    """Numeric per the spec's JSON types; bool is a different JSON type."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def ingest_datums(
    datums: list[dict], power_source_id: str
) -> tuple[int, int, list[tuple[str, int, float]]]:
    """Spec semantics: malformed datums are rejected; well-formed datums for
    other sources are accepted and ignored (a node posts every stream it has,
    not just ours); matching datums must carry numeric i.watts."""
    accepted = rejected = 0
    rows: list[tuple[str, int, float]] = []
    for datum in datums:
        source = datum.get("sourceId")
        ts = _number(datum.get("timestamp"))
        if not isinstance(source, str) or ts is None or "nodeId" not in datum:
            rejected += 1
            continue
        if source != power_source_id:
            accepted += 1
            continue
        watts = _number((datum.get("i") or {}).get("watts"))
        if watts is None:  # claims to be the power stream but has no measurement
            rejected += 1
            continue
        rows.append((source, int(ts), watts))
        accepted += 1
    return accepted, rejected, rows


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = load_settings()
        app.state.bundle = load_bundle(app.state.settings.model_path)
        app.state.db = store.connect(app.state.settings.db_path)
        backfill(app.state.settings, app.state.db)
        dayclose.close_pending(app.state.settings, app.state.bundle, app.state.db)
        app.state.started = time.time()
        yield
        app.state.db.close()

    app = FastAPI(title="triage plugin", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def bad_input(_: Request, exc: RequestValidationError) -> JSONResponse:
        # the spec's 400 Error shape, not FastAPI's default 422
        return JSONResponse(
            status_code=400,
            content={"error": "bad_input", "message": str(exc.errors()[:3])},
        )

    # handlers are async def but never await: they serialize on the event
    # loop, so the single sqlite connection sees one request at a time
    @app.get("/health")
    async def health() -> dict:
        return {
            "status": "healthy",
            "timestamp": int(time.time()),
            "uptime": round(time.time() - app.state.started, 3),
            "details": {
                "model_version": app.state.bundle.version,
                "closed_days": store.closed_days(app.state.db),
                "buffered_intervals": store.buffered_intervals(app.state.db),
            },
        }

    @app.post("/measure")
    async def measure(body: MeasureBody) -> dict:
        settings = app.state.settings
        accepted, rejected, rows = ingest_datums(body.datums, settings.power_source_id)
        if rows:
            store.upsert_intervals(app.state.db, rows)
        dayclose.close_pending(settings, app.state.bundle, app.state.db)
        return {
            "accepted": accepted,
            "rejected": rejected,
            "predictions": store.drain_predictions(app.state.db),
            "message": f"stored {len(rows)} power intervals",
        }

    return app


app = create_app()
