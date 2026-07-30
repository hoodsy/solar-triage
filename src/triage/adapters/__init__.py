"""Source adapters: each turns a site's raw data into the canonical frame.

Canonical contract (every adapter's postcondition): tz-aware site-local
DatetimeIndex named "measured_on" at site.interval, where each label marks
the END of its interval (the 00:15 stamp covers 00:00-00:15); column
ac_power_kw (kW) and, when the site has an irradiance stream, poa_wm2
(W/m^2). expected_kw is a model, not a measurement — it is computed
downstream in build, never here.

This package index holds the generic pieces (the Adapter protocol and the
declarative spec dataclasses); each concrete source lives in its own module
(csv.py, solarnetwork.py) and is re-exported here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

import pandas as pd

if TYPE_CHECKING:
    from triage.config import SiteConfig


class Adapter(Protocol):
    def load(self, site: SiteConfig) -> pd.DataFrame:
        """Return the canonical measured frame for this site."""
        ...


@dataclass(frozen=True)
class SourceFile:
    name: str  # filename under the adapter's data_dir
    time_col: str = "measured_on"
    tz: str | None = None  # None: naive stamps in site-local time


@dataclass(frozen=True)
class Stream:
    # concat order = dedupe precedence order; a plain str means
    # SourceFile(name) with defaults (local naive "measured_on" stamps)
    files: tuple[SourceFile | str, ...]
    column: str  # source data column to extract
    keep: Literal["first", "last"] = "last"  # duplicate-timestamp winner
    resample: bool = False  # mean-resample to site.interval


from triage.adapters.csv import CsvAdapter  # noqa: E402
from triage.adapters.solarnetwork import SolarNetworkAdapter  # noqa: E402

__all__ = [
    "Adapter",
    "CsvAdapter",
    "SolarNetworkAdapter",
    "SourceFile",
    "Stream",
]
