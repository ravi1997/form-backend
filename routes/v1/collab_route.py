import time
import json
from flask import request
from flask_socketio import Namespace, emit, join_room, leave_room
from extensions import socketio
from logger.unified_logger import app_logger, error_logger
from flask_jwt_extended import decode_token

# Room structure: collab:<resource_type>:<resource_id>
# E.g., collab:form:form-123, collab:dashboard:dash-456
# Presence data stored in memory/Redis. Since we want resilient lease tracking, 
# we can store this in memory or Redis if client is configured.
# We'll use a simple in-memory cache/lease storage first, falling back to local memory.

class CollaborationNamespace(Namespace):
    def __init__(self, namespace=None):
        super().__init__(namespace)
        self.rooms_presence = {}  # room_id -> {sid -> {user_id, display_name, target, timestamp}}
        self.leases = {}          # room_id -> {target -> {user_id, display_name, timestamp}}

    def _get_user_info(self):
        """Helper to extract user information from authorization headers/cookies/query params"""
        try:
            # Check for token in query params or headers
            token = request.args.get('token')
            if not token:
                auth_header = request.headers.get('Authorization')
                if auth_header and auth_header.startswith('Bearer '):
                    token = auth_header.split(' ')[1]
            
            if token:
                decoded = decode_token(token)
                user_id = decoded.get("sub", "anonymous")
                # We can mock metadata or extract details from payload if needed
                username = decoded.get("username", "User")
                org_id = decoded.get("organization_id", "default")
                return user_id, username, org_id
        except Exception as e:
            app_logger.warning(f"Failed to authenticate socket user: {e}")
        
        # Return fallback values
        return request.sid, "Anonymous", "default"

    def on_connect(self):
        user_id, username, org_id = self._get_user_info()
        app_logger.info(f"Socket client connected: sid={request.sid}, user={username} ({user_id})")
        emit('authenticated', {'user_id': user_id, 'display_name': username})

    def on_disconnect(self):
        user_id, username, _ = self._get_user_info()
        app_logger.info(f"Socket client disconnected: sid={request.sid}, user={username}")
        # Clean up presence in all rooms this client joined
        sid = request.sid
        rooms_to_notify = []
        for room_id, presence in list(self.rooms_presence.items()):
            if sid in presence:
                del presence[sid]
                rooms_to_notify.append(room_id)
                
                # Cleanup leases held by this user in this room
                if room_id in self.leases:
                    for target, lease in list(self.leases[room_id].items()):
                        if lease['user_id'] == user_id:
                            del self.leases[room_id][target]
                            # Broadcast release
                            emit('lease_released', {
                                'room_id': room_id,
                                'target': target,
                                'user_id': user_id
                            }, to=room_id)
        
        # Notify rooms of updated presence
        for room_id in rooms_to_notify:
            self._broadcast_presence(room_id)

    def _broadcast_presence(self, room_id):
        presence_list = list(self.rooms_presence.get(room_id, {}).values())
        # Deduplicate by user_id to keep the presence list clean on reconnects
        deduped = {}
        for p in presence_list:
            deduped[p['user_id']] = p
        emit('presence_update', {
            'room_id': room_id,
            'collaborators': list(deduped.values())
        }, to=room_id)

    def on_join(self, data):
        """
        Join collaboration room.
        Payload: {
            "resource_type": "form" | "dashboard",
            "resource_id": "..."
        }
        """
        resource_type = data.get("resource_type")
        resource_id = data.get("resource_id")
        if not resource_type or not resource_id:
            return emit('error', {'message': 'Missing resource_type or resource_id'})

        room_id = f"collab:{resource_type}:{resource_id}"
        join_room(room_id)
        
        user_id, username, _ = self._get_user_info()
        
        if room_id not in self.rooms_presence:
            self.rooms_presence[room_id] = {}
        
        self.rooms_presence[room_id][request.sid] = {
            'user_id': user_id,
            'display_name': username,
            'target': None,
            'timestamp': time.time()
        }

        app_logger.info(f"User {username} joined room {room_id}")
        self._broadcast_presence(room_id)
        
        # Send current leases in the room to the newly joined client
        emit('leases_sync', {
            'room_id': room_id,
            'leases': self.leases.get(room_id, {})
        })

    def on_leave(self, data):
        """
        Leave collaboration room.
        Payload: {
            "resource_type": "form" | "dashboard",
            "resource_id": "..."
        }
        """
        resource_type = data.get("resource_type")
        resource_id = data.get("resource_id")
        if not resource_type or not resource_id:
            return

        room_id = f"collab:{resource_type}:{resource_id}"
        leave_room(room_id)
        
        if room_id in self.rooms_presence and request.sid in self.rooms_presence[room_id]:
            del self.rooms_presence[room_id][request.sid]
            
        app_logger.info(f"User left room {room_id}")
        self._broadcast_presence(room_id)

    def on_lease_acquire(self, data):
        """
        Acquire a lock/lease on a specific target field/section.
        Payload: {
            "room_id": "...",
            "target": "..." # field ID or section ID
        }
        """
        room_id = data.get("room_id")
        target = data.get("target")
        if not room_id or not target:
            return emit('error', {'message': 'Missing room_id or target'})

        user_id, username, _ = self._get_user_info()
        now = time.time()

        # Enforce server-side authority: check if lease is already held by someone else
        if room_id not in self.leases:
            self.leases[room_id] = {}
        
        existing_lease = self.leases[room_id].get(target)
        # Expiry rule: leases expire after 30 seconds of inactivity
        if existing_lease and existing_lease['user_id'] != user_id and (now - existing_lease['timestamp'] < 30):
            # Collision prevention: reject and notify of collision
            emit('collision', {
                'room_id': room_id,
                'target': target,
                'held_by': existing_lease['display_name'],
                'user_id': existing_lease['user_id']
            })
            return

        # Grant lease
        self.leases[room_id][target] = {
            'user_id': user_id,
            'display_name': username,
            'timestamp': now
        }

        # Broadcast lease acquisition to room
        emit('lease_acquired', {
            'room_id': room_id,
            'target': target,
            'user_id': user_id,
            'display_name': username,
            'timestamp': now
        }, to=room_id)

    def on_lease_release(self, data):
        """
        Explicitly release a lock/lease.
        Payload: {
            "room_id": "...",
            "target": "..."
        }
        """
        room_id = data.get("room_id")
        target = data.get("target")
        if not room_id or not target:
            return

        user_id, _, _ = self._get_user_info()
        if room_id in self.leases and target in self.leases[room_id]:
            lease = self.leases[room_id][target]
            if lease['user_id'] == user_id:
                del self.leases[room_id][target]
                emit('lease_released', {
                    'room_id': room_id,
                    'target': target,
                    'user_id': user_id
                }, to=room_id)

    def on_cursor_move(self, data):
        """
        Broadcast cursor / active targeting details.
        Payload: {
            "room_id": "...",
            "target": "..."
        }
        """
        room_id = data.get("room_id")
        target = data.get("target")
        if not room_id:
            return

        user_id, username, _ = self._get_user_info()
        
        # Update presence target
        if room_id in self.rooms_presence and request.sid in self.rooms_presence[room_id]:
            self.rooms_presence[room_id][request.sid]['target'] = target
            self.rooms_presence[room_id][request.sid]['timestamp'] = time.time()
            
        emit('cursor_updated', {
            'room_id': room_id,
            'user_id': user_id,
            'display_name': username,
            'target': target
        }, to=room_id, include_self=False)

# Register namespace
socketio.on_namespace(CollaborationNamespace('/collab'))
