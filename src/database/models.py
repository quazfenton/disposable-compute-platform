"""
Database models and connection management for disposable compute platform
"""
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from dataclasses import dataclass, field

# Try to import asyncpg, fall back to mock if not available
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None
    ASYNCPG_AVAILABLE = False


class SessionStatus(Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    DESTROYED = "destroyed"
    ERROR = "error"


class SessionType(Enum):
    PREVIEW = "preview"
    RUN_REPO = "run_repo"
    FORK_GUI = "fork_gui"


class SnapshotType(Enum):
    DISK = "disk"
    MEMORY = "memory"
    PROJECT = "project"


@dataclass
class Session:
    """Database model for sessions"""
    id: str
    type: SessionType
    status: SessionStatus
    user_id: str
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    repo_url: Optional[str] = None
    repo_ref: Optional[str] = None
    pr_number: Optional[int] = None
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_row(cls, row: Dict) -> 'Session':
        """Create Session from database row"""
        return cls(
            id=str(row['id']),
            type=SessionType(row['type']),
            status=SessionStatus(row['status']),
            user_id=str(row['user_id']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            expires_at=row.get('expires_at'),
            repo_url=row.get('repo_url'),
            repo_ref=row.get('repo_ref'),
            pr_number=row.get('pr_number'),
            config=row.get('config', {}),
            metadata=row.get('metadata', {})
        )


@dataclass
class Pod:
    """Database model for pods"""
    id: str
    session_id: str
    node_id: Optional[str]
    status: str
    spec: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    destroyed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_row(cls, row: Dict) -> 'Pod':
        """Create Pod from database row"""
        return cls(
            id=str(row['id']),
            session_id=str(row['session_id']),
            node_id=str(row['node_id']) if row.get('node_id') else None,
            status=row['status'],
            spec=row.get('spec', {}),
            created_at=row['created_at'],
            destroyed_at=row.get('destroyed_at'),
            metadata=row.get('metadata', {})
        )


@dataclass
class Snapshot:
    """Database model for snapshots"""
    id: str
    pod_id: str
    type: SnapshotType
    storage_path: str
    size_bytes: int
    created_at: datetime
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_row(cls, row: Dict) -> 'Snapshot':
        """Create Snapshot from database row"""
        return cls(
            id=str(row['id']),
            pod_id=str(row['pod_id']),
            type=SnapshotType(row['type']),
            storage_path=row['storage_path'],
            size_bytes=row['size_bytes'],
            created_at=row['created_at'],
            parent_id=str(row['parent_id']) if row.get('parent_id') else None,
            metadata=row.get('metadata', {})
        )


@dataclass
class User:
    """Database model for users"""
    id: str
    email: str
    tier: str  # free, pro, enterprise
    created_at: datetime
    updated_at: datetime
    quota_sessions_per_day: int = 10
    quota_max_ttl_minutes: int = 120
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_row(cls, row: Dict) -> 'User':
        """Create User from database row"""
        return cls(
            id=str(row['id']),
            email=row['email'],
            tier=row['tier'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            quota_sessions_per_day=row.get('quota_sessions_per_day', 10),
            quota_max_ttl_minutes=row.get('quota_max_ttl_minutes', 120),
            metadata=row.get('metadata', {})
        )


# SQL Schema
SCHEMA_SQL = """
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    tier VARCHAR(50) NOT NULL DEFAULT 'free',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    quota_sessions_per_day INTEGER DEFAULT 10,
    quota_max_ttl_minutes INTEGER DEFAULT 120,
    metadata JSONB DEFAULT '{}'
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'creating',
    user_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    repo_url VARCHAR(1000),
    repo_ref VARCHAR(500),
    pr_number INTEGER,
    config JSONB DEFAULT '{}',
    metadata JSONB DEFAULT '{}'
);

-- Pods table
CREATE TABLE IF NOT EXISTS pods (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    node_id UUID,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    spec JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    destroyed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'
);

-- Snapshots table
CREATE TABLE IF NOT EXISTS snapshots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pod_id UUID NOT NULL REFERENCES pods(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    storage_path VARCHAR(1000) NOT NULL,
    size_bytes BIGINT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    parent_id UUID REFERENCES snapshots(id),
    metadata JSONB DEFAULT '{}'
);

-- Events table for audit trail
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_pods_session_id ON pods(session_id);
CREATE INDEX IF NOT EXISTS idx_pods_node_id ON pods(node_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_pod_id ON snapshots(pod_id);
CREATE INDEX IF NOT EXISTS idx_events_entity ON events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);

-- Update timestamp trigger function
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to tables
DROP TRIGGER IF EXISTS update_users_updated_at ON users;
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

DROP TRIGGER IF EXISTS update_sessions_updated_at ON sessions;
CREATE TRIGGER update_sessions_updated_at
    BEFORE UPDATE ON sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
"""
