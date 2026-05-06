"""initial_schema

Revision ID: 358f026a5fbf
Revises: 
Create Date: 2026-03-03 17:52:05.641926

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '358f026a5fbf'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    op.execute("""
    CREATE TABLE users (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        email VARCHAR(255) UNIQUE NOT NULL,
        tier VARCHAR(50) NOT NULL DEFAULT 'free',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        quota_sessions_per_day INTEGER DEFAULT 10,
        quota_max_ttl_minutes INTEGER DEFAULT 120,
        metadata JSONB DEFAULT '{}'
    )
    """)

    op.execute("""
    CREATE TABLE sessions (
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
    )
    """)

    op.execute("""
    CREATE TABLE pods (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        node_id UUID,
        status VARCHAR(50) NOT NULL DEFAULT 'pending',
        spec JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        destroyed_at TIMESTAMP WITH TIME ZONE,
        metadata JSONB DEFAULT '{}'
    )
    """)

    op.execute("""
    CREATE TABLE snapshots (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        pod_id UUID NOT NULL REFERENCES pods(id) ON DELETE CASCADE,
        type VARCHAR(50) NOT NULL,
        storage_path VARCHAR(1000) NOT NULL,
        size_bytes BIGINT DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        parent_id UUID REFERENCES snapshots(id),
        metadata JSONB DEFAULT '{}'
    )
    """)

    op.execute("""
    CREATE TABLE events (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        entity_type VARCHAR(50) NOT NULL,
        entity_id UUID NOT NULL,
        event_type VARCHAR(100) NOT NULL,
        data JSONB DEFAULT '{}',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    )
    """)

    op.execute("CREATE INDEX idx_sessions_user_id ON sessions(user_id)")
    op.execute("CREATE INDEX idx_sessions_status ON sessions(status)")
    op.execute("CREATE INDEX idx_sessions_expires_at ON sessions(expires_at)")
    op.execute("CREATE INDEX idx_pods_session_id ON pods(session_id)")
    op.execute("CREATE INDEX idx_pods_node_id ON pods(node_id)")
    op.execute("CREATE INDEX idx_snapshots_pod_id ON snapshots(pod_id)")
    op.execute("CREATE INDEX idx_events_entity ON events(entity_type, entity_id)")
    op.execute("CREATE INDEX idx_events_created_at ON events(created_at)")

    op.execute("""
    CREATE OR REPLACE FUNCTION update_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """)

    op.execute("""
    CREATE TRIGGER update_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at()
    """)

    op.execute("""
    CREATE TRIGGER update_sessions_updated_at
        BEFORE UPDATE ON sessions
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at()
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS events")
    op.execute("DROP TABLE IF EXISTS snapshots")
    op.execute("DROP TABLE IF EXISTS pods")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at")
