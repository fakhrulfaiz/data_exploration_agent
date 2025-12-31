from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class PolicyResult(BaseModel):
    policy_name: str = Field(description="Name of the policy")
    passed: bool = Field(description="Whether the policy check passed")
    message: str = Field(description="Explanation of the result")
    severity: str = Field(
        default="info",
        description="Severity level: 'info', 'warning', 'error'"
    )


class Policy:
    name: str = "Base Policy"
    description: str = "Base policy class"
    
    def check(self, context: Dict[str, Any]) -> PolicyResult:
        raise NotImplementedError("Subclasses must implement check()")


class DataVolumePolicy(Policy):
    
    name = "Data Volume Efficiency"
    description = "Ensures tool selection matches data size"
    
    def check(self, context: Dict[str, Any]) -> PolicyResult:
        tool_name = context.get('tool_name')
        row_count = context.get('row_count')
        
        if tool_name not in ['sql_db_query', 'sql_db_to_df', 'data_exploration_agent']:
            return PolicyResult(
                policy_name=self.name,
                passed=True,
                message="Not applicable to this tool",
                severity="info"
            )
        
        if row_count is None or row_count == -1:
            return PolicyResult(
                policy_name=self.name,
                passed=True,
                message="Row count not available for validation",
                severity="info"
            )
        
        # Check sql_db_query threshold
        if tool_name == 'sql_db_query':
            if row_count > 30:
                return PolicyResult(
                    policy_name=self.name,
                    passed=False,
                    message=f"sql_db_query used for {row_count} rows (recommended limit: 30). Consider sql_db_to_df for large datasets.",
                    severity="warning"
                )
            else:
                return PolicyResult(
                    policy_name=self.name,
                    passed=True,
                    message=f"Appropriate tool for {row_count} rows",
                    severity="info"
                )
        
        # Check sql_db_to_df usage
        if tool_name == 'sql_db_to_df':
            if row_count <= 20:
                return PolicyResult(
                    policy_name=self.name,
                    passed=True,  # Not a failure, just inefficient
                    message=f"Using dataframe for {row_count} rows is acceptable but sql_db_query might be more efficient for very small datasets",
                    severity="info"
                )
            else:
                return PolicyResult(
                    policy_name=self.name,
                    passed=True,
                    message=f"Appropriate tool for {row_count} rows",
                    severity="info"
                )
        
        return PolicyResult(
            policy_name=self.name,
            passed=True,
            message="Tool usage validated",
            severity="info"
        )


class SafetyPolicy(Policy):   
    name = "Safety and Security"
    description = "Ensures operations are read-only and safe"
    
    DANGEROUS_SQL_KEYWORDS = [
        'INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER',
        'TRUNCATE', 'GRANT', 'REVOKE'
    ]
    
    def check(self, context: Dict[str, Any]) -> PolicyResult:
        tool_name = context.get('tool_name')
        tool_input = context.get('tool_input', {})
        
        # Check SQL tools
        if tool_name in ['sql_db_query', 'sql_db_to_df', 'text2SQL', 'data_exploration_agent']:
            # Get SQL query from input
            sql_query = None
            if isinstance(tool_input, dict):
                sql_query = tool_input.get('query') or tool_input.get('sql_query')
            elif isinstance(tool_input, str):
                sql_query = tool_input
            
            if sql_query:
                sql_upper = sql_query.upper()
                for keyword in self.DANGEROUS_SQL_KEYWORDS:
                    if keyword in sql_upper:
                        return PolicyResult(
                            policy_name=self.name,
                            passed=False,
                            message=f"Detected potentially unsafe SQL keyword: {keyword}",
                            severity="error"
                        )
                
                return PolicyResult(
                    policy_name=self.name,
                    passed=True,
                    message="Read-only SQL query validated",
                    severity="info"
                )
        
        # Default: pass if not a SQL tool
        return PolicyResult(
            policy_name=self.name,
            passed=True,
            message="Safety check passed",
            severity="info"
        )


class VisualizationSuitabilityPolicy(Policy):
    
    name = "Visualization Suitability"
    description = "Ensures chart type matches data characteristics"
    
    def check(self, context: Dict[str, Any]) -> PolicyResult:
        tool_name = context.get('tool_name')
        tool_input = context.get('tool_input', {})
        
        # Only check visualization tools
        if tool_name not in ['smart_transform_for_viz', 'large_plotting_tool']:
            return PolicyResult(
                policy_name=self.name,
                passed=True,
                message="Not applicable to this tool",
                severity="info"
            )
        
        # Get chart type from input
        chart_type = None
        if isinstance(tool_input, dict):
            chart_type = tool_input.get('viz_type') or tool_input.get('chart_type')
        
        if not chart_type:
            return PolicyResult(
                policy_name=self.name,
                passed=True,
                message="Chart type not specified in input",
                severity="info"
            )
        
        # Get data summary if available
        data_summary = context.get('data_summary', {})
        row_count = context.get('row_count')
        
        # Check pie chart constraints
        if 'pie' in chart_type.lower():
            if data_summary.get('has_negative_values'):
                return PolicyResult(
                    policy_name=self.name,
                    passed=False,
                    message="Pie charts cannot display negative values. Consider bar chart.",
                    severity="warning"
                )
            
            category_count = data_summary.get('unique_categories', 0)
            if category_count > 10:
                return PolicyResult(
                    policy_name=self.name,
                    passed=False,
                    message=f"Pie chart with {category_count} categories is hard to read (recommended: ≤ 10). Consider bar chart.",
                    severity="warning"
                )
        
        # Check bar chart constraints
        if 'bar' in chart_type.lower():
            category_count = data_summary.get('unique_categories', 0)
            if category_count > 50:
                return PolicyResult(
                    policy_name=self.name,
                    passed=False,
                    message=f"Bar chart with {category_count} categories is cluttered (recommended: ≤ 50). Consider aggregation or filtering.",
                    severity="warning"
                )
        
        return PolicyResult(
            policy_name=self.name,
            passed=True,
            message="Visualization type is appropriate for the data",
            severity="info"
        )


# Registry of all active policies
POLICY_REGISTRY: List[Policy] = [
    DataVolumePolicy(),
    SafetyPolicy(),
    VisualizationSuitabilityPolicy(),
]


def run_all_policies(context: Dict[str, Any]) -> List[PolicyResult]:
    results = []
    for policy in POLICY_REGISTRY:
        try:
            result = policy.check(context)
            results.append(result)
            logger.debug(f"Policy '{policy.name}': {'PASS' if result.passed else 'FAIL'} - {result.message}")
        except Exception as e:
            logger.error(f"Error running policy '{policy.name}': {e}")
            # Add error result
            results.append(PolicyResult(
                policy_name=policy.name,
                passed=True,  # Don't fail on policy errors
                message=f"Policy check error: {str(e)}",
                severity="info"
            ))
    
    return results
