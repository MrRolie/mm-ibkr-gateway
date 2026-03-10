#!/bin/bash
cd "$(dirname "$0")/.."

echo "=== Container Status ==="
docker compose ps

echo -e "\n=== IB Gateway Ports ==="
nc -z localhost 4001 2>/dev/null && echo "Live port 4001: OPEN" || echo "Live port 4001: CLOSED"
nc -z localhost 4002 2>/dev/null && echo "Paper port 4002: OPEN" || echo "Paper port 4002: CLOSED"

echo -e "\n=== API Health ==="
curl -s http://localhost:8000/health 2>/dev/null | python3 -m json.tool 2>/dev/null || echo "API not responding"

echo -e "\n=== Recent IB Gateway Logs ==="
docker compose logs --tail=10 ib-gateway 2>/dev/null || true