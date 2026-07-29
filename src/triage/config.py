"""Site metadata and pipeline tuning. Everything downstream reads from SITE.

Declarations only, no logic. Site facts sourced from
data/2107/metadata/2107_system_metadata.json.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SiteConfig:
    # site facts (PVDAQ system 2107, "Farm Solar Array", Arbuckle CA)
    name: str = "PVDAQ 2107"
    data_dir: Path = Path("data/2107/data")
    tz: str = "US/Pacific"
    dc_capacity_kw: float = 893.0
    # measured 15-min max ≈ 706 kW (healthy-era 2024): the inverters overdrive
    # their 662.4 kW summed nameplate (24 × TRIO-27.6), so ceiling-relative
    # rules use the empirical value
    ac_capacity_kw: float = 705.0
    derate: float = 0.8  # loss stack (heat, inverter conversion, wiring, mismatch, aging)

    # flagger tuning
    coverage_min: float = 0.8  # exclude days missing >20% of intervals
    flag_threshold: float = 0.92  # flag 8%+ underperformance vs baseline
    window: int = 30  # baseline rolling window, days


SITE = SiteConfig()
