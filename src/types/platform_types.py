"""
Type definitions for disposable compute platform
"""
from enum import Enum
from typing import Union, Dict, List, Optional, Callable, Any, Protocol
from dataclasses import dataclass
from datetime import datetime


# Basic Type Aliases
SessionId = str
PodId = str
NodeId = str
VolumeId = str
SnapshotId = str
StreamId = str
UserId = str
GroupId = str


# Enums for platform types
class SessionType(str, Enum):
    PREVIEW = "preview"
    RUN_REPO = "run_repo"
    FORK_GUI = "fork_gui"


class SessionStatus(str, Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    DESTROYED = "destroyed"
    ERROR = "error"


class PodType(str, Enum):
    CONTAINER = "container"
    VM = "vm"
    HYBRID = "hybrid"


class PodStatus(str, Enum):
    REQUESTED = "requested"
    SCHEDULING = "scheduling"
    SCHEDULED = "scheduled"
    PROVISIONING = "provisioning"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VMType(str, Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    CUSTOM = "custom"


class VMStatus(str, Enum):
    CREATING = "creating"
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    DESTROYED = "destroyed"
    ERROR = "error"


class GPUVendor(str, Enum):
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"


class GPUFamily(str, Enum):
    # NVIDIA families
    TESLA = "tesla"
    QUADRO = "quadro"
    GEFORCE = "geforce"
    A100 = "a100"
    H100 = "h100"
    V100 = "v100"
    
    # AMD families
    INSTINCT = "instinct"
    RADEON = "radeon"
    PRO = "pro"
    
    # Intel families
    DATA_CENTER_GPU = "data-center-gpu"
    ARC = "arc"


class GPUStatus(str, Enum):
    AVAILABLE = "available"
    ALLOCATED = "allocated"
    MAINTENANCE = "maintenance"
    ERROR = "error"
    OFFLINE = "offline"


class StorageClass(str, Enum):
    SSD = "ssd"
    HDD = "hdd"
    NVME = "nvme"
    NETWORK = "network"


class StreamType(str, Enum):
    WEBRTC = "webrtc"
    VNC = "vnc"
    RDP = "rdp"
    CUSTOM = "custom"


class ResourceType(str, Enum):
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    GPU = "gpu"
    NETWORK = "network"


# Protocol definitions for interfaces
class SessionManagerInterface(Protocol):
    """Protocol for session management interface"""
    
    async def create_session(self, session_type: SessionType, repo_url: str,
                           repo_ref: Optional[str] = None, pr_number: Optional[int] = None,
                           ttl_minutes: int = None) -> Any:
        ...
    
    async def destroy_session(self, session_id: SessionId) -> None:
        ...
    
    async def get_session_logs(self, session_id: SessionId, service_name: str = "main", lines: int = 100) -> str:
        ...


class OrchestratorInterface(Protocol):
    """Protocol for orchestrator interface"""
    
    async def create_pod(self, pod_spec: Any) -> PodId:
        ...
    
    async def start_pod(self, pod_id: PodId) -> None:
        ...
    
    async def stop_pod(self, pod_id: PodId) -> None:
        ...
    
    async def destroy_pod(self, pod_id: PodId) -> None:
        ...


class StorageManagerInterface(Protocol):
    """Protocol for storage management interface"""
    
    async def create_volume(self, name: str, size_gb: int, storage_class: str = "ssd") -> Any:
        ...
    
    async def attach_volume_to_pod(self, volume_id: VolumeId, pod_id: PodId) -> bool:
        ...
    
    async def detach_volume_from_pod(self, volume_id: VolumeId, pod_id: PodId) -> bool:
        ...
    
    async def delete_volume(self, volume_id: VolumeId) -> bool:
        ...


class StreamManagerInterface(Protocol):
    """Protocol for streaming management interface"""
    
    async def start_pod_streaming(self, pod_id: PodId, stream_type: str = "webrtc",
                                resolution: str = "1920x1080", fps: int = 30) -> StreamId:
        ...
    
    async def stop_pod_streaming(self, pod_id: PodId) -> None:
        ...
    
    async def get_stream_url(self, pod_id: PodId) -> Optional[str]:
        ...


# Data Transfer Objects (DTOs)
@dataclass
class SessionRequestDTO:
    """Data transfer object for session creation requests"""
    type: SessionType
    repo_url: str
    repo_ref: Optional[str] = None
    pr_number: Optional[int] = None
    ttl_minutes: Optional[int] = None
    gpu_required: bool = False
    resource_requirements: Optional[Dict[str, Any]] = None


@dataclass
class PodSpecDTO:
    """Data transfer object for pod specifications"""
    pod_type: PodType
    app_type: str
    app_version: str = "latest"
    image: str = ""
    command: Optional[List[str]] = None
    environment: Dict[str, str] = None
    resource_requirements: Optional[Dict[str, Any]] = None
    gpu_required: bool = False
    gpu_config: Optional[Dict[str, Any]] = None
    ports: List[int] = None
    volumes: List[str] = None
    network_mode: str = "bridge"
    privileged: bool = False
    
    def __post_init__(self):
        if self.environment is None:
            self.environment = {}
        if self.ports is None:
            self.ports = []
        if self.volumes is None:
            self.volumes = []


@dataclass
class ResourceRequirementsDTO:
    """Data transfer object for resource requirements"""
    cpu_cores: float = 1.0
    memory_mb: int = 1024
    storage_gb: int = 10
    gpu_count: int = 0
    gpu_type: Optional[GPUFamily] = None
    network_bandwidth_mbps: int = 100


@dataclass
class StreamConfigDTO:
    """Data transfer object for streaming configuration"""
    stream_type: StreamType = StreamType.WEBRTC
    resolution: str = "1920x1080"
    fps: int = 30
    bitrate_kbps: int = 8192
    codec: str = "h264"
    enable_audio: bool = True
    enable_clipboard: bool = True
    enable_file_transfer: bool = False


@dataclass
class HealthStatusDTO:
    """Data transfer object for health status"""
    service: str
    status: str  # healthy, warning, error
    timestamp: datetime
    details: Optional[Dict[str, Any]] = None


# Event types for pub/sub system
class EventType(str, Enum):
    SESSION_CREATED = "session.created"
    SESSION_STARTED = "session.started"
    SESSION_STOPPED = "session.stopped"
    SESSION_DESTROYED = "session.destroyed"
    POD_SCHEDULED = "pod.scheduled"
    POD_STARTED = "pod.started"
    POD_STOPPED = "pod.stopped"
    POD_FAILED = "pod.failed"
    RESOURCE_EXHAUSTED = "resource.exhausted"
    NODE_UNAVAILABLE = "node.unavailable"
    STREAM_STARTED = "stream.started"
    STREAM_STOPPED = "stream.stopped"


@dataclass
class EventDTO:
    """Data transfer object for events"""
    type: EventType
    source: str  # Component that generated the event
    timestamp: datetime
    payload: Dict[str, Any]
    correlation_id: Optional[str] = None


# Configuration types
@dataclass
class PlatformConfigDTO:
    """Configuration for the platform"""
    domain: str = "preview.yourapp.dev"
    default_ttl: int = 30  # minutes
    max_ttl: int = 1440  # 24 hours
    storage_path: str = "/tmp/disposable-storage"
    max_concurrent_sessions: int = 100
    enable_gpu_support: bool = True
    enable_vm_support: bool = True
    enable_streaming: bool = True
    streaming_port: int = 8765


@dataclass
class NodeConfigDTO:
    """Configuration for a compute node"""
    node_id: NodeId
    hostname: str
    ip_address: str
    max_cpu_cores: float
    max_memory_mb: int
    max_storage_gb: int
    max_gpus: int
    gpu_type: Optional[GPUFamily] = None
    enabled: bool = True


# Callback types
OnSessionEventCallback = Callable[[SessionId, SessionStatus], None]
OnPodEventCallback = Callable[[PodId, PodStatus], None]
OnStreamEventCallback = Callable[[StreamId, str], None]  # stream_id, status
OnResourceEventCallback = Callable[[str, ResourceType, float], None]  # resource_id, type, utilization


# Response types
@dataclass
class ApiResponse:
    """Standard API response wrapper"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    code: int = 200


@dataclass
class SessionInfoResponse:
    """Response for session information"""
    id: SessionId
    type: SessionType
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]
    repo_url: Optional[str]
    repo_ref: Optional[str]
    pr_number: Optional[int]
    ports: Dict[str, int]
    metadata: Dict[str, str]
    streaming_url: Optional[str] = None


@dataclass
class ResourceUsageResponse:
    """Response for resource usage"""
    cpu_percent: float
    memory_mb_used: int
    memory_mb_total: int
    storage_gb_used: float
    storage_gb_total: float
    gpu_utilization: Optional[float] = None
    gpu_memory_used_mb: Optional[int] = None
    gpu_memory_total_mb: Optional[int] = None


# Utility types
JSONValue = Union[str, int, float, bool, List[Any], Dict[str, Any], None]
QueryParam = Union[str, int, float, bool]
Headers = Dict[str, str]