import redis
import json
from datetime import datetime

r = redis.Redis(host='127.0.0.1', port=6380, db=7, decode_responses=True)

state = {
  "issue_id": "login-flow-debug",
  "status": "active",
  "owner": "backend",
  "current_phase": "analyze",
  "frontend_status": "unknown",
  "backend_status": "working",
  "latest_frontend_summary": "",
  "latest_backend_summary": "",
  "current_blocker": "",
  "next_action_for_frontend": "Read bootstrap and respond",
  "next_action_for_backend": "Wait for frontend",
  "canonical_routes": {
    "login": "/form/api/v1/auth/login",
    "user_status": "/form/api/v1/user/status",
    "refresh": "/form/api/v1/auth/refresh",
    "logout": "/form/api/v1/auth/logout"
  },
  "auth_contract": {
    "login_response_shape": "",
    "status_response_shape": "",
    "auth_mechanism": ""
  },
  "last_updated_by": "backend",
  "last_updated_at": datetime.utcnow().isoformat()
}

r.set('agent:issue:login-flow-debug:state', json.dumps(state))

bootstrap_msg = {
  "issue_id": "login-flow-debug",
  "from": "backend",
  "to": "frontend",
  "kind": "bootstrap",
  "summary": "Redis is ready on port 6380",
  "details": {
    "redis_host": "0.0.0.0",
    "redis_port": 6380,
    "redis_db": 7
  },
  "next_action_requested": "Confirm connection and trigger initial retest of login flow",
  "timestamp": datetime.utcnow().isoformat()
}

r.lpush('agent:frontend:inbox', json.dumps(bootstrap_msg))
r.set('agent:backend:heartbeat', datetime.utcnow().isoformat())

print("Setup completed.")
