# Thought Process Knowledge Base (Layer 1)

**Purpose**: Guide the agent's thinking process when analyzing user queries. This is the first layer of explainability where the agent thinks through what needs to be done BEFORE creating a plan.

**Key Principles**:
- Think in first-person ("I need to...", "The goal is...")
- Focus on WHAT needs to be done, not HOW (no tool names)
- Consider database constraints and capabilities
- Identify multi-step requirements
- Explain the logical reasoning

---

## Query Pattern Categories

### Category 1: Simple Metadata Retrieval

**Pattern**: "What is the [attribute] of the [superlative] [entity]?"

**Examples**:
- "What is the oldest impressionist artwork in the database?"
- "What is the genre of the newest painting in the database?"
- "What is the movement of the painting that depicts the highest number of swords?"

**Thought Process Template**:
```
The user wants to find a specific [attribute] of a painting that meets certain criteria. I need to:
1. Filter the paintings by [condition] if specified (e.g., only Renaissance paintings)
2. Identify the one with the [superlative] value (e.g., oldest = earliest inception date)
3. Return the [attribute] field (e.g., genre, movement)

The challenge is [mention any complexity, e.g., "determining which painting has the most swords requires visual analysis since this isn't in the metadata - I'll need to analyze images first, then find the maximum count"].
```

**Tool to Use**: `data_exploration_tool`

**Tool Requirements**:
- Use SQL to filter and sort data
- SELECT the required attribute field
- Use WHERE clause for filtering (e.g., movement = 'Impressionist')
- Use ORDER BY for superlatives (ASC for oldest, DESC for newest)
- Use LIMIT 1 to get single result

**When NOT to use this tool**:
- If the query asks about visual content (e.g., "depicts swords") - use `image_batch_qa_tool` first
- If visualization is requested - use `smart_transform_for_viz` after getting data

**Database Considerations**:
- Metadata fields: title, inception, movement, genre, image_url, img_path
- Visual attributes (e.g., "depicts swords") require image analysis
- Superlatives: oldest/newest (inception), highest/lowest (requires counting)

---

### Category 2: Visual Analysis with Metadata Filtering

**Pattern**: "What is depicted on the [filtered] painting?"

**Examples**:
- "What is depicted on the oldest Renaissance painting in the database?"
- "What is depicted on the oldest religious artwork in the database?"

**Thought Process Template**:
```
The user wants to know the visual content of a specific painting. I need to:
1. First, identify which painting meets the criteria (oldest + Renaissance/religious)
2. This requires filtering by [movement/genre] and sorting by inception date
3. Then, I need to analyze the image to describe what's depicted
4. The visual analysis requires the image file path from the database

This is a two-step process: find the right painting using metadata, then analyze its visual content.
```

**Tools to Use** (in sequence):
1. `data_exploration_tool` - Query database to find the specific painting
   - Must include 'img_path' in SELECT
   - Filter by movement/genre if specified
   - ORDER BY inception to find oldest/newest
   
2. `image_batch_qa_tool` - Analyze the image
   - question: "main subject and what is depicted"
   - output_column: "visual_description"

**Key Insight**: Visual questions about specific paintings require metadata filtering FIRST to identify which painting, THEN image analysis.

---

### Category 3: Temporal Aggregation & Visualization

**Pattern**: "Plot the [metric] for each [time period]"

**Examples**:
- "Plot the number of paintings for each year"
- "Plot the number of paintings for each century"
- "Plot the year of the oldest painting per movement"

**Thought Process Template**:
```
The user wants a visualization showing [metric] across [time periods]. I need to:
1. Extract the [time period] from the inception dates (year or century)
2. Group the data by [time period]
3. Calculate the [metric] for each group (count, min, max, etc.)
4. Create a visualization (likely a bar or line chart for temporal data)

For century calculation, I need to convert years to centuries using: (year - 1) / 100 + 1.
The visualization will show trends over time.
```

**Database Considerations**:
- Inception is stored as DATETIME ('YYYY-MM-DD HH:MM:SS')
- Year extraction: `strftime('%Y', inception)`
- Century calculation: `(CAST(strftime('%Y', inception) AS INTEGER) - 1) / 100 + 1`

---

### Category 4: Visual Counting with Aggregation

**Pattern**: "Get/Plot the number of paintings that depict [object] for each [grouping]"

**Examples**:
- "Get the number of paintings that depict Fruit for each century"
- "Plot the number of paintings that depict War for each year"
- "Get the number of paintings that depict Animals for each movement"

**Thought Process Template**:
```
The user wants to count paintings showing [object] grouped by [category]. This is complex because:
1. "Depicts [object]" requires visual analysis - this information isn't in the metadata
2. I need to analyze ALL paintings to determine which ones show [object]
3. Then group the results by [category] (century/year/movement)
4. Count how many paintings in each group depict [object]
5. If "Plot" is requested, create a visualization of the counts

This requires analyzing multiple images and aggregating the results. The visual analysis must happen before grouping.
```

**Challenge**: Visual attributes aren't in the database, so this requires:
- Step 1: Get all paintings with their img_paths
- Step 2: Analyze each image for the presence of [object]
- Step 3: Group and count the results
- Step 4: Visualize if requested

---

### Category 4a: Image Question Answering (Visual Analysis)

**Pattern**: Questions about visual content that require analyzing images

**Examples**:
- "What is the main subject in each painting?"
- "What colors are visible in the Renaissance paintings?"
- "Is there a person in the oldest painting?"
- "What objects can you see in paintings from the 18th century?"
- "What is the art style of each painting?"

**Thought Process Template**:
```
The user wants to extract visual information from images that isn't available in the database metadata. I need to:
1. First, query the database to get the paintings that match any filters (e.g., movement, genre, time period)
2. Ensure the query includes the 'img_path' column - this is REQUIRED for image analysis
3. Use the image_batch_qa_tool to analyze all images in the result set
4. The tool will process each image locally (from backend/app/resource/) and add the answers as a new column
5. The DataFrame will be updated in Redis with the new visual data
6. Then I can use this enriched data for further analysis or visualization

Key requirements:
- The DataFrame MUST contain 'img_path' column (e.g., 'images/img_0.jpg')
- Images must exist locally in backend/app/resource/
- The question should be direct and specific (e.g., "main subject" not "Can you tell me what the main subject is?")
- The tool creates a new column with the answers, which can be used by subsequent tools
```

**Tool to Use**: `image_batch_qa_tool`

**Tool Requirements**:
- **Input 1 - question** (str): Direct, imperative visual question
  - ✅ GOOD: "main subject in the image"
  - ✅ GOOD: "primary colors visible"
  - ✅ GOOD: "art style and technique"
  - ❌ BAD: "Can you tell me what is in this image?"
  - ❌ BAD: "Is there anything interesting?"
  
- **Input 2 - output_column** (str): Name for the new column to store results
  - Examples: "main_subject", "colors", "art_style", "has_person"
  - Should be descriptive and snake_case
  
- **Prerequisites**:
  - DataFrame must exist in Redis (from previous SQL query)
  - DataFrame MUST have 'img_path' column
  - Images must be local paths (e.g., 'images/img_0.jpg'), NOT URLs
  
- **Output**:
  - Updates the DataFrame in Redis with a new column
  - Returns summary: number of images processed, success count, error count
  - The new column can be used by visualization or analysis tools

**Workflow Example**:
```
User: "What is the main subject in each Renaissance painting?"

Thought Process:
The user wants visual information about Renaissance paintings. I need to:
1. Query the database for Renaissance paintings (filter by movement='Renaissance')
2. Make sure to include 'img_path' in the SELECT statement
3. Use image_batch_qa_tool with:
   - question: "main subject in the image"
   - output_column: "main_subject"
4. The tool will analyze each image and add a 'main_subject' column
5. Then I can present the results or create a visualization if requested

Steps:
Step 1: Query database
  Tool: data_exploration_tool
  Query: SELECT title, inception, img_path FROM paintings WHERE movement = 'Renaissance'
  
Step 2: Analyze images
  Tool: image_batch_qa_tool
  Parameters:
    - question: "main subject in the image"
    - output_column: "main_subject"
  
Step 3: Present results
  The DataFrame now has columns: title, inception, img_path, main_subject
  I can show this data or create a chart if requested
```

**Common Image QA Scenarios**:

1. **Subject Identification**:
   - Question: "What is the main subject?"
   - Output column: "main_subject"
   - Use case: Understanding what each painting depicts

2. **Object Detection**:
   - Question: "objects visible in the image"
   - Output column: "objects"
   - Use case: Cataloging items shown in artworks

3. **Color Analysis**:
   - Question: "primary colors used"
   - Output column: "colors"
   - Use case: Analyzing color palettes

4. **Style Recognition**:
   - Question: "art style and technique"
   - Output column: "art_style"
   - Use case: Classifying artistic approaches

5. **Boolean Checks**:
   - Question: "is there a person in this image"
   - Output column: "has_person"
   - Use case: Filtering paintings with/without people

**Integration with Other Tools**:

After using `image_batch_qa_tool`, the enriched DataFrame can be used with:
- `smart_transform_for_viz`: Create charts showing visual attributes
- `data_exploration_tool`: Further SQL analysis on the new columns
- `large_plotting_tool`: Generate matplotlib visualizations
- `secure_python_repl_tool`: Custom analysis on the visual data

**Performance Considerations**:
- Processing images takes time (~1-2 seconds per image)
- For 10 images: expect ~10-20 seconds
- For 100 images: expect ~2-3 minutes
- The BLIP model loads once and is cached for subsequent uses
- Results are stored in Redis, so re-running the same query is instant

---

### Category 5: Visual Counting with Aggregation

**Pattern**: "Get/Plot the number of paintings that depict [object] for each [grouping]"

**Examples**:
- "Get the number of paintings that depict Fruit for each century"
- "Plot the number of paintings that depict War for each year"
- "Get the number of paintings that depict Animals for each movement"

**Thought Process Template**:
```
The user wants to count paintings showing [object] grouped by [category]. This is complex because:
1. "Depicts [object]" requires visual analysis - this information isn't in the metadata
2. I need to analyze ALL paintings to determine which ones show [object]
3. Then group the results by [category] (century/year/movement)
4. Count how many paintings in each group depict [object]
5. If "Plot" is requested, create a visualization of the counts

This requires analyzing multiple images and aggregating the results. The visual analysis must happen before grouping.

Recommended approach:
1. Query all paintings with img_path and the grouping field (e.g., movement)
2. Use image_batch_qa_tool to ask "is there [object] in this image" → creates boolean column
3. Use data_exploration_tool to count TRUE values grouped by the category
4. If plotting requested, use smart_transform_for_viz
```

**Challenge**: Visual attributes aren't in the database, so this requires:
- Step 1: Get all paintings with their img_paths and grouping fields
- Step 2: Use image_batch_qa_tool to detect presence of [object]
- Step 3: Group and count the results using SQL or Python
- Step 4: Visualize if requested

---

### Category 6: Visual Extremes with Grouping

**Pattern**: "Get the [highest/lowest] number of [objects] depicted in paintings of each [grouping]"

**Examples**:
- "Get the highest number of swords depicted in paintings of each movement"
- "Plot the lowest number of swords depicted in each genre"

**Thought Process Template**:
```
The user wants to find the [extreme] count of [objects] within each [group]. This requires:
1. Analyze all paintings to count how many [objects] appear in each
2. Group the paintings by [category] (movement/genre)
3. Find the [maximum/minimum] count within each group
4. Return or visualize the results

This is computationally intensive because every painting needs visual analysis to count [objects], then we aggregate to find extremes per group.
```

**Complexity Note**: This combines visual counting (requires image analysis) with aggregation (requires grouping and finding extremes).

---

### Category 7: Simple Aggregation (No Visual Analysis)

**Pattern**: "Get the number of paintings for each [grouping]"

**Examples**:
- "Get the number of paintings for each year"
- "Get the number of paintings for each century"
- "Get the century of the newest painting per movement"

**Thought Process Template**:
```
The user wants to count or find [metric] grouped by [category]. Since this only involves metadata:
1. Group paintings by [category] (year/century/movement/genre)
2. Calculate the [metric] (count, newest inception date, etc.)
3. Return the aggregated results

This is straightforward because all required information is in the database metadata - no image analysis needed.
```

**Database Operations**:
- GROUP BY [field]
- COUNT(*) for counting
- MAX(inception) for newest, MIN(inception) for oldest
- Century extraction if needed

---

## Decision Framework for Thought Process

### Step 1: Identify Query Type

**Questions to ask**:
1. Does the query mention visual attributes? (depicts, shows, contains, colors, objects)
   - YES → Requires image analysis
   - NO → Metadata only

2. Does the query ask for aggregation? (for each, per, count, highest, lowest)
   - YES → Requires grouping and calculation
   - NO → Single record retrieval

3. Does the query request visualization? (plot, chart, graph, show)
   - YES → Need to create visual output
   - NO → Return data/text

### Step 2: Identify Data Requirements

**Metadata fields available**:
- title, inception, movement, genre, image_url, img_path

**Visual analysis needed for**:
- Object detection (swords, babies, fruit, animals, war)
- Scene description (what is depicted)
- Counting objects in images
- Color analysis
- Composition analysis

### Step 3: Identify Complexity

**Simple** (1 step):
- Single metadata query: "What is the oldest painting?"
- Simple aggregation: "Count paintings per genre"

**Medium** (2 steps):
- Metadata filter + image analysis: "What is depicted on the oldest Renaissance painting?"
- Query + visualization: "Plot paintings per year"

**Complex** (3+ steps):
- Visual analysis + aggregation + visualization: "Plot the number of paintings depicting War for each century"
- Multiple image analyses + grouping + extremes: "Get the highest number of swords per movement"

---

## Common Reasoning Patterns

### Pattern: Superlatives (Oldest/Newest)

**Reasoning**:
```
To find the [oldest/newest] painting, I need to identify the one with the earliest or latest creation date.
- Oldest = find the painting with the earliest inception date
- Newest = find the painting with the latest inception date
```

### Pattern: Filtering by Movement/Genre

**Reasoning**:
```
The user specified [movement/genre], so I need to filter the paintings to only include those matching this criteria. This narrows down the dataset before applying other operations.
```

### Pattern: Visual + Metadata Combination

**Reasoning**:
```
This query combines metadata filtering with visual analysis:
1. Use metadata to identify which painting(s) to analyze
2. Get the image path for those paintings
3. Perform visual analysis on the identified images
The metadata acts as a filter to reduce the number of images to analyze.
```

### Pattern: Temporal Grouping

**Reasoning**:
```
Grouping by time period requires extracting the period from the creation date:
- Year: Extract the 4-digit year from the inception date
- Century: Calculate the century number from the year
Then group the paintings by the extracted period and aggregate (count, find min/max, etc.)
```

### Pattern: Visual Counting Across Dataset

**Reasoning**:
```
Counting visual attributes across all paintings is resource-intensive:
1. Need to analyze every painting's image
2. Count occurrences of [object] in each image
3. Aggregate the counts by the requested grouping
This requires processing all images, which may take time.
```

---

## Example Thought Processes

### Example 1: "What is the oldest impressionist artwork in the database?"

**Thought Process**:
```
The user wants to find the oldest painting from the Impressionist movement. I need to filter the paintings to only include those from the Impressionist period, then identify the one with the earliest creation date. This will give me the oldest Impressionist painting, and I can return its title, inception date, and other details.
```

### Example 2: "What is depicted on the oldest Renaissance painting?"

**Thought Process**:
```
The user wants to know what's shown in a specific painting - the oldest one from the Renaissance movement. First, I need to identify which painting is the oldest Renaissance work by finding the one with the earliest creation date. Then, I'll analyze that painting's image to describe its visual content. This is a two-step process: find the right painting, then examine what it depicts.
```

### Example 3: "Plot the number of paintings that depict War for each century"

**Thought Process**:
```
The user wants a visualization showing how many paintings depicting war exist in each century. This is complex because "depicts War" requires visual analysis - it's not in the metadata. I need to analyze all paintings to determine which ones show war-related scenes, then group those paintings by century and count them. The century needs to be calculated from the inception date. Finally, I'll create a chart showing the count of war-themed paintings per century. This combines image analysis with data aggregation.
```

### Example 4: "Get the highest number of swords depicted in paintings of each movement"

**Thought Process**:
```
The user wants to find the maximum count of swords shown in any single painting, grouped by art movement. This requires analyzing every painting to count how many swords appear in each image, then grouping the paintings by movement and finding the highest sword count within each movement group. This is computationally intensive because it requires visual analysis of all paintings to count objects, followed by aggregation to find the maximum per movement.
```

### Example 5: "Get the number of paintings for each century"

**Thought Process**:
```
The user wants a count of paintings grouped by century. Since this only involves the creation dates, I need to determine which century each painting belongs to, then count how many paintings are in each century. This is straightforward aggregation using the inception dates, with no image analysis needed.
```

---

## Database Schema Quick Reference

**Table**: `paintings`

**Columns**:
- `title` (TEXT): Name of the painting
- `inception` (DATETIME): Creation date ('YYYY-MM-DD HH:MM:SS')
- `movement` (TEXT): Art movement (Renaissance, Impressionist, etc.)
- `genre` (TEXT): Genre (religious art, portrait, landscape, etc.)
- `image_url` (TEXT): Public URL to image
- `img_path` (TEXT): Local file path (e.g., 'images/img_0.jpg')

**NO artist column** - artist information is not available

---

## Key Constraints to Mention in Thought Process

1. **Visual attributes require image analysis**: Objects, colors, composition aren't in metadata
2. **Century calculation needed**: Database has dates, not centuries
3. **Multiple image analysis is slow**: Analyzing many images takes time
4. **No artist data**: Can't answer questions about who painted something
5. **Image path required**: Visual analysis needs the img_path from database first
