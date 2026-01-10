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
                # STANDARDIZED ERROR: No DataFrame Available
                return json.dumps({
                    "error": "No DataFrame available. Please run a SQL query first using data_exploration_tool.",
                    "error_type": "resource_not_found",
                    "tool_name": "smart_transform_for_viz",
                    "details": {"missing_resource": "data_context.df_id"},
                    "recoverable": False  # Needs previous step
                })
            
            # Load DataFrame from Redis
            redis_service = get_redis_dataframe_service()
            df = redis_service.get_dataframe(data_context.df_id)
            
            # If DataFrame not found in Redis, try to regenerate from SQL query
            if df is None:
                # STANDARDIZED ERROR: DataFrame Expired
                return json.dumps({
                    "error": f"DataFrame {data_context.df_id} not found or expired. Please run the SQL query again using data_exploration_tool.",
                    "error_type": "resource_not_found",
                    "tool_name": "smart_transform_for_viz",
                    "details": {
                        "df_id": data_context.df_id,
                        "reason": "expired_or_missing"
                    },
                    "recoverable": True  # Can rerun SQL query
                })
            
            # Extend TTL since we're using the DataFrame
            redis_service.extend_ttl(data_context.df_id)
            
            logger.info(f"Using DataFrame {data_context.df_id} with shape {df.shape} for visualization")
            
            if df.empty:
                # STANDARDIZED ERROR: Empty DataFrame
                return json.dumps({
                    "error": "The DataFrame is empty, so no visualization could be generated.",
                    "error_type": "validation_error",
                    "tool_name": "smart_transform_for_viz",
                    "details": {"df_id": data_context.df_id},
                    "recoverable": False  # Empty data can't be visualized
                })
            
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
            # STANDARDIZED ERROR: Transformation Failed
            return json.dumps({
                "error": f"Failed to transform data: {str(e)}",
                "error_type": "execution_error",
                "tool_name": "smart_transform_for_viz",
                "details": {
                    "exception": str(e),
                    "viz_type": viz_type if 'viz_type' in locals() else "unknown"
                },
                "recoverable": True  # Can retry
            })
    
    async def _arun(
        self,
        viz_type: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool."""
        return self._run(reasoning, viz_type, config, state, tool_call_id)



from langchain_experimental.tools import PythonAstREPLTool
import random
import string
import logging

class LargePlottingTool(BaseTool):
    """
    Tool for generating high-quality matplotlib plots using DataFrames from Redis.
    Uses LLM to generate code, allowing for smart handling of categorical data and aggregations.
    """
    
    name: str = "large_plotting_tool"
    description: str = """Generate high-quality matplotlib plots using the current DataFrame from Redis.
    
    This tool builds the plot using Python code generated by an LLM, making it capable of:
    - Handling categorical data (e.g. bar charts of counts)
    - Aggregating data automatically
    - Creating complex visualizations
    
    Use this tool when:
    - Dataset has more than 100 rows
    - You need to visualize specific columns (e.g. "depicts_sword")
    - User requests matplotlib, static image, or high-quality plots
    
    Prerequisites:
    - A DataFrame must be available (created by sql_db_to_df tool)
    
    Parameters:
    - x_column (str): Primary column or category to plot
    - y_column (str): Secondary column (value) or None if just counting x
    - plot_type (str): Type of plot (bar, scatter, line, pie, histogram)
    - title (str): Title for the plot
    
    Returns: Markdown image syntax with Supabase public URL for display in chat."""
    
    llm: Any = Field(description="Language model instance")
    
    def _run(
        self,
        x_column: str,
        y_column: str = None,
        *,
        plot_type: str = "bar",
        title: str = "Data Plot",
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Execute the large plotting tool using LLM-generated code."""
        
        logger = logging.getLogger(__name__)
        
        # 1. Retrieve DataFrame from Redis
        try:
            if state is None:
                state = {}
                
            data_context = state.get("data_context")
            if not data_context or not data_context.df_id:
                return "Error: No active DataFrame found in context. Please run a data retrieval query first."

            redis_service = get_redis_dataframe_service()
            df = redis_service.get_dataframe(data_context.df_id)
            
            if df is None or df.empty:
                return "Error: DataFrame not found along the provided ID or is empty."
                
        except Exception as e:
            logger.error(f"Error checking dataframe: {e}")
            return f"Error retrieving data: {str(e)}"

        # 2. Setup output path
        # We need a unique filename for the generated plot
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        output_filename = f"plot_{random_suffix}.png"
        
        # 3. Generate Plotting Code using LLM
        # We give the LLM the dataframe schema and the goal
        
        columns_info = str(list(df.columns))
        dtypes_info = str(df.dtypes)
        head_info = str(df.head(3).to_dict())
        
        prompt = f"""
        You are a Python data visualization expert.
        
        DATA CONTEXT:
        - DataFrame 'df' is available in your environment.
        - Columns: {columns_info}
        - Types: {dtypes_info}
        - Sample Data: {head_info}
        
        GOAL:
        Create a '{plot_type}' plot.
        - X Axis / Category: {x_column}
        - Y Axis / Value: {y_column if y_column else "Count/Frequency"}
        - Title: {title}
        
        CRITICAL RULES:
        1. Handle Data Types:
           - If data is Categorical (strings like 'yes'/'no') and plot is 'bar'/'pie', you MUST aggregate it (e.g. df['{x_column}'].value_counts()).
           - Do NOT try to plot raw string values on Y axis.
        2. Plotting:
           - Use 'matplotlib.pyplot' as 'plt'.
           - Use 'matplotlib.use("Agg")' at the start.
           - Ensure figure size is large (e.g. 10x6).
           - Add grid, labels, and title.
           - Use `plt.tight_layout()`.
        3. Saving:
           - Save the figure to filename: '{output_filename}'
           - Use `plt.savefig('{output_filename}', dpi=100, bbox_inches='tight')`
           - Do NOT use plt.show().
           
        Provide ONLY the Python code to generate and save this plot.
        """
        
        try:
            # Ask LLM for the code
            code_response = self.llm.invoke(prompt)
            code = code_response.content if hasattr(code_response, 'content') else str(code_response)
            
            # Clean code (remove markdown blocks if present)
            code = code.replace("```python", "").replace("```", "").strip()
            
            logger.info(f"Generated Plotting Code:\n{code}")
            
            # 4. Execute Code
            # Initialize REPL with df in local scope
            repl = PythonAstREPLTool(locals={"df": df})
            
            result = repl.run(code)
            
            if "Error" in str(result) and "Traceback" in str(result):
                logger.error(f"Plotting code failed: {result}")
                return f"Error visualizing data: The generated code failed to run. {result}"
                
        except Exception as e:
            logger.error(f"Code generation or execution exception: {e}")
            return f"Error generating visualization: {str(e)}"

        # 5. Upload to Supabase
        # Read the file that should have been created
        try:
            import os
            if not os.path.exists(output_filename):
                return f"Error: The plotting code ran but did not create the expected file '{output_filename}'. Output: {result}"
            
            # Read into buffer
            from io import BytesIO
            with open(output_filename, "rb") as f:
                buf = BytesIO(f.read())
            
            # Cleanup local file
            os.remove(output_filename)
            
            # Upload
            from app.services.dependencies import get_supabase_storage_service
            
            storage_service = get_supabase_storage_service()
            
            # Define storage path
            storage_path = f"plots/generated_{random_suffix}.png"
            content_type = "image/png"
            
            # Upload
            # Upload
            public_url = storage_service.upload_plot_image(
                image_data=buf.getvalue(),
                filename=f"generated_{random_suffix}.png",
                content_type=content_type
            )
            
            return f"![{title}]({public_url})"
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return f"Error uploading plot: {str(e)}"

    async def _arun(
        self,
        x_column: str,
        y_column: str = None,
        *,
        plot_type: str = "bar",
        title: str = "Data Plot",
        state: Annotated[Dict[str, Any], InjectedState] = None,
        tool_call_id: Annotated[Optional[str], InjectedToolCallId] = None,
    ) -> str:
        """Async version of the tool."""
        return self._run(
            x_column,
            y_column,
            plot_type=plot_type,
            title=title,
            state=state,
            tool_call_id=tool_call_id,
        )