from src.domain.status_constants import *


def _norm(model: str | None) -> str:
    return (model or "").strip().lower()


def range_for_airplane_model(model: str | None) -> str:

    model = _norm(model)
    try:
        return MODEL_INFO[model][1]
    except KeyError:
        raise ValueError(f"Unknown airplane model: {model!r}") from None


def type_for_airplane_model(model: str | None) -> str:

    model = _norm(model)
    try:
        return MODEL_INFO[model][0]
    except KeyError:
        raise ValueError(f"Unknown airplane model: {model!r}") from None


def landing_source_for_range(range_value: str | None) -> str:
    """Map an airplane range string into a path source spline name"""

    # Normalize range string
    r = (range_value or "").lower()

    # Map for naming conventions
    if "long" in r:
        return LONG_LANDING_SPLINE
    if "medium" in r:
        return MEDIUM_LANDING_SPLINE
    
    return SHORT_LANDING_SPLINE
