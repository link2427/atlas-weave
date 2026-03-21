from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CORE_COUNTRY_MAP = {
    "US": "United States",
    "USA": "United States",
    "UNITED STATES": "United States",
    "UK": "United Kingdom",
    "GB": "United Kingdom",
    "UNITED KINGDOM": "United Kingdom",
    "CN": "China",
    "CHINA": "China",
    "RU": "Russia",
    "RUSSIAN FEDERATION": "Russia",
    "RUSSIA": "Russia",
    "FR": "France",
    "FRANCE": "France",
    "DE": "Germany",
    "GERMANY": "Germany",
    "IN": "India",
    "INDIA": "India",
    "JP": "Japan",
    "JAPAN": "Japan",
    "CA": "Canada",
    "CANADA": "Canada",
    "KR": "South Korea",
    "KOREA, REPUBLIC OF": "South Korea",
    "BR": "Brazil",
    "BRAZIL": "Brazil",
    "ES": "Spain",
    "SPAIN": "Spain",
    "IT": "Italy",
    "ITALY": "Italy",
    "LU": "Luxembourg",
    "LUXEMBOURG": "Luxembourg",
    "AE": "United Arab Emirates",
    "UNITED ARAB EMIRATES": "United Arab Emirates",
    "NZ": "New Zealand",
    "NEW ZEALAND": "New Zealand",
    "IL": "Israel",
    "ISRAEL": "Israel",
    "AU": "Australia",
    "AUSTRALIA": "Australia",
    "NL": "Netherlands",
    "NETHERLANDS": "Netherlands",
    "NO": "Norway",
    "NORWAY": "Norway",
    "SE": "Sweden",
    "SWEDEN": "Sweden",
    "AR": "Argentina",
    "ARGENTINA": "Argentina",
    "TW": "Taiwan",
    "TAIWAN": "Taiwan",
    "SG": "Singapore",
    "SINGAPORE": "Singapore",
    "SA": "Saudi Arabia",
    "SAUDI ARABIA": "Saudi Arabia",
    "KZ": "Kazakhstan",
    "KAZAKHSTAN": "Kazakhstan",
    "UA": "Ukraine",
    "UKRAINE": "Ukraine",
    "CIS": "CIS",
    "ESA": "ESA",
    "EUMETSAT": "EUMETSAT",
    "MULTINATIONAL": "Multinational",
}

CORE_COUNTRY_CODES = {
    "United States": "US",
    "United Kingdom": "GB",
    "China": "CN",
    "Russia": "RU",
    "France": "FR",
    "Germany": "DE",
    "India": "IN",
    "Japan": "JP",
    "Canada": "CA",
    "South Korea": "KR",
    "Brazil": "BR",
    "Spain": "ES",
    "Italy": "IT",
    "Luxembourg": "LU",
    "United Arab Emirates": "AE",
    "New Zealand": "NZ",
    "Israel": "IL",
    "Australia": "AU",
    "Netherlands": "NL",
    "Norway": "NO",
    "Sweden": "SE",
    "Argentina": "AR",
    "Taiwan": "TW",
    "Singapore": "SG",
    "Saudi Arabia": "SA",
    "Kazakhstan": "KZ",
    "Ukraine": "UA",
    "CIS": "CIS",
    "ESA": "ESA",
    "EUMETSAT": "EUMETSAT",
    "Multinational": "MULTI",
}

COMPLETENESS_FIELDS = [
    "object_name",
    "object_type",
    "active_status",
    "operator_name",
    "operator_country_code",
    "owner_name",
    "owner_country_code",
    "purpose_primary",
    "mission_class",
    "constellation_name",
    "launch_date",
    "launch_vehicle",
    "manufacturer_name",
    "bus_platform",
    "epoch_utc",
    "inclination_deg",
    "eccentricity",
    "perigee_km",
    "apogee_km",
    "altitude_km",
    "orbit_class",
    "tle_line1",
    "tle_line2",
    "dry_mass_kg",
    "design_life_years",
]

LLM_ALLOWED_FIELDS = [
    "operator_name",
    "operator_country_code",
    "operator_country_name",
    "owner_name",
    "owner_country_code",
    "owner_country_name",
    "purpose_primary",
    "purpose_secondary",
    "mission_class",
    "manufacturer_name",
    "bus_platform",
    "dry_mass_kg",
    "design_life_years",
    "program_name",
    "constellation_name",
    "operator_type",
    "civilian_military",
    "object_type",
    "launch_date",
]

SQLITE_COLUMN_TYPES: dict[str, str] = {
    "norad_id": "INTEGER PRIMARY KEY",
    "international_designator": "TEXT",
    "object_name": "TEXT",
    "alternate_names_json": "TEXT",
    "object_type": "TEXT",
    "object_status": "TEXT",
    "active_status": "TEXT",
    "operator_name": "TEXT",
    "operator_country_code": "TEXT",
    "operator_country_name": "TEXT",
    "owner_name": "TEXT",
    "owner_country_code": "TEXT",
    "owner_country_name": "TEXT",
    "operator_type": "TEXT",
    "civilian_military": "TEXT",
    "purpose_primary": "TEXT",
    "purpose_secondary": "TEXT",
    "mission_class": "TEXT",
    "constellation_name": "TEXT",
    "program_name": "TEXT",
    "launch_date": "TEXT",
    "launch_year": "INTEGER",
    "launch_site": "TEXT",
    "launch_site_country_code": "TEXT",
    "launch_vehicle": "TEXT",
    "launch_provider": "TEXT",
    "manufacturer_name": "TEXT",
    "prime_contractor": "TEXT",
    "bus_platform": "TEXT",
    "epoch_utc": "TEXT",
    "inclination_deg": "REAL",
    "eccentricity": "REAL",
    "period_min": "REAL",
    "mean_motion_rev_per_day": "REAL",
    "semi_major_axis_km": "REAL",
    "perigee_km": "REAL",
    "apogee_km": "REAL",
    "altitude_km": "REAL",
    "orbit_class": "TEXT",
    "raan_deg": "REAL",
    "arg_perigee_deg": "REAL",
    "mean_anomaly_deg": "REAL",
    "tle_line1": "TEXT",
    "tle_line2": "TEXT",
    "dry_mass_kg": "REAL",
    "launch_mass_kg": "REAL",
    "power_watts": "REAL",
    "design_life_years": "REAL",
    "expected_life_years": "REAL",
    "dimensions_text": "TEXT",
    "propulsion_type": "TEXT",
    "shape": "TEXT",
    "radar_cross_section_m2": "REAL",
    "last_contact_date": "TEXT",
    "decay_date": "TEXT",
    "is_debris": "INTEGER",
    "is_crewed": "INTEGER",
    "source_space_track": "TEXT",
    "source_discos": "TEXT",
    "source_ucs": "TEXT",
    "source_celestrak": "TEXT",
    "source_llm": "TEXT",
    "data_completeness_pct": "REAL",
    "enrichment_confidence": "REAL",
    "llm_research_status": "TEXT",
    "created_at_utc": "TEXT",
    "updated_at_utc": "TEXT",
    "last_verified_at_utc": "TEXT",
}


class EnrichedSatellite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    norad_id: int
    international_designator: str | None = None
    object_name: str | None = None
    alternate_names_json: str | None = None
    object_type: str | None = None
    object_status: str | None = None
    active_status: str | None = None
    operator_name: str | None = None
    operator_country_code: str | None = None
    operator_country_name: str | None = None
    owner_name: str | None = None
    owner_country_code: str | None = None
    owner_country_name: str | None = None
    operator_type: str | None = None
    civilian_military: str | None = None
    purpose_primary: str | None = None
    purpose_secondary: str | None = None
    mission_class: str | None = None
    constellation_name: str | None = None
    program_name: str | None = None
    launch_date: str | None = None
    launch_year: int | None = None
    launch_site: str | None = None
    launch_site_country_code: str | None = None
    launch_vehicle: str | None = None
    launch_provider: str | None = None
    manufacturer_name: str | None = None
    prime_contractor: str | None = None
    bus_platform: str | None = None
    epoch_utc: str | None = None
    inclination_deg: float | None = None
    eccentricity: float | None = None
    period_min: float | None = None
    mean_motion_rev_per_day: float | None = None
    semi_major_axis_km: float | None = None
    perigee_km: float | None = None
    apogee_km: float | None = None
    altitude_km: float | None = None
    orbit_class: str | None = None
    raan_deg: float | None = None
    arg_perigee_deg: float | None = None
    mean_anomaly_deg: float | None = None
    tle_line1: str | None = None
    tle_line2: str | None = None
    dry_mass_kg: float | None = None
    launch_mass_kg: float | None = None
    power_watts: float | None = None
    design_life_years: float | None = None
    expected_life_years: float | None = None
    dimensions_text: str | None = None
    propulsion_type: str | None = None
    shape: str | None = None
    radar_cross_section_m2: float | None = None
    last_contact_date: str | None = None
    decay_date: str | None = None
    is_debris: bool = False
    is_crewed: bool = False
    source_space_track: str | None = None
    source_discos: str | None = None
    source_ucs: str | None = None
    source_celestrak: str | None = None
    source_llm: str | None = None
    data_completeness_pct: float = 0.0
    enrichment_confidence: float = 0.0
    llm_research_status: str | None = None
    created_at_utc: str = Field(default_factory=lambda: utc_now())
    updated_at_utc: str = Field(default_factory=lambda: utc_now())
    last_verified_at_utc: str | None = None


class RunManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    recipe_name: str
    output_db_path: str
    latest_db_path: str
    total_records: int = 0
    active_records: int = 0
    research_candidates: int = 0
    researched_records: int = 0
    accepted_llm_records: int = 0
    anomaly_count: int = 0
    source_breakdown_json: str = "{}"
    source_status_json: str = "{}"
    cached_sources_json: str = "[]"
    stale_sources_json: str = "[]"
    space_track_mode: str = "prefer_cache"
    field_completion_rates_json: str = "{}"
    created_at_utc: str = Field(default_factory=lambda: utc_now())
    updated_at_utc: str = Field(default_factory=lambda: utc_now())


class QualityFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    norad_id: int | None = None
    severity: str
    code: str
    message: str
    created_at_utc: str = Field(default_factory=lambda: utc_now())


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def field_names() -> list[str]:
    return list(EnrichedSatellite.model_fields.keys())


def compute_completeness(record: dict[str, Any]) -> float:
    populated = 0
    for field_name in COMPLETENESS_FIELDS:
        value = record.get(field_name)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        populated += 1
    return round(populated / len(COMPLETENESS_FIELDS), 4)


def normalize_country(value: str | None) -> tuple[str | None, str | None]:
    if value is None:
        return (None, None)
    normalized = value.strip()
    if not normalized:
        return (None, None)

    upper = normalized.upper()
    if upper in CORE_COUNTRY_MAP:
        name = CORE_COUNTRY_MAP[upper]
        return (CORE_COUNTRY_CODES.get(name), name)

    if upper in CORE_COUNTRY_CODES.values():
        for name, code in CORE_COUNTRY_CODES.items():
            if code == upper:
                return (code, name)

    if len(upper) in {2, 3} and upper.isalpha():
        return (upper, normalized.title())

    titled = normalized.title()
    code = CORE_COUNTRY_CODES.get(titled)
    return (code, titled)


def derive_orbit_class(altitude_km: float | None) -> str | None:
    if altitude_km is None:
        return None
    if altitude_km < 2000:
        return "LEO"
    if altitude_km < 35786:
        return "MEO"
    if abs(altitude_km - 35786) <= 500:
        return "GEO"
    return "HEO"


# CelesTrak groups that are meta-categories (aggregation/status groups), not actual constellations.
# These should be filtered out when deriving constellation names.
_META_GROUPS = {
    "active", "visual", "analyst", "tle-new", "last-30-days",
    "active-geo", "geo-protected", "other", "geo",
}


def derive_constellation_name(object_name: str | None, celestrak_groups: list[str]) -> str | None:
    # Filter out meta-groups that don't represent actual constellations
    specific_groups = [g for g in celestrak_groups if g and g not in _META_GROUPS]
    if specific_groups:
        preferred = sorted(specific_groups, key=len)[0]
        return preferred.replace("-", " ").title()

    if not object_name:
        return None

    upper = object_name.upper()
    patterns = {
        "STARLINK": "Starlink",
        "ONEWEB": "OneWeb",
        "IRIDIUM": "Iridium",
        "GLOBALSTAR": "Globalstar",
        "ORBCOMM": "Orbcomm",
        "GPS": "GPS",
        "GALILEO": "Galileo",
        "BEIDOU": "BeiDou",
        "GLONASS": "GLONASS",
    }
    for pattern, label in patterns.items():
        if pattern in upper:
            return label
    return None
