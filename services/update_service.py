"""
services/update_service.py
Platform update mechanism service.
"""

import os
import json
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from flask import current_app
from logger.unified_logger import app_logger, error_logger, audit_logger
from services.redis_service import redis_service

class UpdateService:
    """Service for managing platform updates and deployments."""
    
    def __init__(self):
        self.redis = redis_service().cache
        self.docker_client = None
        self._docker_init_attempted = False
        self.update_lock_key = "platform_update_lock"
        self.update_status_key = "platform_update_status"
        self.version_info_key = "platform_version_info"

    def _get_docker_client(self):
        """Return a Docker client when the host socket is available.

        The backend runs inside containers in development and production, and
        the Docker socket is not always mounted. Treat Docker as optional until
        an update operation explicitly needs it.
        """
        if self.docker_client is not None:
            return self.docker_client
        if self._docker_init_attempted:
            return None

        self._docker_init_attempted = True
        try:
            import docker

            self.docker_client = docker.from_env()
            return self.docker_client
        except Exception as e:
            error_logger.warning(f"Docker client unavailable: {e}")
            return None
    
    def get_current_version(self) -> Dict:
        """Get current platform version information."""
        try:
            # Try to get from cache first
            cached_version = self.redis.get(self.version_info_key)
            if cached_version:
                return json.loads(cached_version)
            
            # Get version from system config
            from models.oauth import SystemConfig
            version_config = SystemConfig.objects(key="platform_version").first()
            
            if not version_config:
                version_config = SystemConfig(
                    key="platform_version",
                    value="1.0.0",
                    updated_at=datetime.utcnow()
                )
                version_config.save()
            
            version_info = {
                "version": version_config.value,
                "last_updated": version_config.updated_at.isoformat(),
                "components": self._get_component_versions()
            }
            
            # Cache version info
            self.redis.setex(self.version_info_key, 3600, json.dumps(version_info))
            
            return version_info
            
        except Exception as e:
            error_logger.error(f"Error getting current version: {e}")
            return {"version": "unknown", "error": str(e)}
    
    def _get_component_versions(self) -> Dict:
        """Get versions of individual components."""
        components = {}
        
        try:
            docker_client = self._get_docker_client()
            if docker_client:
                # Get running containers
                containers = docker_client.containers.list()
                
                for container in containers:
                    if container.name.startswith(('backend', 'frontend', 'nginx', 'mongodb', 'redis')):
                        components[container.name] = {
                            "image": container.image.tags[0] if container.image.tags else "unknown",
                            "status": container.status,
                            "created": container.attrs['Created']
                        }
            
            # Get package versions from requirements.txt
            requirements_path = os.path.join(current_app.root_path, '..', 'requirements.txt')
            if os.path.exists(requirements_path):
                with open(requirements_path, 'r') as f:
                    components['python_packages'] = f.read().splitlines()
            
        except Exception as e:
            error_logger.error(f"Error getting component versions: {e}")
        
        return components
    
    def check_for_updates(self) -> Dict:
        """Check for available platform updates."""
        try:
            current_version = self.get_current_version()
            
            # In a real implementation, this would check a registry or API
            # For now, we'll simulate the check
            available_updates = self._simulate_update_check(current_version['version'])
            
            return {
                "current_version": current_version,
                "available_updates": available_updates,
                "last_checked": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            error_logger.error(f"Error checking for updates: {e}")
            return {"error": str(e)}
    
    def _simulate_update_check(self, current_version: str) -> List[Dict]:
        """Simulate checking for updates (replace with real implementation)."""
        # This would normally check a registry or API
        # For demo purposes, we'll return some mock updates
        
        version_parts = current_version.split('.')
        major, minor, patch = map(int, version_parts)
        
        updates = []
        
        # Simulate patch update
        if patch < 10:
            updates.append({
                "version": f"{major}.{minor}.{patch + 1}",
                "type": "patch",
                "description": "Bug fixes and security patches",
                "release_date": (datetime.utcnow() + timedelta(days=1)).isoformat(),
                "size_mb": 50,
                "download_url": f"https://registry.example.com/mahasangraha/{major}.{minor}.{patch + 1}"
            })
        
        # Simulate minor update
        if minor < 5:
            updates.append({
                "version": f"{major}.{minor + 1}.0",
                "type": "minor",
                "description": "New features and improvements",
                "release_date": (datetime.utcnow() + timedelta(days=7)).isoformat(),
                "size_mb": 200,
                "download_url": f"https://registry.example.com/mahasangraha/{major}.{minor + 1}.0"
            })
        
        # Simulate major update
        if major < 2:
            updates.append({
                "version": f"{major + 1}.0.0",
                "type": "major",
                "description": "Major version with breaking changes",
                "release_date": (datetime.utcnow() + timedelta(days=30)).isoformat(),
                "size_mb": 500,
                "download_url": f"https://registry.example.com/mahasangraha/{major + 1}.0.0"
            })
        
        return updates
    
    def prepare_update(self, version: str, download_url: str) -> Dict:
        """Prepare for platform update."""
        try:
            # Check if update is already in progress
            if self.redis.get(self.update_lock_key):
                return {"error": "Update already in progress"}
            
            # Acquire update lock
            self.redis.setex(self.update_lock_key, 3600, "1")  # 1 hour lock
            
            # Update status
            status = {
                "status": "preparing",
                "version": version,
                "download_url": download_url,
                "started_at": datetime.utcnow().isoformat(),
                "progress": 0
            }
            self.redis.setex(self.update_status_key, 3600, json.dumps(status))
            
            # In a real implementation, this would:
            # 1. Download the update
            # 2. Verify checksums
            # 3. Prepare containers
            # 4. Backup current configuration
            
            # For now, we'll simulate the process
            audit_logger.info(f"Preparing update to version {version}")
            
            return {
                "status": "preparing",
                "version": version,
                "message": "Update preparation started"
            }
            
        except Exception as e:
            error_logger.error(f"Error preparing update: {e}")
            self._release_update_lock()
            return {"error": str(e)}
    
    def perform_update(self, version: str, strategy: str = "rolling") -> Dict:
        """Perform platform update with specified strategy."""
        try:
            # Check if update is prepared
            status = self._get_update_status()
            if not status or status.get("status") != "preparing":
                return {"error": "Update not prepared or already in progress"}
            
            # Update status
            status["status"] = "updating"
            status["strategy"] = strategy
            status["started_at"] = datetime.utcnow().isoformat()
            status["progress"] = 10
            self.redis.setex(self.update_status_key, 3600, json.dumps(status))
            
            audit_logger.info(f"Starting update to version {version} with strategy {strategy}")
            
            if strategy == "rolling":
                result = self._perform_rolling_update(version)
            elif strategy == "blue_green":
                result = self._perform_blue_green_update(version)
            elif strategy == "maintenance":
                result = self._perform_maintenance_update(version)
            else:
                raise ValueError(f"Unknown update strategy: {strategy}")
            
            # Update status
            status["status"] = "completed"
            status["completed_at"] = datetime.utcnow().isoformat()
            status["progress"] = 100
            status["result"] = result
            self.redis.setex(self.update_status_key, 3600, json.dumps(status))
            
            # Update version in system config
            from models.oauth import SystemConfig
            version_config = SystemConfig.objects(key="platform_version").first()
            if version_config:
                version_config.value = version
                version_config.updated_at = datetime.utcnow()
                version_config.save()
            
            # Clear version cache
            self.redis.delete(self.version_info_key)
            
            # Release update lock
            self._release_update_lock()
            
            audit_logger.info(f"Update to version {version} completed successfully")
            
            return {
                "status": "completed",
                "version": version,
                "result": result
            }
            
        except Exception as e:
            error_logger.error(f"Error performing update: {e}")
            self._release_update_lock()
            
            # Update status to failed
            status = self._get_update_status()
            if status:
                status["status"] = "failed"
                status["error"] = str(e)
                status["failed_at"] = datetime.utcnow().isoformat()
                self.redis.setex(self.update_status_key, 3600, json.dumps(status))
            
            return {"error": str(e)}
    
    def _perform_rolling_update(self, version: str) -> Dict:
        """Perform rolling update (zero downtime)."""
        try:
            docker_client = self._get_docker_client()
            if not docker_client:
                raise Exception("Docker client not available")
            
            # Get current containers
            containers = docker_client.containers.list()
            
            # Update containers one by one
            updated_containers = []
            for container in containers:
                if container.name.startswith(('backend', 'frontend')):
                    # Pull new image
                    new_image_name = container.image.tags[0].replace(
                        container.image.tags[0].split(':')[-1],
                        version
                    )
                    
                    docker_client.images.pull(new_image_name)
                    
                    # Stop and remove old container
                    container.stop()
                    container.remove()
                    
                    # Start new container
                    new_container = docker_client.containers.run(
                        new_image_name,
                        name=container.name,
                        detach=True,
                        environment=container.attrs['Config']['Env'],
                        ports=container.attrs['NetworkSettings']['Ports'],
                        volumes=container.attrs['Mounts']
                    )
                    
                    updated_containers.append({
                        "name": container.name,
                        "old_image": container.image.tags[0],
                        "new_image": new_image_name,
                        "status": "updated"
                    })
            
            return {
                "strategy": "rolling",
                "updated_containers": updated_containers,
                "downtime": "minimal"
            }
            
        except Exception as e:
            error_logger.error(f"Error in rolling update: {e}")
            raise
    
    def _perform_blue_green_update(self, version: str) -> Dict:
        """Perform blue-green update (zero downtime with full environment swap)."""
        try:
            docker_client = self._get_docker_client()
            if not docker_client:
                raise Exception("Docker client not available")
            
            # This is a simplified implementation
            # In a real scenario, you would:
            # 1. Deploy new version to green environment
            # 2. Test green environment
            # 3. Switch traffic to green
            # 4. Decommission blue environment
            
            return {
                "strategy": "blue_green",
                "status": "simulated",
                "message": "Blue-green update would be performed here"
            }
            
        except Exception as e:
            error_logger.error(f"Error in blue-green update: {e}")
            raise
    
    def _perform_maintenance_update(self, version: str) -> Dict:
        """Perform maintenance update (with downtime)."""
        try:
            # Set maintenance mode
            from models.oauth import SystemConfig
            maintenance_config = SystemConfig.objects(key="maintenance_mode").first()
            if not maintenance_config:
                maintenance_config = SystemConfig(
                    key="maintenance_mode",
                    value=True,
                    updated_at=datetime.utcnow()
                )
                maintenance_config.save()
            
            # Stop all application containers
            docker_client = self._get_docker_client()
            if docker_client:
                containers = docker_client.containers.list()
                for container in containers:
                    if container.name.startswith(('backend', 'frontend')):
                        container.stop()
            
            # Perform update (simplified)
            # In a real implementation, this would update images and restart containers
            
            # Disable maintenance mode
            maintenance_config.value = False
            maintenance_config.updated_at = datetime.utcnow()
            maintenance_config.save()
            
            return {
                "strategy": "maintenance",
                "downtime": "scheduled",
                "maintenance_duration": "5 minutes"
            }
            
        except Exception as e:
            error_logger.error(f"Error in maintenance update: {e}")
            raise
    
    def _get_update_status(self) -> Optional[Dict]:
        """Get current update status."""
        status_data = self.redis.get(self.update_status_key)
        return json.loads(status_data) if status_data else None
    
    def _release_update_lock(self):
        """Release update lock."""
        self.redis.delete(self.update_lock_key)
    
    def rollback_update(self, target_version: str) -> Dict:
        """Rollback to a previous version."""
        try:
            # Check if update is in progress
            if self.redis.get(self.update_lock_key):
                return {"error": "Cannot rollback during update"}
            
            # Acquire update lock
            self.redis.setex(self.update_lock_key, 3600, "1")
            
            # Update status
            status = {
                "status": "rolling_back",
                "target_version": target_version,
                "started_at": datetime.utcnow().isoformat(),
                "progress": 0
            }
            self.redis.setex(self.update_status_key, 3600, json.dumps(status))
            
            # Perform rollback (simplified)
            # In a real implementation, this would:
            # 1. Stop current containers
            # 2. Start containers with previous version
            # 3. Verify rollback
            
            audit_logger.info(f"Starting rollback to version {target_version}")
            
            # Update version in system config
            from models.oauth import SystemConfig
            version_config = SystemConfig.objects(key="platform_version").first()
            if version_config:
                version_config.value = target_version
                version_config.updated_at = datetime.utcnow()
                version_config.save()
            
            # Clear version cache
            self.redis.delete(self.version_info_key)
            
            # Update status
            status["status"] = "completed"
            status["completed_at"] = datetime.utcnow().isoformat()
            status["progress"] = 100
            self.redis.setex(self.update_status_key, 3600, json.dumps(status))
            
            # Release update lock
            self._release_update_lock()
            
            audit_logger.info(f"Rollback to version {target_version} completed successfully")
            
            return {
                "status": "completed",
                "version": target_version,
                "message": "Rollback completed successfully"
            }
            
        except Exception as e:
            error_logger.error(f"Error rolling back update: {e}")
            self._release_update_lock()
            return {"error": str(e)}
    
    def get_update_history(self, limit: int = 10) -> List[Dict]:
        """Get update history."""
        try:
            # In a real implementation, this would query a database table
            # For now, we'll return mock data
            history = [
                {
                    "version": "1.0.1",
                    "type": "patch",
                    "status": "completed",
                    "started_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
                    "completed_at": (datetime.utcnow() - timedelta(days=1) + timedelta(minutes=5)).isoformat(),
                    "strategy": "rolling"
                },
                {
                    "version": "1.0.0",
                    "type": "major",
                    "status": "completed",
                    "started_at": (datetime.utcnow() - timedelta(days=30)).isoformat(),
                    "completed_at": (datetime.utcnow() - timedelta(days=30) + timedelta(minutes=15)).isoformat(),
                    "strategy": "maintenance"
                }
            ]
            
            return history[:limit]
            
        except Exception as e:
            error_logger.error(f"Error getting update history: {e}")
            return []

# Global update service instance
update_service = UpdateService()
