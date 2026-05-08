# Workflow: [Name Your Workflow]

## Objective
Describe what this workflow accomplishes in one or two sentences.

## Required Inputs
- `input_one` — description of what this is (e.g., a URL, a file path, a search term)
- `input_two` — description of what this is

## Steps

### Step 1: [Action Name]
- **Tool**: `tools/example_tool.py`
- **Command**: `python tools/example_tool.py --input "{{input_one}}"`
- **Output**: Describe what the script produces (e.g., saves to `.tmp/output.json`)

### Step 2: [Next Action]
- **Tool**: `tools/another_tool.py`
- **Command**: `python tools/another_tool.py --file ".tmp/output.json"`
- **Output**: Describe what this step produces

### Step 3: [Deliver Output]
- Describe where the final output goes (e.g., Google Sheet, local file, printed summary)

## Expected Output
Describe what success looks like. What file was created? What was posted? What was printed?

## Edge Cases & Known Issues

| Issue | Resolution |
|-------|-----------|
| Rate limit from API | Wait 60s and retry. Batch endpoint available — see `tools/example_tool.py` comments. |
| Empty result set | Log warning and exit cleanly. Check input formatting. |
| Auth failure | Re-run `python tools/auth_google.py` to refresh `token.json`. |

## Notes
- Any quirks, timing constraints, or undocumented behaviors discovered during use
- Update this section when you encounter and solve new issues
