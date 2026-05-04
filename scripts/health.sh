#!/usr/bin/env bash
# Solboards single-shot health check. Run on the VM from the repo root:
#
#   ./scripts/health.sh
#
# Bundles every check from RUNBOOK.md "sanity sweep" into one pass:
# containers, HTTP, resources, recent errors, settler health, DB
# reconciliation, treasury balances, Privy reachability.
#
# Read-only — no on-chain txs, no DB mutations.

set -u

cd "$(dirname "$0")/.." || exit 1

COMPOSE=(docker compose -f docker-compose.prod.yml)
BACKEND=solboards-backend
CADDY=solboards-caddy
DOMAIN=${DOMAIN:-solboards.xyz}

section() { printf "\n========== %s ==========\n" "$1"; }
ok()      { printf "  [OK]   %s\n" "$1"; }
warn()    { printf "  [WARN] %s\n" "$1"; }
fail()    { printf "  [FAIL] %s\n" "$1"; }

# 1. Containers up + restart count
section "1. Containers"
"${COMPOSE[@]}" ps
for c in $BACKEND $CADDY; do
  state=$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo missing)
  restarts=$(docker inspect -f '{{.RestartCount}}' "$c" 2>/dev/null || echo "?")
  started=$(docker inspect -f '{{.State.StartedAt}}' "$c" 2>/dev/null || echo "?")
  if [ "$state" = "running" ] && [ "$restarts" = "0" ]; then
    ok "$c running, restarts=0, started=$started"
  elif [ "$state" = "running" ]; then
    warn "$c running but restarts=$restarts (check docker logs)"
  else
    fail "$c state=$state"
  fi
done

# 2. HTTP /health through Caddy
section "2. HTTP /health"
if body=$(curl -fsS --max-time 5 "https://$DOMAIN/health" 2>&1); then
  ok "$body"
else
  fail "https://$DOMAIN/health -> $body"
fi

# 3. Disk + container resource usage
section "3. Resources"
df -h / | awk 'NR==1 || NR==2 { print "  " $0 }'
data_size=$(du -sh backend/data 2>/dev/null | awk '{print $1}')
echo "  backend/data: $data_size"
docker stats --no-stream --format "  {{.Name}}: cpu={{.CPUPerc}} mem={{.MemUsage}} ({{.MemPerc}}) net={{.NetIO}}" $BACKEND $CADDY

# 4. Recent backend errors + settler ticks
section "4. Backend errors (last 1h)"
err_count=$(docker logs --since 1h $BACKEND 2>&1 | grep -ciE 'error|traceback|exception|already exists' || true)
bad_ticks=$(docker logs --since 1h $BACKEND 2>&1 | grep -cE 'failed=[1-9]|left_pending=[1-9]' || true)
total_ticks=$(docker logs --since 1h $BACKEND 2>&1 | grep -c 'batch settler tick' || true)
if [ "$err_count" = "0" ]; then
  ok "0 error/traceback/exception lines"
else
  warn "$err_count error-ish lines  (docker logs --since 1h $BACKEND | grep -iE 'error|traceback' )"
fi
if [ "$bad_ticks" = "0" ]; then
  ok "$total_ticks settler ticks, all clean (failed=0 left_pending=0)"
else
  fail "$bad_ticks of $total_ticks settler ticks had failures or left pending rows"
fi

# 5. Caddy errors (TLS / 5xx)
section "5. Caddy errors (last 1h)"
caddy_errs=$(docker logs --since 1h $CADDY 2>&1 | grep -ciE '"level":"error"|tls handshake|5[0-9]{2}' || true)
if [ "$caddy_errs" = "0" ]; then
  ok "0 caddy error/TLS/5xx lines"
else
  warn "$caddy_errs caddy error lines  (docker logs --since 1h $CADDY)"
fi

# 6. NEEDS_REVIEW (Privy dup-cycle parking lot)
section "6. Stuck settlements"
review_out=$(docker exec $BACKEND python scripts/triage_stuck.py list 2>&1)
echo "$review_out" | sed 's/^/  /'
if echo "$review_out" | grep -q "Nothing to triage"; then
  ok "NEEDS_REVIEW empty"
else
  warn "NEEDS_REVIEW rows present — triage with scripts/triage_stuck.py"
fi

# 7. Campaigns overview
section "7. Campaigns"
docker exec $BACKEND python scripts/list_campaigns.py --limit 20

# 8. Audit reconciliation (DB vs on-chain). Slow — makes RPC calls.
section "8. Ledger reconciliation (audit_ledger.py)"
audit_out=$(docker exec $BACKEND python scripts/audit_ledger.py 2>&1)
echo "$audit_out"
short=$(echo "$audit_out" | grep -c "SHORT" || true)
drift=$(echo "$audit_out" | grep -c "DRIFT" || true)
[ "$short" = "0" ] && ok "no SHORT publisher rows" || fail "$short SHORT publisher rows"
[ "$drift" = "0" ] && ok "no DRIFT campaign rows" || warn "$drift DRIFT campaign rows"

# 9. Privy reachability
section "9. Privy"
privy_out=$(docker exec $BACKEND python scripts/probe_privy.py 2>&1 | head -10)
echo "$privy_out" | sed 's/^/  /'
if echo "$privy_out" | grep -q "listed wallets"; then
  ok "Privy reachable"
else
  fail "Privy probe did not return wallet list"
fi

# 10. Solana RPC reachable through Caddy (validates the origin-strip fix)
section "10. Solana RPC proxy"
rpc_body=$(curl -fsS --max-time 5 -H 'content-type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"getHealth"}' \
  "https://$DOMAIN/solana-rpc" 2>&1 || true)
if echo "$rpc_body" | grep -q '"result":"ok"'; then
  ok "$rpc_body"
else
  fail "Solana RPC proxy: $rpc_body"
fi

echo
echo "========== Done =========="
