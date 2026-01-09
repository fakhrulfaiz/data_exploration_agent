from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional, Literal


class AxisConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    key: str = Field(..., description="Column name to use for this axis")
    label: str = Field(..., description="Display label for this axis")
    color: Optional[str] = Field(default=None, description="Color for this axis/series (hex code)")


class BarChartConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    xAxis: AxisConfig = Field(..., description="X-axis configuration")
    yAxis: List[AxisConfig] = Field(..., description="Y-axis configuration (can have multiple series)")
    orientation: Optional[Literal["vertical", "horizontal"]] = Field(default="vertical", description="Bar chart orientation")


class LineChartConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    xAxis: AxisConfig = Field(..., description="X-axis configuration")
    yAxis: List[AxisConfig] = Field(..., description="Y-axis configuration (can have multiple lines)")


class PieChartConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    nameKey: str = Field(..., description="Column name for slice labels")
    valueKey: str = Field(..., description="Column name for slice values")
    variant: Optional[Literal["simple", "donut", "semi-donut"]] = Field(
        default="simple",
        description="Pie chart variant"
    )


class ChartDataItem(BaseModel):
    """Single data item for charts - allows arbitrary fields based on actual columns."""
    model_config = ConfigDict(extra='allow')


class BarChartOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    type: Literal["bar"] = "bar"
    title: str = Field(..., description="Chart title based on the description context")
    data: List[ChartDataItem] = Field(..., description="Chart data as list of objects")
    config: BarChartConfig = Field(..., description="Chart configuration")


class LineChartOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    type: Literal["line"] = "line"
    title: str = Field(..., description="Chart title based on the description context")
    data: List[ChartDataItem] = Field(..., description="Chart data as list of objects")
    config: LineChartConfig = Field(..., description="Chart configuration")


class PieChartOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    
    type: Literal["pie"] = "pie"
    title: str = Field(..., description="Chart title based on the description context")
    data: List[ChartDataItem] = Field(..., description="Chart data as list of objects")
    config: PieChartConfig = Field(..., description="Chart configuration")
