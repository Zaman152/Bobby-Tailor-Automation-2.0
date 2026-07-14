"""Durable cross-run learning package (Phase 21, V3-LEARN-01..04).

Modules:
    store     — SQLite learning store: append-only corrections log plus
                distilled vocabulary/assumptions/manifests tables.
    distill   — idempotent job rebuilding distilled tables from the log.

Human verifications recorded here survive run-folder deletion and are
retrieved on future runs (prompt hints, aggregation naming, calculator
assumptions). See 21-RESEARCH.md §6 for the normative schema and the
conflict/decay policy.
"""
