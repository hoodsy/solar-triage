"""Plugin configuration: everything arrives via the environment, because one
container serves one SolarNode and the node's deployment is where site facts
live. Boot fails loudly on anything missing — a silently-defaulted azimuth
would poison every expected-power number after it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from triage.config import SiteConfig
from triage.plugin.constants import DEFAULT_PREDICTION_SOURCE_ID


@dataclass(frozen=True)
class Settings:
    site: SiteConfig
    node_id: int
    power_source_id: str
    prediction_source_id: str
    model_path: Path
    db_path: Path
    backfill_days: int
    weather: bool


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"missing required env var {name}")
    return value


def load_settings() -> Settings:
    node_id = int(_required("NODE_ID"))
    site = SiteConfig(
        name=f"SolarNetwork node {node_id}",
        tz=_required("SITE_TZ"),
        dc_capacity_kw=float(_required("DC_KW")),
        ac_capacity_kw=float(_required("AC_KW")),
        source=None,  # datums are pushed via /measure; nothing pulls through the site
        lat=float(_required("LAT")),
        lon=float(_required("LON")),
        tilt=float(_required("TILT")),
        azimuth=float(_required("AZIMUTH")),
        interval=os.environ.get("INTERVAL", "15min"),
    )
    return Settings(
        site=site,
        node_id=node_id,
        power_source_id=_required("POWER_SOURCE_ID"),
        prediction_source_id=os.environ.get(
            "PREDICTION_SOURCE_ID", DEFAULT_PREDICTION_SOURCE_ID
        ),
        model_path=Path(os.environ.get("MODEL_PATH", "model/model.joblib")),
        db_path=Path(os.environ.get("DB_PATH", "/data/triage.db")),
        backfill_days=int(os.environ.get("BACKFILL_DAYS", "30")),
        weather=os.environ.get("WEATHER", "true").lower() in ("1", "true", "yes"),
    )
