#!/bin/zsh
set -e
cd "${0:A:h}"
export PYTHONPATH="$PWD/.auth-deps${PYTHONPATH:+:$PYTHONPATH}"
exec /Users/kuroshhashemi/Documents/fantasy-bot/.venv/bin/streamlit run concert_discovery/shortlist_app.py --server.port 8503 --server.headless true
