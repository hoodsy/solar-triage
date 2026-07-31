"""Adapter for the main PVDAQ data lake (parquet mirror).

Layout: data_dir holds the hive tree fetched by scripts/fetch_lake.sh —
year=YYYY/month=M/day=D/system_<id>__date_*.snappy.000.parquet, one file
per day, naive site-local "measured_on" stamps.

Unlike the Solar Data Prize CSVs, lake channels are per-system chaos: the
same quantity arrives as W, kW, or hectowatts, temperatures as °C, °F, or
K — so every column spec carries (offset, scale), applied as
(raw + offset) * scale, verified against daytime magnitude during
onboarding. -999/-9999 are PVDAQ missing-data sentinels, masked before
any conversion.

Sub-metering: site.electrical names the per-inverter AC power columns
(in fleet order); load_inverters returns them as inv_01..inv_NN like the
prize adapter, so the referee never knows which adapter fed it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from triage.adapters.pvdaq import _localize

if TYPE_CHECKING:
    from triage.config import SiteConfig

SENTINELS = (-999.0, -9999.0)


@dataclass(frozen=True)
class LakeColumn:
    name: str
    offset: float = 0.0  # applied before scale: (raw + offset) * scale
    scale: float = 1.0  # W -> kW: 0.001; °F -> °C: offset=-32, scale=5/9


@dataclass(frozen=True)
class PvdaqLakeAdapter:
    data_dir: Path  # the fetched year=/month=/day= parquet tree
    meter: LakeColumn  # becomes ac_power_kw
    irradiance: LakeColumn | None = None  # becomes poa_wm2; None = model tier
    temperature: LakeColumn | None = None  # becomes temp_c
    inverter_scale: float = 1.0  # site.electrical columns' AC power -> kW

    def _read(self, columns: list[str], site: SiteConfig) -> pd.DataFrame:
        """All day-files at once, on the tz-aware site grid."""
        df = pd.read_parquet(self.data_dir, columns=["measured_on", *columns])
        df = df.set_index("measured_on").sort_index()
        df.index = _localize(df.index, site.tz)
        df = df[df.index.notna()]
        df = df[~df.index.duplicated(keep="last")]
        df = df.mask(df.isin(SENTINELS))
        return df.resample(site.interval, closed="right", label="right").mean()

    def load(self, site: SiteConfig) -> pd.DataFrame:
        spec = {"ac_power_kw": self.meter}
        if self.irradiance is not None:
            spec["poa_wm2"] = self.irradiance
        if self.temperature is not None:
            spec["temp_c"] = self.temperature
        df = self._read([c.name for c in spec.values()], site)
        out = pd.DataFrame(index=df.index)
        for canonical, col in spec.items():
            out[canonical] = (df[col.name] + col.offset) * col.scale
        return out

    def load_inverters(self, site: SiteConfig) -> pd.DataFrame:
        df = self._read(list(site.electrical), site)
        renamed = {
            c: f"inv_{i + 1:02d}" for i, c in enumerate(site.electrical)
        }
        return df.rename(columns=renamed) * self.inverter_scale
