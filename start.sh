#!/usr/bin/env bash
set -e

# Activate virtual environment if present
if [ -f "/opt/render/project/src/.venv/bin/activate" ]; then
    source "/opt/render/project/src/.venv/bin/activate"
elif [ -f ".venv/bin/activate" ]; then
    source ".venv/bin/activate"
elif [ -f "./.venv/bin/activate" ]; then
    source "./.venv/bin/activate"
fi

# Detect python binary
if [ -n "$VIRTUAL_ENV" ] && [ -f "$VIRTUAL_ENV/bin/python" ]; then
    PYTHON_CMD="$VIRTUAL_ENV/bin/python"
elif [ -f "/opt/render/project/src/.venv/bin/python" ]; then
    PYTHON_CMD="/opt/render/project/src/.venv/bin/python"
elif [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
elif command -v python &>/dev/null; then
    PYTHON_CMD=python
else
    echo "Error: Python executable not found!"
    exit 1
fi

echo "Using Python binary: $PYTHON_CMD"
echo "Starting Autonomous Crypto Scalper on port ${PORT:-8000}..."
exec $PYTHON_CMD main.py --mode ${TRADING_MODE:-PAPER} --serve --host 0.0.0.0 --port ${PORT:-8000}
