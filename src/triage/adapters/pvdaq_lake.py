"""Adapter for the main PVDAQ data lake (parquet mirror).

Layout: data_dir holds the hive tree fetched by scripts/fetch_lake.sh —
year=YYYY/month=M/day=D/system_<id>__date_*.snappy.000.parquet, one file
per day. The mirror is LONG format: rows of (measured_on, metric_id,
value), naive site-local stamps. The wide CSV lake encodes the same
metric_id as each column's __NNNN suffix; configs carry the id.

Unlike the Solar Data Prize CSVs, lake channels are per-system chaos: the
same quantity arrives as W, kW, or hectowatts, temperatures as °C, °F, or
K — so every channel spec carries (offset, scale), applied as
(raw + offset) * scale, verified against daytime magnitude during
onboarding. -999/-9999 are PVDAQ missing-data sentinels, masked before
any conversion.

Sub-metering: site.electrical names the per-inverter AC power metric ids
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


def _convert(series: pd.Series, col: LakeColumn) -> pd.Series:
    """(raw + offset) * scale, piecewise over the column's unit eras."""
    out = (series + col.offset) * col.scale
    for start, offset, scale in col.breaks:
        after = series.index >= pd.Timestamp(start, tz=series.index.tz)
        out[after] = (series[after] + offset) * scale
    return out


@dataclass(frozen=True)
class LakeColumn:
    metric: int  # the channel's metric_id (the __NNNN suffix in lake CSVs)
    offset: float = 0.0  # applied before scale: (raw + offset) * scale
    scale: float = 1.0  # W -> kW: 0.001; °F -> °C: offset=-32, scale=5/9
    # logger swaps change a channel's units mid-history (the 2018-08-04
    # fleet migration flipped hW->W and °F->°C on several systems): from
    # each date, (offset, scale) are replaced. Onboarding must verify the
    # break is CLEAN — an overlap of both units (1202's meter) is unusable.
    breaks: tuple[tuple[str, float, float], ...] = ()  # (from_date, offset, scale)


@dataclass(frozen=True)
class PvdaqLakeAdapter:
    data_dir: Path  # the fetched year=/month=/day= parquet tree
    # one channel, or several summed (multi-meter plants like 1203's two
    # revenue meters); the sum is NaN whenever ANY constituent is missing —
    # half a plant reading as the whole plant would fake an outage
    meter: LakeColumn | tuple[LakeColumn, ...]  # becomes ac_power_kw
    irradiance: LakeColumn | None = None  # becomes poa_wm2; None = model tier
    temperature: LakeColumn | None = None  # becomes temp_c
    inverter_scale: float = 1.0  # site.electrical metrics' AC power -> kW
    # unit eras shared by every inverter channel — logger migrations flip
    # a whole logger's channels on the same date
    inverter_breaks: tuple[tuple[str, float, float], ...] = ()
    # stamp clamp: drop rows outside [start, end]. Old DAS files can carry
    # corrupt dates (system 50 stamps rows in 1822), and one such row makes
    # the resampled grid span centuries
    start: str | None = None
    end: str | None = None

    def _read(self, metrics: list[int], site: SiteConfig) -> pd.DataFrame:
        """Selected channels pivoted wide, on the tz-aware site grid."""
        df = pd.read_parquet(
            self.data_dir,
            columns=["measured_on", "metric_id", "value"],
            filters=[("metric_id", "in", metrics)],
        )
        df["value"] = df["value"].mask(df["value"].isin(SENTINELS))
        wide = df.pivot_table(
            index="measured_on", columns="metric_id", values="value",
            aggfunc="last",
        ).sort_index()
        wide.index = _localize(wide.index, site.tz)
        wide = wide[wide.index.notna()]
        if self.start is not None or self.end is not None:
            wide = wide.loc[self.start : self.end]
        wide = wide.resample(site.interval, closed="right", label="right").mean()
        wide.index.name = "measured_on"
        return wide.reindex(columns=metrics)  # a fully-absent channel -> NaN

    def load(self, site: SiteConfig) -> pd.DataFrame:
        meters = self.meter if isinstance(self.meter, tuple) else (self.meter,)
        spec: dict[str, tuple[LakeColumn, ...]] = {"ac_power_kw": meters}
        if self.irradiance is not None:
            spec["poa_wm2"] = (self.irradiance,)
        if self.temperature is not None:
            spec["temp_c"] = (self.temperature,)
        df = self._read([c.metric for cols in spec.values() for c in cols], site)
        out = pd.DataFrame(index=df.index)
        for canonical, cols in spec.items():
            parts = [_convert(df[c.metric], c) for c in cols]
            out[canonical] = sum(parts)  # NaN poisons the sum, by design
        return out

    def load_inverters(self, site: SiteConfig) -> pd.DataFrame:
        metrics = [int(m) for m in site.electrical]
        df = self._read(metrics, site)
        col = LakeColumn(0, scale=self.inverter_scale, breaks=self.inverter_breaks)
        out = pd.DataFrame(
            {f"inv_{i + 1:02d}": _convert(df[m], col) for i, m in enumerate(metrics)},
            index=df.index,
        )
        return out
