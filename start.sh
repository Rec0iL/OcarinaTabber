#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ ! -f "$VENV/bin/activate" ]; then
    echo "Error: virtual environment not found at $VENV" >&2
    echo "Create it with:  python3 -m venv .venv && pip install -r requirements.txt" >&2
    exit 1
fi

source "$VENV/bin/activate"
exec python "$SCRIPT_DIR/main.py" "$@"
