#!/bin/sh
cd -- "$(dirname -- "$0")/.." || exit 1

if [ ! -x .venv/bin/python ]; then
  echo "Set up the project's Python environment in .venv first. See README.md."
  exit 1
fi

if /usr/bin/curl --silent --fail --max-time 2 \
    --header 'X-Model-Studio: desktop' http://127.0.0.1:8766/model >/dev/null; then
  echo "ALMG's local backend is already running."
  exit 0
fi

exec .venv/bin/python backend/studio.py
