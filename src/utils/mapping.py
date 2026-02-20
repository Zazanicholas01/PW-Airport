
def _norm(model: str | None) -> str:
    return (model or "").strip().lower()

_MODEL_INFO: dict[str, tuple[str, str]] = {
    "turboelica": ("Passengers", "Short"),
    "jet": ("Passengers", "Short"),
    "b2_stealth": ("Passengers", "Short"),
    "aeroplanoleggendario": ("Passengers", "Short"),
    "turboelica_cargo": ("Cargo", "Short"),
    "e190": ("Passengers", "Medium"),
    "a320": ("Passengers", "Medium"),
    "b737": ("Passengers", "Medium"),
    "b737_cargo": ("Cargo", "Medium"),
    "b787": ("Passengers", "Long"),
    "beluga": ("Cargo", "Long"),
}

def range_for_airplane_model(model: str | None) -> str:

    model = _norm(model)
    try:
        return _MODEL_INFO[model][1]
    except KeyError:
        raise ValueError(f"Unknown airplane model: {model!r}") from None

def type_for_airplane_model(model: str | None) -> str:

    model = _norm(model)
    try:
        return _MODEL_INFO[model][0]
    except KeyError:
        raise ValueError(f"Unknown airplane model: {model!r}") from None
