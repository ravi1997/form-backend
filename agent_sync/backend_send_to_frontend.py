import redis
import json
from datetime import datetime

r = redis.Redis(host='192.168.1.50', port=6380, db=7, decode_responses=True)

frontend_msg = {
  "issue_id": "login-flow-debug",
  "from": "backend",
  "to": "frontend",
  "kind": "contract_update",
  "summary": "Confirmed backend shapes and EnvelopeInterceptor conflict",
  "details": {
    "routes": ["/form/api/v1/auth/login", "/form/api/v1/user/status"],
    "files_changed": [],
    "contract_notes": {
      "login": "Backend returns { 'success': true, 'data': { 'access_token': '...', 'refresh_token': '...', 'user': {...} } }",
      "user_status": "Backend returns { 'success': true, 'data': { 'user': {...} } }",
      "envelope_interceptor_issue": "If EnvelopeInterceptor unwraps 'data', the object returned to AuthRemoteSource is the inner data object itself. Thus AuthRemoteSource should access 'response.user' instead of 'response.data.user', and 'response.access_token' instead of 'response.data.access_token'."
    }
  },
  "next_action_requested": "Fix AuthRemoteSource to expect unwrapped data (response.user instead of response.data.user) or remove EnvelopeInterceptor. Then retest the full login and status flow.",
  "timestamp": datetime.utcnow().isoformat() + "Z"
}

r.lpush('agent:frontend:inbox', json.dumps(frontend_msg))

state = json.loads(r.get('agent:issue:login-flow-debug:state'))
state['status'] = 'active'
state['owner'] = 'frontend'
state['current_phase'] = 'analyze'
state['latest_backend_summary'] = 'Backend confirmed contract shape. Frontend EnvelopeInterceptor issue identified.'
state['next_action_for_frontend'] = 'Fix data unwrap mismatch and retest full flow'
state['next_action_for_backend'] = 'Wait for frontend test results'

r.set('agent:issue:login-flow-debug:state', json.dumps(state))

r.set('agent:backend:heartbeat', datetime.utcnow().isoformat() + "Z")

print("Message sent to frontend inbox.")
