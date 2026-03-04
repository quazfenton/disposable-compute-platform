"""
GPU model for managing GPU resources in disposable compute environments
"""
from dataclasses import dataclass, field
, field

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
import uuid


class GPUStatus(Enum):
    AVAILABLE = "available"
    ALLOCATED = "allocated"
    MAINTENANCE = "maintenance"
    ERROR = "error"
    OFFLINE = "offline"


class GPUVendor(Enum):
    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"


class GPUFamily(Enum):
    # NVIDIA families
    TESLA = "tesla"
    QUADRO = "quadro"
    GEFORCE = "geforce"
    A100 = "a100"
    H100 = "h100"
    V100 = "v100"
    
    # Compatibility aliases/families
    NVIDIA_TESLA = "tesla"
    NVIDIA_A100 = "a100"
    NVIDIA_H100 = "h100"
    NVIDIA_V100 = "v100"
    
    # AMD families
    INSTINCT = "instinct"
    RADEON = "radeon"
    PRO = "pro"
    
    # Intel families
    DATA_CENTER_GPU = "data-center-gpu"
    ARC = "arc"



@dataclass
class GPUSpec:
    """Specification for a GPU"""
    vendor: GPUVendor
    family: GPUFamily
    model: str  # Specific model name
    memory_mb: int  # Total memory in MB
    cuda_cores: Optional[int] = None  # For NVIDIA
    stream_processors: Optional[int] = None  # For AMD
    base_clock_mhz: Optional[int] = None
    boost_clock_mhz: Optional[int] = None
    tdp_watts: Optional[int] = None
    compute_capability: Optional[str] = None  # For NVIDIA (e.g., "8.0")


@dataclass
class GPUDevice:
    """Represents a physical GPU device"""
    id: str  # Usually PCI ID or similar
    spec: GPUSpec
    status: GPUStatus
    node_id: str  # Node where this GPU is located
    driver_version: str
    firmware_version: Optional[str] = None
    utilization_percent: float = 0.0
    temperature_celsius: Optional[float] = None
    power_draw_watts: Optional[float] = None
    power_limit_watts: Optional[float] = None
    memory_used_mb: int = 0
    memory_total_mb: int = 0
    allocated_to_pod: Optional[str] = None  # Pod ID if allocated
    created_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_heartbeat is None:
            self.last_heartbeat = datetime.now()


@dataclass
class GPUAllocation:
    """Represents a GPU allocation to a pod"""
    id: str
    pod_id: str
    gpu_device_id: str
    allocation_time: Optional[datetime] = None
    release_time: Optional[datetime] = None
    status: str = "active"  # active, released, failed
    memory_requested_mb: Optional[int] = None
    compute_requested_percent: Optional[float] = None  # Percentage of compute to allocate

    def __post_init__(self):
        if self.allocation_time is None:
            self.allocation_time = datetime.now()


@dataclass
class GPUConfiguration:
    """Configuration for GPU access in a pod"""
    gpu_type: str  # nvidia, amd, intel
    count: int = 1
    memory_limit_mb: Optional[int] = None
    use_exclusive_mode: bool = False
    driver_capabilities: List[str] = field(default_factory=lambda: ["compute"])


@dataclass
class GPUCluster:
    """Represents a cluster of GPU-enabled nodes"""
    id: str
    name: str
    status: str  # active, maintenance, offline
    total_gpus: int
    available_gpus: int
    allocated_gpus: int
    gpu_types: List[str] = field(default_factory=list)  # List of GPU types available in the cluster
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_updated is None:
            self.last_updated = datetime.now()


@dataclass
class GPUJob:
    """Represents a job running on GPU resources"""
    id: str
    pod_id: str
    gpu_allocation_id: str
    job_type: str  # training, inference, rendering, etc.
    priority: int = 1  # Lower number means higher priority
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"  # pending, running, completed, failed, cancelled
    estimated_runtime_minutes: Optional[int] = None
    actual_runtime_minutes: Optional[int] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
