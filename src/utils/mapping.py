def range_for_airplane_model(model: str) -> str:
    m = (model or "").strip().lower()

    corto = {
        "turboelica",
        "jet",
        "b2_stealth",
        "aeroplanoleggendario",
        "b737_cargo",
    }

    medio = {
        "e190",
        "a320",
        "b737",
        "b737_cargo",
    }

    lungo = {
        "b787",
        "beluga",
    }

    if m in corto:
        return "Short"
    if m in medio:
        return "Medium"
    if m in lungo:
        return "Long"
    
    raise ValueError("Unknown airplane model for range mapping")

def type_for_airplane_model(model: str) -> str:
    m = (model or "").strip().lower()

    cargo = {"b737_cargo", "beluga"}

    if m in cargo:
        return "Cargo"
    return "Passenger"