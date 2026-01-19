"""Data management endpoints for DataFrame operations."""

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response
from typing import Dict, Any, List
import logging
import pandas as pd
import io
import zipfile
import httpx
from pydantic import BaseModel

from app.services.redis_dataframe_service import RedisDataFrameService
from app.services.dependencies import get_redis_dataframe_service
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

# Dependency function to get agent service from app state
def get_agent_service(request: Request) -> AgentService:
    agent_service = request.app.state.agent_service
    if not hasattr(agent_service, '_agent') or agent_service._agent is None:
        raise HTTPException(status_code=500, detail="Agent service not properly initialized")
    return agent_service

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
    request_body: RecreateDataFrameRequest,
    request: Request,
    redis_service: RedisDataFrameService = Depends(get_redis_dataframe_service),
    agent_service: AgentService = Depends(get_agent_service)
) -> RecreateDataFrameResponse:
    """
    Recreate a DataFrame in Redis using the original SQL query and
    update the agent's data_context state for the given thread.
    Returns a preview payload identical to the /{df_id}/preview endpoint.
    """
    try:

        # Optimized Logic: Check if DataFrame exists first if df_id is provided
        if request_body.df_id and not request_body.force_recreate:
            if redis_service.exists(request_body.df_id):
                logger.info(f"DataFrame {request_body.df_id} exists, returning preview instead of recreating")
                
                df = redis_service.get_dataframe(request_body.df_id)
                context = redis_service.get_metadata(request_body.df_id)
                
                if df is not None:
                     # Convert to records for frontend display
                    preview_df = df.head(100)
                    records = preview_df.where(pd.notnull(preview_df), None).to_dict(orient='records')
                    
                    return RecreateDataFrameResponse(
                        data=RecreateDataFrameData(
                            df_id=context["df_id"],
                            columns=df.columns.tolist(),
                            total_rows=len(df),
                            preview_rows=len(records),
                            data=records,
                            metadata=context
                        ),
                        message="Existing DataFrame retrieved successfully"
                    )

        logger.info(f"Recreating DataFrame for thread {request_body.thread_id}")

        # Get agent to reuse its SQL engine
        agent = agent_service.get_agent()

        # Re-execute SQL query using the same engine as the agent
        df = pd.read_sql_query(request_body.sql_query, agent.engine)

        if df.empty:
            return RecreateDataFrameResponse(
                status="error",
                message="SQL query returned no data; no DataFrame created",
                errors=[{"code": "EMPTY_DATAFRAME", "message": "SQL query returned no data"}]
            )

        # Store DataFrame in Redis and build context
        context = redis_service.store_dataframe(
            df=df,
            sql_query=request_body.sql_query,
            metadata={
                "thread_id": request_body.thread_id,
                "created_by": "recreate_dataframe",
            },
        )

        # Update agent state data_context for this thread
        # Convert datetime objects to ISO format strings for Pydantic validation
        created_at_str = context["created_at"].isoformat() if hasattr(context["created_at"], 'isoformat') else str(context["created_at"])
        expires_at_str = context["expires_at"].isoformat() if hasattr(context["expires_at"], 'isoformat') else str(context["expires_at"])
        
        data_context = DataContext(
            df_id=context["df_id"],
            sql_query=context["sql_query"],
            columns=context["columns"],
            shape=context["shape"],
            created_at=created_at_str,
            expires_at=expires_at_str,
            metadata=context.get("metadata", {}),
        )

        config = {"configurable": {"thread_id": request_body.thread_id}}
        try:
            agent.graph.update_state(config, {"data_context": data_context})
        except Exception as state_error:
            logger.warning(
                "Failed to update agent state data_context for thread %s: %s",
                request_body.thread_id,
                state_error,
            )

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
        logger.error(f"Error recreating DataFrame for thread {request_body.thread_id}: {e}")
        return RecreateDataFrameResponse(
            status="error",
            message=f"Error recreating DataFrame: {str(e)}",
            errors=[{"code": "RECREATE_ERROR", "message": str(e)}]
        )


class ExportRequest(BaseModel):
    df_id: str


class DownloadPlotsRequest(BaseModel):
    plot_urls: List[str]


@router.post("/export-dataframe")
async def export_dataframe(
    request: ExportRequest,
    redis_service: RedisDataFrameService = Depends(get_redis_dataframe_service)
):
    """
    Export a DataFrame from Redis to XLSX format.
    Returns all rows (not limited like preview).
    """
    try:
        # Check if DataFrame exists
        if not redis_service.exists(request.df_id):
            raise HTTPException(
                status_code=404,
                detail="DataFrame not found or expired. Please create a new chat to regenerate the data."
            )
        
        # Get the DataFrame
        df = redis_service.get_dataframe(request.df_id)
        if df is None:
            raise HTTPException(
                status_code=404,
                detail="DataFrame not found or expired. Please create a new chat to regenerate the data."
            )
        
        # Convert to XLSX
        output = io.BytesIO()
        with io.BytesIO() as buffer:
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Data')
            buffer.seek(0)
            output = buffer.getvalue()
        
        logger.info(f"Exported DataFrame {request.df_id} with {len(df)} rows to XLSX")
        
        # Return as downloadable file
        return Response(
            content=output,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=data_export.xlsx"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export DataFrame: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to export DataFrame: {str(e)}")


@router.post("/download-plots")
async def download_plots(
    request: DownloadPlotsRequest
):
    """
    Download plot images from URLs.
    If multiple plots, returns a ZIP file.
    Only downloads plots from HTTP URLs (not local file paths).
    """
    try:
        if not request.plot_urls:
            raise HTTPException(status_code=400, detail="No plot URLs provided")
        
        # Filter only HTTP URLs (exclude local file paths)
        http_urls = [url for url in request.plot_urls if url.startswith("http")]
        
        if not http_urls:
            raise HTTPException(
                status_code=400,
                detail="No valid plot URLs found. Only HTTP URLs are supported for download."
            )
        
        # Download images
        images = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for idx, url in enumerate(http_urls):
                try:
                    response = await client.get(url)
                    response.raise_for_status()
                    
                    # Determine file extension from URL or content-type
                    content_type = response.headers.get('content-type', '')
                    if 'png' in content_type or url.endswith('.png'):
                        ext = 'png'
                    elif 'jpeg' in content_type or 'jpg' in content_type or url.endswith(('.jpg', '.jpeg')):
                        ext = 'jpg'
                    elif 'svg' in content_type or url.endswith('.svg'):
                        ext = 'svg'
                    else:
                        ext = 'png'  # default
                    
                    images.append({
                        'filename': f'plot_{idx + 1}.{ext}',
                        'content': response.content
                    })
                    logger.info(f"Downloaded plot {idx + 1} from {url}")
                except Exception as e:
                    logger.warning(f"Failed to download plot from {url}: {e}")
                    # Continue with other plots
        
        if not images:
            raise HTTPException(
                status_code=500,
                detail="Failed to download any plots. Images may have expired or URLs are invalid."
            )
        
        # If single image, return directly
        if len(images) == 1:
            return Response(
                content=images[0]['content'],
                media_type="image/png",
                headers={
                    "Content-Disposition": f"attachment; filename={images[0]['filename']}"
                }
            )
        
        # Multiple images - create ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for img in images:
                zip_file.writestr(img['filename'], img['content'])
        
        zip_buffer.seek(0)
        logger.info(f"Created ZIP file with {len(images)} plots")
        
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=plots.zip"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download plots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to download plots: {str(e)}")


@router.get("/plot/{plot_filename}")
async def serve_plot(plot_filename: str):
    """
    Serve a plot image file from the workspace.
    This allows displaying generated plots inline in the frontend.
    """
    import os
    from pathlib import Path
    from fastapi.responses import FileResponse
    
    # Security: Only allow specific extensions
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.gif'}
    ext = Path(plot_filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Invalid file extension: {ext}")
    
    # Security: Prevent directory traversal
    if '..' in plot_filename or '/' in plot_filename or '\\' in plot_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Define workspace plot directories to search
    workspace_dirs = [
        Path(__file__).resolve().parent.parent.parent.parent / "agents" / "workspace" / "plot",
        Path(__file__).resolve().parent.parent.parent.parent / "agents" / "dev" / "workspace" / "plot",
    ]
    
    # Find the file
    for workspace_dir in workspace_dirs:
        file_path = workspace_dir / plot_filename
        if file_path.exists() and file_path.is_file():
            logger.info(f"Serving plot: {file_path}")
            
            # Determine media type
            media_types = {
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.svg': 'image/svg+xml',
                '.gif': 'image/gif'
            }
            media_type = media_types.get(ext, 'image/png')
            
            return FileResponse(
                path=str(file_path),
                media_type=media_type,
                filename=plot_filename
            )
    
    logger.warning(f"Plot not found: {plot_filename}")
    raise HTTPException(status_code=404, detail=f"Plot not found: {plot_filename}")


@router.get("/output/{output_filename}")
async def serve_output(output_filename: str):
    """
    Serve a CSV output file from the workspace as JSON for table display.
    """
    import os
    from pathlib import Path
    
    # Security: Only allow CSV files
    if not output_filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    # Security: Prevent directory traversal
    if '..' in output_filename or '/' in output_filename or '\\' in output_filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Define workspace output directories to search
    workspace_dirs = [
        Path(__file__).resolve().parent.parent.parent.parent / "agents" / "workspace" / "outputs",
        Path(__file__).resolve().parent.parent.parent.parent / "agents" / "dev" / "workspace" / "outputs",
    ]
    
    # Find the file
    for workspace_dir in workspace_dirs:
        file_path = workspace_dir / output_filename
        if file_path.exists() and file_path.is_file():
            logger.info(f"Serving output: {file_path}")
            
            try:
                df = pd.read_csv(file_path)
                # Convert to JSON-serializable format
                records = df.where(pd.notnull(df), None).to_dict(orient='records')
                
                return {
                    "status": "success",
                    "data": {
                        "filename": output_filename,
                        "columns": df.columns.tolist(),
                        "total_rows": len(df),
                        "data": records
                    }
                }
            except Exception as e:
                logger.error(f"Failed to parse CSV {output_filename}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to parse CSV: {str(e)}")
    
    logger.warning(f"Output not found: {output_filename}")
    raise HTTPException(status_code=404, detail=f"Output not found: {output_filename}")


@router.get("/generated-files")
async def list_generated_files():
    """
    List all generated files (plots and CSV outputs) from the workspace.
    Returns file paths that can be used by /plot/{filename} and /output/{filename} endpoints.
    """
    from pathlib import Path
    import os
    
    result = {
        "plots": [],
        "outputs": []
    }
    
    # Define workspace directories
    workspace_dirs = [
        {
            "plot": Path(__file__).resolve().parent.parent.parent.parent / "agents" / "workspace" / "plot",
            "outputs": Path(__file__).resolve().parent.parent.parent.parent / "agents" / "workspace" / "outputs",
        },
        {
            "plot": Path(__file__).resolve().parent.parent.parent.parent / "agents" / "dev" / "workspace" / "plot",
            "outputs": Path(__file__).resolve().parent.parent.parent.parent / "agents" / "dev" / "workspace" / "outputs",
        }
    ]
    
    plot_extensions = {'.png', '.jpg', '.jpeg', '.svg', '.gif'}
    
    for dirs in workspace_dirs:
        # Collect plots
        plot_dir = dirs["plot"]
        if plot_dir.exists():
            for file_path in plot_dir.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in plot_extensions:
                    stat = file_path.stat()
                    result["plots"].append({
                        "filename": file_path.name,
                        "url": f"/api/v1/data/plot/{file_path.name}",
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })
        
        # Collect outputs (CSV files)
        outputs_dir = dirs["outputs"]
        if outputs_dir.exists():
            for file_path in outputs_dir.iterdir():
                if file_path.is_file() and file_path.suffix.lower() == '.csv':
                    stat = file_path.stat()
                    result["outputs"].append({
                        "filename": file_path.name,
                        "url": f"/api/v1/data/output/{file_path.name}",
                        "size": stat.st_size,
                        "modified": stat.st_mtime
                    })
    
    # Sort by modification time (newest first)
    result["plots"].sort(key=lambda x: x["modified"], reverse=True)
    result["outputs"].sort(key=lambda x: x["modified"], reverse=True)
    
    logger.info(f"Listed generated files: {len(result['plots'])} plots, {len(result['outputs'])} outputs")
    
    return {
        "status": "success",
        "data": result
    }
