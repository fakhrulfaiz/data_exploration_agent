from typing import Any, Dict


def simple_pie_template() -> Dict[str, Any]:
    """Template for a simple pie chart (no data filled)."""
    return {
        "type": "pie",
        "title": "Chart title",
        "data": [
            {"category": "Category 1", "count": 400},
            {"category": "Category 2", "count": 300},
        ],
        "config": {
            "variant": "simple",
            "nested": {
                "enabled": False,
                "innerData": [],
                "outerData": [],
            },
        },
    }


def donut_pie_template() -> Dict[str, Any]:
    """Template for a donut pie chart (no data filled)."""
    return {
        "type": "pie",
        "title": "Chart title",
        "data": [
            {"category": "Category 1", "count": 400},
            {"category": "Category 2", "count": 300},
        ],
        "config": {
            "variant": "donut",
            "centerText": "Total",
            "nested": {
                "enabled": False,
                "innerData": [],
                "outerData": [],
            },
        },
    }


def straight_angle_pie_template() -> Dict[str, Any]:
    """Template for a straight-angle pie chart (no data filled).

    Straight-angle variant is intended for precise proportion comparisons.
    """
    return {
        "type": "pie",
        "title": "Chart title",
        "data": [
            {"category": "Category 1", "count": 55},
            {"category": "Category 2", "count": 45},
        ],
        "config": {
            "variant": "straight-angle",
            "nested": {
                "enabled": False,
                "innerData": [],
                "outerData": [],
            },
        },
    }


def two_level_pie_template() -> Dict[str, Any]:
    """Template for a two-level (nested) pie chart (no data filled)."""
    return {
        "type": "pie",
        "title": "Chart title",
        "data": [],
        "config": {
            "variant": "two-level",
            "nested": {
                "enabled": True,
                "innerData": [
                    {"name": "Category 1", "count": 100},
                    {"name": "Category 2", "count": 150},
                ],
                "outerData": [
                    {"name": "Item 1", "count": 30, "parent": "Category 1"},
                    {"name": "Item 2", "count": 70, "parent": "Category 1"},
                    {"name": "Item 3", "count": 80, "parent": "Category 2"},
                ],
            },
        },
    }


PIE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "simple": simple_pie_template(),
    "donut": donut_pie_template(),
    "straight-angle": straight_angle_pie_template(),
    "two-level": two_level_pie_template(),
}


__all__ = [
    "simple_pie_template",
    "donut_pie_template",
    "straight_angle_pie_template",
    "two_level_pie_template",
    "PIE_TEMPLATES",
]


def get_pie_guidance() -> str:
    """Guidance text for selecting pie chart variants."""
    return (
        "For Pie Charts, choose variant based on data structure:\n\n"
        "1. Variants:\n"
        "   - 'simple': For basic category distribution (e.g., product types)\n"
        "   - 'donut': Same as simple, with center space for total/summary\n"
        "   - 'two-level': For parent-child data (e.g., genre->movies)\n"
        "   - 'straight-angle': For precise proportion comparisons\n\n"
        "2. Choose Based On:\n"
        "   - Data relationships (flat vs hierarchical)\n"
        "   - User interaction needs\n"
        "   - Comparison requirements\n"
    )


def get_pie_chart_template(variant: str) -> Dict[str, Any]:
    """Return a pie chart template by variant.

    Supported variants: 'simple', 'donut', 'two-level', 'straight-angle'.
    Defaults to 'simple' if unknown.
    """
    key = (variant or "").strip().lower()
    if key in ("two-level", "twolevel", "two_level"):
        return two_level_pie_template()
    if key in ("donut", "doughnut"):
        return donut_pie_template()
    if key in ("straight-angle", "straightangle", "straight_angle"):
        return straight_angle_pie_template()
    return simple_pie_template()


__all__.extend([
    "get_pie_guidance",
    "get_pie_chart_template",
])


