from typing import Any, Dict, Optional

from app.utils.bar_chart_utils import get_bar_chart_template
from app.utils.line_chart_utils import get_line_chart_template
from app.utils.pie_chart_utils import get_pie_chart_template


def get_chart_template(viz_type: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Return a template for the given visualization type and config.

    For pie, uses config['variant'] when provided. For bar/line, variant selects
    orientation or specific subtype where applicable.
    """
    vtype = (viz_type or "").strip().lower()
    variant = ((config or {}).get("variant") or "").strip().lower()

    if vtype == "pie":
        return get_pie_chart_template(variant or "simple")
    if vtype == "bar":
        return get_bar_chart_template(variant or "vertical")
    if vtype == "line":
        return get_line_chart_template(variant or "line")

    # Default fallback (bar vertical)
    return get_bar_chart_template("vertical")


__all__ = ["get_chart_template"]



def get_supported_charts() -> Dict[str, Any]:
    """Return supported chart types and their variants.

    This is a centralized description for downstream tooling and UIs.
    """
    return {
        "bar": {
            "description": "Bar chart for comparing categorical data",
            "variants": ["vertical", "horizontal"],
        },
        "line": {
            "description": "Line chart for time-series or trends",
            "variants": ["line"],
        },
        "pie": {
            "description": "Pie chart for proportions (multiple variants)",
            "variants": ["simple", "donut", "two-level", "straight-angle"],
        },
    }


__all__.append("get_supported_charts")