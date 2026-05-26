# Phase 5: Report Preview APIs - Research

**Researched:** 2026-05-26
**Domain:** Flask API file serving, CSV pagination, path security
**Confidence:** HIGH

## Summary

This phase adds in-browser preview capabilities for take-off report files, allowing users to inspect outputs without downloading. The codebase already has a download endpoint at `/api/reports/<run_folder>/<filename>` with basic `../` rejection. Phase 5 adds a parallel preview endpoint that returns file contents as structured JSON for frontend rendering.

Research focused on:
1. **Path traversal prevention** — Beyond simple `../` checks, validate resolved paths stay within OUTPUT_DIR
2. **CSV pagination patterns** — Return row counts and capped data for large files
3. **Content-type routing** — Different response shapes for `.csv`, `.json`, `.txt`
4. **Frontend rendering** — What JSON structure the UI needs for sortable tables, collapsible trees, styled text

**Current state assessment:**
- `app.py` line 262-271: download endpoint exists with `if "/" in run_folder or ".." in run_folder` check ✓
- `config.py` line 41: `OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")` ✓
- `reporter.py` generates 4 files per run: `takeoff.json`, `raw_items.csv`, `calculations.csv`, `summary.txt` ✓
- Phase 1 established Flask error handler patterns (reuse for 400/404 responses)
- Master.md Step 3 (line 1238-1262) provides reference implementation

**Primary recommendation:** Implement a single `/api/reports/<run_folder>/preview/<filename>` endpoint that returns type-appropriate JSON. Use `pathlib.Path.resolve()` for robust path validation. Cap CSV rows at 500 with metadata showing total count.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Flask | >=3.0.0 | Web framework | Already in use; `jsonify()` for JSON responses |
| pathlib (stdlib) | 3.10+ | Path manipulation | `.resolve()` handles symlink/traversal attacks |
| csv (stdlib) | 3.10+ | CSV parsing | DictReader for header-based access |
| json (stdlib) | 3.10+ | JSON parsing | Already used throughout codebase |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| markupsafe | >=2.0.0 | Text escaping | **Already installed** (Flask dependency) — escape user text if rendering as HTML |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib csv | pandas | Overkill for simple row reading; adds 50MB dependency |
| Manual path checks | secure-filename from werkzeug | `secure_filename` is for uploads, not reads; manual validation is clearer here |
| Server-side pagination | Frontend virtual scroll | Frontend complexity; server pagination is simpler for MVP |

**Installation:**

No new dependencies required — all tools already present.

## Architecture Patterns

### Recommended Endpoint Structure

```
app.py
├── /api/reports/<run_folder>/<filename>          # Existing download
└── /api/reports/<run_folder>/preview/<filename>  # NEW preview endpoint
    ├── .csv → {"type": "csv", "rows": [...], "count": N, "capped": bool}
    ├── .json → {"type": "json", "data": {...}}
    └── .txt → {"type": "text", "content": "..."}
```

### Pattern 1: Robust Path Validation

**What:** Use `Path.resolve()` to canonicalize paths, then verify the result is under OUTPUT_DIR.

**Why:** Simple string checks (`../` in input) can be bypassed with URL encoding, symlinks, or edge cases. Resolve-then-verify is defense in depth.

**Example:**

```python
# Source: OWASP Path Traversal Prevention + Python pathlib docs
from pathlib import Path

def validate_preview_path(run_folder: str, filename: str) -> Path | None:
    """Return resolved file path if valid, None if path traversal detected."""
    output_root = Path(OUTPUT_DIR).resolve()
    
    # Reject obvious traversal attempts early (defense in depth)
    if ".." in run_folder or ".." in filename:
        return None
    if "/" in run_folder or "/" in filename:
        return None
    
    # Construct and resolve the full path
    target = (output_root / run_folder / filename).resolve()
    
    # Verify resolved path is still under output root
    try:
        target.relative_to(output_root)
    except ValueError:
        # Path escaped output directory
        return None
    
    if not target.is_file():
        return None
    
    return target
```

**Key insight:** `Path.relative_to()` raises `ValueError` if the path is not relative to the base — this catches symlink escapes and encoded traversal.

### Pattern 2: CSV Pagination with Row Cap

**What:** Read CSV rows up to a limit, return total count for UI pagination.

**Example:**

```python
# Source: Flask CSV API patterns + Master.md Step 3
import csv

MAX_PREVIEW_ROWS = 500

def preview_csv(path: Path) -> dict:
    """Return CSV rows with pagination metadata."""
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = []
        for i, row in enumerate(reader):
            if i < MAX_PREVIEW_ROWS:
                rows.append(row)
            # Keep counting even after cap
        total_count = i + 1 if 'i' in dir() else 0
    
    return {
        "type": "csv",
        "headers": list(rows[0].keys()) if rows else [],
        "rows": rows,
        "count": len(rows),
        "total": total_count,
        "capped": total_count > MAX_PREVIEW_ROWS,
        "cap_limit": MAX_PREVIEW_ROWS
    }
```

**Frontend expectation:** When `capped: true`, show "Showing {count} of {total} rows" message.

### Pattern 3: Content-Type Routing

**What:** Single endpoint that returns different JSON shapes based on file extension.

**Example:**

```python
@app.route("/api/reports/<run_folder>/preview/<filename>")
def preview_report(run_folder: str, filename: str):
    """Preview file content for in-browser rendering."""
    path = validate_preview_path(run_folder, filename)
    if path is None:
        return jsonify({"error": "Invalid path"}), 400
    
    if filename.endswith(".csv"):
        return jsonify(preview_csv(path))
    elif filename.endswith(".json"):
        return jsonify({
            "type": "json",
            "data": json.loads(path.read_text(encoding='utf-8'))
        })
    elif filename.endswith(".txt"):
        return jsonify({
            "type": "text",
            "content": path.read_text(encoding='utf-8')
        })
    else:
        return jsonify({"error": "Unsupported format for preview"}), 400
```

### Anti-Patterns to Avoid

- **String concatenation for paths:** Use `Path /` operator instead of `os.path.join` with strings
- **Trusting only input validation:** Always verify resolved paths, not just input strings
- **Loading entire files into memory:** Cap CSV rows; use streaming for very large JSON (not needed for takeoff.json which is typically <1MB)
- **Returning raw file content for HTML display:** Summary text should be escaped if rendered as HTML to prevent XSS

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Path traversal detection | Regex on input | `Path.resolve()` + `relative_to()` | Handles URL encoding, symlinks, OS-specific quirks |
| CSV parsing | Split on comma | `csv.DictReader` | Handles quoted fields, escaping, newlines in values |
| JSON parsing | Manual string processing | `json.loads()` | Handles all JSON edge cases |
| Error responses | Custom JSON shapes | Flask `jsonify()` + error handlers | Consistent with Phase 1 patterns |

**Key insight:** Path security is tricky — use `resolve()` to let the OS normalize the path, then verify it's where you expect.

## Common Pitfalls

### Pitfall 1: Incomplete Path Validation

**What goes wrong:** Checking only for `../` in the input string allows other traversal vectors like URL-encoded `%2e%2e%2f`, double-encoding, or symlinks.

**Why it happens:** Simple string checks look sufficient during local testing.

**How to avoid:**
1. Use `Path.resolve()` to get the canonical absolute path
2. Use `relative_to()` to verify containment
3. Keep the simple string checks as defense in depth (fast-fail obvious attacks)

**Warning signs:**
- Security tests with encoded paths succeed
- Symlinks in output directory cause unexpected behavior

### Pitfall 2: CSV Memory Exhaustion

**What goes wrong:** Loading a 100MB CSV into memory crashes the server or causes OOM kills.

**Why it happens:** `list(csv.DictReader(f))` loads everything eagerly.

**How to avoid:**
1. Iterate with a counter and break after MAX_ROWS
2. Still count total rows for accurate "showing N of M" message
3. Consider streaming for very large files (not needed for typical takeoff CSVs)

**Warning signs:**
- Preview endpoint times out on large reports
- Server memory spikes when previewing CSVs

### Pitfall 3: Encoding Errors

**What goes wrong:** Files with non-UTF-8 characters cause `UnicodeDecodeError`.

**Why it happens:** CSV/text files may have been written with different encodings or contain binary data.

**How to avoid:**
1. Explicitly specify `encoding='utf-8'` in `open()` calls
2. Use `errors='replace'` or `errors='ignore'` as fallback
3. reporter.py already writes UTF-8, so this is mainly for safety

**Warning signs:**
- Preview fails on specific reports with `UnicodeDecodeError`
- Garbled characters in preview output

### Pitfall 4: Exposing File System Errors

**What goes wrong:** `FileNotFoundError` or `PermissionError` messages reveal server paths to users.

**Why it happens:** Not wrapping file operations in try/except.

**How to avoid:**
1. Catch file errors and return generic 404/500
2. Log full errors server-side (Phase 1 pattern)
3. Flask global error handlers catch unhandled exceptions

**Warning signs:**
- API responses contain `/var/app/output/...` paths
- Error messages mention OS-level errors

## Code Examples

### Complete Preview Endpoint (Reference Implementation)

```python
# Source: Master.md Step 3 + security hardening
# Location: app.py

import csv
import json
from pathlib import Path
from flask import jsonify
from config import OUTPUT_DIR

MAX_PREVIEW_ROWS = 500
ALLOWED_PREVIEW_EXTENSIONS = {'.csv', '.json', '.txt'}

def _validate_preview_path(run_folder: str, filename: str) -> Path | None:
    """Validate and resolve preview file path.
    
    Returns resolved Path if valid, None if path traversal or invalid.
    """
    # Fast-fail obvious traversal attempts
    if ".." in run_folder or ".." in filename:
        return None
    if "/" in run_folder or "/" in filename:
        return None
    
    # Check extension is previewable
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_PREVIEW_EXTENSIONS:
        return None
    
    # Resolve and validate containment
    output_root = Path(OUTPUT_DIR).resolve()
    target = (output_root / run_folder / filename).resolve()
    
    try:
        target.relative_to(output_root)
    except ValueError:
        return None  # Escaped output directory
    
    if not target.is_file():
        return None
    
    return target


def _preview_csv(path: Path) -> dict:
    """Read CSV with row cap and count."""
    total = 0
    rows = []
    headers = []
    
    with open(path, newline='', encoding='utf-8', errors='replace') as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        for row in reader:
            total += 1
            if len(rows) < MAX_PREVIEW_ROWS:
                rows.append(row)
    
    return {
        "type": "csv",
        "headers": headers,
        "rows": rows,
        "count": len(rows),
        "total": total,
        "capped": total > MAX_PREVIEW_ROWS,
        "cap_limit": MAX_PREVIEW_ROWS
    }


@app.route("/api/reports/<run_folder>/preview/<filename>")
def preview_report(run_folder: str, filename: str):
    """Preview report file content for in-browser rendering.
    
    Supports:
    - .csv → {"type": "csv", "headers": [...], "rows": [...], "total": N}
    - .json → {"type": "json", "data": {...}}
    - .txt → {"type": "text", "content": "..."}
    """
    path = _validate_preview_path(run_folder, filename)
    if path is None:
        return jsonify({"error": "Invalid path or file not found"}), 400
    
    ext = path.suffix.lower()
    
    try:
        if ext == '.csv':
            return jsonify(_preview_csv(path))
        elif ext == '.json':
            data = json.loads(path.read_text(encoding='utf-8'))
            return jsonify({"type": "json", "data": data})
        elif ext == '.txt':
            content = path.read_text(encoding='utf-8', errors='replace')
            return jsonify({"type": "text", "content": content})
        else:
            return jsonify({"error": "Unsupported format"}), 400
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON file"}), 400
    except Exception:
        # Let global error handler log and sanitize
        raise
```

### CSV Row Counting Without Full Load

```python
# More memory-efficient counting for very large files
def count_csv_rows(path: Path) -> int:
    """Count total rows without loading all data."""
    with open(path, newline='', encoding='utf-8') as f:
        return sum(1 for _ in csv.reader(f)) - 1  # -1 for header
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `os.path.join` + string checks | `pathlib.Path` + `resolve()` | Python 3.4+ | Safer path handling, cleaner code |
| Load all CSV rows | Iterator with cap | Always best practice | Prevents memory issues |
| Return raw file bytes | Return structured JSON | API best practice | Enables rich frontend rendering |
| Manual content-type headers | Flask `jsonify()` auto-sets | Flask convention | Consistent JSON responses |

**Deprecated/outdated:**
- Using `os.path` functions over `pathlib` (less readable, no operator overloading)
- Trusting user input for file paths (always validate server-side)

## Open Questions

None — all requirements for this phase have well-established patterns in the Flask ecosystem.

## Files Requiring Changes

Based on codebase analysis:

1. **`app.py`** — Add `/api/reports/<run_folder>/preview/<filename>` endpoint with path validation and content-type routing
2. **`config.py`** — Optionally add `MAX_PREVIEW_ROWS` configuration (can also be hardcoded in app.py)

No changes needed to `reporter.py` — it already generates the files we need to preview.

## Testing Approach

### Unit Testing

1. **Path validation tests:**
   - Valid path returns resolved Path
   - `../` in folder returns None
   - `../` in filename returns None
   - Non-existent file returns None
   - Symlink escape returns None

2. **CSV pagination tests:**
   - Small CSV returns all rows with `capped: false`
   - Large CSV returns MAX_PREVIEW_ROWS with `capped: true`, correct `total`
   - Empty CSV returns empty rows with count 0

### Integration Testing

1. **Endpoint response shapes:**
   - `.csv` returns `{"type": "csv", "headers": [...], "rows": [...], ...}`
   - `.json` returns `{"type": "json", "data": {...}}`
   - `.txt` returns `{"type": "text", "content": "..."}`

2. **Security scenarios:**
   - `GET /api/reports/../../../etc/passwd/preview/file` returns 400
   - URL-encoded traversal attempts return 400
   - Non-existent run folder returns 400

### Manual Testing

1. **Production simulation:**
   - Create a run with large CSV (>500 rows)
   - Verify preview shows "Showing 500 of N rows"
   - Verify JSON tree renders collapsible structure
   - Verify text content displays correctly

## Sources

### Primary (HIGH confidence)

- Python pathlib documentation — Path.resolve(), relative_to()
  https://docs.python.org/3/library/pathlib.html
- OWASP Path Traversal Prevention Cheat Sheet
  https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
- Flask jsonify() documentation
  https://flask.palletsprojects.com/en/3.0.x/api/#flask.json.jsonify
- Master.md Step 3 (line 1238-1262) — Reference implementation

### Secondary (MEDIUM confidence)

- CSV module documentation — DictReader behavior
  https://docs.python.org/3/library/csv.html

### Tertiary (LOW confidence)

None — all findings verified with official documentation

## Metadata

**Confidence breakdown:**
- Path validation patterns: **HIGH** — stdlib + OWASP recommendations
- CSV pagination: **HIGH** — stdlib csv module, straightforward
- API design: **HIGH** — Master.md provides reference implementation
- Security: **HIGH** — Standard path traversal prevention patterns

**Research date:** 2026-05-26
**Valid until:** ~2026-08-26 (90 days — Flask patterns are stable)
