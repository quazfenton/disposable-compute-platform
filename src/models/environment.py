"""
Environment model for managing disposable compute environments
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
import uuid


@dataclass
class Environment:
    """Represents a complete disposable environment with multiple services"""
    id: str
    name: str
    session_id: str
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    
    # Services in this environment
    services: List[Dict] = None  # List of service definitions
    
    # Networking
    network_name: Optional[str] = None
    external_urls: List[str] = None
    
    # Resources
    cpu_limit: Optional[str] = None  # e.g., "1000m"
    memory_limit: Optional[str] = None  # e.g., "1Gi"
    
    # Metadata
    metadata: Dict[str, str] = None
    
    def __post_init__(self):
        if self.services is None:
            self.services = []
        if self.external_urls is None:
            self.external_urls = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ResourceLimits:
    """Resource limits for an environment"""
    cpu: str  # e.g., "1000m", "2"
    memory: str  # e.g., "1Gi", "2Gi"
    disk: str  # e.g., "10Gi"
    network: str  # e.g., "100mbps"


@dataclass
class ServiceHealth:
    """Health status of a service"""
    service_name: str
    status: str  # running, stopped, error, starting
    last_heartbeat: datetime
    error_message: Optional[str] = None
    restart_count: int = 0