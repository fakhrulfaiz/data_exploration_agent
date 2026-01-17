# XpAgentV2 Workspace

This directory is the workspace for XpAgentV2 (experimental agent).

## Structure

- `outputs/` - CSV files and data exports from database queries
- `plot/` - Generated visualizations and charts

## Usage

XpAgentV2 uses this workspace instead of the dev workspace (`backend/app/agents/dev/workspace/`).

This separation allows:

1. Independent testing of experimental features
2. Clean separation between development and production experiments
3. Easy cleanup and reset of experimental data
