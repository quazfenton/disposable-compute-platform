"""
Shared platform services for disposable compute platform
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import json
import os
from src.models.session import Session, SessionType, SessionStatus, ServiceDefinition
from src.models.environment import Environment
from src.containers.orchestrator import ContainerOrchestrator
from src.networking.router import NetworkManager


@dataclass
class PlatformConfig:
    """Configuration for the platform"""
    domain: str = "preview.yourapp.dev"
    default_ttl: int = 30  # minutes
    max_ttl: int = 1440  # 24 hours
    storage_path: str = "/tmp/disposable-storage"
    max_concurrent_sessions: int = 100


class SessionManager:
    """Manages the lifecycle of disposable compute sessions"""
    
    def __init__(self, config: PlatformConfig):
        self.config = config
        self.sessions: Dict[str, Session] = {}
        self.environments: Dict[str, Environment] = {}
        self.container_orchestrator = ContainerOrchestrator()
        self.network_manager = NetworkManager()
        self.logger = logging.getLogger(__name__)
    
    async def create_session(self, session_type: SessionType, repo_url: str, 
                           repo_ref: Optional[str] = None, pr_number: Optional[int] = None,
                           ttl_minutes: int = None) -> Session:
        """Create a new disposable session"""
        session_id = f"sess-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.urandom(4).hex()}"
        
        # Set expiration
        ttl = ttl_minutes or self.config.default_ttl
        expires_at = datetime.now() + timedelta(minutes=ttl)
        
        session = Session(
            id=session_id,
            type=session_type,
            status=SessionStatus.CREATING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=expires_at,
            repo_url=repo_url,
            repo_ref=repo_ref,
            pr_number=pr_number
        )
        
        self.sessions[session_id] = session
        
        # Start the session creation process based on type
        if session_type == SessionType.PREVIEW:
            await self._create_preview_session(session)
        elif session_type == SessionType.RUN_REPO:
            await self._create_run_repo_session(session)
        elif session_type == SessionType.FORK_GUI:
            await self._create_fork_gui_session(session)
        
        return session
    
    async def _create_preview_session(self, session: Session):
        """Create a preview environment session"""
        # Parse .preview.yaml from the repository
        services = await self._parse_preview_config(session.repo_url, session.repo_ref)
        
        # Create environment
        environment = Environment(
            id=f"env-{session.id}",
            name=f"preview-{session.id}",
            session_id=session.id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=session.expires_at,
            services=services
        )
        
        # Create isolated network
        network_name = self.network_manager.create_isolated_network(environment.id)
        environment.network_name = network_name
        
        # Set up internal DNS
        internal_dns = self.network_manager.setup_internal_dns(network_name, services)
        
        # Create containers
        container_ids = self.container_orchestrator.create_environment_containers(environment)
        
        # Update session with container info
        session.container_id = json.dumps(container_ids)
        session.network_id = network_name
        session.status = SessionStatus.RUNNING
        
        # Create external URLs
        external_urls = []
        for service_def in services:
            service = ServiceDefinition(**service_def)
            if service.port:
                url = self.network_manager.create_external_access(session.id, service.port, self.config.domain)
                external_urls.append(url)
        
        session.ports = {svc['name']: svc.get('port', 0) for svc in services if svc.get('port')}
        
        self.environments[environment.id] = environment
        self.sessions[session.id] = session
    
    async def _create_run_repo_session(self, session: Session):
        """Create a run-repo session"""
        # Detect runtime from repository
        runtime = await self._detect_runtime(session.repo_url, session.repo_ref)
        
        # Create default service based on detected runtime
        service = await self._create_default_service(runtime, session.repo_url, session.repo_ref)
        
        environment = Environment(
            id=f"env-{session.id}",
            name=f"run-{session.id}",
            session_id=session.id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=session.expires_at,
            services=[service]
        )
        
        # Create isolated network
        network_name = self.network_manager.create_isolated_network(environment.id)
        environment.network_name = network_name
        
        # Create containers
        container_ids = self.container_orchestrator.create_environment_containers(environment)
        
        # Update session with container info
        session.container_id = json.dumps(container_ids)
        session.network_id = network_name
        session.status = SessionStatus.RUNNING
        
        # Create external access
        if service.get('port'):
            url = self.network_manager.create_external_access(session.id, service['port'], self.config.domain)
            session.ports = {service['name']: service['port']}
        
        self.environments[environment.id] = environment
        self.sessions[session.id] = session
    
    async def _create_fork_gui_session(self, session: Session):
        """Create a forkable GUI session"""
        # For now, create a basic GUI environment
        # In the future, this would handle state capture and forking
        service = {
            'name': 'gui-app',
            'type': 'gui',
            'image': 'base-gui-image',  # This would be determined by the specific GUI app
            'command': 'start-gui-app',
            'port': 8080,
            'env': {}
        }
        
        environment = Environment(
            id=f"env-{session.id}",
            name=f"gui-{session.id}",
            session_id=session.id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=session.expires_at,
            services=[service]
        )
        
        # Create isolated network
        network_name = self.network_manager.create_isolated_network(environment.id)
        environment.network_name = network_name
        
        # Create containers
        container_ids = self.container_orchestrator.create_environment_containers(environment)
        
        # Update session with container info
        session.container_id = json.dumps(container_ids)
        session.network_id = network_name
        session.status = SessionStatus.RUNNING
        
        # Create external access
        url = self.network_manager.create_external_access(session.id, 8080, self.config.domain)
        session.ports = {'gui': 8080}
        
        self.environments[environment.id] = environment
        self.sessions[session.id] = session
    
    async def _parse_preview_config(self, repo_url: str, repo_ref: Optional[str]) -> List[Dict]:
        """Parse .preview.yaml from repository"""
        # This would actually fetch the file from the repository
        # For now, return a default configuration
        return [
            {
                'name': 'web',
                'type': 'web',
                'image': 'node:18-alpine',
                'command': 'npm start',
                'port': 3000,
                'env': {}
            }
        ]
    
    async def _detect_runtime(self, repo_url: str, repo_ref: Optional[str]) -> str:
        """Detect runtime from repository files"""
        # This would actually inspect the repository
        # For now, return a default
        return 'node'
    
    async def _create_default_service(self, runtime: str, repo_url: str, repo_ref: Optional[str]) -> Dict:
        """Create a default service based on detected runtime"""
        if runtime == 'node':
            return {
                'name': 'app',
                'type': 'web',
                'image': 'node:18-alpine',
                'command': 'npm start',
                'port': 3000,
                'env': {}
            }
        elif runtime == 'python':
            return {
                'name': 'app',
                'type': 'web',
                'image': 'python:3.11-slim',
                'command': 'python app.py',
                'port': 8000,
                'env': {}
            }
        else:
            # Default to a basic service
            return {
                'name': 'app',
                'type': 'web',
                'image': 'alpine:latest',
                'command': 'sleep infinity',
                'port': 8080,
                'env': {}
            }
    
    async def destroy_session(self, session_id: str):
        """Destroy a session and all its resources"""
        if session_id not in self.sessions:
            return
        
        session = self.sessions[session_id]
        session.status = SessionStatus.STOPPED
        
        # Get environment for this session
        environment_id = f"env-{session_id}"
        if environment_id in self.environments:
            environment = self.environments[environment_id]
            
            # Parse container IDs from session
            container_ids = json.loads(session.container_id) if session.container_id else {}
            
            # Destroy containers and network
            self.container_orchestrator.destroy_environment(environment, container_ids)
            
            # Clean up network
            self.network_manager.cleanup_network(environment_id, [])
            
            # Remove from tracking
            del self.environments[environment_id]
        
        # Mark session as destroyed
        session.status = SessionStatus.DESTROYED
        session.updated_at = datetime.now()
    
    async def get_session_logs(self, session_id: str, service_name: str = "main", lines: int = 100) -> str:
        """Get logs from a session's service"""
        if session_id not in self.sessions:
            return ""
        
        session = self.sessions[session_id]
        if not session.container_id:
            return ""
        
        container_ids = json.loads(session.container_id)
        if service_name not in container_ids:
            return ""
        
        container_id = container_ids[service_name]
        return self.container_orchestrator.get_container_logs(container_id, lines)
    
    async def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        now = datetime.now()
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if session.expires_at and session.expires_at < now
        ]
        
        for session_id in expired_sessions:
            await self.destroy_session(session_id)
            del self.sessions[session_id]
        
        return expired_sessions


class SnapshotManager:
    """Manages snapshots for forkable sessions"""
    
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.logger = logging.getLogger(__name__)
    
    async def create_snapshot(self, session_id: str, state_data: Dict[str, Any]) -> str:
        """Create a snapshot of a session's state"""
        snapshot_id = f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.urandom(4).hex()}"
        
        # Save state data to storage
        snapshot_path = os.path.join(self.storage_path, f"{snapshot_id}.json")
        os.makedirs(self.storage_path, exist_ok=True)
        
        with open(snapshot_path, 'w') as f:
            json.dump({
                'id': snapshot_id,
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'state_data': state_data
            }, f)
        
        return snapshot_id
    
    async def load_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Load a snapshot's state"""
        snapshot_path = os.path.join(self.storage_path, f"{snapshot_id}.json")
        
        if not os.path.exists(snapshot_path):
            return None
        
        with open(snapshot_path, 'r') as f:
            data = json.load(f)
        
        return data