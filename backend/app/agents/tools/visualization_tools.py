"""
Visualization tools for the explainable agent project.
These tools help transform database query results into visualization-ready formats.
"""

from langchain.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from typing import List, Dict, Any, Tuple, Optional, Annotated
from pydantic import Field
import json
from app.utils.pie_chart_utils import get_pie_guidance
from app.utils.bar_chart_utils import get_bar_guidance
from app.utils.line_chart_utils import get_line_guidance
from app.utils.chart_utils import get_chart_template
from app.services.redis_dataframe_service import get_redis_dataframe_service



VIZ_FORMAT_SCHEMAS = {
    "bar": {
        "description": "Bar chart for comparing categorical data",
        "format": get_chart_template("bar", {"variant": "vertical"}),
    },
    "line": {
        "description": "Line chart for time series or trends",
        "format": get_chart_template("line", {"variant": "line"}),
    },
    "pie": {
        "description": "Pie chart for showing proportions with multiple variants",
        "format": get_chart_template("pie", {"variant": "simple"}),
    },
}

def get_pie_specific_guidance() -> str:
    return get_pie_guidance()

def get_viz_format_for_prompt(viz_type: str, config: Optional[Dict[str, Any]] = None) -> str:
    """
    Dynamically fetch visualization format schema and type-specific guidance for the prompt.
    
    Args:
        viz_type: Visualization type to include in prompt
        config: Optional configuration dict (e.g., {"variant": "donut"})
        
    Returns:
        Formatted string with schema and guidance
    """
    if viz_type not in VIZ_FORMAT_SCHEMAS:
        return ""
        
    schema = VIZ_FORMAT_SCHEMAS[viz_type]
    # Build dynamic format based on config/variant when provided
    dynamic_format = get_chart_template(viz_type, config)
    format_str = f"""
**{viz_type.upper()} Chart**
Description: {schema['description']}
Format:
```json
{json.dumps(dynamic_format, indent=2)}
```
"""
    
    # Add type-specific guidance
    if viz_type == 'pie':
        format_str += "\n" + get_pie_specific_guidance()
    elif viz_type == 'bar':
        format_str += "\n" + get_bar_guidance()
    elif viz_type == 'line':
        format_str += "\n" + get_line_guidance()
    
    return format_str


class SmartTransformForVizTool(BaseTool):
    """
    Tool that uses LLM to intelligently transform database query results into visualization format.
    Uses structured output for reliability and proper type conversion for JSON serialization.
    """
    
    name: str = "smart_transform_for_viz"
    description: str = """ONLY use when user explicitly requests a chart, graph, or visualization.
    Transforms DataFrame data (from Redis) into visualization format for frontend rendering.
    Uses structured output for reliable transformation.
    
    Prerequisites:
    - A DataFrame must be available in Redis (created by data_exploration_tool)
    
    Parameters:
    - viz_type (optional string): Type of visualization (bar, line, pie)
    - config (optional dict): Override specific visualization settings
    
    Returns visualization-ready JSON with chart type and formatted data.
    DO NOT use for regular data queries - use only when user asks for visualizations.
    Supported types: bar, line, pie with all variants"""
    
    llm: Any = Field(description="Language model instance for intelligent transformation")
    
    def _get_structured_llm(self, viz_type: str):
        from app.schemas.visualization import BarChartOutput, LineChartOutput, PieChartOutput
        
        schema_map = {
            "bar": BarChartOutput,
            "line": LineChartOutput,
            "pie": PieChartOutput
        }
        schema = schema_map.get(viz_type, BarChartOutput)
        # Use function_calling method to avoid schema compatibility issues with json_schema
        return self.llm.with_structured_output(schema, method="function_calling")
    
    def _run(
        self,
        viz_type: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Execute the smart transform tool using DataFrame from Redis.
        
        Args:
            viz_type: Type of visualization (bar, line, pie)
            config: Optional configuration overrides for the visualization
            state: Injected state containing data_context
            tool_call_id: Optional tool call ID
        """
        try:
            import pandas as pd
            import logging
            from app.services.redis_dataframe_service import get_redis_dataframe_service
            from app.utils.serialization_utils import serialize_dataframe, safe_json_dumps
            
            logger = logging.getLogger(__name__)
            
            if state is None:
                state = {}
            
            # 1. GET DATAFRAME FROM REDIS
            data_context = state.get("data_context")
            if not data_context or not data_context.df_id:
                return json.dumps({"error": "No DataFrame available. Please run a SQL query first using data_exploration_tool."})
            
            # Load DataFrame from Redis
            redis_service = get_redis_dataframe_service()
            df = redis_service.get_dataframe(data_context.df_id)
            
            # If DataFrame not found in Redis, try to regenerate from SQL query
            if df is None:
                return json.dumps({"error": f"DataFrame {data_context.df_id} not found or expired. Please run the SQL query again using data_exploration_tool."})
            
            # Extend TTL since we're using the DataFrame
            redis_service.extend_ttl(data_context.df_id)
            
            logger.info(f"Using DataFrame {data_context.df_id} with shape {df.shape} for visualization")
            
            if df.empty:
                return json.dumps({"error": "The DataFrame is empty, so no visualization could be generated."})
            
            # 2. PREPARE DATA WITH PROPER SERIALIZATION
            columns = df.columns.tolist()
            
            # Default to bar chart if not specified
            if viz_type is None:
                viz_type = 'bar'
            
            # Limit to 100 rows for frontend charts
            max_rows = min(100, len(df))
            
            # Serialize DataFrame with numpy type conversion
            sample_data = serialize_dataframe(df, max_rows=5)  # Sample for LLM
            full_data = serialize_dataframe(df, max_rows=max_rows)  # Full data for output
            
            logger.info(f"Prepared {len(full_data)} rows for visualization (sample: {len(sample_data)} rows)")
            
            # 3. GET VISUALIZATION FORMAT GUIDANCE
            viz_formats = get_viz_format_for_prompt(viz_type, config)
            
            # Extract description from data_context metadata if available
            query_description = None
            if data_context and hasattr(data_context, 'metadata') and data_context.metadata:
                query_description = data_context.metadata.get('description')
            
            # 4. BUILD PROMPT FOR STRUCTURED OUTPUT
            context_info = f"\n\n**Original Query Context**: {query_description}" if query_description else ""
            
            system_prompt = f"""You are a data visualization expert. Transform the provided DataFrame data into a {viz_type} chart format.

Your task:
1. Map actual column names from the DataFrame to the visualization format
2. Create a meaningful chart title based on the data and query context
3. Configure axes/keys appropriately for the chart type
4. Use the actual column names - DO NOT use generic names like "label", "value"

Available columns: {', '.join(columns)}{context_info}

{viz_formats}

Return a properly structured {viz_type} chart configuration."""

            user_prompt = f"""Columns: {columns}

Sample data (first 5 rows):
{safe_json_dumps(sample_data, indent=2)}

Total rows: {len(df)}

Config overrides: {safe_json_dumps(config, indent=2) if config else "None"}

Create the best {viz_type} chart for this data. Use the query context to create a meaningful title."""

            # 5. INVOKE LLM WITH STRUCTURED OUTPUT
            try:
                structured_llm = self._get_structured_llm(viz_type)
                
                from langchain_core.messages import SystemMessage, HumanMessage
                viz_output = structured_llm.invoke([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt)
                ])
                
                # Convert Pydantic model to dict
                viz_config = viz_output.model_dump()
                
                # Replace sample data with full data
                viz_config["data"] = full_data
                
                # Apply any provided configuration overrides
                if config and isinstance(config, dict):
                    # Override top-level fields (title, etc.)
                    if "title" in config:
                        viz_config["title"] = config["title"]
                    
                    # Override config section (xAxis, yAxis, etc.)
                    if "config" not in viz_config:
                        viz_config["config"] = {}
                    
                    # Merge config fields (excluding top-level overrides)
                    config_fields = {k: v for k, v in config.items() if k not in ["title"]}
                    viz_config["config"].update(config_fields)
                
                logger.info(f"Successfully generated {viz_type} chart with structured output")

                
            except Exception as e:
                logger.error(f"Error with structured output: {e}")
                # Fallback to basic chart
                x_key = columns[0] if columns else "category"
                y_key = columns[1] if len(columns) > 1 else "value"
                
                viz_config = {
                    "type": viz_type,
                    "title": f"Data Analysis Results ({len(df)} rows)",
                    "data": full_data,
                    "config": {
                        "xAxis": {"key": x_key, "label": x_key.replace('_', ' ').title()},
                        "yAxis": [{"key": y_key, "label": y_key.replace('_', ' ').title()}]
                    }
                }
            
            # 6. ADD METADATA
            viz_config["metadata"] = {
                "source": "smart_transform_for_viz",
                "total_rows": len(df),
                "displayed_rows": len(full_data),
                "columns": columns,
                "df_id": data_context.df_id
            }
            
            logger.info(f"Successfully transformed DataFrame {data_context.df_id} into {viz_type} visualization")
            
            # 7. RETURN WITH SAFE JSON SERIALIZATION
            return safe_json_dumps(viz_config, indent=2)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error generating visualization: {str(e)}", exc_info=True)
            return json.dumps({"error": f"Failed to transform data: {str(e)}"})
    
    async def _arun(
        self,
        viz_type: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool."""
        return self._run(reasoning, viz_type, config, state, tool_call_id)



class LargePlottingTool(BaseTool):
    """
    Tool for generating high-quality matplotlib plots using DataFrames from Redis.
    No longer executes SQL directly - uses DataFrame stored by sql_db_to_df tool.
    """
    
    name: str = "large_plotting_tool"
    description: str = """Generate high-quality matplotlib plots using the current DataFrame from Redis.
    
    Use this tool when:
    - Dataset has more than 100 rows
    - User requests matplotlib, static image, or high-quality plots
    - Complex scatter plots with many data points
    - Time series data with many points
    - Statistical plots (histograms, box plots, etc.)
    - Advanced matplotlib features not available in frontend charts
    
    Prerequisites:
    - A DataFrame must be available (created by sql_db_to_df tool)
    
    Parameters:
    - x_column (str): Column name for X-axis
    - y_column (str): Column name for Y-axis  
    - plot_type (str): Type of plot (scatter, line, bar, histogram)
    - title (str): Title for the plot
    - x_label (optional str): Custom X-axis label
    - y_label (optional str): Custom Y-axis label
    - color (optional str): Color for the plot elements
    - fig_width (optional int): Figure width in inches (default: 10)
    - fig_height (optional int): Figure height in inches (default: 6)
    
    Returns: Markdown image syntax with Supabase public URL for display in chat."""
    
    llm: Any = Field(description="Language model instance")
    
    def _run(
        self,
        x_column: str,
        y_column: str,
        *,
        plot_type: str = "scatter",
        title: str = "Data Plot",
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        color: str = "blue",
        fig_width: int = 10,
        fig_height: int = 6,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Execute the large plotting tool using DataFrame from Redis."""
        
        # Import required libraries
        try:
            import pandas as pd
            import matplotlib.pyplot as plt
            import matplotlib
            from io import BytesIO
            from app.services.dependencies import get_supabase_storage_service
            import logging
            
            # Set matplotlib to non-interactive mode for server environments
            matplotlib.use('Agg')
            
            logger = logging.getLogger(__name__)
            
        except ImportError as e:
            return f"Error: Required libraries not available: {str(e)}"
        
        try:
            if state is None:
                state = {}
            # 1. GET DATAFRAME FROM REDIS
            data_context = state.get("data_context")
            if not data_context or not data_context.df_id:
                return "Error: No DataFrame available. Please run a SQL query first using sql_db_to_df tool."
            
            # Load DataFrame from Redis
            redis_service = get_redis_dataframe_service()
            df = redis_service.get_dataframe(data_context.df_id)
            
            if df is None:
                return f"Error: DataFrame {data_context.df_id} not found or expired. Please run the SQL query again using sql_db_to_df tool."
            
            # Extend TTL since we're using the DataFrame
            redis_service.extend_ttl(data_context.df_id)
            
            logger.info(f"Using DataFrame {data_context.df_id} with shape {df.shape} for plotting")
            
            if df.empty:
                return "Error: The DataFrame is empty, so no plot could be generated."
            
            # 2. VALIDATE COLUMNS
            if x_column not in df.columns:
                return f"Error: X-axis column '{x_column}' not found in query results. Available columns: {list(df.columns)}"
            
            if y_column not in df.columns:
                return f"Error: Y-axis column '{y_column}' not found in query results. Available columns: {list(df.columns)}"
            
            # 3. GENERATE PLOT
            plt.figure(figsize=(fig_width, fig_height))
            
            # Create plot based on type
            if plot_type.lower() == "scatter":
                plt.scatter(df[x_column], df[y_column], alpha=0.6, c=color, s=30)
            elif plot_type.lower() == "line":
                plt.plot(df[x_column], df[y_column], color=color, linewidth=2)
            elif plot_type.lower() == "bar":
                plt.bar(df[x_column], df[y_column], color=color, alpha=0.7)
            elif plot_type.lower() == "histogram":
                plt.hist(df[x_column], bins=30, color=color, alpha=0.7, edgecolor='black')
            elif plot_type.lower() == "pie":
                # For pie charts, x_column is labels, y_column is values
                plt.pie(df[y_column], labels=df[x_column], autopct='%1.1f%%', startangle=90)
                plt.axis('equal')  # Equal aspect ratio ensures circular pie
            else:
                # Default to scatter plot
                plt.scatter(df[x_column], df[y_column], alpha=0.6, c=color, s=30)
            
            # 4. CUSTOMIZE PLOT
            plt.title(title, fontsize=14, fontweight='bold', pad=20)
            
            # Skip axis labels and grid for pie charts
            if plot_type.lower() != "pie":
                plt.xlabel(x_label or x_column.replace('_', ' ').title(), fontsize=12)
                plt.ylabel(y_label or y_column.replace('_', ' ').title(), fontsize=12)
                plt.grid(True, linestyle='--', alpha=0.7)
            
            # Improve layout
            plt.tight_layout()
            
            # 5. SAVE TO BYTES
            img_buffer = BytesIO()
            plt.savefig(img_buffer, format='png', dpi=300, bbox_inches='tight')
            img_buffer.seek(0)
            
            # 6. CLEAR MATPLOTLIB MEMORY
            plt.close()
            
            # 7. UPLOAD TO SUPABASE (with fallback to base64 if Supabase not configured)
            try:
                storage_service = get_supabase_storage_service()
                public_url = storage_service.upload_plot_image(
                    image_data=img_buffer.getvalue(),
                    filename=f"{plot_type}_plot.png",
                    content_type="image/png"
                )
                
                # 8. RETURN MARKDOWN IMAGE
                plot_description = f"{title} ({plot_type} plot with {len(df)} data points)"
                markdown_image = f"![{plot_description}]({public_url})"
                
                logger.info(f"Successfully generated {plot_type} plot with {len(df)} data points")
                
                return f"""Plot generated successfully!

{markdown_image}

**Plot Details:**
- Type: {plot_type.title()} Plot
- Data Points: {len(df):,}
- X-axis: {x_column}
- Y-axis: {y_column}
- Image URL: {public_url}"""
            except ValueError as e:  
                logger.error(f"Supabase not configured: {str(e)}")
                # Reset the service instance to allow retry on next call
                # Reset functionality could be added to storage_service if needed
                pass
                return "Plot unsuccessful because there is a problem with storage."
            except Exception as upload_error:
                logger.error(f"Failed to upload to Supabase: {str(upload_error)}")
                import traceback
                logger.error(f"Upload error traceback: {traceback.format_exc()}")
                return f"Plot unsuccessful because there is a problem with storage: {str(upload_error)}"
            
        except Exception as e:
            logger.error(f"Error generating large plot: {str(e)}")
            return f"Error generating plot: {str(e)}"
    
    async def _arun(
        self,
        x_column: str,
        y_column: str,
        *,
        plot_type: str = "scatter",
        title: str = "Data Plot",
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        color: str = "blue",
        fig_width: int = 10,
        fig_height: int = 6,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool."""
        return self._run(
            x_column,
            y_column,
            plot_type=plot_type,
            title=title,
            x_label=x_label,
            y_label=y_label,
            color=color,
            fig_width=fig_width,
            fig_height=fig_height,
            state=state,
            tool_call_id=tool_call_id,
        )