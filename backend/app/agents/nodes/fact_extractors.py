import json
import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ToolFactExtractor:

    def extract(self, tool_output: str) -> Dict[str, Any]:
        """Extract verifiable facts from tool output"""
        return {
            'has_error': False,
            'output_type': 'unknown'
        }


class DataExplorationFactExtractor(ToolFactExtractor):

    def extract(self, tool_output: str) -> Dict[str, Any]:
        facts = {
            'has_error': False,
            'output_type': 'data_retrieval',
            'row_count': None,
            'columns': [],
            'shape': None,
            'df_id': None
        }
        
        try:
            output_data = json.loads(tool_output)
            r
            if 'error' in output_data:
                facts['has_error'] = True
                facts['error_type'] = output_data.get('error_type')
                facts['error_message'] = output_data.get('error')
                facts['recoverable'] = output_data.get('recoverable', False)
                return facts
            
            facts['row_count'] = output_data.get('row_count')
            if 'data_context' in output_data:
                dc = output_data['data_context']
                facts['columns'] = dc.get('columns', [])
                facts['shape'] = dc.get('shape')
                facts['df_id'] = dc.get('df_id')
                
        except json.JSONDecodeError:
            logger.warning(f"Could not parse data_exploration_tool output as JSON")
            
        return facts


class SmartVizFactExtractor(ToolFactExtractor):

    def extract(self, tool_output: str) -> Dict[str, Any]:
        facts = {
            'has_error': False,
            'output_type': 'visualization',
            'viz_type': None,
            'total_rows': None,
            'displayed_rows': None,
            'columns': []
        }
        
        try:
            output_data = json.loads(tool_output)
            
            if 'error' in output_data:
                facts['has_error'] = True
                facts['error_type'] = output_data.get('error_type')
                facts['error_message'] = output_data.get('error')
                facts['recoverable'] = output_data.get('recoverable', False)
                return facts
            
            facts['viz_type'] = output_data.get('type')
            if 'metadata' in output_data:
                meta = output_data['metadata']
                facts['total_rows'] = meta.get('total_rows')
                facts['displayed_rows'] = meta.get('displayed_rows')
                facts['columns'] = meta.get('columns', [])
                
        except json.JSONDecodeError:
            logger.warning(f"Could not parse smart_transform_for_viz output as JSON")
            
        return facts


class LargePlottingFactExtractor(ToolFactExtractor):

    def extract(self, tool_output: str) -> Dict[str, Any]:
        facts = {
            'has_error': False,
            'output_type': 'matplotlib_plot',
            'data_points': None,
            'plot_type': None,
            'x_axis': None,
            'y_axis': None
        }
        
        try:
            # Try JSON first (for errors)
            output_data = json.loads(tool_output)
            if 'error' in output_data:
                facts['has_error'] = True
                facts['error_type'] = output_data.get('error_type')
                facts['error_message'] = output_data.get('error')
                facts['recoverable'] = output_data.get('recoverable', False)
                return facts
        except json.JSONDecodeError:
            # Text output - extract from markdown
            if 'Plot generated successfully' in tool_output:
                # Extract data points
                match = re.search(r'Data Points:\s*([\d,]+)', tool_output)
                if match:
                    facts['data_points'] = int(match.group(1).replace(',', ''))
                
                # Extract plot type
                type_match = re.search(r'Type:\s*(\w+)\s+Plot', tool_output)
                if type_match:
                    facts['plot_type'] = type_match.group(1).lower()
                
                # Extract axes
                x_match = re.search(r'X-axis:\s*(\w+)', tool_output)
                if x_match:
                    facts['x_axis'] = x_match.group(1)
                    
                y_match = re.search(r'Y-axis:\s*(\w+)', tool_output)
                if y_match:
                    facts['y_axis'] = y_match.group(1)
            else:
                logger.warning(f"Could not parse large_plotting_tool output")
                
        return facts


# Registry for scalability - add new tools here
FACT_EXTRACTORS = {
    'data_exploration_tool': DataExplorationFactExtractor(),
    'smart_transform_for_viz': SmartVizFactExtractor(),
    'large_plotting_tool': LargePlottingFactExtractor(),
}


def get_fact_extractor(tool_name: str) -> ToolFactExtractor:
    return FACT_EXTRACTORS.get(tool_name, ToolFactExtractor())
