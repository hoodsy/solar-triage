from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from triage.adapters import SourceFile

if TYPE_CHECKING:
    from triage.adapters import Stream
    from triage.config import SiteConfig


@dataclass(frozen=True)
class CsvAdapter:
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
                df.index = df.index.tz_localize(
                    site.tz,
                    ambiguous="NaT",  # fall-back hour recorded once: unresolvable
                    nonexistent="shift_forward",
                )
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
