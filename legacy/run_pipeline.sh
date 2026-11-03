#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

NAME="${1:-Classroom of the Elite}"
ARC="${2:-Year 1}"
SLUG=$(python3 -c "
import sys; sys.path.insert(0, '.')
from src.shared.naming import slugify
print(slugify(sys.argv[1], sys.argv[2]))
" "$NAME" "$ARC")

echo "############################################################"
echo "# PIPELINE: $NAME / $ARC  (slug: $SLUG)"
echo "############################################################"

echo
echo "=== stage 1: cast (python) ==="
echo "=== roster+groups are pushed to DCS for review, NOT written to Postgres"
echo "=== directly anymore — open DCS and approve before the confirmed data lands ==="
docker compose run --rm analyse_service \
    conda run --no-capture-output -n analyse_service python -m src.services.collection.cast.main "$NAME" "$ARC"
docker compose run --rm --entrypoint "" analyse_service \
    chown 1000:1000 "/app/run/stage1_cast_${SLUG}.json" >/dev/null

echo
echo "=== stage 3: relations (python) — runs before stage 2 now, so stage 2 ==="
echo "=== can skip flag/ordinal collection for 0-relation, non-isolate chars. ==="
echo "=== The relation graph is pushed to DCS for review the same way stage 1's ==="
echo "=== roster+groups are — Postgres only gets it once approved there. ==="
docker compose run --rm analyse_service \
    conda run --no-capture-output -n analyse_service python -m src.services.collection.relations.main "$NAME" "$ARC"
docker compose run --rm --entrypoint "" analyse_service \
    chown 1000:1000 "/app/run/relations_passes_${SLUG}.json" "/app/run/relations_merged_${SLUG}.json" >/dev/null

echo
echo "=== stage 2 ==="
./run_stage2.sh "$NAME" "$ARC"

echo
echo "############################################################"
echo "# DONE: $SLUG"
echo "############################################################"
echo "run/stage1_cast_${SLUG}.json"
echo "run/stage2_features_${SLUG}.json  run/pass{1,2,3}_${SLUG}.csv  run/kappa_verdicts_${SLUG}.csv"
echo "run/relations_passes_${SLUG}.json  run/relations_merged_${SLUG}.json"
