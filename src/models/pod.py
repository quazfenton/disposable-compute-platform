"""
Pod model for managing disposable compute environments with VM and GPU support
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import uuid


class PodType(Enum):
    CONTAINER = "container"
    VM = "vm"
    HYBRID = "hybrid"


class PodStatus(Enum):
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


class GPUType(Enum):
    NVIDIA_TESLA = "nvidia-tesla"
    NVIDIA_A100 = "nvidia-a100"
    NVIDIA_H100 = "nvidia-h100"
    NVIDIA_V100 = "nvidia-v100"
    AMD_INSTINCT = "amd-instinct"
    AMD_RADEON = "amd-radeon"


@dataclass
class GPUResource:
    """GPU resource specification"""
    gpu_type: GPUType
    count: int = 1
    memory_mb: int = 0  # Memory per GPU in MB
    dedicated: bool = True  # Whether GPUs are exclusively allocated


@dataclass
class ResourceRequirements:
    """Resource requirements for a pod"""
    cpu_cores: float = 1.0
    memory_mb: int = 1024
    storage_gb: int = 10
    gpu_resources: Optional[GPUResource] = None
    network_bandwidth_mbps: int = 100


@dataclass
class PodSpec:
    """Specification for a pod"""
    pod_type: PodType
    app_type: str  # linux, windows, macos, web, etc.
    app_version: str = "latest"
    image: str = ""
    command: Optional[List[str]] = None
    environment: Dict[str, str] = None
    resource_requirements: ResourceRequirements = None
    gpu_required: bool = False
    gpu_config: Optional[GPUResource] = None
    ports: List[int] = None
    volumes: List[str] = None
    network_mode: str = "bridge"
    privileged: bool = False
    
    def __post_init__(self):
        if self.environment is None:
            self.environment = {}
        if self.resource_requirements is None:
            self.resource_requirements = ResourceRequirements()
        if self.ports is None:
            self.ports = []
        if self.volumes is None:
            self.volumes = []


@dataclass
class Pod:
    """Represents a disposable compute pod with VM and GPU support"""
    id: str
    spec: PodSpec
    status: PodStatus
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None

    # Runtime information
    node_id: Optional[str] = None
    container_id: Optional[str] = None
    vm_id: Optional[str] = None
    vm_disk_path: Optional[str] = None
    network_id: Optional[str] = None
    streaming_agent: Optional[str] = None
    streaming_url: Optional[str] = None

    # Resource tracking
    assigned_resources: Optional[ResourceRequirements] = None
    resource_usage: Dict[str, Any] = None

    # Metadata
    metadata: Dict[str, str] = None
    failure_reason: Optional[str] = None

    def __post_init__(self):
        if self.resource_usage is None:
            self.resource_usage = {}
        if self.metadata is None:
            self.metadata = {}


@dataclass
class NodeResources:
    """Available resources on a compute node"""
    total_cpu_cores: float
    available_cpu_cores: float
    total_memory_mb: int
    available_memory_mb: int
    total_storage_gb: int
    available_storage_gb: int
    total_gpus: int
    available_gpus: int
    gpu_type: Optional[GPUType] = None
    network_bandwidth_mbps: int = 1000


@dataclass
class ComputeNode:
    """Represents a compute node in the cluster"""
    id: str
    hostname: str
    ip_address: str
    resources: NodeResources
    status: str  # active, inactive, maintenance
    capabilities: List[str]  # gpu, vm, container, etc.
    last_heartbeat: datetime
    gpu_info: Optional[Dict[str, Any]] = None  # GPU details if available
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []
        if self.gpu_info is None:
            self.gpu_info = {}