# TreeMaker - Workspace Tree Analyzer

A CLI tool that analyzes Python projects and generates a hierarchical tree of function calls.

## Features

- 📊 **Function Call Tree** - Visualizes which functions call which in a tree format
- 🔄 **Multi-Caller Detection** - Marks functions called from multiple places with `[*]`
- ⚠️ **Unused Function Detection** - Lists functions that are never called
- 🚫 **GitIgnore Support** - Respects `.gitignore` patterns
- 📁 **File Grouping** - Groups results by file for easy navigation

## Requirements

- Python 3.7+
- A `.gitignore` file must exist in the target project root (mandatory)[**can be left empty**]

## ⚠️ CAUTION
- ```.gitignore``` is **recommended** especially if the workspace have ```./build or android or node_modules``` or similar folders which will be Larger in depth.

## Installation

```bash
git clone https://github.com/karthikvvk/WorspaceTreeMaker.git
cp treemaker.py <ur_workspace_path> #Copy treemaker.py to the root of ur workspace
python treemaker.py
```

## Usage

```bash
python treemaker.py #this takes "./"as Base dir
```


## Output Format

```
================================================================================
PYTHON PROJECT FUNCTION CALL TREE
================================================================================

Project: /path/to/project
Files analyzed: 5
Functions found: 23

--------------------------------------------------------------------------------
FILES ANALYZED:
--------------------------------------------------------------------------------
  • main.py
  • utils/helpers.py
  • services/api.py

--------------------------------------------------------------------------------
LEGEND:
--------------------------------------------------------------------------------
  [*] = This function is also called from other places
  └── = Calls to other functions

================================================================================
FUNCTION CALL TREE (Entry Points)
================================================================================

main (main.py:15)
└── initialize (main.py:20)
    └── setup_logging [*] (utils/helpers.py:10)
    └── load_config (utils/helpers.py:25)
        └── parse_yaml (utils/helpers.py:40)

run_server (main.py:45)
└── setup_logging [*] (utils/helpers.py:10)
    └── ... (already shown above)
└── handle_request (services/api.py:12)

================================================================================
UNUSED FUNCTIONS
================================================================================
(Functions that are never called by any other analyzed function)
--------------------------------------------------------------------------------

📁 utils/helpers.py
   ⚠️  deprecated_function (line 100)
   ⚠️  old_parser (line 150)

================================================================================
```

## How It Works

1. **Parsing**: Uses Python's `ast` module to parse all `.py` files
2. **Filtering**: Respects `.gitignore` patterns to skip irrelevant files
3. **Analysis**: 
   - Extracts all function definitions (including class methods)
   - Tracks which functions call which
   - Identifies entry points (functions not called by others)
   - Detects multi-caller functions
4. **Output**: Renders a clean tree structure in the terminal

## Legend

| Symbol | Meaning |
|--------|---------|
| `[*]` | Function is called from multiple places |
| `└──` | Child call (function calls this) |
| `├──` | Sibling call (more calls follow) |
| `... (already shown above)` | Subtree already printed, avoiding duplication |
| `⚠️` | Unused function warning |

## Limitations

- Only analyzes Python files (`.py`)
- Dynamic function calls (via `getattr`, etc.) may not be detected
- External library calls are not tracked
- Decorator-based calls may not be fully resolved
