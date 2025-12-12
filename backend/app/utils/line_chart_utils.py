from typing import Any, Dict


def line_template() -> Dict[str, Any]:
    return {
        "type": "line",
        "title": "Chart title",
        "data": [
            {"time_period": "Jan", "metric1": 100, "metric2": 50},
            {"time_period": "Feb", "metric1": 120, "metric2": 60},
        ],
        "config": {
            "xAxis": {"key": "time_period", "label": "Time Period"},
            "yAxis": [
                {"key": "metric1", "label": "Metric 1", "color": "#8884d8"},
                {"key": "metric2", "label": "Metric 2", "color": "#82ca9d"},
            ],
        },
    }


def get_line_chart_template(variant: str) -> Dict[str, Any]:
    # Placeholder for future variants like area, spline, etc.
    return line_template()


__all__ = [
    "line_template",
    "get_line_chart_template",
]


def get_line_guidance() -> str:
    return (
        "Line Charts guidance:\n\n"
        "- Ideal for trends over ordered domains (time, sequence).\n"
        "- Keep x-axis sorted; avoid irregular intervals unless annotated.\n"
        "- Limit simultaneous series; differentiate with color and labels.\n"
        "- Use column names for xAxis and yAxis keys."
    )


__all__.append("get_line_guidance")


