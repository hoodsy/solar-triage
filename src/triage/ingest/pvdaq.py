from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from triage.ingest import SourceFile

if TYPE_CHECKING:
    from triage.ingest import Stream
    from triage.config import SiteConfig

# both PVDAQ inverter-column vintages: inv_01_ac_power_inv_149583 (2107) and
# inverter_01_ac_power_(kw)_inv_150953 (9069)
INV_COL = re.compile(r"(?:inverter|inv)_(\d+)_ac_power")


def _localize(index: pd.DatetimeIndex, tz: str) -> pd.DatetimeIndex:
    """PVDAQ naive-local stamps -> tz-aware; the unresolvable fall-back hour
    becomes NaT (callers drop it)."""
    return index.tz_localize(tz, ambiguous="NaT", nonexistent="shift_forward")


def load_inverters(site: SiteConfig) -> pd.DataFrame:
    """Per-inverter AC power (kW) on the site grid, columns inv_01..inv_NN,
    from the files named in site.electrical (vintage order, newest wins)."""
    frames = []
    for name in site.electrical:
        path = site.source.data_dir / name
        header = pd.read_csv(path, nrows=0).columns
        keep = {
            c: f"inv_{int(m.group(1)):02d}"
            for c in header
            if (m := INV_COL.match(c))
        }
        df = pd.read_csv(  # usecols: the 9069 file is 1.6 GB of mixed channels
            path,
            usecols=["measured_on", *keep],
            parse_dates=["measured_on"],
            index_col="measured_on",
        )
        df.index = _localize(df.index, site.tz)
        df = df[df.index.notna()]
        frames.append(df.rename(columns=keep))
    out = pd.concat(frames)
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out.resample(site.interval, closed="right", label="right").mean()


@dataclass(frozen=True)
class PvdaqAdapter:
    data_dir: Path
    meter: Stream  # becomes ac_power_kw
    irradiance: Stream | None = None  # becomes poa_wm2; None = clear-sky site
    temperature: Stream | None = None  # becomes temp_c (converted if fahrenheit)

    def _load_stream(self, stream: Stream, site: SiteConfig, name: str) -> pd.DataFrame:
        frames = []
        for f in stream.files:
            if isinstance(f, str):
                f = SourceFile(f)  # plain filename -> all defaults
            df = pd.read_csv(
                self.data_dir / f.name, parse_dates=[f.time_col], index_col=f.time_col
            )
            if f.tz is None:
                df.index = _localize(df.index, site.tz)
            else:
                df.index = df.index.tz_localize(f.tz).tz_convert(site.tz)
            df = df[df.index.notna()]
            df.index.name = "measured_on"
            frames.append(df)
        out = pd.concat(frames)
        out = out[~out.index.duplicated(keep=stream.keep)].sort_index()
        out = out[[stream.column]].rename(columns={stream.column: name})
        if stream.resample:
            out = out.resample(site.interval, closed="right", label="right").mean()
        return out

    def load(self, site: SiteConfig) -> pd.DataFrame:
        out = self._load_stream(self.meter, site, "ac_power_kw")
        if self.irradiance is not None:
            out = out.join(
                self._load_stream(self.irradiance, site, "poa_wm2"), how="outer"
            )
        if self.temperature is not None:
            temp = self._load_stream(self.temperature, site, "temp_c")
            if self.temperature.fahrenheit:
                temp["temp_c"] = (temp["temp_c"] - 32.0) * 5.0 / 9.0
            out = out.join(temp, how="outer")
        return out

    def load_inverters(self, site: SiteConfig) -> pd.DataFrame:
        # adapter-uniform entry point: __main__ never cares which format
        return load_inverters(site)
