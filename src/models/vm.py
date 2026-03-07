"""
VM model for managing virtual machines in disposable compute environments
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class VMStatus(Enum):
    CREATING = "creating"
    PENDING = "pending"
    RUNNING = "running"
    STOPPED = "stopped"
    PAUSED = "paused"
    SUSPENDED = "suspended"
    DESTROYED = "destroyed"
    ERROR = "error"


class VMType(Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    CUSTOM = "custom"


@dataclass
class VMSpec:
    """Specification for a virtual machine"""
    vm_type: VMType
    base_image: str
    cpu_cores: int = 2
    memory_mb: int = 2048
    disk_size_gb: int = 20
    network_interfaces: List[Dict[str, str]] = None
    gpu_passthrough: bool = False
    gpu_config: Optional[Dict[str, Any]] = None
    boot_order: List[str] = None  # e.g., ["cdrom", "hd"]
    
    def __post_init__(self):
        if self.network_interfaces is None:
            self.network_interfaces = [{"type": "bridge", "model": "virtio"}]
        if self.boot_order is None:
            self.boot_order = ["hd"]


@dataclass
class VM:
    """Represents a virtual machine in the disposable compute platform"""
    id: str
    spec: VMSpec
    status: VMStatus
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None

    # Runtime information
    hypervisor_id: Optional[str] = None  # ID in hypervisor (e.g., libvirt UUID)
    disk_path: Optional[str] = None
    network_id: Optional[str] = None
    ip_address: Optional[str] = None
    ssh_port: Optional[int] = None
    spice_port: Optional[int] = None
    vnc_port: Optional[int] = None

    # Application information
    app_name: Optional[str] = None
    app_version: Optional[str] = None
    app_command: Optional[str] = None

    # Resource tracking
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
class Hypervisor:
    """Represents a hypervisor managing VMs"""
    id: str
    name: str
    type: str  # qemu, vmware, virtualbox, etc.
    host_ip: str
    status: str  # active, inactive, maintenance
    capabilities: List[str]  # gpu_passthrough, nested_virt, etc.
    max_vms: int
    current_vms: int
    last_heartbeat: datetime
    version: Optional[str] = None
    api_endpoint: Optional[str] = None
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = []


@dataclass
class VMDisk:
    """Represents a virtual disk for a VM"""
    id: str
    vm_id: str
    path: str
    size_gb: int
    format: str  # qcow2, raw, vmdk, etc.
    backing_file: Optional[str] = None  # Base image if using copy-on-write
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()


@dataclass
class VMNetworkInterface:
    """Represents a network interface for a VM"""
    id: str
    vm_id: str
    interface_type: str  # bridge, nat, host-only
    mac_address: str
    ip_address: Optional[str] = None
    model: str = "virtio"  # virtio, e1000, rtl8139
    connected: bool = True