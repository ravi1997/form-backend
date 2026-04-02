#!/bin/bash
for i in {1..20}
do
    msg=$(docker exec shared-redis-6380 redis-cli -h 192.168.1.50 -p 6380 -n 7 RPOP agent:backend:inbox)
    if [ ! -z "$msg" ]; then
        echo "$msg"
        exit 0
    fi
    sleep 3
done
echo "No message received after 60 seconds."
exit 1
