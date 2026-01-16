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


class ImageBatchQAFactExtractor(ToolFactExtractor):
    """Extract facts from image_batch_qa_tool output"""
    
    def extract(self, tool_output: str) -> Dict[str, Any]:
        facts = {
            'has_error': False,
            'output_type': 'image_analysis',
            'total_rows': None,
            'success_count': None,
            'error_count': None,
            'output_column': None,
            'error_breakdown': {}
        }
        
        try:
            output_data = json.loads(tool_output)
            
            # Check for errors
            if 'error' in output_data:
                facts['has_error'] = True
                facts['error_type'] = output_data.get('error_type')
                facts['error_message'] = output_data.get('error')
                facts['recoverable'] = output_data.get('recoverable', False)
                return facts
            
            # Extract from description text (tool returns structured text)
            description = output_data.get('description', '')
            
            # Extract total rows
            if 'Total Rows:' in description:
                match = re.search(r'Total Rows:\s*(\d+)', description)
                if match:
                    facts['total_rows'] = int(match.group(1))
            elif 'Processed Rows:' in description:
                match = re.search(r'Processed Rows:\s*(\d+)', description)
                if match:
                    facts['total_rows'] = int(match.group(1))
            
            # Extract success/error counts
            if 'Successful Analyses:' in description:
                match = re.search(r'Successful Analyses:\s*(\d+)', description)
                if match:
                    facts['success_count'] = int(match.group(1))
            
            if 'Failed Analyses:' in description:
                match = re.search(r'Failed Analyses:\s*(\d+)', description)
                if match:
                    facts['error_count'] = int(match.group(1))
            
            # Extract output column
            if 'Target Column:' in description:
                match = re.search(r'Target Column:\s*"([^"]+)"', description)
                if match:
                    facts['output_column'] = match.group(1)
            
            # Extract error breakdown if present
            if 'Error breakdown:' in description:
                # Parse error types (e.g., "- ERROR_NOT_FOUND: 3")
                error_lines = description.split('Error breakdown:')[1].split('\n')
                for line in error_lines:
                    if ':' in line and 'ERROR_' in line:
                        parts = line.strip().split(':')
                        if len(parts) == 2:
                            error_type = parts[0].strip('- ').strip()
                            count = parts[1].strip()
                            try:
                                facts['error_breakdown'][error_type] = int(count)
                            except ValueError:
                                pass
            
            # Also get row_count from JSON if available
            if 'row_count' in output_data:
                facts['total_rows'] = output_data['row_count']
                
        except json.JSONDecodeError:
            logger.warning(f"Could not parse image_batch_qa_tool output as JSON")
            
        return facts


class SmartDataAnalysisFactExtractor(ToolFactExtractor):
    """Extract facts from smart_data_analysis tool output"""
    
    def extract(self, tool_output: str) -> Dict[str, Any]:
        facts = {
            'has_error': False,
            'output_type': 'data_analysis',
            'result_type': None,
            'result_preview': None,
            'result_length': None
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
            # Text output - extract from result
            if 'Analysis Result:' in tool_output:
                result_text = tool_output.split('Analysis Result:')[1].strip()
                
                # Determine result type based on content
                if '\n' in result_text and len(result_text.split('\n')) > 5:
                    facts['result_type'] = 'dataframe/series'
                    facts['result_length'] = len(result_text.split('\n'))
                elif any(keyword in result_text.lower() for keyword in ['dtype:', 'name:', 'length:']):
                    facts['result_type'] = 'series'
                    # Try to extract length
                    if 'Length:' in result_text:
                        match = re.search(r'Length:\s*(\d+)', result_text)
                        if match:
                            facts['result_length'] = int(match.group(1))
                else:
                    facts['result_type'] = 'scalar'
                
                # Get preview (first 100 chars)
                facts['result_preview'] = result_text[:100]
                if len(result_text) > 100:
                    facts['result_preview'] += '...'
            else:
                logger.warning(f"Could not parse smart_data_analysis output")
                
        return facts


# Registry for scalability - add new tools here
FACT_EXTRACTORS = {
    'data_exploration_tool': DataExplorationFactExtractor(),
    'smart_transform_for_viz': SmartVizFactExtractor(),
    'large_plotting_tool': LargePlottingFactExtractor(),
    'image_batch_qa_tool': ImageBatchQAFactExtractor(),
    'smart_data_analysis': SmartDataAnalysisFactExtractor(),
}


def get_fact_extractor(tool_name: str) -> ToolFactExtractor:
    return FACT_EXTRACTORS.get(tool_name, ToolFactExtractor())
