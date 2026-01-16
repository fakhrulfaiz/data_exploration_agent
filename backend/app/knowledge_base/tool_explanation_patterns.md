# Tool Explanation Patterns Knowledge Base

**Purpose**: Guide the explainer node in generating consistent, high-quality explanations for tool executions. These patterns provide templates and examples for explaining what happened during each step.

**Key Principles**:
- Focus on WHAT was returned, not HOW WELL it performed
- Use specific facts from tool output (row counts, column names, etc.)
- Provide context about why this result matters for the next step
- Be honest about limitations and errors

---

## Pattern: data_exploration_tool - Query Execution Success

**Tool**: data_exploration_tool
**Task Type**: query_execution
**Complexity**: simple

**Context**:
- User requested specific data from the database
- SQL query executed successfully
- Retrieved N rows with specific columns
- Data is ready for next step (analysis, visualization, etc.)

**Explanation Template**:
```json
{
  "task_completion_status": "success",
  "execution_summary": "Retrieved {row_count} {entity_type} records from the database with {key_columns}. The data includes {column_list} and is ready for {next_step_purpose}.",
  "data_evidence": "Row Count: {row_count}; Columns: {column_names}; Shape: {rows} rows × {cols} columns.",
  "confidence_score": 0.85-0.95,
  "confidence_factors": ["{row_count} rows retrieved", "All requested columns present: {column_names}", "No errors or warnings"]
}
```

**Example**:
- **Step Goal**: "Retrieve Renaissance paintings with their image paths"
- **Tool Input**: `{"question": "SELECT title, inception, img_path FROM paintings WHERE movement = 'Renaissance'"}`
- **Tool Output**: 65 rows with columns: title, inception, img_path
- **Generated Explanation**:
  - task_completion_status: "success"
  - execution_summary: "Retrieved 65 Renaissance painting records from the database with title, inception date, and image path. The data includes all necessary columns for the subsequent image analysis step."
  - data_evidence: "Row Count: 65; Columns: title, inception, img_path; Shape: 65 rows × 3 columns."
  - confidence_score: 0.9
  - confidence_factors: ["65 rows retrieved", "All requested columns present: title, inception, img_path", "No errors or warnings"]

---

## Pattern: data_exploration_tool - Query Execution with Large Dataset

**Tool**: data_exploration_tool
**Task Type**: query_execution
**Complexity**: simple

**Context**:
- User requested all or most records from database
- Query returned large dataset (>50 rows)
- Data retrieved for broad analysis or filtering

**Explanation Template**:
```json
{
  "task_completion_status": "success",
  "execution_summary": "Retrieved all available {entity_type} records from the database ({row_count} total). The dataset includes {column_list}, providing a complete view for {next_step_purpose}.",
  "data_evidence": "Row Count: {row_count}; Columns: {column_names}; Shape: {rows} rows × {cols} columns.",
  "confidence_score": 0.85-0.95,
  "confidence_factors": ["{row_count} rows retrieved", "Complete dataset loaded", "Columns: {column_names}"]
}
```

**Example**:
- **Step Goal**: "Retrieve all image paths from the database for analysis"
- **Tool Input**: `{"question": "Retrieve all image paths from the database. Include img_path in the query."}`
- **Tool Output**: 101 rows with column: img_path
- **Generated Explanation**:
  - task_completion_status: "success"
  - execution_summary: "Retrieved all available image paths from the database (101 total). The dataset includes the img_path column, providing a complete view for the subsequent image analysis."
  - data_evidence: "Row Count: 101; Columns: img_path; Shape: 101 rows × 1 column."
  - confidence_score: 0.9
  - confidence_factors: ["101 rows retrieved", "Complete dataset loaded", "img_path column present"]

---

## Pattern: image_batch_qa_tool - Binary Classification

**Tool**: image_batch_qa_tool
**Task Type**: visual_analysis
**Complexity**: medium

**Context**:
- Analyzing images to answer Yes/No questions
- Creating new column with binary results
- All or most images processed successfully
- Some failures may occur (file not found, processing errors)

**Explanation Template**:
```json
{
  "task_completion_status": "success",
  "execution_summary": "Analyzed {processed_rows} images to determine {analysis_purpose}. Successfully processed {successful_count} images and created the '{output_column}' column with binary results (yes/no).",
  "data_evidence": "Processed Rows: {processed_rows}; Successful Analyses: {successful_count}; Failed Analyses: {failed_count}; Target Column: '{output_column}'.",
  "confidence_score": 0.75-0.90,
  "confidence_factors": ["{successful_count}/{processed_rows} images analyzed successfully", "New column '{output_column}' created", "{failed_count} failures (acceptable threshold)"]
}
```

**Example 1**:
- **Step Goal**: "Analyze the retrieved paintings to determine which depict war"
- **Tool Input**: `{"question": "Does the painting depict war?", "output_column": "depicts_war"}`
- **Tool Output**: 65 processed, 65 successful, 0 failed
- **Generated Explanation**:
  - task_completion_status: "success"
  - execution_summary: "Analyzed 65 images to determine which paintings depict war. Successfully processed all 65 images and created the 'depicts_war' column with binary results (yes/no)."
  - data_evidence: "Processed Rows: 65; Successful Analyses: 65; Failed Analyses: 0; Target Column: 'depicts_war'."
  - confidence_score: 0.95
  - confidence_factors: ["65/65 images analyzed successfully", "New column 'depicts_war' created", "No failures"]

**Example 2**:
- **Step Goal**: "Analyze images to determine which contain nudity"
- **Tool Input**: `{"question": "Do the images contain nudity?", "output_column": "contains_nudity"}`
- **Tool Output**: 101 processed, 100 successful, 1 failed (ERROR_NOT_FOUND)
- **Generated Explanation**:
  - task_completion_status: "success"
  - execution_summary: "Analyzed 101 images to determine which contain nudity. Successfully processed 100 images and created the 'contains_nudity' column with binary results (yes/no). One image failed due to file not found error."
  - data_evidence: "Processed Rows: 101; Successful Analyses: 100; Failed Analyses: 1; Target Column: 'contains_nudity'."
  - confidence_score: 0.85
  - confidence_factors: ["100/101 images analyzed successfully", "New column 'contains_nudity' created", "1 failure (ERROR_NOT_FOUND) - acceptable threshold"]

---

## Pattern: image_batch_qa_tool - Binary Classification with Multiple Calls

**Tool**: image_batch_qa_tool
**Task Type**: visual_analysis
**Complexity**: medium

**Context**:
- Multiple sequential image analyses on same dataset
- Each analysis creates a new column
- Building up multiple visual attributes

**Explanation Template**:
```json
{
  "task_completion_status": "success",
  "execution_summary": "Analyzed {processed_rows} images to determine {analysis_purpose}. Successfully processed {successful_count} images and created the '{output_column}' column, adding to the existing visual analysis columns.",
  "data_evidence": "Processed Rows: {processed_rows}; Successful Analyses: {successful_count}; New Column: '{output_column}' added to the DataFrame.",
  "confidence_score": 0.80-0.95,
  "confidence_factors": ["{successful_count} images analyzed", "Column '{output_column}' successfully added", "DataFrame now has {total_columns} columns"]
}
```

**Example**:
- **Step Goal**: "Analyze the retrieved paintings to determine which depict swords"
- **Tool Input**: `{"question": "Does the painting depict swords?", "output_column": "depicts_sword"}`
- **Tool Output**: 65 processed, 65 successful, new column added
- **Generated Explanation**:
  - task_completion_status: "success"
  - execution_summary: "Analyzed 65 images to determine which paintings depict swords. Successfully processed all 65 images and created the 'depicts_sword' column, adding to the existing 'depicts_war' column from the previous analysis."
  - data_evidence: "Processed Rows: 65; Successful Analyses: 65; New Column: 'depicts_sword' added to the DataFrame."
  - confidence_score: 0.95
  - confidence_factors: ["65 images analyzed successfully", "Column 'depicts_sword' successfully added", "DataFrame now has 5 columns (title, inception, img_path, depicts_war, depicts_sword)"]

---

## Pattern: smart_data_analysis - Counting/Filtering

**Tool**: smart_data_analysis
**Task Type**: data_transformation
**Complexity**: simple

**Context**:
- Counting specific values in a column
- Filtering data based on conditions
- Simple aggregation operations

**Explanation Template**:
```json
{
  "task_completion_status": "success",
  "execution_summary": "Counted {result_description} based on the '{column_name}' column. Found {count_result}.",
  "data_evidence": "{specific_counts}",
  "confidence_score": 0.90-1.0,
  "confidence_factors": ["Direct count from existing column", "Clear numeric result: {result}", "No ambiguity in counting logic"]
}
```

**Example**:
- **Step Goal**: "Count the number of paintings that depict war and swords"
- **Tool Input 1**: `{"analysis_request": "Count the number of paintings where 'depicts_war' is 'yes'."}`
- **Tool Output 1**: "1"
- **Tool Input 2**: `{"analysis_request": "Count the number of paintings where 'depicts_sword' is 'yes'."}`
- **Tool Output 2**: "25"
- **Generated Explanation**:
  - task_completion_status: "success"
  - execution_summary: "Counted paintings depicting war and swords based on the visual analysis columns. Found 1 painting depicting war and 25 paintings depicting swords."
  - data_evidence: "1 painting depicts war and 25 paintings depict swords."
  - confidence_score: 0.95
  - confidence_factors: ["Direct count from existing columns 'depicts_war' and 'depicts_sword'", "Clear numeric results: 1 and 25", "No ambiguity in counting logic"]

---

## Pattern: large_plotting_tool - Bar Chart Visualization

**Tool**: large_plotting_tool
**Task Type**: visualization
**Complexity**: simple

**Context**:
- Creating bar chart to visualize counts or distributions
- Data already prepared in DataFrame
- Categorical x-axis, numeric y-axis

**Explanation Template**:
```json
{
  "task_completion_status": "success",
  "execution_summary": "Created a bar chart visualizing {visualization_purpose}. The plot shows {key_insight} using {x_column} on the x-axis and {y_column} on the y-axis.",
  "data_evidence": "Output Type: matplotlib_plot; Plot Type: bar; Title: '{plot_title}'",
  "confidence_score": 0.85-0.95,
  "confidence_factors": ["Plot successfully generated", "Data properly visualized with {data_points} categories", "Clear visual representation of {insight}"]
}
```

**Example**:
- **Step Goal**: "Visualize the counts of images containing nudity versus those that do not"
- **Tool Input**: `{"x_column": "contains_nudity", "y_column": "count", "plot_type": "bar", "title": "Counts of Images Containing Nudity vs. Not"}`
- **Tool Output**: Plot image URL
- **Generated Explanation**:
  - task_completion_status: "success"
  - execution_summary: "Created a bar chart visualizing the distribution of images containing nudity versus those that do not. The plot shows the count comparison using 'contains_nudity' categories on the x-axis and count values on the y-axis."
  - data_evidence: "Output Type: matplotlib_plot; Plot Type: bar; Title: 'Counts of Images Containing Nudity vs. Not'"
  - confidence_score: 0.9
  - confidence_factors: ["Plot successfully generated", "Data properly visualized with 2 categories (yes/no)", "Clear visual representation of nudity distribution"]

---

## Pattern: data_exploration_tool - Query with No Results

**Tool**: data_exploration_tool
**Task Type**: query_execution
**Complexity**: simple

**Context**:
- Query executed successfully but returned 0 rows
- Filters may be too restrictive
- Data may not exist for the requested criteria

**Explanation Template**:
```json
{
  "task_completion_status": "partial",
  "execution_summary": "Executed the database query successfully, but no records matched the specified criteria ({filter_description}). This may indicate that {possible_reason}.",
  "data_evidence": "Row Count: 0; Query executed without errors.",
  "confidence_score": 0.70-0.80,
  "confidence_factors": ["Query executed successfully", "No matching records found", "May need to adjust filters or criteria"]
}
```

---

## Pattern: image_batch_qa_tool - High Failure Rate

**Tool**: image_batch_qa_tool
**Task Type**: visual_analysis
**Complexity**: medium

**Context**:
- Many images failed to process (>10% failure rate)
- Errors like ERROR_NOT_FOUND, ERROR_PROCESSING, ERROR_TOO_LARGE
- Results may be incomplete

**Explanation Template**:
```json
{
  "task_completion_status": "partial",
  "execution_summary": "Attempted to analyze {processed_rows} images for {analysis_purpose}, but encountered {failed_count} failures ({failure_percentage}%). Successfully processed {successful_count} images and created the '{output_column}' column, but results may be incomplete.",
  "data_evidence": "Processed Rows: {processed_rows}; Successful Analyses: {successful_count}; Failed Analyses: {failed_count}; Error Types: {error_breakdown}",
  "confidence_score": 0.50-0.70,
  "confidence_factors": ["Only {successful_count}/{processed_rows} images analyzed", "High failure rate: {failure_percentage}%", "Results may not represent full dataset"]
}
```

---

## Pattern: smart_data_analysis - Failed Execution

**Tool**: smart_data_analysis
**Task Type**: data_transformation
**Complexity**: simple

**Context**:
- Analysis request failed or returned null
- May be due to missing columns, invalid operations, or data issues

**Explanation Template**:
```json
{
  "task_completion_status": "failed",
  "execution_summary": "Attempted to {analysis_description} but the operation failed. This may be due to {possible_reason}.",
  "data_evidence": "Analysis returned null or error.",
  "confidence_score": 0.30-0.50,
  "confidence_factors": ["Operation failed", "No result returned", "May need to check data structure or column names"]
}
```

**Example**:
- **Step Goal**: "Count how many images depict nudity and how many do not"
- **Tool Input**: `{"analysis_request": "Count images where 'contains_nudity' is 'yes' and 'no'."}`
- **Tool Output**: null
- **Generated Explanation**:
  - task_completion_status: "failed"
  - execution_summary: "Attempted to count images by nudity status but the operation failed. This may be due to an issue with the analysis request format or data structure."
  - data_evidence: "Analysis returned null or error."
  - confidence_score: 0.4
  - confidence_factors: ["Operation failed", "No result returned", "May need to rephrase analysis request"]

---

## Usage Notes

**For Explainer Node**:
1. Search patterns using: `tool_name + step_goal`
2. Retrieve top 2 most relevant patterns
3. Use templates as guidance, not rigid rules
4. Always prioritize VERIFIABLE FACTS over templates
5. Adapt language to match user's communication style preference

**Pattern Matching**:
- Semantic search will find similar goals even with different wording
- Example: "Get paintings" matches "Retrieve paintings"
- Tool name ensures correct tool-specific guidance

**Confidence Scoring**:
- Use pattern ranges as guidelines
- Adjust based on actual execution facts
- Lower confidence for partial results or errors
- Higher confidence for complete, error-free executions
