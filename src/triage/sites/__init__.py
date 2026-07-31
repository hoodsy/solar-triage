"""Site registry: one module per site, assembled here.

Onboarding a site = one new file in this package defining SITE, plus one
line in the dict below. The key is what TRIAGE_SITE selects at startup.
"""

from triage.config import SiteConfig
from triage.sites import pvdaq_2107, pvdaq_9069, sn120

SITES: dict[str, SiteConfig] = {
    "2107": pvdaq_2107.SITE,
    "9069": pvdaq_9069.SITE,
    "sn120": sn120.SITE,
}
