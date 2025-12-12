"""Data management endpoints for DataFrame operations."""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any
import logging
import pandas as pd

from app.services.redis_dataframe_service import RedisDataFrameService
from app.services.dependencies import get_redis_dataframe_service, get_agent_service
from app.services.agent_service import AgentService
from app.schemas.data import (
    DataFramePreviewData,
    DataFramePreviewResponse,
    RecreateDataFrameRequest,
    RecreateDataFrameData,
    RecreateDataFrameResponse
)
from app.schemas.conversation import DataContext

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/data",
    tags=["data"]
)


@router.get("/{df_id}/preview", response_model=DataFramePreviewResponse)
async def get_dataframe_preview(
    df_id: str,
    redis_service: RedisDataFrameService = Depends(get_redis_dataframe_service)
) -> DataFramePreviewResponse:
    """
    Get a preview (first 100 rows) of the DataFrame from Redis.
    """
    try:
        logger.info(f"Fetching preview for DataFrame: {df_id}")
        
        if not redis_service.exists(df_id):
            return DataFramePreviewResponse(
                status="error",
                message="DataFrame not found or expired",
                errors=[{"code": "DATAFRAME_NOT_FOUND", "message": "DataFrame not found or expired"}]
            )
            
        df = redis_service.get_dataframe(df_id)
        if df is None:
            return DataFramePreviewResponse(
                status="error",
                message="Failed to retrieve DataFrame",
                errors=[{"code": "DATAFRAME_RETRIEVAL_FAILED", "message": "Failed to retrieve DataFrame"}]
            )
            
        # Get metadata
        metadata = redis_service.get_metadata(df_id)
        
        # Convert to records for frontend display
        # Limit to 100 rows for preview
        preview_df = df.head(100)
        
        # Handle NaN/Infinity for JSON serialization
        records = preview_df.where(pd.notnull(preview_df), None).to_dict(orient='records')
        
        return DataFramePreviewResponse(
            data=DataFramePreviewData(
                df_id=df_id,
                columns=df.columns.tolist(),
                total_rows=len(df),
                preview_rows=len(records),
                data=records,
                metadata=metadata
            ),
            message="DataFrame preview retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Error fetching DataFrame preview {df_id}: {e}")
        return DataFramePreviewResponse(
            status="error",
            message=f"Error fetching DataFrame preview: {str(e)}",
            errors=[{"code": "PREVIEW_ERROR", "message": str(e)}]
        )


@router.post("/recreate", response_model=RecreateDataFrameResponse)
async def recreate_dataframe(
    request: RecreateDataFrameRequest,
    redis_service: RedisDataFrameService = Depends(get_redis_dataframe_service),
    agent_service: AgentService = Depends(get_agent_service)
) -> RecreateDataFrameResponse:
    """
    Recreate a DataFrame in Redis using the original SQL query and
    update the agent's data_context state for the given thread.
    Returns a preview payload identical to the /{df_id}/preview endpoint.
    """
    try:
        logger.info(f"Recreating DataFrame for thread {request.thread_id}")

        # Get agent to reuse its SQL engine
        agent = agent_service.get_agent()

        # Re-execute SQL query using the same engine as the agent
        df = pd.read_sql_query(request.sql_query, agent.engine)

        if df.empty:
            return RecreateDataFrameResponse(
                status="error",
                message="SQL query returned no data; no DataFrame created",
                errors=[{"code": "EMPTY_DATAFRAME", "message": "SQL query returned no data"}]
            )

        # Store DataFrame in Redis and build context
        context = redis_service.store_dataframe(
            df=df,
            sql_query=request.sql_query,
            metadata={
                "thread_id": request.thread_id,
                "created_by": "recreate_dataframe",
            },
        )

        # Update agent state data_context for this thread
        data_context = DataContext(
            df_id=context["df_id"],
            sql_query=context["sql_query"],
            columns=context["columns"],
            shape=context["shape"],
            created_at=context["created_at"],
            expires_at=context["expires_at"],
            metadata=context.get("metadata", {}),
        )

        config = {"configurable": {"thread_id": request.thread_id}}
        try:
            agent.graph.update_state(config, {"data_context": data_context})
        except Exception as state_error:
            logger.warning(
                "Failed to update agent state data_context for thread %s: %s",
                request.thread_id,
                state_error,
            )

        # Build preview (first 100 rows) same as get_dataframe_preview
        preview_df = df.head(100)
        records = preview_df.where(pd.notnull(preview_df), None).to_dict(orient="records")

        return RecreateDataFrameResponse(
            data=RecreateDataFrameData(
                df_id=context["df_id"],
                columns=df.columns.tolist(),
                total_rows=len(df),
                preview_rows=len(records),
                data=records,
                metadata=context
            ),
            message="DataFrame recreated and preview retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Error recreating DataFrame for thread {request.thread_id}: {e}")
        return RecreateDataFrameResponse(
            status="error",
            message=f"Error recreating DataFrame: {str(e)}",
            errors=[{"code": "RECREATE_ERROR", "message": str(e)}]
        )
