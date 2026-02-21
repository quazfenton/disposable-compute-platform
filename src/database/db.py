"""
Async database connection and operations
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List, TypeVar, Type
from datetime import datetime
import json
from contextlib import asynccontextmanager

# Try imports
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None
    ASYNCPG_AVAILABLE = False

from src.database.models import (
    Session, Pod, Snapshot, User, SessionStatus, SessionType, SnapshotType,
    SCHEMA_SQL
)

T = TypeVar('T')

logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration"""
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "disposable_compute",
        user: str = "postgres",
        password: str = "",
        min_pool_size: int = 5,
        max_pool_size: int = 20,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size


class MockPool:
    """Mock pool for when asyncpg is not available"""
    def __init__(self):
        self._data = {
            'users': {},
            'sessions': {},
            'pods': {},
            'snapshots': {},
            'events': []
        }
        self._counters = {
            'users': 1,
            'sessions': 1,
            'pods': 1,
            'snapshots': 1,
            'events': 1
        }
    
    async def execute(self, query: str, *args) -> str:
        """Mock execute"""
        return "OK"
    
    async def fetch(self, query: str, *args) -> List[Dict]:
        """Mock fetch"""
        if "FROM sessions" in query:
            return list(self._data['sessions'].values())
        elif "FROM pods" in query:
            return list(self._data['pods'].values())
        elif "FROM snapshots" in query:
            return list(self._data['snapshots'].values())
        elif "FROM users" in query:
            return list(self._data['users'].values())
        return []
    
    async def fetchrow(self, query: str, *args) -> Optional[Dict]:
        """Mock fetchrow"""
        results = await self.fetch(query, *args)
        return results[0] if results else None
    
    async def fetchval(self, query: str, *args) -> Any:
        """Mock fetchval"""
        row = await self.fetchrow(query, *args)
        if row:
            return list(row.values())[0]
        return None
    
    async def close(self):
        """Mock close"""
        pass


class Database:
    """Async database manager"""
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None
        self._mock_pool: Optional[MockPool] = None
        self._connected = False
    
    async def connect(self):
        """Initialize database connection"""
        if ASYNCPG_AVAILABLE:
            try:
                self._pool = await asyncpg.create_pool(
                    host=self.config.host,
                    port=self.config.port,
                    database=self.config.database,
                    user=self.config.user,
                    password=self.config.password,
                    min_size=self.config.min_pool_size,
                    max_size=self.config.max_pool_size,
                )
                self._connected = True
                logger.info(f"Connected to PostgreSQL at {self.config.host}:{self.config.port}")
                
                # Initialize schema
                await self.init_schema()
            except Exception as e:
                logger.warning(f"Failed to connect to PostgreSQL: {e}. Using mock database.")
                self._mock_pool = MockPool()
                self._connected = True
        else:
            logger.info("asyncpg not available. Using mock database.")
            self._mock_pool = MockPool()
            self._connected = True
    
    async def disconnect(self):
        """Close database connection"""
        if self._pool:
            await self._pool.close()
        self._connected = False
        logger.info("Disconnected from database")
    
    async def init_schema(self):
        """Initialize database schema"""
        if self._pool:
            async with self._pool.acquire() as conn:
                await conn.execute(SCHEMA_SQL)
                logger.info("Database schema initialized")
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool"""
        if self._pool:
            async with self._pool.acquire() as conn:
                yield conn
        elif self._mock_pool:
            yield self._mock_pool
        else:
            raise RuntimeError("Database not connected")
    
    # User operations
    async def create_user(self, email: str, tier: str = "free", **kwargs) -> User:
        """Create a new user"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO users (email, tier, metadata)
                VALUES ($1, $2, $3)
                RETURNING *
                """,
                email, tier, json.dumps(kwargs.get('metadata', {}))
            )
            return User.from_row(dict(row)) if row else None
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1",
                user_id
            )
            return User.from_row(dict(row)) if row else None
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE email = $1",
                email
            )
            return User.from_row(dict(row)) if row else None
    
    # Session operations
    async def create_session(
        self,
        session_type: SessionType,
        user_id: str,
        config: Dict[str, Any] = None,
        ttl_minutes: int = 60,
        **kwargs
    ) -> Session:
        """Create a new session"""
        expires_at = datetime.utcnow()
        from datetime import timedelta
        expires_at = expires_at + timedelta(minutes=ttl_minutes)
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO sessions (type, user_id, expires_at, repo_url, repo_ref, pr_number, config, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                """,
                session_type.value,
                user_id,
                expires_at,
                kwargs.get('repo_url'),
                kwargs.get('repo_ref'),
                kwargs.get('pr_number'),
                json.dumps(config or {}),
                json.dumps(kwargs.get('metadata', {}))
            )
            
            session = Session.from_row(dict(row)) if row else None
            
            # Log event
            if session:
                await self.log_event('session', session.id, 'created', {'type': session_type.value})
            
            return session
    
    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sessions WHERE id = $1",
                session_id
            )
            return Session.from_row(dict(row)) if row else None
    
    async def update_session_status(self, session_id: str, status: SessionStatus) -> bool:
        """Update session status"""
        async with self.acquire() as conn:
            result = await conn.execute(
                "UPDATE sessions SET status = $1 WHERE id = $2",
                status.value,
                session_id
            )
            
            await self.log_event('session', session_id, 'status_changed', {'status': status.value})
            
            return result == "UPDATE 1"
    
    async def list_user_sessions(
        self,
        user_id: str,
        status: Optional[SessionStatus] = None,
        limit: int = 50
    ) -> List[Session]:
        """List sessions for a user"""
        async with self.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT * FROM sessions 
                    WHERE user_id = $1 AND status = $2
                    ORDER BY created_at DESC
                    LIMIT $3
                    """,
                    user_id, status.value, limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT * FROM sessions 
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                    """,
                    user_id, limit
                )
            
            return [Session.from_row(dict(row)) for row in rows]
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete a session (cascade deletes pods)"""
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM sessions WHERE id = $1",
                session_id
            )
            
            await self.log_event('session', session_id, 'deleted', {})
            
            return result == "DELETE 1"
    
    # Pod operations
    async def create_pod(
        self,
        session_id: str,
        spec: Dict[str, Any],
        node_id: str = None,
        **kwargs
    ) -> Pod:
        """Create a new pod"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO pods (session_id, node_id, spec, metadata)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                session_id,
                node_id,
                json.dumps(spec),
                json.dumps(kwargs.get('metadata', {}))
            )
            
            pod = Pod.from_row(dict(row)) if row else None
            
            if pod:
                await self.log_event('pod', pod.id, 'created', {'session_id': session_id})
            
            return pod
    
    async def get_pod(self, pod_id: str) -> Optional[Pod]:
        """Get pod by ID"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM pods WHERE id = $1",
                pod_id
            )
            return Pod.from_row(dict(row)) if row else None
    
    async def update_pod_status(self, pod_id: str, status: str, node_id: str = None) -> bool:
        """Update pod status"""
        async with self.acquire() as conn:
            if node_id:
                result = await conn.execute(
                    "UPDATE pods SET status = $1, node_id = $2 WHERE id = $3",
                    status, node_id, pod_id
                )
            else:
                result = await conn.execute(
                    "UPDATE pods SET status = $1 WHERE id = $2",
                    status, pod_id
                )
            
            await self.log_event('pod', pod_id, 'status_changed', {'status': status})
            
            return result == "UPDATE 1"
    
    async def destroy_pod(self, pod_id: str) -> bool:
        """Mark pod as destroyed"""
        async with self.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE pods 
                SET status = 'destroyed', destroyed_at = NOW() 
                WHERE id = $1
                """,
                pod_id
            )
            
            await self.log_event('pod', pod_id, 'destroyed', {})
            
            return result == "UPDATE 1"
    
    async def get_session_pods(self, session_id: str) -> List[Pod]:
        """Get all pods for a session"""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM pods WHERE session_id = $1",
                session_id
            )
            return [Pod.from_row(dict(row)) for row in rows]
    
    # Snapshot operations
    async def create_snapshot(
        self,
        pod_id: str,
        snapshot_type: SnapshotType,
        storage_path: str,
        size_bytes: int = 0,
        parent_id: str = None,
        metadata: Dict[str, Any] = None
    ) -> Snapshot:
        """Create a new snapshot"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO snapshots (pod_id, type, storage_path, size_bytes, parent_id, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING *
                """,
                pod_id,
                snapshot_type.value,
                storage_path,
                size_bytes,
                parent_id,
                json.dumps(metadata or {})
            )
            
            snapshot = Snapshot.from_row(dict(row)) if row else None
            
            if snapshot:
                await self.log_event('snapshot', snapshot.id, 'created', {'type': snapshot_type.value})
            
            return snapshot
    
    async def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """Get snapshot by ID"""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM snapshots WHERE id = $1",
                snapshot_id
            )
            return Snapshot.from_row(dict(row)) if row else None
    
    async def get_pod_snapshots(self, pod_id: str) -> List[Snapshot]:
        """Get all snapshots for a pod"""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM snapshots WHERE pod_id = $1 ORDER BY created_at DESC",
                pod_id
            )
            return [Snapshot.from_row(dict(row)) for row in rows]
    
    async def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot"""
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM snapshots WHERE id = $1",
                snapshot_id
            )
            
            await self.log_event('snapshot', snapshot_id, 'deleted', {})
            
            return result == "DELETE 1"
    
    # Event logging
    async def log_event(
        self,
        entity_type: str,
        entity_id: str,
        event_type: str,
        data: Dict[str, Any]
    ):
        """Log an event for audit trail"""
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO events (entity_type, entity_id, event_type, data)
                VALUES ($1, $2, $3, $4)
                """,
                entity_type,
                entity_id,
                event_type,
                json.dumps(data)
            )
    
    async def get_entity_events(
        self,
        entity_type: str,
        entity_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get events for an entity"""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM events 
                WHERE entity_type = $1 AND entity_id = $2
                ORDER BY created_at DESC
                LIMIT $3
                """,
                entity_type,
                entity_id,
                limit
            )
            return [dict(row) for row in rows]
    
    # Cleanup
    async def cleanup_expired_sessions(self) -> List[str]:
        """Find and mark expired sessions"""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                UPDATE sessions 
                SET status = 'destroyed'
                WHERE status IN ('running', 'creating') 
                  AND expires_at < NOW()
                RETURNING id
                """
            )
            
            expired_ids = [row['id'] for row in rows]
            
            for session_id in expired_ids:
                await self.log_event('session', session_id, 'expired', {})
            
            return expired_ids


# Global database instance
_db: Optional[Database] = None


async def get_database() -> Database:
    """Get the global database instance"""
    global _db
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _db


async def init_database(config: DatabaseConfig = None) -> Database:
    """Initialize the global database instance"""
    global _db
    
    if config is None:
        import os
        config = DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "disposable_compute"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )
    
    _db = Database(config)
    await _db.connect()
    return _db


async def close_database():
    """Close the global database connection"""
    global _db
    if _db:
        await _db.disconnect()
        _db = None
