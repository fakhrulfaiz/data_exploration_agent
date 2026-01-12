# Thought Process Knowledge Base (Layer 1)

**Purpose**: Guide the agent's thinking process when analyzing user queries. This is the first layer of explainability where the agent thinks through what needs to be done BEFORE creating a plan.

**Key Principles**:
- **Mention Tools Explicitly**: Always name the tools you intend to use in the thought process (e.g., "I will use `data_exploration_tool`...", "I need to call `large_plotting_tool`...").
- **Detailed Step-by-Step**: Break down the problem into logical steps (Filter -> Analyze -> Visualize).
- **Think in First-Person**: "I need to...", "My goal is..."

---

## Query Pattern Categories

### Category 1: Simple Metadata Retrieval

**Pattern**: "What is the [attribute] of the [superlative] [entity]?"

**Examples**:
- "What is the genre of the oldest painting in the database?"
- "What is the genre of the newest painting in the database?"

**Thought Process Template**:
```
The user wants to find the [attribute] (e.g., genre) of the painting that is the [superlative] (e.g., oldest/newest). 

My plan is:
1.  **Retrieve Data**: I will use the `data_exploration_tool` to query the database.
    -   I need to ORDER BY the temporal column (e.g., `inception`) in the correct direction (ASC for oldest, DESC for newest).
    -   I will LIMIT the result to 1 to get the specific painting.
    -   I will SELECT the [attribute] column requested.
2.  **Refine**: If the user specified a subset (e.g., "oldest *Renaissance* painting"), I will add a WHERE clause to filter by that criteria.
3.  **Answer**: Once I have the record, I will provide the [attribute] to the user.

Since this relies purely on metadata stored in the database, I do not need any visual analysis tools or plotting tools.
```

### Category 2: Visual Analysis with Metadata Filtering

**Pattern**: "What is depicted on the [filtered] painting?"

**Examples**:
- "What is depicted on the oldest Renaissance painting in the database?"
- "What is depicted on the oldest religious artwork in the database?"

**Thought Process Template**:
```
The user wants to know the visual content of a specific painting subject to certain filters (e.g. oldest + Renaissance).

My plan is:
1.  **Identify the Painting**: First, I must find the specific painting record. I will use the `data_exploration_tool`.
    -   I will filter by the criteria (e.g., `movement = 'Renaissance'`).
    -   I will sort by `inception` to find the [superlative] one.
    -   **Crucial**: I MUST select the `img_path` column because I need it for the next step.
2.  **Analyze Image**: Once I have the file path, I will use the `image_batch_qa_tool`.
    -   I will ask a question like "What is depicted in this image?" or "Describe the main subject".
3.  **Synthesize**: I will combine the metadata title/date with the visual description to answer.
```

### Category 3: Temporal Aggregation & Visualization

**Pattern**: "Plot the [metric] per [time_period]"

**Examples**:
- "Plot the number of paintings for each year"
- "Plot the number of paintings for each century"
- "Plot the year of the oldest painting per movement"

**Thought Process Template**:
```
The user wants a visualization (Plot) of a metadata-based metric grouped by a time period.

My plan is:
1.  **Data Extraction**: I will use `data_exploration_tool` to get the raw data.
    -   I need to query all relevant records.
    -   I will select the grouping columns (e.g., `movement`, `inception`).
    -   I need to ensure I can extract the [time_period] (year or century) from the `inception` date.
2.  **Visualization**: I will use the `large_plotting_tool`.
    -   I will NOT use `smart_transform_for_viz` because `large_plotting_tool` is more direct.
    -   I will specify the X-axis (e.g., `year`) and Y-axis (e.g., `count`).
    -   I will ask for a 'bar' or 'line' chart.
```

### Category 4: Visual Counting with Aggregation

**Pattern**: "Get/Plot the number of paintings that depict [object] for each [grouping]"

**Examples**:
- "Get the number of paintings that depict Fruit for each century"
- "Plot the number of paintings that depict War for each year"
- "Get the number of paintings that depict Animals for each movement"

**Thought Process Template**:
```
The user wants to count paintings showing [object] grouped by [category].

My plan is:
1.  **Data Retrieval**: I will use `data_exploration_tool` to get ALL paintings that might be relevant.
    -   I MUST include `img_path` and the grouping column (e.g., `inception` for year/century).
2.  **Visual Analysis**: I will use `image_batch_qa_tool`.
    -   I will set the question to "Does this painting depict [object]?" (e.g., "depicts war").
    -   I will create a new column to store this result.
3.  **Aggregation**: I will use `smart_data_analysis` (or do it within the plotting tool) to group by the category and count the 'Yes' matches.
4.  **Visualization**: If requested, I will use `large_plotting_tool` to plot these counts.
```

### Category 5: Visual Aggregation (Extremes)

**Pattern**: "Get the [highest/lowest] number of [objects] depicted in paintings of each [grouping]"

**Examples**:
- "Get the highest number of swords depicted in paintings of each movement"
- "Plot the lowest number of swords depicted in each genre"

**Thought Process Template**:
```
The user wants to find extreme values (lowest/highest) of a *countable visual object* grouped by a category.

My plan is:
1.  **Data Retrieval**: I will use `data_exploration_tool`.
    -   Select `img_path` and the grouping column.
2.  **Visual Counting**: I will use `image_batch_qa_tool`.
    -   Question: "How many [objects] are in this painting? Return a number."
    -   Output Column: `[object]_count`.
3.  **Analysis/Aggregation**: I will use `smart_data_analysis` to group by the category and find the MIN or MAX.
4.  **Visualization**: Use `large_plotting_tool` if visualization is requested, otherwise just return the data.
```

### Category 6: Simple Aggregation

**Pattern**: "Get the number of paintings for each [grouping]"

**Examples**:
- "Get the number of paintings for each year"
- "Get the number of paintings for each century"
- "Get the century of the newest painting per movement"

**Thought Process Template**:
```
The user wants simple statistics based purely on database metadata.

My plan is:
1.  **Data Query**: I will use `data_exploration_tool`.
    -   This is a metadata-only query.
    -   I can likely do this in SQL: `SELECT [Grouping], COUNT(*) FROM paintings GROUP BY [Grouping]`.
    -   For centuries, I'll handle the date format logic in the SQL query.
2.  **Result**: I will return the aggregated table or plot it using `large_plotting_tool` if "Plot" was asked.
```

---

## Example Thought Processes

### Example 1: "What is the oldest impressionist artwork in the database?"

**Thought Process**:
```
The user is asking for the "oldest" artwork within the "Impressionist" movement.
My goal is to find the single record with the earliest `inception` date that matches `movement = 'Impressionist'`.

1.  **Query Database**: I will use the `data_exploration_tool` to execute a SQL query.
    -   I will `SELECT title, inception, movement FROM paintings`.
    -   I will add `WHERE movement = 'Impressionist'` to filter.
    -   I will `ORDER BY inception ASC` to put the oldest first.
    -   I will `LIMIT 1` to get just the oldest one.

I do not need to look at images or create charts. This is a direct metadata lookup.
```

### Example 2: "What is depicted on the oldest Renaissance painting?"

**Thought Process**:
```
The user wants to know the visual content ("what is depicted") of a specific painting: the oldest Renaissance one.

1.  **Find the Painting**: I will use `data_exploration_tool`.
    -   Query: `SELECT title, inception, img_path FROM paintings WHERE movement = 'Renaissance' ORDER BY inception ASC LIMIT 1`.
    -   I specifically need `img_path` to enable the next step.
2.  **Analyze Content**: I will use `image_batch_qa_tool`.
    -   I will pass the `img_path` from the specific painting found.
    -   I will set the question to: "Describe the main subject and scene depicted in this painting."
    -   This will output a text description.
3.  **Answer**: I will clarify to the user "The oldest Renaissance painting is [Title] from [Year], and it depicts [Description]."
```

### Example 3: "Plot the number of paintings that depict War for each century"

**Thought Process**:
```
The user wants a plot showing the trend of war paintings over centuries. 
"Depicting War" is a visual attribute, not a database column, so I have to "see" the paintings first.
1. **Get Candidates**: I will use `data_exploration_tool`.
   - Query: `SELECT FLOOR(EXTRACT(YEAR FROM inception) / 100) * 100 as century, img_path FROM paintings`.
   - This extracts the year from the timestamp and calculates the century (e.g., 1438 → 1400).
2. **Visual Classification**: I will use `image_batch_qa_tool`.
   - Question: "Does this painting depict scenes of war, battle, or conflict? Answer Yes or No."
   - Output Column: `depicts_war`.
3. **Visualize**: I will use `large_plotting_tool`.
   - X-Axis: `century`.
   - The tool will automatically count paintings where `depicts_war` is 'Yes' per century.
   - No `smart_data_analysis` needed - the plotting tool handles the aggregation.
```

### Example 4: "Get the highest number of swords depicted in paintings of each movement"

**Thought Process**:
```
This is a complex query. I need to count "swords" in *every* painting, then find the *maximum* count per "movement".

1.  **Retrieve Images**: I will use `data_exploration_tool` to get `img_path` and `movement` for all paintings.
2.  **Count Objects**: I will use `image_batch_qa_tool`.
    -   Question: "How many swords are visible in this painting? Return a single integer."
    -   Output Column: `sword_count`.
3.  **Find Maxima**: I will use `smart_data_analysis`.
    -   I will group the data by `movement`.
    -   For each movement, I will find the `MAX(sword_count)`.
4.  **Report**: I will present a table or list showing "Movement: Max Swords".
```

### Example 5: "Plot the number of paintings for each century"

**Thought Process**:
```
The user wants a simple frequency plot of paintings by century. This is purely metadata.

1.  **Aggregate Data**: I will use `data_exploration_tool`.
    -   I can do this directly in SQL if possible, or pull `inception` dates and process in Python.
    -   SQL approach: `SELECT (CAST(strftime('%Y', inception) AS INT) / 100) + 1 AS century, COUNT(*) as count FROM paintings GROUP BY century`.
2.  **Plot**: I will use `large_plotting_tool`.
    -   I will take the result from Step 1.
    -   X-Axis: Century.
    -   Y-Axis: Count.
    -   Type: Bar Chart.
    -   This is the most direct way to get a high-quality plot.
```

### Example 6: "In the Renaissance, find the total number of paintings depicting war and the number of paintings depicting swords."

**Thought Process**:
```
The user wants two specific counts for Renaissance paintings: those with war and those with swords.

1.  **Filter Data**: I will use `data_exploration_tool`.
    -   Query: `SELECT title, img_path FROM paintings WHERE movement = 'Renaissance'`.
    -   This limits the scope to just Renaissance works.
2.  **Analyze War**: I will use `image_batch_qa_tool`.
    -   Question: "Does this painting depict war?" -> Column: `depicts_war`.
3.  **Analyze Swords**: I will use `image_batch_qa_tool` again (or in same batch if supported).
    -   Question: "Does this painting depict a sword?" -> Column: `depicts_sword`.
4.  **Count Totals**: I will use `smart_data_analysis`.
    -   Count rows where `depicts_war` is Yes.
    -   Count rows where `depicts_sword` is Yes.
5.  **Answer**: I will report the two numbers clearly.
```
