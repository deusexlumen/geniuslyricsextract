#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=""
if command -v python3 >/dev/null 2>&1; then
  if python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"; then
    PYTHON=python3
  fi
fi
if [[ -z "${PYTHON}" ]] && command -v python >/dev/null 2>&1; then
  if python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"; then
    PYTHON=python
  fi
fi

if [[ -z "${PYTHON}" ]]; then
  echo "Python 3.10 oder neuer wurde nicht gefunden. Bitte Python 3 installieren."
  exit 1
fi

if ! "${PYTHON}" -c "import requests, bs4" >/dev/null 2>&1; then
  echo "Abhängigkeiten werden eingerichtet..."
  "${PYTHON}" -m pip install -r requirements.txt
fi

exec "${PYTHON}" web2txt.py ui
