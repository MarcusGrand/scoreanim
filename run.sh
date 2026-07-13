#!/bin/sh
# Launch ScoreAnim with the project venv.
#
#   ./run.sh                              open the app empty (File > Open…)
#   ./run.sh testdata/testscore.musicxml  open with a score
#   ./run.sh path/to/project.scoreanim    (projects: open the app, then
#                                          File > Open Project…)
cd "$(dirname "$0")" || exit 1
PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "run.sh: no .venv found — create it and 'pip install -e .'" >&2
    exit 1
fi
exec "$PY" -m scoreanim "$@"
