#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"

version_check='import sys; sys.exit(sys.version_info[:2] not in ((3, 12), (3, 13)))'

if [[ ! -x .venv/bin/python ]]; then
    python_cmd=
    for candidate in "${PYTHON_BIN:-${PYTHON312:-python3.13}}" python3.13 python3.12 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -c "$version_check"; then
            python_cmd=$candidate
            break
        fi
    done
    if [[ -z "$python_cmd" ]]; then
        echo "Установите Python 3.13 или 3.12 по инструкции README.md и снова запустите bash setup.sh."
        exit 1
    fi
    # Some Python 3.13 builds need the real executable path to locate their standard library.
    python_executable=$("$python_cmd" -c 'import os, sys; print(os.path.realpath(sys.executable))')
    "$python_executable" -m venv .venv
fi
if ! .venv/bin/python -c "$version_check"; then
    echo "Для .venv нужен Python 3.13 или 3.12. Переименуйте папку .venv и повторите установку."
    exit 1
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.setup
