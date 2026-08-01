"""Per-site configuration dataclass. Declarations only, no logic.

Everything downstream reads a SiteConfig. Site instances live one-per-file
in triage/ingest/sites/, registered in triage.ingest.sites.SITES; the active
site is chosen once at startup via the TRIAGE_SITE env var (see __main__.py).
"""

from dataclasses import dataclass

from triage.ingest import Adapter
from triage.ingest.weather import OpenMeteoWeather


@dataclass(frozen=True)
class SiteConfig:
    name: str
    tz: str
    dc_capacity_kw: float
    ac_capacity_kw: float
    source: Adapter
    # expected-power model facts (None when the site has measured POA)
    lat: float | None = None
    lon: float | None = None
    tilt: float | None = None
    azimuth: float | None = None
    weather: OpenMeteoWeather | None = None  # reanalysis POA; None = clear-sky
    # analysis window (None = open-ended)
    report_start: str | None = None
    report_end: str | None = None
    # per-inverter electrical streams (empty = no sub-metering, no referee)
    electrical: tuple[str, ...] = ()
    # tuning: generic defaults, overridable per site
    n_units: int = 1  # inverters/strings: real partial loss quantizes to capacity/n_units
    interval: str = "15min"
    derate: float = 0.8  # loss stack (heat, inverter conversion, wiring, mismatch, aging)
    # low-light saturation constant (W/m^2), 0 = off: expected power gets an
    # extra eff = G(1000+k)/(1000(G+k)) factor. Fit per site on healthy-day
    # binned actual/expected vs POA — fleets differ (see physics.expected_kw)
    low_light_k: float = 0.0
    coverage_min: float = 0.8  # exclude days missing >20% of intervals
    flag_threshold: float = 0.92  # flag 8%+ underperformance vs baseline
    # absolute-PI guard: at/above this a day never flags, whatever the
    # baseline says (reanalysis bias inflates baselines to ~1.25 and flags
    # weeks of PI≈1.0 days otherwise). Fine-grained sub-metered sites with
    # trusted sensors raise it — a 1-of-24 inverter loss only dips PI to
    # ~0.96, and the referee grades those marginal flags independently.
    pi_ceiling: float = 0.95
    window: int = 30  # baseline rolling window, days
