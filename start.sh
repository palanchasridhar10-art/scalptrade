#!/usr/bin/env bash
set -e

# Detect available python binary
if command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
elif command -v python &>/dev/null; then
    PYTHON_CMD=python
elif [ -f "/opt/render/project/src/.venv/bin/python" ]; then
    PYTHON_CMD=/opt/render/project/src/.venv/bin/python
else
    echo "Error: Python executable not found!"
    exit 1
fi

echo "Starting Autonomous Crypto Scalper with $PYTHON_CMD..."
exec $PYTHON_CMD main.py --mode ${TRADING_MODE:-PAPER} --serve --host 0.0.0.0 --port ${PORT:-8000}
