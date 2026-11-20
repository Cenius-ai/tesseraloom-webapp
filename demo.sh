#!/bin/sh
# TesseraLoom end-to-end demo: layout, count and cut list over the bundled
# fixtures. Non-interactive, offline, safe to re-run.
# Usage: sh demo.sh
set -u
cd "$(dirname "$0")" || exit 1

PY="${PYTHON:-python3}"
TOOL="$PY tesseraloom.py"
OUT_DIR="./.tesseraloom-demo"

say() { printf '%s\n' "$*"; }
step() { printf '\n$ %s\n' "$*"; }

cleanup() { rm -rf "$OUT_DIR"; }
trap cleanup EXIT INT TERM
mkdir -p "$OUT_DIR" || exit 1

say "== TesseraLoom demo ================================================="
say "bundled design: sample_grid.txt (8 rows x 12 columns)"

step "$TOOL layout sample_grid.txt --legend legend.txt"
"$PY" tesseraloom.py layout sample_grid.txt --legend legend.txt || exit 1

step "$TOOL count sample_grid.txt"
"$PY" tesseraloom.py count sample_grid.txt || exit 1

step "$TOOL cutlist sample_grid.txt --legend legend.txt"
"$PY" tesseraloom.py cutlist sample_grid.txt --legend legend.txt || exit 1

step "$TOOL cutlist sample_grid.txt --format csv"
"$PY" tesseraloom.py cutlist sample_grid.txt --format csv || exit 1

step "$TOOL cutlist sample_grid.txt --format csv --out $OUT_DIR/cutlist.csv"
"$PY" tesseraloom.py cutlist sample_grid.txt --format csv --out "$OUT_DIR/cutlist.csv" || exit 1
say "file written, stdout stayed empty. contents:"
cat "$OUT_DIR/cutlist.csv" || exit 1

say ""
say "-- piping a design in on stdin -------------------------------------"
step "cat sample_grid.txt | $TOOL count - --legend legend.txt"
cat sample_grid.txt | "$PY" tesseraloom.py count - --legend legend.txt || exit 1

say ""
say "-- a design using codes the legend does not define -----------------"
step "$TOOL layout examples/design_garden.txt --legend legend.txt"
"$PY" tesseraloom.py layout examples/design_garden.txt --legend legend.txt || exit 1
say "(the two warning lines above are on stderr; the exit code stays 0)"

say ""
say "-- one-line errors, exit code 1 ------------------------------------"
step "$TOOL layout examples/grid_ragged.txt"
"$PY" tesseraloom.py layout examples/grid_ragged.txt
say "exit code: $?"

step "$TOOL layout nope.txt"
"$PY" tesseraloom.py layout nope.txt
say "exit code: $?"

say ""
say "-- usage errors, exit code 2 ---------------------------------------"
step "$TOOL cutlist sample_grid.txt --format xml"
"$PY" tesseraloom.py cutlist sample_grid.txt --format xml
say "exit code: $?"

say ""
say "== demo complete ==================================================="
exit 0
