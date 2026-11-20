#!/usr/bin/env bash
# TesseraLoom install: project-level dependencies only, then exit.
# Runs as an unprivileged user; installs no system packages and never starts a
# server (TesseraLoom is a command-line tool that exits on its own).
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON:-python3}"

echo "== TesseraLoom install =="
"$PYTHON_BIN" -V

# 1. Toolchain (best effort: the tool itself needs nothing but the stdlib).
if ! "$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel; then
    echo "note: could not upgrade pip/setuptools/wheel (offline?); using the installed versions" >&2
fi

# 2. Project-level install of the `tesseraloom` console script.
if ! "$PYTHON_BIN" -m pip install -e . --no-build-isolation; then
    echo "note: retrying the editable install with build isolation" >&2
    if ! "$PYTHON_BIN" -m pip install -e .; then
        echo "warning: could not install the 'tesseraloom' console script;" >&2
        echo "         the tool still runs as: python3 tesseraloom.py" >&2
    fi
fi

# 3. Test runner for the shipped suite (dev only).
if ! "$PYTHON_BIN" -m pip install -r requirements-dev.txt; then
    echo "warning: could not install the test runner; 'python3 -m pytest' may be unavailable" >&2
fi

# 4. Self check: a stale/incomplete environment must fail here, not at boot.
"$PYTHON_BIN" -c "import tesseraloom; print('import ok, version', tesseraloom.VERSION)"
"$PYTHON_BIN" tesseraloom.py --version
"$PYTHON_BIN" tesseraloom.py count sample_grid.txt >/dev/null

echo
echo "Setup complete."
echo "  Try:  python3 tesseraloom.py --help"
echo "  Demo: bash demo.sh"
echo "  Tests: python3 -m pytest"
