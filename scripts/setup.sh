#!/bin/sh
set -eu
cd /workspace/MyPro2
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --no-audit --no-fund
npm run build
