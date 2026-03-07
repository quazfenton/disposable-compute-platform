"""
Database integration layer for SessionManager
Provides persistence, recovery, and audit trail
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.database.db import Database, DatabaseConfig, init_database
from src.database.models import SessionStatus, SessionType
from src.models.session import Session
from src.services.platform import SessionManager

logger = logging.getLogger(__name__)


class DatabaseIntegration:
    """Integrates database persistence with SessionManager"""
    
    def __init__(self, session_manager: SessionManager, config: DatabaseConfig = None):
        self.session_manager = session_manager
        self.database: Optional[Database] = None
        self.config = config
        self._initialized = False
        self._recovery_task: Optional[asyncio.Task] = None
        
        logger.info("DatabaseIntegration initialized")
    
    async def initialize(self):
        """Initialize database connection and recover sessions"""
        if self._initialized:
            return
        
        try:
            # Initialize database
            if self.config:
                self.database = Database(self.config)
                await self.database.connect()
            else:
                # Use environment variables
                self.database = await init_database()
            
            self._initialized = True
            logger.info("Database connection established")
            
            # Recover active sessions from database
            await self.recover_sessions()
            
            # Start background cleanup task
            self._recovery_task = asyncio.create_task(self._periodic_cleanup())
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def recover_sessions(self):
        """Recover active sessions from database"""
        if not self.database:
            return
        
        try:
            # Get all active sessions from database
            active_sessions = await self.database.list_user_sessions(
                user_id=None,  # All users
                status=SessionStatus.RUNNING
            )
            
            recovered_count = 0
            
            for db_session in active_sessions:
                # Check if session is expired
                if db_session.expires_at and db_session.expires_at < datetime.utcnow():
                    logger.info(f"Session {db_session.id} expired, skipping recovery")
                    await self.database.update_session_status(db_session.id, SessionStatus.DESTROYED)
                    continue
                
                # Recreate in-memory session
                session = Session(
                    id=db_session.id,
                    type=SessionType(db_session.type.value),
                    status=SessionStatus.RUNNING,
                    created_at=db_session.created_at,
                    updated_at=datetime.utcnow(),
                    expires_at=db_session.expires_at,
                    repo_url=db_session.repo_url,
                    repo_ref=db_session.repo_ref,
                    pr_number=db_session.pr_number,
                    metadata=db_session.metadata or {}
                )
                
                # Add to in-memory tracking
                self.session_manager.sessions[session.id] = session
                
                # Try to recover container state (best effort)
                await self._recover_session_containers(session)
                
                recovered_count += 1
                logger.info(f"Recovered session {session.id}")
            
            logger.info(f"Recovered {recovered_count} active sessions from database")
            
        except Exception as e:
            logger.error(f"Failed to recover sessions: {e}")
    
    async def _recover_session_containers(self, session: Session):
        """Attempt to recover container state for a session"""
        # This is a best-effort recovery
        # In production, you would check if containers still exist
        
        if not session.container_id:
            logger.warning(f"Session {session.id} has no container_id, cannot recover")
            return
        
        try:
            import docker
            client = docker.from_env()
            
            # Parse container IDs
            import json
            container_ids = json.loads(session.container_id) if session.container_id else {}
            
            # Check each container
            for service_name, container_data in container_ids.items():
                container_id = container_data.get('id') if isinstance(container_data, dict) else container_data
                
                try:
                    container = client.containers.get(container_id)
                    
                    # Check if container is running
                    if container.status != 'running':
                        logger.warning(f"Container {container_id} ({service_name}) is not running")
                        # Mark session as needing recreation
                        session.status = SessionStatus.STOPPED
                        return
                    
                    logger.info(f"Recovered container {container_id} ({service_name})")
                    
                except Exception as e:
                    logger.warning(f"Container {container_id} not found: {e}")
                    # Container lost, session needs recreation
                    session.status = SessionStatus.STOPPED
                    return
            
        except Exception as e:
            logger.error(f"Error recovering containers for session {session.id}: {e}")
            # Don't fail recovery, just mark session
            session.status = SessionStatus.STOPPED
    
    async def _periodic_cleanup(self):
        """Background task for periodic cleanup"""
        while True:
            try:
                await asyncio.sleep(300)  # Every 5 minutes
                await self.cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
    
    async def cleanup_expired_sessions(self) -> List[str]:
        """Clean up expired sessions in database"""
        if not self.database:
            return []
        
        try:
            expired_ids = await self.database.cleanup_expired_sessions()
            
            for session_id in expired_ids:
                # Remove from in-memory tracking
                if session_id in self.session_manager.sessions:
                    del self.session_manager.sessions[session_id]
                
                logger.info(f"Cleaned up expired session {session_id}")
            
            return expired_ids
            
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {e}")
            return []
    
    async def persist_session(self, session: Session):
        """Persist session to database"""
        if not self.database:
            return
        
        try:
            # Check if session exists in database
            existing = await self.database.get_session(session.id)
            
            if existing:
                # Update existing session
                await self.database.update_session_status(session.id, session.status)
            else:
                # Create new session
                db_session = await self.database.create_session(
                    session_type=session.type,
                    user_id=session.metadata.get('user_id', 'anonymous'),
                    config={
                        'repo_url': session.repo_url,
                        'repo_ref': session.repo_ref,
                        'pr_number': session.pr_number,
                        'ports': session.ports
                    },
                    ttl_minutes=int((session.expires_at - datetime.utcnow()).total_seconds() / 60) if session.expires_at else 60,
                    metadata=session.metadata
                )
                
                if db_session:
                    session.id = db_session.id  # Use DB-generated ID
            
            logger.debug(f"Persisted session {session.id}")
            
        except Exception as e:
            logger.error(f"Failed to persist session {session.id}: {e}")
    
    async def load_session(self, session_id: str) -> Optional[Session]:
        """Load session from database"""
        if not self.database:
            return None
        
        try:
            db_session = await self.database.get_session(session_id)
            
            if not db_session:
                return None
            
            # Convert to in-memory Session
            session = Session(
                id=db_session.id,
                type=SessionType(db_session.type.value),
                status=db_session.status,
                created_at=db_session.created_at,
                updated_at=db_session.updated_at,
                expires_at=db_session.expires_at,
                repo_url=db_session.repo_url,
                repo_ref=db_session.repo_ref,
                pr_number=db_session.pr_number,
                metadata=db_session.metadata or {}
            )
            
            return session
            
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
            return None
    
    async def close(self):
        """Close database connection"""
        if self._recovery_task:
            self._recovery_task.cancel()
            try:
                await self._recovery_task
            except asyncio.CancelledError:
                pass
        
        if self.database:
            await self.database.disconnect()
        
        self._initialized = False
        logger.info("Database connection closed")


def extend_session_manager_with_database(
    session_manager: SessionManager,
    database_config: DatabaseConfig = None
) -> DatabaseIntegration:
    """Extend SessionManager with database capabilities"""
    
    integration = DatabaseIntegration(session_manager, database_config)
    
    # Store reference in session manager
    session_manager.database_integration = integration
    session_manager.database = integration.database
    
    # Wrap create_session to persist
    original_create = session_manager.create_session
    
    async def create_session_with_persist(*args, **kwargs):
        # Create session
        session = await original_create(*args, **kwargs)
        
        # Persist to database
        if integration.database:
            await integration.persist_session(session)
        
        return session
    
    session_manager.create_session = create_session_with_persist
    
    # Wrap destroy_session to update database
    original_destroy = session_manager.destroy_session
    
    async def destroy_session_with_db(*args, **kwargs):
        # Destroy session
        await original_destroy(*args, **kwargs)
        
        # Update database
        if integration.database:
            session_id = args[0] if args else kwargs.get('session_id')
            if session_id:
                await integration.database.update_session_status(session_id, SessionStatus.DESTROYED)
    
    session_manager.destroy_session = destroy_session_with_db
    
    logger.info("SessionManager extended with database integration")
    
    return integration


class SessionHistory:
    """Track session history for analytics and audit"""
    
    def __init__(self, database: Database):
        self.database = database
        self.logger = logging.getLogger(__name__)
    
    async def log_session_event(
        self,
        session_id: str,
        event_type: str,
        data: Dict[str, Any] = None
    ):
        """Log an event for a session"""
        if not self.database:
            return
        
        try:
            await self.database.log_event(
                entity_type='session',
                entity_id=session_id,
                event_type=event_type,
                data=data or {}
            )
            
            self.logger.debug(f"Logged event {event_type} for session {session_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to log session event: {e}")
    
    async def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get event history for a session"""
        if not self.database:
            return []
        
        try:
            events = await self.database.get_entity_events(
                entity_type='session',
                entity_id=session_id,
                limit=100
            )
            
            return events
            
        except Exception as e:
            self.logger.error(f"Failed to get session history: {e}")
            return []
    
    async def get_user_statistics(self, user_id: str) -> Dict[str, Any]:
        """Get statistics for a user"""
        if not self.database:
            return {}
        
        try:
            # Get all sessions for user
            sessions = await self.database.list_user_sessions(user_id, limit=1000)
            
            # Calculate statistics
            total_sessions = len(sessions)
            active_sessions = sum(1 for s in sessions if s.status == SessionStatus.RUNNING)
            failed_sessions = sum(1 for s in sessions if s.status == SessionStatus.FAILED)
            
            # Calculate average session duration
            durations = []
            for session in sessions:
                if session.expires_at and session.created_at:
                    duration = (session.expires_at - session.created_at).total_seconds()
                    durations.append(duration)
            
            avg_duration = sum(durations) / len(durations) if durations else 0
            
            return {
                'user_id': user_id,
                'total_sessions': total_sessions,
                'active_sessions': active_sessions,
                'failed_sessions': failed_sessions,
                'success_rate': (total_sessions - failed_sessions) / total_sessions if total_sessions > 0 else 0,
                'avg_session_duration_seconds': avg_duration,
                'total_session_time_seconds': sum(durations)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get user statistics: {e}")
            return {}
