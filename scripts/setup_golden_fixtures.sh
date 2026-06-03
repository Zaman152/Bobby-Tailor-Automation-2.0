#!/usr/bin/env bash
# scripts/setup_golden_fixtures.sh
# Copy golden PDF fixtures from uploads/ into tests/fixtures/.
# Exits 0 in all cases — missing source files are reported but are not an error.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPLOADS="$REPO_ROOT/uploads"

crow_src="$UPLOADS/Crow - Cass White Road-Plans.pdf"
crow_dst="$REPO_ROOT/tests/fixtures/crow_cass/crow_cass_plans.pdf"

bobs_src="$UPLOADS/Bob's Discount Furniture - Kennesaw, GA-plans.pdf"
bobs_dst="$REPO_ROOT/tests/fixtures/bobs_discount/bobs_discount_plans.pdf"

copied=0
skipped=0

copy_fixture() {
    local src="$1" dst="$2" label="$3"
    if [ -f "$src" ]; then
        mkdir -p "$(dirname "$dst")"
        cp "$src" "$dst"
        echo "[OK]     $label → $(basename "$dst")"
        ((copied++)) || true
    else
        echo "[SKIP]   $label — source not found at: $src"
        ((skipped++)) || true
    fi
}

echo "Bobby Tailor — Golden Fixture Setup"
echo "===================================="
copy_fixture "$crow_src" "$crow_dst" "Crow Cass"
copy_fixture "$bobs_src" "$bobs_dst" "Bob's Discount"
echo "------------------------------------"
echo "Done: $copied copied, $skipped skipped."

if [ "$copied" -gt 0 ]; then
    echo ""
    echo "Run golden tests with:"
    echo "  pytest tests/test_golden_takeoff.py -v -m golden"
fi
