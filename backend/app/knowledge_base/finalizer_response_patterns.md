# Finalizer Response Patterns

This knowledge base contains patterns for generating user-facing responses based on execution results.

## Pattern Categories

### 1. Data Retrieval & Display

#### Simple Data Query
**Execution Context**: data_exploration_tool only
**Response Pattern**:
- Lead with row count and columns retrieved
- Mention key columns if relevant to query
- Keep it brief
- **IMPORTANT**: For local dataset images (img_path), ALWAYS use table format to save space. Show max 3 sample rows.
- Do NOT display local images inline with ![Image](/api/static/...) - this takes too much vertical space

**Actions**:
- export_dataframe: True if any data was retrieved (any row count > 0). Users should always be able to export retrieved data.
- download_images: False
- next_queries: ["Filter by [column]", "Show statistics for [column]", "Plot [column] distribution"]

**Example**:
I retrieved 101 artworks with title, inception date, movement, genre, and image path.

**Sample Data** (first 3 rows):

| Title | Inception | Movement | Genre | Image |
|-------|-----------|----------|-------|-------|
| Predella of the Barbadori altarpiece | 1438 | Renaissance | religious art | ![img](/api/static/images/img_0.jpg) |
| Judith | 1525 | Renaissance | religious art | ![img](/api/static/images/img_1.jpg) |
| Judith | 1528 | Renaissance | religious art | ![img](/api/static/images/img_2.jpg) |

---

### 2. Image Analysis Results

#### Single Image Question
**Execution Context**: data_exploration_tool → image_batch_qa_tool
**Response Pattern**:
- State total images analyzed
- Summarize the distribution (counts/percentages)
- Reference the new column created

**Actions**:
- export_dataframe: True (analysis added new valuable columns)
- download_images: False
- next_queries: ["Show only [yes/no] results", "Analyze for [related concept]", "Compare across [dimension]"]

**Example**:
I analyzed 101 images for sci-fi themes. Results: 98 images without sci-fi (97%) and 3 with sci-fi themes (3%).

#### Multiple Image Questions
**Execution Context**: data_exploration_tool → image_batch_qa_tool (multiple)
**Response Pattern**:
- List each concept analyzed with counts
- Use bullet points for clarity
- Highlight interesting patterns if any

**Actions**:
- export_dataframe: True (complex analysis results)
- download_images: False
- next_queries: ["Sort by count", "Correlate [concept] with [metadata]", "Show examples of [concept]"]

**Example**:
I analyzed 101 Renaissance paintings for multiple themes:
- War depictions: 15 paintings (14.9%)
- Sword imagery: 23 paintings (22.8%)
- Religious themes: 67 paintings (66.3%)

---

### 3. Visualization Results

#### Bar/Count Plot
**Execution Context**: Any tool → large_plotting_tool (bar)
**Response Pattern**:
- State what was plotted
- Include key statistics from the plot
- Embed the plot image

**Actions**:
- export_dataframe: true if df exists
- download_images: true (plot_url exists)
- next_queries: ["Break down by [another dimension]", "Show top [N] [categories]", "Compare with [related metric]"]

**Example**:
Here's the distribution of sci-fi themes across 101 images:

![Plot](plot_url)

The data shows 98 images without sci-fi themes and 3 with them.

#### Scatter/Line Plot
**Execution Context**: Any tool → large_plotting_tool (scatter/line)
**Response Pattern**:
- Describe the relationship shown
- Mention trends or patterns
- Include correlation if calculated

**Actions**:
- export_dataframe: true
- download_images: true
- next_queries: ["Add [third variable] to plot", "Filter by [condition]", "Show outliers"]

---

### 4. Statistical Analysis

#### Aggregations (Count, Sum, Average)
**Execution Context**: data_exploration_tool or smart_data_analysis with aggregations
**Response Pattern**:
- Lead with the direct answer
- Provide context (total, percentage, comparison)
- Be precise with numbers

**Actions**:
- export_dataframe: true
- download_images: true if plot exists
- next_queries: ["Break down by [category]", "Compare with [other group]", "Show trend over time"]

**Example**:
The average inception year for Renaissance paintings is 1547, based on 45 artworks in the dataset.

#### Grouping & Comparison
**Execution Context**: smart_data_analysis with group_by
**Response Pattern**:
- Present groups in order (top to bottom or chronological)
- Use bullet points or table format
- Highlight the top/bottom if relevant

**Actions**:
- export_dataframe: true
- download_images: true if plot exists
- next_queries: ["Show details for [top group]", "Compare [group A] vs [group B]", "Add [another metric]"]

---

### 5. Transformation Results

#### Data Filtering
**Execution Context**: smart_transform_for_viz with filter
**Response Pattern**:
- State what was filtered and how many rows remain
- Mention the filter condition clearly
- Confirm readiness for next step

**Actions**:
- export_dataframe: true
- download_images: false
- next_queries: ["Plot [column]", "Show statistics", "Add another filter"]

**Example**:
I filtered to 45 Renaissance paintings from the original 101 artworks.

#### Column Creation/Transformation
**Execution Context**: smart_transform_for_viz with new column
**Response Pattern**:
- Explain what new column was created
- Show example values if helpful
- State what can be done next

**Actions**:
- export_dataframe: true
- download_images: false
- next_queries: ["Plot [new column]", "Analyze [new column]", "Group by [new column]"]

---

### 6. Error Recovery

#### Partial Success
**Execution Context**: Some steps succeeded, some failed
**Response Pattern**:
- State what was accomplished
- Clearly mention what failed and why
- Suggest alternative approach if possible

**Actions**:
- export_dataframe: true if any data exists
- download_images: false
- next_queries: ["Try [alternative approach]", "Show what we have", "Simplify query"]

**Example**:
I successfully retrieved 101 artworks, but the image analysis failed for 5 images due to file errors. The remaining 96 images were analyzed successfully.

---


### 7. Complex Multi-Concept Analysis

#### Multi-Concept Image Analysis with Counting
**Execution Context**: data_exploration_tool → image_batch_qa_tool (multiple) → smart_data_analysis (multiple counts) or large_plotting_tool
**Response Pattern**:
- Lead with direct counts for each concept
- Use bullet points or list format
- Provide context (total dataset size)
- Mention any limitations if applicable

**Actions**:
- export_dataframe: true (multiple analysis columns added)
- download_images: false (unless plot generated)
- next_queries: ["Find items with both [A] and [B]", "Compare [concept A] vs [concept B]", "Show examples of [concept]"]

**Example**:
Here are the results for Renaissance paintings:

- Total paintings depicting war: 8
- Total paintings depicting swords: 21

(Analyzed 65 Renaissance paintings total)

