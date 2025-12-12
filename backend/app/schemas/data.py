"""Pydantic schemas for data management endpoints."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from .base import BaseResponse


# ==================== DataFrame Schemas ====================

class DataFramePreviewData(BaseModel):
    """DataFrame preview data"""
    df_id: str = Field(..., description="DataFrame identifier")
    columns: List[str] = Field(..., description="Column names")
    total_rows: int = Field(..., description="Total number of rows")
    preview_rows: int = Field(..., description="Number of preview rows")
    data: List[Dict[str, Any]] = Field(..., description="Preview data records")
    metadata: Optional[Dict[str, Any]] = Field(None, description="DataFrame metadata")


class DataFramePreviewResponse(BaseResponse[DataFramePreviewData]):
    """Response for DataFrame preview"""
    pass


class RecreateDataFrameRequest(BaseModel):
    """Request to recreate a DataFrame"""
    thread_id: str = Field(..., description="Thread identifier")
    sql_query: str = Field(..., description="SQL query to execute")


class RecreateDataFrameData(BaseModel):
    """Recreated DataFrame data"""
    df_id: str = Field(..., description="DataFrame identifier")
    columns: List[str] = Field(..., description="Column names")
    total_rows: int = Field(..., description="Total number of rows")
    preview_rows: int = Field(..., description="Number of preview rows")
    data: List[Dict[str, Any]] = Field(..., description="Preview data records")
    metadata: Dict[str, Any] = Field(..., description="DataFrame metadata")


class RecreateDataFrameResponse(BaseResponse[RecreateDataFrameData]):
    """Response for DataFrame recreation"""
    pass
