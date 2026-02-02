from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class PodStatus(str, Enum):
    REQUESTED = "REQUESTED"
    SCHEDULING = "SCHEDULING"
    SCHEDULED = "SCHEDULED"
    PROVISIONING = "PROVISIONING"
    STARTING = "STARTING"
    STREAMING = "STREAMING"
    SNAPSHOT_CREATING = "SNAPSHOT_CREATING"
    SNAPSHOT_COMPLETE = "SNAPSHOT_COMPLETE"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AppType(str, Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"


class PodType(str, Enum):
    CONTAINER = "container"
    VM = "vm"


class SnapshotType(str, Enum):
    DISK = "disk"
    MEMORY = "memory"
    PROJECT = "project"


class PodRequest(BaseModel):
    app_type: AppType
    app_name: str
    app_version: str
    gpu_required: bool = False
    gpu_profile: Optional[str] = None
    min_vram_gb: Optional[int] = 0
    min_cpu_cores: int = 2
    min_memory_gb: int = 4
    storage_gb: int = 10
    duration_estimate: Optional[int] = 60  # minutes
    snapshot_id: Optional[str] = None
    project_files: Optional[List[str]] = []
    user_id: str
    priority: int = 50


class PodSpec(BaseModel):
    id: str
    request: PodRequest
    node_id: Optional[str] = None
    pod_type: PodType
    image: str
    resources: Dict[str, Any]
    environment: Dict[str, str]
    mounts: List[Dict[str, str]]
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PodState(BaseModel):
    id: str
    spec: PodSpec
    status: PodStatus
    container_id: Optional[str] = None
    vm_id: Optional[str] = None
    node_id: Optional[str] = None
    streaming_url: Optional[str] = None
    streaming_agent: Optional[str] = None
    assigned_resources: Optional[Dict[str, Any]] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    terminated_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    snapshots: List[str] = []


class Node(BaseModel):
    id: str
    hostname: str
    ip_address: str
    cpu_total: int
    cpu_available: int
    memory_total_gb: int
    memory_available_gb: int
    gpu_vram_total_gb: int
    gpu_vram_available_gb: int
    storage_total_gb: int
    storage_available_gb: int
    gpu_type: Optional[str] = None
    gpu_count: int = 0
    os_type: str
    location: str
    load_avg: float
    temperature: float
    max_safe_temp: float = 80.0
    is_active: bool = True
    assigned_pods: List[str] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Snapshot(BaseModel):
    id: str
    pod_id: str
    name: str
    snapshot_type: SnapshotType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    size_gb: float
    location: str
    metadata: Dict[str, Any] = {}


class SchedulingResult(BaseModel):
    success: bool
    node_id: Optional[str] = None
    reason: Optional[str] = None
    score: Optional[float] = None


class ResourceUsage(BaseModel):
    cpu_used: float
    memory_used_gb: float
    gpu_vram_used_gb: float
    storage_used_gb: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)