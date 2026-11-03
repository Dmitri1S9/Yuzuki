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

echo "=== stage 2: features (python) — $NAME / $ARC ==="
docker compose run --rm analyse_service \
    conda run --no-capture-output -n analyse_service python -m src.services.collection.features.main "$NAME" "$ARC"

echo
echo "=== stage 2: kappa validation (R) ==="
docker compose run --rm r_analysis Rscript kappa_analysis.R "$SLUG"

docker compose run --rm --entrypoint "" analyse_service \
    chown 1000:1000 "/app/run/stage2_features_${SLUG}.json" \
    "/app/run/pass1_${SLUG}.csv" "/app/run/pass2_${SLUG}.csv" "/app/run/pass3_${SLUG}.csv" >/dev/null
docker compose run --rm --entrypoint "" r_analysis \
    chown 1000:1000 "/app/run/kappa_verdicts_${SLUG}.csv" >/dev/null

echo
echo "done: run/stage2_features_${SLUG}.json, run/pass{1,2,3}_${SLUG}.csv, run/kappa_verdicts_${SLUG}.csv"
