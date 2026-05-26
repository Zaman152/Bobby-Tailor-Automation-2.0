# Phase 3: API Cost Transparency - Research

**Researched:** 2026-05-26
**Domain:** API usage tracking and cost calculation
**Confidence:** HIGH

## Summary

Phase 3 adds API cost transparency to the Bobby Tailor take-off automation system. The Anthropic Python SDK provides token usage metadata in every API response via `response.usage` attributes. The standard approach is to capture per-sheet token counts during Claude vision analysis, aggregate them at the run level, calculate USD costs using current pricing tables, and surface the data in three places: JSON output (`api_usage` block in `takeoff.json`), plain-text summary (`summary.txt`), and web UI report cards.

The existing codebase already follows a clear pattern: `claude_analyzer.py` → `reporter.py` → outputs. This phase extends that flow by adding usage metadata to the extraction dictionaries returned by `analyze_drawing()`, then aggregating in `generate_report()`. No new libraries are needed—everything required is already in the Anthropic SDK (v0.104.1 installed, >=0.28.0 required). The pricing table is hardcoded as a lookup dictionary since rates change infrequently and are publicly documented.

The Master.md Feature 2.1 specification provides prescriptive implementation guidance that the planner should follow exactly: capture usage in `claude_analyzer.py`, aggregate in `reporter.py`, add `api_usage` block to JSON, display in summary.txt, and surface in UI.

**Primary recommendation:** Follow Master.md Feature 2.1 specification exactly—capture `response.usage` attributes in `claude_analyzer.py`, add them to extraction dictionaries with `_tokens_in`, `_tokens_out`, `_cost_usd`, `_model_used` keys, aggregate in `reporter.py` via sum() over all extractions, add `api_usage` block to JSON report, append cost line to `summary.txt`, and display per-run cost in web UI report cards.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| anthropic | >=0.28.0 (0.104.1 installed) | Claude API client with built-in usage tracking | Official SDK from Anthropic; `response.usage` object provides authoritative token counts |
| Python standard library | 3.x | JSON, dict operations, arithmetic | No external deps needed for aggregation and cost math |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| None required | - | - | Token tracking is native to the SDK |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hardcoded pricing table | Live API calls to usage endpoint | Usage API is for historical analysis, not per-request pricing; hardcoded table is faster and sufficient |
| Manual token counting | `client.messages.count_tokens()` | Count Tokens API is for pre-flight estimation; `response.usage` is authoritative for actual consumption |

**Installation:**
```bash
# Already installed in requirements.txt
anthropic>=0.28.0
```

## Architecture Patterns

### Recommended Project Structure
```
claude_analyzer.py    # Add usage capture after API call
reporter.py           # Add aggregation in generate_report()
templates/index.html  # Display cost in report cards
```

### Pattern 1: Per-Sheet Usage Capture
**What:** Each `analyze_drawing()` call captures `response.usage` and adds to extraction dict
**When to use:** After every `client.messages.create()` call that returns a response
**Example:**
```python
# Source: Master.md Feature 2.1 + Anthropic API docs
response = client.messages.create(
    model=model,
    max_tokens=8000,
    system=[{"type": "text", "text": EXTRACTION_PROMPT, "cache_control": {"type": "ephemeral"}}],
    messages=[...]
)

# Capture usage (available in all SDK versions >=0.28.0)
usage = response.usage

# Pricing table (as of May 2026)
PRICING = {
    "claude-haiku-4-5":  {"in": 1.0, "out": 5.0},    # per 1M tokens
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-opus-4-7":   {"in": 5.0, "out": 25.0},
}
p = PRICING.get(model, {"in": 3.0, "out": 15.0})  # default to Sonnet

# Calculate cost
input_tokens = usage.input_tokens
output_tokens = usage.output_tokens
cost_usd = (input_tokens * p["in"] + output_tokens * p["out"]) / 1_000_000

# Add to extraction dict
extracted["_tokens_in"] = input_tokens
extracted["_tokens_out"] = output_tokens
extracted["_cost_usd"] = round(cost_usd, 6)
extracted["_model_used"] = model
```

### Pattern 2: Run-Level Aggregation
**What:** Sum token counts and costs across all sheets in a run
**When to use:** In `reporter.py` `generate_report()` function after processing all sheets
**Example:**
```python
# Source: Master.md Feature 2.1
def generate_report(project_name: str, all_extracted: list, all_estimates: list = None) -> dict:
    # ... existing code ...
    
    # Aggregate API usage
    total_cost = sum(d.get("_cost_usd", 0) for d in all_extracted)
    total_tokens_in = sum(d.get("_tokens_in", 0) for d in all_extracted)
    total_tokens_out = sum(d.get("_tokens_out", 0) for d in all_extracted)
    
    report["api_usage"] = {
        "total_cost_usd": round(total_cost, 4),
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
    }
    
    # ... rest of report generation ...
```

### Pattern 3: Cache-Aware Cost Calculation (Optional Enhancement)
**What:** Track cache reads separately when using prompt caching
**When to use:** If analyzing cache efficiency (not required for Phase 3 MVP)
**Example:**
```python
# Cache tokens are optional attributes
cache_creation = getattr(usage, "cache_creation_input_tokens", 0)
cache_read = getattr(usage, "cache_read_input_tokens", 0)

# Cache reads cost 10% of base input rate (0.1x multiplier)
# Cache writes cost 1.25x (5-min TTL) or 2x (1-hour TTL) of base input
# For simplicity, Phase 3 can treat all input tokens at base rate
```

### Anti-Patterns to Avoid
- **Don't call Usage API per-request:** The `/v1/usage/messages` endpoint is for historical analysis, not real-time per-request tracking. Use `response.usage` instead.
- **Don't trust training data pricing:** Pricing changes every 6-12 months. Verify current rates from official docs before hardcoding the table.
- **Don't ignore optional cache fields:** Use `getattr(usage, "field", 0)` to avoid AttributeError when cache tokens are present.
- **Don't calculate cost before checking model:** Different models have different rates; always look up the model in the pricing table first.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token counting | Custom tokenizer | `response.usage` from API | API returns authoritative actual usage; custom counting is estimation-only |
| Pricing lookups | Scraping pricing page | Hardcoded lookup dict with references | Rates change infrequently; dict is faster and testable |
| USD formatting | String concatenation | `round(cost, 4)` + f-string | Consistent precision prevents floating-point display issues |
| Cache detection | Parsing model config | `getattr(usage, "cache_read_input_tokens", 0)` | SDK provides optional fields; no need to infer |

**Key insight:** The Anthropic SDK already provides everything needed. Don't add external dependencies for token counting, cost APIs, or pricing lookups—the SDK returns exact usage, and pricing is a static table.

## Common Pitfalls

### Pitfall 1: Missing Optional Cache Fields
**What goes wrong:** Code crashes with `AttributeError` when `usage.cache_read_input_tokens` isn't present
**Why it happens:** Cache tokens are only present when prompt caching is used; standard requests omit these fields
**How to avoid:** Always use `getattr(usage, "field_name", 0)` for optional fields
**Warning signs:** Code works on first test but crashes on subsequent runs (caching kicks in)

### Pitfall 2: Stale Pricing Table
**What goes wrong:** Cost estimates are incorrect because pricing changed and table wasn't updated
**Why it happens:** Anthropic adjusts pricing every 6-12 months; hardcoded tables go stale
**How to avoid:** Add comments with pricing source URL and "Last verified: YYYY-MM-DD"; check pricing page quarterly
**Warning signs:** User reports costs don't match their Anthropic invoice

### Pitfall 3: Integer Division Instead of Float
**What goes wrong:** Cost calculation returns 0 because `(tokens * rate) / 1_000_000` uses integer division
**Why it happens:** Python 2 habits carry over; forgetting that rates are per-million
**How to avoid:** Always use float rates (1.0 not 1) in pricing dict; verify with small token counts
**Warning signs:** All costs show as $0.0000

### Pitfall 4: Forgetting Model Fallback
**What goes wrong:** Code crashes with `KeyError` when model name doesn't match pricing table
**Why it happens:** Model names have versioning (claude-sonnet-4-6 vs claude-sonnet-4-5); new models aren't in old tables
**How to avoid:** Always use `PRICING.get(model, default_dict)` with sensible default
**Warning signs:** Code works on test data but fails on production with new model

### Pitfall 5: Aggregating Before All Sheets Complete
**What goes wrong:** Partial run costs are reported; final cost is missing later sheets
**Why it happens:** Aggregation happens in a loop instead of after all sheets finish
**How to avoid:** Aggregate in `reporter.py` after `scraper.py` completes all sheets
**Warning signs:** Progress bar shows 10/10 sheets but cost only reflects 7 sheets

## Code Examples

Verified patterns from official sources:

### Capturing Usage in Claude Analyzer
```python
# Source: Anthropic SDK docs + Master.md Feature 2.1
# File: claude_analyzer.py

def analyze_drawing(screenshot_path: str, sheet_name: str = "") -> dict:
    """Send drawing screenshot to Claude for vision analysis. Returns structured extraction data."""
    logger.info(f"Analyzing drawing: {sheet_name or screenshot_path}")

    try:
        image_data, media_type = encode_image(screenshot_path)
        model = _pick_model(sheet_name)
        
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            system=[{
                "type": "text",
                "text": EXTRACTION_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                    {"type": "text", "text": f"Sheet name: {sheet_name}\n\nAnalyze this drawing and return the JSON."}
                ],
            }],
        )

        # Capture usage (PHASE 3 ADDITION)
        usage = response.usage
        
        # Pricing table (as of May 2026 - verify at https://docs.anthropic.com/en/api/pricing)
        PRICING = {
            "claude-haiku-4-5":   {"in": 1.0,  "out": 5.0},
            "claude-sonnet-4-6":  {"in": 3.0,  "out": 15.0},
            "claude-opus-4-7":    {"in": 5.0,  "out": 25.0},
        }
        p = PRICING.get(model, {"in": 3.0, "out": 15.0})
        
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cost_usd = (input_tokens * p["in"] + output_tokens * p["out"]) / 1_000_000

        # Parse JSON response
        raw_text = response.content[0].text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        
        extracted = json.loads(raw_text)
        
        # Add usage metadata (PHASE 3 ADDITION)
        extracted["_tokens_in"] = input_tokens
        extracted["_tokens_out"] = output_tokens
        extracted["_cost_usd"] = round(cost_usd, 6)
        extracted["_model_used"] = model
        
        # Existing fields
        extracted["_source_sheet"] = sheet_name
        extracted["_screenshot"] = screenshot_path
        
        logger.info(f"  Extracted {len(extracted.get('measurements', []))} measurements, "
                    f"{len(extracted.get('components', []))} components "
                    f"[{input_tokens} in / {output_tokens} out tokens, ${cost_usd:.6f}]")
        return extracted

    except json.JSONDecodeError as e:
        logger.error(f"Claude returned invalid JSON: {e}")
        return {"error": "invalid_json", "raw": raw_text, "_source_sheet": sheet_name}
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        return {"error": str(e), "_source_sheet": sheet_name}
```

### Aggregating in Reporter
```python
# Source: Master.md Feature 2.1
# File: reporter.py

def generate_report(project_name: str, all_extracted: list, all_estimates: list = None) -> dict:
    """Build the final takeoff report."""
    all_estimates = all_estimates or []
    output_root = Path(OUTPUT_DIR)
    output_root.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = project_name.replace(" ", "_").replace("/", "-")
    run_dir = output_root / f"{safe}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    # Flatten raw extractions
    raw_line_items = _flatten_raw_extractions(all_extracted)
    calculated_items = _normalize_calculated(all_estimates)

    # Aggregate API usage (PHASE 3 ADDITION)
    total_cost = sum(d.get("_cost_usd", 0) for d in all_extracted)
    total_tokens_in = sum(d.get("_tokens_in", 0) for d in all_extracted)
    total_tokens_out = sum(d.get("_tokens_out", 0) for d in all_extracted)

    report = {
        "project_name": project_name,
        "generated_at": datetime.now().isoformat(),
        "sheets_processed": len(all_extracted),
        "total_line_items": len(raw_line_items),
        "total_calculated_items": len(calculated_items),
        "api_usage": {  # PHASE 3 ADDITION
            "total_cost_usd": round(total_cost, 4),
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "cost_per_sheet": round(total_cost / max(len(all_extracted), 1), 4),
        },
        "calculated_takeoff": calculated_items,
        "raw_line_items": raw_line_items,
        "by_sheet": _group_by_sheet(raw_line_items + calculated_items),
        "by_category": _group_by_category(raw_line_items),
        "by_table": _group_by_table(calculated_items),
        "sheet_log": [
            {
                "sheet": d.get("_source_sheet"),
                "page_id": d.get("_page_id"),
                "type": d.get("sheet_type"),
                "title": d.get("sheet_title"),
                "scale": d.get("scale"),
                "measurements": len(d.get("measurements", [])),
                "components": len(d.get("components", [])),
                "rooms": len(d.get("rooms", [])),
                "materials": len(d.get("materials", [])),
                "schedules": len(d.get("schedules", [])),
                "confidence": d.get("confidence"),
                "notes": d.get("notes"),
                "tokens_in": d.get("_tokens_in", 0),    # PHASE 3 ADDITION
                "tokens_out": d.get("_tokens_out", 0),  # PHASE 3 ADDITION
                "cost_usd": d.get("_cost_usd", 0),      # PHASE 3 ADDITION
            }
            for d in all_extracted
        ],
    }

    # Write files
    json_path = run_dir / "takeoff.json"
    csv_raw = run_dir / "raw_items.csv"
    csv_calc = run_dir / "calculations.csv"
    txt_path = run_dir / "summary.txt"

    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    # ... CSV writing ...

    try:
        _write_summary(report, txt_path)
    except Exception as e:
        logger.error(f"Failed to write summary text: {e}")

    logger.info(f"Saved run to: {run_dir} "
                f"[Total cost: ${total_cost:.4f}, "
                f"{total_tokens_in + total_tokens_out:,} tokens]")
    report["_files"] = {
        "run_folder": str(run_dir),
        "json": str(json_path),
        "raw_csv": str(csv_raw),
        "calculated_csv": str(csv_calc),
        "summary_txt": str(txt_path),
    }
    report["_run_folder_name"] = run_dir.name
    return report
```

### Adding to Summary Text
```python
# Source: Master.md Feature 2.1
# File: reporter.py

def _write_summary(report: dict, path: Path):
    lines = [
        "═" * 70,
        "QUANTITY TAKEOFF SUMMARY",
        "═" * 70,
        f"Project:          {report['project_name']}",
        f"Generated:        {report['generated_at']}",
        f"Sheets analyzed:  {report['sheets_processed']}",
        f"Raw items:        {report['total_line_items']}",
        f"Calculated items: {report['total_calculated_items']}",
        "",
        "─" * 70,
        "API USAGE & COST",  # PHASE 3 ADDITION
        "─" * 70,
    ]
    
    # Add cost breakdown (PHASE 3 ADDITION)
    usage = report.get("api_usage", {})
    lines.append(f"Total cost:       ${usage.get('total_cost_usd', 0):.4f} USD")
    lines.append(f"Input tokens:     {usage.get('total_tokens_in', 0):,}")
    lines.append(f"Output tokens:    {usage.get('total_tokens_out', 0):,}")
    lines.append(f"Cost per sheet:   ${usage.get('cost_per_sheet', 0):.4f} USD")
    lines.append("")
    
    lines += [
        "─" * 70,
        "SHEET-BY-SHEET LOG (source traceability)",
        "─" * 70,
    ]
    
    # ... rest of summary ...
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual cost tracking in spreadsheets | `response.usage` built into SDK | Anthropic SDK v0.3.0 (2023) | Usage data is authoritative; no estimation needed |
| Fetching pricing via API | Hardcoded lookup table | Always (no pricing API exists) | Faster, testable, no runtime dependencies |
| Per-token pricing display | Per-run aggregate | Best practice (2024+) | Users care about total run cost, not per-call |
| Cache-unaware cost | Cache-aware cost calculation | Prompt caching launch (2024) | Can show 90% savings when caching is effective |

**Deprecated/outdated:**
- **Token counting libraries:** `tiktoken` and similar are for estimation only; SDK provides actual usage
- **Scraping pricing from docs:** No need—pricing is stable enough for hardcoded tables with version control

## Open Questions

Things that couldn't be fully resolved:

1. **UI Report Card Display Format**
   - What we know: Flask web UI exists, shows report list, downloads available
   - What's unclear: Exact HTML structure for cost display in report cards not specified in Master.md
   - Recommendation: Add cost as inline text in report metadata line (e.g., "10 sheets • $0.12 • 2 min ago")

2. **Cache Efficiency Metrics**
   - What we know: Prompt caching is enabled (`cache_control: ephemeral`), SDK reports cache reads
   - What's unclear: Whether Phase 3 should display cache efficiency (% cached reads) or just total cost
   - Recommendation: Phase 3 MVP shows total cost only; cache efficiency is a Phase 4+ enhancement

3. **Cost Alerts/Thresholds**
   - What we know: API usage is tracked per-run
   - What's unclear: Should the system warn if a run exceeds a cost threshold (e.g., $1.00)?
   - Recommendation: No alerting in Phase 3; just display actual cost; add thresholds in Phase 5+ if needed

## Sources

### Primary (HIGH confidence)
- Anthropic Python SDK documentation - https://github.com/anthropics/anthropic-sdk-python (usage object structure)
- Anthropic API Messages endpoint - https://docs.anthropic.com/en/api/messages (response.usage fields)
- Anthropic Pricing Page - https://docs.anthropic.com/en/api/pricing (verified May 2026 rates)
- Master.md Feature 2.1 specification - Project's authoritative implementation guide
- Codebase inspection - `claude_analyzer.py`, `reporter.py`, `scraper.py`, `templates/index.html`

### Secondary (MEDIUM confidence)
- CloudZero Claude Pricing Guide 2026 - https://www.cloudzero.com/blog/claude-api-pricing/ (pricing verification)
- Anthropic Cookbook usage tracking - https://github.com/anthropics/anthropic-cookbook (usage patterns)

### Tertiary (LOW confidence)
- None - all findings verified with primary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Anthropic SDK provides native usage tracking, no external deps
- Architecture: HIGH - Master.md Feature 2.1 provides prescriptive implementation steps
- Pitfalls: HIGH - Common pitfalls verified via SDK documentation and code inspection
- Pricing: HIGH - Multiple sources agree on May 2026 rates, verified on official Anthropic pricing page
- UI integration: MEDIUM - Report card structure inferred from HTML inspection, exact format needs planner decision

**Research date:** 2026-05-26
**Valid until:** 2026-08-26 (90 days - pricing stable, SDK structure stable)
**Next verification needed:** Check pricing page quarterly (pricing changes every 6-12 months)
