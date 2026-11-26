#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
python_cmd=
for candidate in "${PYTHON312:-python3.12}" python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 &&
        "$candidate" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then
        python_cmd=$candidate
        break
    fi
done
if [[ -z "$python_cmd" ]]; then
    echo "Установите Python 3.12 по инструкции README.md, затем снова запустите bash setup.sh."
    exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
    "$python_cmd" -m venv .venv
fi
if ! .venv/bin/python -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then
    echo "Окружение .venv использует другую версию Python. Переименуйте его и повторите установку."
    exit 1
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m app.setup
