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
        return "Cargo"
    if "passeg" in v:
        return "Passengers"
    
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
        return "Short"
    if "medi" in v:
        return "Medium"
    if "lung" in v:
        return "Long"
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
        return "P"
    if v.startswith("c") or "cargo" in v or "merce" in v:
        return "C"
    if v.startswith("o") or "other" in v or "altro" in v:
        return "O"
    return None