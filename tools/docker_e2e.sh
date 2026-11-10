#!/usr/bin/env bash
# End to end inside the image (read-only root, no capabilities, no network): raw files are generated into a volume,
# dbt builds the warehouse (models, data tests, unit tests), every mart is checked against the independent calculation,
# the documentation page is written, a small benchmark is run, and the result files are checked. Needs Docker.
# Usage: tools/docker_e2e.sh [image]
set -euo pipefail
IMAGE="${1:-dbtwh}"
VOL="dbtwh-e2e-$$"
TMP="$(mktemp -d)"
trap 'docker volume rm -f "$VOL" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT

[ "$(docker run --rm --entrypoint id "$IMAGE" -u)" != 0 ]   # not root
docker volume create "$VOL" >/dev/null
docker run --rm --user 0 -v "$VOL":/data --entrypoint chown "$IMAGE" 10001 /data

RUN=(docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --network none -v "$VOL":/data "$IMAGE")
cat_file() { docker run --rm --entrypoint cat -v "$VOL":/data "$IMAGE" "$1" > "$2"; }

out="$("${RUN[@]}" generate --orders 3000 --seed 1 --out /data/raw)"
grep -q 'written: 5 parquet files and manifest.json in /data/raw' <<<"$out"
cat_file /data/raw/manifest.json "$TMP/manifest.json"
grep -q '"orders": 3000' "$TMP/manifest.json"

out="$("${RUN[@]}" build --raw /data/raw --db /data/wh.duckdb --workdir /data/work --threads 2 --quiet --docs)"
grep -q '^dbt build: 12 models, 49 data tests, 5 unit tests: 66 passed, 0 failed' <<<"$out"
grep -q 'static_index.html' <<<"$out"
cat_file /data/work/target/static_index.html "$TMP/docs.html"
grep -q 'mart_cohort_retention' "$TMP/docs.html"

out="$("${RUN[@]}" verify --raw /data/raw --db /data/wh.duckdb)"
grep -q '^31 of 31 checks match the independent calculation' <<<"$out"

"${RUN[@]}" bench --sizes 500,1000 --repeat 1 --threads 2 --out /data/bench >/dev/null
cat_file /data/bench/bench.json "$TMP/bench.json"
cat_file /data/bench/bench.md "$TMP/bench.md"
grep -q '"verified": true' "$TMP/bench.json"
"${RUN[@]}" render /data/bench/bench.json -o /data/bench/again.md >/dev/null
cat_file /data/bench/again.md "$TMP/again.md"
cmp "$TMP/again.md" "$TMP/bench.md"                               # the report is rebuilt exactly from the JSON
cat_file /data/bench/summary.png "$TMP/summary.png"
[ "$(head -c 4 "$TMP/summary.png" | tail -c 3)" = "PNG" ]

set +e; "${RUN[@]}" verify --raw /data/nope --db /data/wh.duckdb >/dev/null 2>&1; rc=$?; set -e   # missing raw files: exit 2
[ "$rc" = 2 ]
echo "docker end-to-end: OK"
