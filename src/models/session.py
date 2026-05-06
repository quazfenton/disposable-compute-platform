"""
Session model for managing disposable compute environments
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import uuid


class SessionType(str, Enum):
    PREVIEW = "preview"
    RUN_REPO = "run_repo"
    FORK_GUI = "fork_gui"


class SessionStatus(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    DESTROYED = "destroyed"
    ERROR = "error"


@dataclass
class Session:
    """Represents a disposable compute session"""
    id: str
    type: SessionType
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    user_id: str = "default"
    expires_at: Optional[datetime] = None
    
    # Repository information
    repo_url: Optional[str] = None
    repo_ref: Optional[str] = None  # branch, tag, or commit hash
    pr_number: Optional[int] = None
    
    # Container information
    container_id: Optional[str] = None
    network_id: Optional[str] = None
    ports: Dict[str, int] = field(default_factory=dict)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Lifecycle control
    _destroy_lock: bool = False


@dataclass
class ServiceDefinition:
    """Defines a service within a session"""
    name: str
    type: str  # web, worker, db, cron, cli
    image: str
    command: Optional[str] = None
    port: Optional[int] = None
    env: Dict[str, str] = field(default_factory=dict)
    volumes: List[str] = field(default_factory=list)


@dataclass
class Snapshot:
    """Represents a snapshot of a session state"""
    id: str
    session_id: str
    created_at: datetime
    parent_snapshot_id: Optional[str] = None
    state_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, str] = field(default_factory=dict)
