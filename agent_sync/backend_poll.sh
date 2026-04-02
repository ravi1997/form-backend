#!/bin/bash
echo "Polling backend inbox..."
docker exec shared-redis-6380 redis-cli -n 7 RPOP agent:backend:inbox
docker exec shared-redis-6380 redis-cli -n 7 SET agent:backend:heartbeat "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
