from src.domain.status_constants import AIRPLANE_STATUS, FLIGHT_STATUS, STAND_STATUS


def normalize_flight_type(value: str | None) -> str | None:
    """Normalize flight type to ensure naming conventions"""

    # Sanity check on existing value
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    
    # Check almost similar patterns and convert to standard naming convention
    if "cargo" in v or "merce" in v:
        return FLIGHT_STATUS.CARGO_TYPE
    if "passeg" in v:
        return FLIGHT_STATUS.PASSEGNERS_TYPE
    
    return value


def normalize_distance(value: str | None) -> str | None:
    """Normalize range types to ensure naming conventions"""

    # Sanity check on existing value
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    
    # Check italian possible values and convert to standard english convention
    if "cort" in v:
        return AIRPLANE_STATUS.RANGE_SHORT
    if "medi" in v:
        return AIRPLANE_STATUS.RANGE_MEDIUM
    if "lung" in v:
        return AIRPLANE_STATUS.RANGE_LONG
    return value


def stand_category(value: str | None) -> str | None:
    """Retrieve stand category (Cargo / Passengers / Both)"""

    # Sanity check on value existing
    if value is None:
        return None
    v = value.strip().lower()
    if not v:
        return None
    
    # Check on stand first letter or similar patterns and ensure naming convention (P / C / O)
    if v.startswith("p") or "passeg" in v:
        return STAND_STATUS.PASSENGERS_CATEGORY
    if v.startswith("c") or "cargo" in v or "merce" in v:
        return STAND_STATUS.CARGO_CATEGORY
    if v.startswith("o") or "other" in v or "altro" in v:
        return STAND_STATUS.O_CATEGORY
    return None
