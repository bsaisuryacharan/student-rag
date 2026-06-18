#!/usr/bin/env bash
# Start N Celery workers for parallel document processing.
# Each worker is a separate process with its own fastembed/ONNX instance —
# no GIL or CPU-thread contention between workers.
#
# Usage:
#   ./start_workers.sh          # start 4 workers (default)
#   ./start_workers.sh 2        # start 2 workers
#   ./start_workers.sh stop     # stop all running workers

set -e
WORKERS=${1:-4}
VENV="$(dirname "$0")/.venv"
APP_DIR="$(dirname "$0")"
LOG_DIR="/tmp/celery-logs"
PID_DIR="/tmp/celery-pids"
BROKER_DIR="/tmp/celery-broker"

mkdir -p "$LOG_DIR" "$PID_DIR" "$BROKER_DIR" /tmp/celery-results

if [[ "$1" == "stop" ]]; then
    echo "Stopping all workers..."
    for pid_file in "$PID_DIR"/worker*.pid; do
        [[ -f "$pid_file" ]] || continue
        pid=$(cat "$pid_file")
        worker=$(basename "$pid_file" .pid)
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" && echo "  Stopped $worker (PID $pid)"
        fi
        rm -f "$pid_file"
    done
    echo "Done."
    exit 0
fi

# Kill any leftover workers from a previous run
pkill -f "celery.*worker.*notebook_rag" 2>/dev/null && echo "Cleared old workers" || true
sleep 1

echo "Starting $WORKERS Celery worker(s)..."
echo "  Broker  : filesystem:///tmp/celery-broker"
echo "  Logs    : $LOG_DIR/worker-N.log"
echo ""

source "$VENV/bin/activate"

for i in $(seq 1 "$WORKERS"); do
    HOSTNAME="worker${i}@%h"
    LOG="$LOG_DIR/worker-${i}.log"
    PID="$PID_DIR/worker-${i}.pid"

    celery -A app.worker.celery_app worker \
        --loglevel=info \
        --concurrency=1 \
        --hostname="$HOSTNAME" \
        --pidfile="$PID" \
        --logfile="$LOG" \
        --detach

    echo "  worker-${i} started → $LOG"
done

echo ""
echo "All $WORKERS workers running. To stop: ./start_workers.sh stop"
echo "To tail logs: tail -f $LOG_DIR/worker-*.log"
echo ""

# Wait a moment then confirm all workers are alive
sleep 3
source "$VENV/bin/activate"
cd "$APP_DIR"
echo "Live workers:"
celery -A app.worker.celery_app inspect ping 2>/dev/null \
    | grep -E "worker[0-9]+@|pong" | sed 's/^/  /' || echo "  (ping failed — workers may still be loading)"
