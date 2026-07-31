"""Site registry: one module per site, assembled here.

Onboarding a site = one new file in this package defining SITE, plus one
line in the dict below. The key is what TRIAGE_SITE selects at startup.
"""

from triage.config import SiteConfig
from triage.sites import (
    pvdaq_34,
    pvdaq_1199,
    pvdaq_1200,
    pvdaq_1202,
    pvdaq_1203,
    pvdaq_1239,
    pvdaq_1276,
    pvdaq_1277,
    pvdaq_1283,
    pvdaq_1367,
    pvdaq_1433,
    pvdaq_2107,
    pvdaq_9069,
    sn120,
)

SITES: dict[str, SiteConfig] = {
    "2107": pvdaq_2107.SITE,
    "9069": pvdaq_9069.SITE,
    "sn120": sn120.SITE,
    "34": pvdaq_34.SITE,
    "1199": pvdaq_1199.SITE,
    "1200": pvdaq_1200.SITE,
    "1202": pvdaq_1202.SITE,
    "1203": pvdaq_1203.SITE,
    "1239": pvdaq_1239.SITE,
    "1276": pvdaq_1276.SITE,
    "1277": pvdaq_1277.SITE,
    "1283": pvdaq_1283.SITE,
    "1367": pvdaq_1367.SITE,
    "1433": pvdaq_1433.SITE,
}
