from typing import Any, Dict


def vertical_bar_template() -> Dict[str, Any]:
    return {
        "type": "bar",
        "title": "Chart title",
        "data": [
            {"category": "Category 1", "metric1": 100, "metric2": 50},
            {"category": "Category 2", "metric1": 150, "metric2": 75},
        ],
        "config": {
            "xAxis": {"key": "category", "label": "Category"},
            "yAxis": [
                {"key": "metric1", "label": "Metric 1", "color": "#8884d8"},
                {"key": "metric2", "label": "Metric 2", "color": "#82ca9d"},
            ],
            "orientation": "vertical",
        },
    }


def horizontal_bar_template() -> Dict[str, Any]:
    t = vertical_bar_template()
    t["config"]["orientation"] = "horizontal"
    return t


def stacked_bar_template() -> Dict[str, Any]:
    t = vertical_bar_template()
    t["config"]["stacked"] = True
    return t


def get_bar_chart_template(variant: str) -> Dict[str, Any]:
    key = (variant or "").strip().lower()
    if key in ("horizontal", "h", "row"):
        return horizontal_bar_template()
    if key in ("stacked", "stack", "s"):
        return stacked_bar_template()
    return vertical_bar_template()


__all__ = [
    "vertical_bar_template",
    "horizontal_bar_template",
    "stacked_bar_template",
    "get_bar_chart_template",
]


def get_bar_guidance() -> str:
    return (
        "Bar Charts guidance:\n\n"
        "- Use vertical bars for categorical comparisons over discrete groups.\n"
        "- Use horizontal bars when category labels are long or many.\n"
        "- Use stacked bars to show part-to-whole relationships within categories.\n"
        "- Limit series count for readability; prefer stacking or grouping intentionally.\n"
        "- Ensure axes are labeled with data column names."
    )


__all__.append("get_bar_guidance")