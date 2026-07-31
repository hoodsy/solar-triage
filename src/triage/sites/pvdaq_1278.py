"""PVDAQ system 1278, Andre Agassi Preparatory Academy Building D, Las
Vegas NV. 171.4 kW DC roof — THE fleet's clipping site: DC/AC 1.24
against a razor-stable ~138 kW inverter ceiling (17 plateau days in
1,704 bright days on the clean-era data). Two asymmetric inverters
(~100 + ~40 kW) with hectowatt-era channels flipping to W at the
2018-08-04 campus migration; the plant meter channel (3081) stayed
W-scale throughout — no break. Measured POA + °F-era temps like its
siblings; fleet-relative referee normalization absorbs the inverter
size asymmetry by design."""

from pathlib import Path

from triage.adapters import LakeColumn, PvdaqLakeAdapter
from triage.config import SiteConfig

SITE = SiteConfig(
    name="PVDAQ 1278 Agassi D",
    tz="Etc/GMT+8",
    dc_capacity_kw=171.36,
    ac_capacity_kw=138.1,  # empirical 15-min p99.9 — the clipping ceiling
    n_units=2,
    lat=36.1952,
    lon=-115.1582,
    tilt=10.0,  # census blank; campus roofs run 5-11
    azimuth=180.0,
    electrical=("3070", "3079"),  # invN_ac_power_hw: hectowatt era then W
    source=PvdaqLakeAdapter(
        data_dir=Path("data/1278/lake"),
        meter=LakeColumn(3081, scale=0.001),  # W-scale, full span, no break
        irradiance=LakeColumn(3056),
        temperature=LakeColumn(
            3058, offset=-32.0, scale=5 / 9, breaks=(("2018-08-05", 0.0, 1.0),)
        ),
        inverter_scale=0.1,
        inverter_breaks=(("2018-08-04", 0.0, 0.001),),
    ),
)
