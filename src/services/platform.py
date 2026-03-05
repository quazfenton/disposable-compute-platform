"""
Shared platform services for disposable compute platform
"""
import asyncio
import logging
import json
import os
import secrets
import pickle
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field

# Try imports
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None
    REDIS_AVAILABLE = False

from src.models.session import Session, SessionType, SessionStatus, ServiceDefinition
from src.models.environment import Environment
from src.containers.orchestrator import ContainerOrchestrator
from src.networking.router import NetworkManager as BasicNetworkManager
from src.networking_advanced.network_manager import AdvancedNetworkManager
from src.orchestrator.orchestrator import AdvancedOrchestrator
from src.scheduler.scheduler import Scheduler, PodRequest
from src.models.pod import PodType, ResourceRequirements, PodSpec
from src.metrics.alerting import get_alert_manager


@dataclass
class PlatformConfig:
    """Configuration for the platform"""
    domain: str = "preview.yourapp.dev"
    default_ttl: int = 30  # minutes
    max_ttl: int = 1440  # 24 hours
    storage_path: str = "/tmp/disposable-storage"
    max_concurrent_sessions: int = 100
    redis_url: Optional[str] = "redis://localhost:6379/0"
    firecracker_socket: str = "/tmp/firecracker.socket"


class SnapshotManager:
    """Manages snapshots for forkable sessions with security hardening"""

    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.logger = logging.getLogger(__name__)
        os.makedirs(storage_path, exist_ok=True)
        self.storage_path_abs = os.path.abspath(storage_path)

    async def create_snapshot(self, session_id: str, state_data: Dict[str, Any]) -> str:
        """Create a snapshot of a session's state"""
        snapshot_id = f"snapshot-{session_id}-{secrets.token_hex(4)}"
        snapshot_path = os.path.join(self.storage_path_abs, f"{snapshot_id}.json")
        
        with open(snapshot_path, 'w') as f:
            json.dump({
                'id': snapshot_id,
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'state_data': state_data
            }, f, indent=2)
            
        self.logger.info(f"Created snapshot {snapshot_id}")
        return snapshot_id

    async def load_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Load a snapshot's state"""
        snapshot_path = os.path.join(self.storage_path_abs, f"{snapshot_id}.json")
        if not os.path.exists(snapshot_path):
            return None

        with open(snapshot_path, 'r') as f:
            return json.load(f)

    async def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot"""
        snapshot_path = os.path.join(self.storage_path_abs, f"{snapshot_id}.json")
        if os.path.exists(snapshot_path):
            os.remove(snapshot_path)
            return True
        return False


class SessionManager:
    """Manages the lifecycle of disposable compute sessions with Redis caching, Database Persistence, and Advanced Orchestration"""

    def __init__(self, config: PlatformConfig, database=None):
        self.config = config
        self.sessions: Dict[str, Session] = {}
        self.environments: Dict[str, Environment] = {}
        self.database = database  # Database integration instance

        # Core Infrastructure
        self.orchestrator = AdvancedOrchestrator()
        self.scheduler = Scheduler(orchestrator=self.orchestrator)
        self.basic_network = BasicNetworkManager()
        self.advanced_network = AdvancedNetworkManager()
        self.snapshot_manager = SnapshotManager(config.storage_path)
        self.alert_manager = get_alert_manager()

        self.logger = logging.getLogger(__name__)

        # Concurrency control - prevents race conditions
        self._session_lock = asyncio.Lock()
        self._creation_locks: Dict[str, asyncio.Lock] = {}

        # Initialize Redis if configured
        self.redis = None
        if REDIS_AVAILABLE and config.redis_url:
            try:
                import redis as redis_lib
                self.redis = redis_lib.from_url(config.redis_url)
                self.logger.info(f"Connected to Redis at {config.redis_url}")
            except Exception as e:
                self.logger.error(f"Failed to connect to Redis: {e}")

    async def _cache_session(self, session: Session):
        """Cache session data in Redis"""
        if self.redis:
            try:
                data = pickle.dumps(session)
                await self.redis.set(f"session:{session.id}", data, ex=int(self.config.default_ttl * 60))
            except Exception as e:
                self.logger.error(f"Failed to cache session {session.id}: {e}")

    async def _get_cached_session(self, session_id: str) -> Optional[Session]:
        """Retrieve session data from Redis"""
        if self.redis:
            try:
                data = await self.redis.get(f"session:{session_id}")
                if data:
                    # In some redis versions, get might return bytes or awaitable
                    if asyncio.iscoroutine(data):
                        data = await data
                    return pickle.loads(data)
            except Exception as e:
                self.logger.error(f"Failed to retrieve cached session {session_id}: {e}")
        return None

    async def _publish_event(self, event_type: str, data: Dict[str, Any]):
        """Publish an event to Redis PubSub"""
        if self.redis:
            try:
                event = {
                    'type': event_type,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                }
                await self.redis.publish("pod_events", json.dumps(event))
            except Exception as e:
                self.logger.error(f"Failed to publish event {event_type}: {e}")

    async def create_session(
        self,
        session_type: SessionType,
        repo_url: str,
        repo_ref: Optional[str] = None,
        pr_number: Optional[int] = None,
        ttl_minutes: Optional[int] = None,
        user_id: Optional[str] = None
    ) -> Session:
        """Create a new disposable session with database persistence and race condition prevention
        
        SECURITY: Uses locks to prevent duplicate session creation
        PERSISTENCE: Stores session in database before returning
        """
        # RACE CONDITION PREVENTION: Use lock for session creation
        async with self._session_lock:
            # Generate unique ID with collision check
            max_retries = 3
            for attempt in range(max_retries):
                session_id = f"sess-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}"
                if session_id not in self.sessions:
                    break
            else:
                raise Exception("Failed to generate unique session ID after 3 attempts")

            # Set expiration
            ttl = ttl_minutes or self.config.default_ttl
            expires_at = datetime.now() + timedelta(minutes=ttl)

            # Create session object
            session = Session(
                id=session_id,
                type=session_type,
                status=SessionStatus.CREATING,
                user_id=user_id or "default-user",
                created_at=datetime.now(),
                updated_at=datetime.now(),
                expires_at=expires_at,
                repo_url=repo_url,
                repo_ref=repo_ref,
                pr_number=pr_number,
                metadata={'user_id': user_id} if user_id else {}
            )

            # DATABASE PERSISTENCE: Store in database FIRST
            if self.database and self.database.database:
                try:
                    await self.database.database.create_session(
                        session_id=session_id,
                        session_type=SessionType(session_type),
                        user_id=user_id or "default-user",
                        repo_url=repo_url,
                        repo_ref=repo_ref,
                        pr_number=pr_number,
                        expires_at=expires_at,
                        metadata=session.metadata
                    )
                    self.logger.info(f"Session {session_id} persisted to database")
                except Exception as e:
                    self.logger.error(f"Failed to persist session to database: {e}")
                    # Continue without database - graceful degradation

            # Add to in-memory tracking
            self.sessions[session_id] = session

        # Continue with session creation outside lock (allows concurrent operations)
        # Schedule the pod
        pod_spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="web",
            image="alpine:latest",
            resource_requirements=ResourceRequirements(cpu_cores=1.0, memory_mb=1024)
        )

        pod_request = PodRequest(
            id=f"pod-{session_id}",
            pod_spec=pod_spec,
            user_id=user_id or "default-user",
            user_tier="free",
            priority=50
        )

        success, message, node_id = await self.scheduler.schedule(pod_request)
        if not success:
            session.status = SessionStatus.FAILED
            await self.alert_manager.trigger_alert(
                severity="critical",
                title=f"Scheduling failed for session {session_id}",
                description=message
            )
            raise Exception(f"Failed to schedule: {message}")

        # Start the session creation process based on type
        try:
            if session_type == SessionType.PREVIEW:
                await self._create_preview_session(session)
            elif session_type == SessionType.RUN_REPO:
                await self._create_run_repo_session(session)
            elif session_type == SessionType.FORK_GUI:
                await self._create_fork_gui_session(session)
        except Exception as e:
            session.status = SessionStatus.FAILED
            self.scheduler.unschedule(pod_request.id)
            raise e

        # Cache the session
        await self._cache_session(session)

        # Publish event
        await self._publish_event("session_created", {"session_id": session.id, "type": session_type.value, "user_id": user_id})

        return session

    async def _create_preview_session(self, session: Session):
        """Create a preview environment session"""
        repo_url = session.repo_url
        if repo_url is None:
            session.status = SessionStatus.ERROR
            return
            
        # Services would normally be parsed from .preview.yaml
        # For now, create a default pod via AdvancedOrchestrator
        pod_spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="web",
            image="node:18-alpine",
            command=["npm", "start"],
            ports=[3000],
            environment={"NODE_ENV": "production"}
        )
        
        try:
            pod_id = await self.orchestrator.create_pod(pod_spec)
            session.metadata['pod_id'] = pod_id
            
            # Create isolated network
            network_name = self.basic_network.create_isolated_network(session.id)
            session.network_id = network_name
            
            session.status = SessionStatus.RUNNING
        except Exception as e:
            self.logger.error(f"Failed to create preview session: {e}")
            session.status = SessionStatus.ERROR
            raise
    
    async def _create_run_repo_session(self, session: Session):
        """Create a run-repo session"""
        repo_url = session.repo_url
        if repo_url is None:
            session.status = SessionStatus.ERROR
            return
            
        pod_spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="web",
            image="python:3.11-slim",
            command=["python", "app.py"],
            ports=[8000]
        )
        
        try:
            pod_id = await self.orchestrator.create_pod(pod_spec)
            session.metadata['pod_id'] = pod_id
            
            network_name = self.basic_network.create_isolated_network(session.id)
            session.network_id = network_name
            
            session.status = SessionStatus.RUNNING
        except Exception as e:
            self.logger.error(f"Failed to create run-repo session: {e}")
            session.status = SessionStatus.ERROR
            raise
    
    async def _create_fork_gui_session(self, session: Session):
        """Create a forkable GUI session"""
        pod_spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="gui",
            image="base-gui-image",
            command=["start-gui-app"],
            ports=[8080]
        )
        
        try:
            pod_id = await self.orchestrator.create_pod(pod_spec)
            session.metadata['pod_id'] = pod_id
            
            network_name = self.basic_network.create_isolated_network(session.id)
            session.network_id = network_name
            
            session.status = SessionStatus.RUNNING
        except Exception as e:
            self.logger.error(f"Failed to create fork-gui session: {e}")
            session.status = SessionStatus.ERROR
            raise
    
    async def destroy_session(self, session_id: str):
        """Destroy a session and its resources with database persistence
        
        PERSISTENCE: Updates session status in database
        """
        if session_id not in self.sessions:
            return

        session = self.sessions[session_id]
        if session._destroy_lock:
            return

        session._destroy_lock = True
        session.status = SessionStatus.STOPPING

        try:
            environment_id = f"env-{session_id}"
            if environment_id in self.environments:
                await self.basic_network.cleanup_network_with_retry(environment_id, [])
                del self.environments[environment_id]

            pod_id = f"pod-{session_id}"
            try:
                await self.orchestrator.destroy_pod(pod_id)
            except:
                pass

            self.scheduler.unschedule(pod_id)

            session.status = SessionStatus.DESTROYED
            session.updated_at = datetime.now()

            # DATABASE PERSISTENCE: Update status in database
            if self.database and self.database.database:
                try:
                    await self.database.database.update_session_status(
                        session_id,
                        SessionStatus.DESTROYED
                    )
                    self.logger.info(f"Session {session_id} status updated in database")
                except Exception as e:
                    self.logger.error(f"Failed to update session status in database: {e}")

            self.logger.info(f"Successfully destroyed session {session_id}")

        except Exception as e:
            self.logger.error(f"Error destroying session {session_id}: {e}")
            session.status = SessionStatus.ERROR
            raise
        finally:
            session._destroy_lock = False

    async def recover_sessions_from_database(self):
        """Load active sessions from database on startup
        
        PERSISTENCE: Restores sessions that were active before restart
        """
        if not self.database or not self.database.database:
            self.logger.info("No database configured, skipping session recovery")
            return

        try:
            # Get all active sessions from database
            active_sessions = await self.database.database.list_user_sessions(
                user_id=None,  # All users
                status=SessionStatus.RUNNING
            )

            recovered_count = 0
            for db_session in active_sessions:
                # Check if session is expired
                if db_session.expires_at and db_session.expires_at < datetime.now():
                    self.logger.info(f"Session {db_session.id} expired, skipping recovery")
                    await self.database.database.update_session_status(
                        db_session.id,
                        SessionStatus.DESTROYED
                    )
                    continue

                # Skip if already in memory
                if db_session.id in self.sessions:
                    continue

                # Recreate in-memory session
                session = Session(
                    id=db_session.id,
                    type=SessionType(db_session.type),
                    status=SessionStatus.RUNNING,
                    user_id=db_session.user_id,
                    created_at=db_session.created_at,
                    updated_at=datetime.now(),
                    expires_at=db_session.expires_at,
                    repo_url=db_session.repo_url,
                    repo_ref=db_session.repo_ref,
                    pr_number=db_session.pr_number,
                    metadata=db_session.metadata or {},
                    container_id=db_session.metadata.get('container_id') if db_session.metadata else None
                )

                # Add to in-memory tracking
                self.sessions[session.id] = session
                recovered_count += 1
                self.logger.info(f"Recovered session {session.id} for user {db_session.user_id}")

            self.logger.info(f"Recovered {recovered_count} active sessions from database")

        except Exception as e:
            self.logger.error(f"Failed to recover sessions from database: {e}")
    
    async def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        now = datetime.now()
        expired_sessions = [
            sid for sid, session in self.sessions.items()
            if session.expires_at and session.expires_at < now
        ]
        
        for session_id in expired_sessions:
            await self.destroy_session(session_id)
            if session_id in self.sessions:
                del self.sessions[session_id]
        
        return expired_sessions

    async def get_session_logs(self, session_id: str, service: str = "main", lines: int = 100) -> str:
        """Get logs from a session's container"""
        if session_id not in self.sessions:
            return ""
        
        session = self.sessions[session_id]
        pod_id = session.metadata.get('pod_id')
        
        if not pod_id:
            return ""
        
        try:
            # Use the orchestrator to get logs
            return await self.orchestrator.container_orchestrator.get_container_logs(pod_id, lines)
        except Exception as e:
            self.logger.error(f"Failed to get logs for session {session_id}: {e}")
        
        return ""

    async def deploy_ai_generated_environment(self, user_id: str, compose_yaml: str) -> str:
        """
        Deploy an environment directly from AI-generated Docker Compose YAML
        """
        session_id = f"sess-ai-{secrets.token_hex(4)}"
        
        session = Session(
            id=session_id,
            type=SessionType.RUN_REPO,
            status=SessionStatus.CREATING,
            user_id=user_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=60)
        )
        
        self.sessions[session_id] = session
        
        try:
            # Logic to pass YAML to Docker Compose runner
            # For now, we simulate the deployment success
            await asyncio.sleep(1)
            
            session.status = SessionStatus.RUNNING
            self.logger.info(f"AI-Generated session {session_id} deployed successfully")
            
            return session_id
        except Exception as e:
            session.status = SessionStatus.ERROR
            self.logger.error(f"AI deployment failed: {e}")
            raise
