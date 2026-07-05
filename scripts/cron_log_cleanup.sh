#!/bin/bash
# Weekly log hygiene (Sunday 3:30 PM via setup_cron.sh):
# 1. gzip any plain .log over 100MB in place (truncate-copy so open fds keep writing)
# 2. gzip rotated .jsonl.N archives from src/core/logrotate.py
# 3. prune .gz archives older than 60 days
#
# Never touches the live .jsonl files themselves — those rotate at write time.

set -u
QUANT_RESULTS_DIR="${QUANT_RESULTS_DIR:-$HOME/quant_results}"
LOG_DIR="$QUANT_RESULTS_DIR/logs"
MAX_LOG_MB=100

echo "[log-cleanup] $(date '+%Y-%m-%d %H:%M') starting"

# 1. Oversized plain logs: archive content, truncate in place (cron >> keeps the fd)
find "$LOG_DIR" -maxdepth 1 -name '*.log' -size +"${MAX_LOG_MB}"M 2>/dev/null | while read -r f; do
    ts=$(date +%Y%m%d)
    gzip -c "$f" > "${f}.${ts}.gz" && : > "$f"
    echo "[log-cleanup] archived $(basename "$f") -> $(basename "$f").${ts}.gz"
done

# 2. Rotated jsonl archives from logrotate.py (file.jsonl.1 etc.)
find "$LOG_DIR" -maxdepth 1 -name '*.jsonl.[0-9]' 2>/dev/null | while read -r f; do
    gzip -f "$f"
    echo "[log-cleanup] gzipped $(basename "$f")"
done

# 3. Prune old archives
pruned=$(find "$LOG_DIR" -maxdepth 1 -name '*.gz' -mtime +60 -print -delete 2>/dev/null | wc -l)
echo "[log-cleanup] pruned $pruned archives older than 60d"
echo "[log-cleanup] done"
