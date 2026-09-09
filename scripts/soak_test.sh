#!/bin/bash
set -euo pipefail

# M6 Soak Test
# Requisitos: 7 dias contínuos (ou smoke test), verificação de duplicidades, check de pause/degraded.

MODE="${1:-}"
if [[ "$MODE" == "--smoke" ]]; then
    DURATION_SECONDS=10
    echo "Running in SMOKE mode for 10 seconds."
elif [[ "$MODE" == "--duration" && "${2:-}" == "7d" ]]; then
    DURATION_SECONDS=$((7 * 24 * 3600))
    echo "Running in FULL SOAK mode for 7 days."
elif [[ "$MODE" == "--simulated-failure" ]]; then
    DURATION_SECONDS=5
    echo "Running in SIMULATED FAILURE mode."
else
    echo "Usage: $0 --smoke | --duration 7d | --simulated-failure"
    exit 1
fi

API_URL="http://127.0.0.1:8000"
ARTIFACTS_DIR=".artifacts"
mkdir -p "$ARTIFACTS_DIR"
REPORT_FILE="$ARTIFACTS_DIR/soak_report_$(date +%s).log"

log() {
    local msg
    msg="[$(date -u +'%Y-%m-%dT%H:%M:%SZ')] $1"
    echo "$msg" | tee -a "$REPORT_FILE"
}

get_health() {
    curl -s --max-time 5 "$API_URL/health" || echo "HTTP_FAIL"
}

get_portfolio() {
    curl -s --max-time 5 "$API_URL/api/v1/paper/portfolio" || echo "HTTP_FAIL"
}

pause_system() {
    local status
    status=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_URL/api/v1/paper/pause" \
        -H "X-Paper-Control: stop" --max-time 5)
    if [[ "$status" != "200" ]]; then
        log "CRITICAL: Pause endpoint returned $status"
        return 1
    fi
    return 0
}

log "Starting soak test. Duration: $DURATION_SECONDS seconds."
START_TIME=$(date +%s)
END_TIME=$((START_TIME + DURATION_SECONDS))

# Check initial health
HEALTH=$(get_health)
if [[ "$HEALTH" == "HTTP_FAIL" || "$HEALTH" != *"\"status\":\"ok\""* ]]; then
    log "CRITICAL: Initial health check failed or degraded: $HEALTH"
    exit 1
fi

if [[ "$MODE" == "--simulated-failure" ]]; then
    log "Simulating a health failure..."
    HEALTH="HTTP_FAIL"
    if [[ "$HEALTH" == "HTTP_FAIL" || "$HEALTH" != *"\"status\":\"ok\""* ]]; then
        log "CRITICAL: Simulated health check failed as expected."
        exit 1
    fi
fi

# Pause the system at start to test PAUSED condition
pause_system || exit 1

PORTFOLIO_INITIAL=$(get_portfolio)
if [[ "$PORTFOLIO_INITIAL" == "HTTP_FAIL" ]]; then
    log "CRITICAL: Initial portfolio fetch failed."
    exit 1
fi

ORDERS_INITIAL=$(echo "$PORTFOLIO_INITIAL" | grep -o '"orders_count":[0-9]*' | cut -d':' -f2 || echo "0")
FILLS_INITIAL=$(echo "$PORTFOLIO_INITIAL" | grep -o '"fills_count":[0-9]*' | cut -d':' -f2 || echo "0")
log "Initial Orders: $ORDERS_INITIAL, Fills: $FILLS_INITIAL"

# Main Loop
while [[ $(date +%s) -lt $END_TIME ]]; do
    sleep 2
    
    HEALTH=$(get_health)
    if [[ "$HEALTH" == "HTTP_FAIL" || "$HEALTH" != *"\"status\":\"ok\""* ]]; then
        log "CRITICAL: Health check failed mid-soak: $HEALTH"
        exit 1
    fi
    
    PORTFOLIO_CURRENT=$(get_portfolio)
    if [[ "$PORTFOLIO_CURRENT" == "HTTP_FAIL" ]]; then
        log "CRITICAL: Portfolio fetch failed mid-soak."
        exit 1
    fi
    
    ORDERS_CURRENT=$(echo "$PORTFOLIO_CURRENT" | grep -o '"orders_count":[0-9]*' | cut -d':' -f2 || echo "0")
    FILLS_CURRENT=$(echo "$PORTFOLIO_CURRENT" | grep -o '"fills_count":[0-9]*' | cut -d':' -f2 || echo "0")
    
    if [[ "$ORDERS_CURRENT" -gt "$ORDERS_INITIAL" || "$FILLS_CURRENT" -gt "$FILLS_INITIAL" ]]; then
        log "CRITICAL: Operations recorded while PAUSED/DEGRADED!"
        log "Initial: O=$ORDERS_INITIAL F=$FILLS_INITIAL, Current: O=$ORDERS_CURRENT F=$FILLS_CURRENT"
        exit 1
    fi
done

log "Soak test completed successfully."
log "Total time elapsed: $(( $(date +%s) - START_TIME )) seconds."
log "Orders remained stable at $ORDERS_INITIAL."

if [[ "$MODE" == "--duration" && "${2:-}" == "7d" ]]; then
    log "7-DAY SOAK TEST PASSED."
    exit 0
else
    log "SMOKE TEST PASSED (Not a 7-day soak)."
    exit 0
fi
