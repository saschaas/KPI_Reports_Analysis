# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Tool

```bash
# Basic usage - analyze all files in input directory
python src/main.py

# Analyze specific file
python src/main.py --file "input/report.pdf"

# List available report types
python src/main.py --list-types

# Test LLM connection (requires Ollama running)
python src/main.py --test-llm

# Clear file cache
python src/main.py --clear-cache
```

## Development Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Ollama setup (required for LLM features)
ollama serve  # Start Ollama service
ollama pull llama3.2  # Download model
```

## Architecture Overview

### Hybrid Analysis Pipeline

The tool uses a **dual-path analysis approach**:

1. **Primary: Algorithmic Analysis**
   - Fast, deterministic processing
   - Report-specific analyzer classes (e.g., `VeeamBackupAnalyzer`)
   - Registered in `ReportAnalyzer.analyzers` dict
   - Falls back to generic checks if no specific analyzer exists

2. **Fallback: LLM Analysis**
   - Activates when algorithmic analysis fails
   - Ollama-based with configurable prompts
   - Flexible for handling format changes

### Report-Specific Analyzers

When adding support for a new report type that requires custom logic:

1. **Create analyzer class** in `src/analyzers/` inheriting from `BaseAnalyzer`
2. **Implement required methods**:
   - `run_checks(df)` - return list of `CheckResult` objects
   - `extract_fields(df)` - return dict of extracted metrics
3. **Register in ReportAnalyzer**: Add to `self.analyzers` dict in `src/core/report_analyzer.py`

Example:
```python
class VeeamBackupAnalyzer(BaseAnalyzer):
    def run_checks(self, data: pd.DataFrame) -> List[CheckResult]:
        # Implement checks
        pass

    def extract_fields(self, data: pd.DataFrame) -> Dict[str, Any]:
        # Extract metrics
        pass
```

### Intelligent PDF Table Parsing

The `PDFParser` includes **automatic header detection** (`_detect_header_row`) that:
- Analyzes first 10 rows using multiple heuristics
- Scores based on: non-empty cells, non-numeric content, header keywords, text length
- Handles PDFs where header is not in row 0 (common in real-world reports)
- **Critical**: This makes parsing resilient to varying PDF structures

### Flexible Date Format Detection

For reports with varying date formats (see `VeeamBackupAnalyzer._detect_date_format`):

**Problem**: Date format can vary (`yyyy-mm-dd` vs `yyyy-dd-mm`, etc.) and must be auto-detected

**Solution**: Analyze ALL date values to detect format:
1. Extract components from each date value
2. Find position with all identical values (likely the month in monthly reports)
3. Check for values >12 (must be days)
4. Determine correct format programmatically

**Key insight**: Don't assume format from first value - analyze the entire dataset for patterns.

### Configuration-Driven Report Types

All report type logic is defined in YAML files under `config/report_types/`:

```yaml
report_type:
  id: "veeam_backup"

identification:
  filename_patterns: [".*veeam.*backup.*\\.pdf$"]
  content_identifiers:
    required_columns: ["vm name", "status"]

  fuzzy_matching:
    enabled: true
    threshold: 0.85
    field_mappings:
      vm_name:
        alternatives: ["vm name", "vmname", "virtual machine"]

analysis:
  algorithmic_checks:
    - check_id: "completeness"
      type: "column_validation"

  scoring:
    base_score: 100
    deductions:
      - condition: "failed_backups > 0"
        points: 10
```

**Fuzzy matching**: Uses string normalization (trim, lowercase, unicode, diacritics removal) + similarity threshold to handle column name variations across reports.

## Key Design Patterns

### 3-Stage Report Detection

Located in `src/core/report_detector.py`:

1. **Stage 1**: Filename regex matching (fastest)
2. **Stage 2**: Content analysis (column names + keywords scoring)
3. **Stage 3**: LLM classification (flexible but slower)
4. **Stage 4**: Manual user selection (interactive fallback)

Each stage can definitively identify or pass to next stage.

### Parser System

All parsers inherit from `BaseParser` and must implement:
- `parse(file_path)` - return pandas DataFrame
- `extract_text(file_path)` - return text for LLM
- `get_metadata(file_path)` - return file metadata

Parsers are registered in `ReportAnalyzer.parsers` dict by file extension.

### Scoring System

Implemented in `src/utils/scoring.py`:

- Base score: 100
- Deductions configured per report type
- Can be per-occurrence or one-time
- Risk levels: niedrig (86-100), mittel (61-85), hoch (0-60)
- Status: ok, mit_einschraenkungen, fehler, nicht_erfolgreich_analysiert

## Critical Implementation Details

### Windows Console Encoding

Located in `src/main.py`:
```python
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
```
Required for emoji/unicode support on Windows terminals.

### Path Management

Tool uses `sys.path.insert(0, str(Path(__file__).parent))` to enable direct module imports from `src/`. This allows imports like `from utils import ...` instead of relative imports.

### Ollama Model Response Structure

The `OllamaHandler._test_connection()` handles various response formats from `client.list()`:
- Checks for `.model` attribute on objects
- Falls back to dict access with 'name' or 'model' keys
- Critical for compatibility across Ollama versions

## Common Modifications

### Adding a New Check Type

1. Add check config to report YAML:
```yaml
algorithmic_checks:
  - check_id: "my_check"
    type: "my_new_type"
    parameters:
      foo: "bar"
```

2. Implement handler in `ReportAnalyzer._run_algorithmic_checks()`:
```python
elif check_type == 'my_new_type':
    result = self._check_my_new_type(df, parameters)
```

3. Add check method:
```python
def _check_my_new_type(self, df, parameters):
    # Implement logic
    return CheckResult(...)
```

### Adding Report-Specific Logic

If a report type needs custom analysis beyond configuration:

1. Create `src/analyzers/my_report_analyzer.py`
2. Inherit from `BaseAnalyzer` (initializes with config, includes `scorer`)
3. Register in `ReportAnalyzer.__init__()`: `self.analyzers['my_report'] = MyReportAnalyzer`

The analyzer will be automatically used when `report_type` matches the key.

## File Organization

- `src/core/` - Main analysis pipeline
- `src/parsers/` - File format handlers
- `src/analyzers/` - Report-specific analysis logic
- `src/utils/` - Shared utilities (config, logging, scoring)
- `config/report_types/` - Report type definitions (YAML)
- `input/` - Drop files here for analysis
- `output/YYYY-MM/` - Results organized by month
- `logs/` - Daily log files
