# Advanced Components Documentation

## Table of Contents
1. [Pod Model](#pod-model)
2. [VM Model](#vm-model)
3. [GPU Model](#gpu-model)
4. [Advanced Orchestrator](#advanced-orchestrator)
5. [Scheduler](#scheduler)
6. [Storage Manager](#storage-manager)
7. [Streaming Server](#streaming-server)
8. [Type Definitions](#type-definitions)

## Pod Model

The Pod model represents a disposable compute unit that can be either a container, VM, or hybrid environment.

### Key Features
- Supports multiple pod types (container, VM, hybrid)
- Resource requirements specification
- GPU resource allocation
- Lifecycle management

### Usage Example
```python
from src.models.pod import Pod, PodSpec, PodType, ResourceRequirements, GPUResource, GPUType

# Create a pod specification
pod_spec = PodSpec(
    pod_type=PodType.VM,
    app_type="linux",
    app_version="ubuntu-20.04",
    image="ubuntu:20.04",
    resource_requirements=ResourceRequirements(
        cpu_cores=2.0,
        memory_mb=4096,
        storage_gb=20,
        gpu_resources=GPUResource(
            gpu_type=GPUType.NVIDIA_TESLA,
            count=1,
            memory_mb=8192
        )
    ),
    gpu_required=True
)

# Create a pod instance
pod = Pod(
    id="my-pod-123",
    spec=pod_spec,
    status=PodStatus.CREATING,
    created_at=datetime.now(),
    updated_at=datetime.now()
)
```

## VM Model

The VM model manages virtual machine instances within the disposable compute platform.

### Key Features
- VM lifecycle management
- Disk and network interface management
- Hypervisor integration
- Different VM types (Linux, Windows, macOS)

### Usage Example
```python
from src.models.vm import VM, VMSpec, VMType

# Create a VM specification
vm_spec = VMSpec(
    vm_type=VMType.LINUX,
    base_image="ubuntu:20.04",
    cpu_cores=2,
    memory_mb=4096,
    disk_size_gb=30,
    gpu_passthrough=True
)

# Create a VM instance
vm = VM(
    id="my-vm-123",
    spec=vm_spec,
    status=VMStatus.CREATING,
    created_at=datetime.now(),
    updated_at=datetime.now()
)
```

## GPU Model

The GPU model handles GPU resource management and allocation for compute-intensive tasks.

### Key Features
- GPU device tracking
- Allocation and deallocation management
- Multiple GPU vendor support (NVIDIA, AMD, Intel)
- GPU family classification

### Usage Example
```python
from src.models.gpu import GPUDevice, GPUVendor, GPUFamily, GPUStatus, GPUSpec

# Create a GPU specification
gpu_spec = GPUSpec(
    vendor=GPUVendor.NVIDIA,
    family=GPUFamily.A100,
    model="NVIDIA A100 80GB PCIe",
    memory_mb=81920,  # 80GB
    cuda_cores=6912
)

# Create a GPU device
gpu = GPUDevice(
    id="gpu-nvidia-001",
    spec=gpu_spec,
    status=GPUStatus.AVAILABLE,
    node_id="compute-node-1",
    driver_version="470.123"
)
```

## Advanced Orchestrator

The Advanced Orchestrator manages both container and VM workloads with GPU support.

### Key Features
- Hybrid workload orchestration (containers and VMs)
- GPU resource allocation
- Pod lifecycle management
- Integration with container and VM orchestrators

### Usage Example
```python
from src.orchestrator.orchestrator import AdvancedOrchestrator

# Initialize the orchestrator
orchestrator = AdvancedOrchestrator()

# Create a pod
pod_id = await orchestrator.create_pod(pod_spec)

# Start the pod
await orchestrator.start_pod(pod_id)

# Stop the pod
await orchestrator.stop_pod(pod_id)

# Destroy the pod
await orchestrator.destroy_pod(pod_id)
```

## Scheduler

The Scheduler handles intelligent placement of pods based on resource requirements and availability.

### Key Features
- GPU-aware scheduling
- Priority-based queueing
- Node selection algorithms
- Resource constraint checking

### Usage Example
```python
from src.scheduler.scheduler import Scheduler

# Initialize the scheduler with an orchestrator
scheduler = Scheduler(orchestrator)

# Add compute nodes
scheduler.add_node(compute_node)

# Submit a pod request
pod_id = await scheduler.submit_pod_request(pod_spec, priority=1)

# Start the scheduler loop
await scheduler.start_scheduler()
```

## Storage Manager

The Storage Manager handles persistent and ephemeral storage for pods.

### Key Features
- Volume creation and management
- Snapshot and backup capabilities
- Multiple storage classes (SSD, HDD, NVMe)
- Volume attachment/detachment

### Usage Example
```python
from src.storage.storage_manager import StorageManager

# Initialize the storage manager
storage_manager = StorageManager(base_storage_path="/var/lib/disposable-storage")
await storage_manager.initialize()

# Create an ephemeral volume for a pod
volume = await storage_manager.create_ephemeral_volume("pod-123", size_gb=10)

# Create a persistent volume
persistent_volume = await storage_manager.create_persistent_volume("data-volume", size_gb=50)

# Create a snapshot
snapshot = await storage_manager.snapshot_manager.create_snapshot(volume.id, "Backup before update")

# Clean up pod volumes
await storage_manager.cleanup_pod_volumes("pod-123")
```

## Streaming Server

The Streaming Server provides real-time GUI application streaming capabilities.

### Key Features
- WebRTC, VNC, and RDP support
- Input event handling
- Quality adaptation
- Metrics collection
- Low-latency streaming

### Usage Example
```python
from src.streaming.streaming_server import StreamingManager

# Initialize the streaming manager
streaming_manager = StreamingManager()
await streaming_manager.initialize()

# Start streaming for a pod
session_id = await streaming_manager.start_pod_streaming(
    pod_id="pod-123",
    stream_type="webrtc",
    resolution="1920x1080",
    fps=30
)

# Get the streaming URL
stream_url = await streaming_manager.get_stream_url("pod-123")

# Get streaming status
status = streaming_manager.get_streaming_status("pod-123")

# Stop streaming
await streaming_manager.stop_pod_streaming("pod-123")
```

## Type Definitions

The Type Definitions module provides standardized type annotations and protocols for the platform.

### Key Features
- Enum definitions for all major types
- Protocol interfaces for components
- DTOs for data transfer
- Type aliases for common identifiers

### Usage Example
```python
from src.types.platform_types import (
    SessionType, PodType, GPUVendor, 
    SessionRequestDTO, PodSpecDTO, 
    SessionManagerInterface
)

# Using enums
session_type = SessionType.PREVIEW
pod_type = PodType.VM
gpu_vendor = GPUVendor.NVIDIA

# Using DTOs
session_request = SessionRequestDTO(
    type=SessionType.RUN_REPO,
    repo_url="https://github.com/example/repo.git",
    gpu_required=True
)

pod_spec = PodSpecDTO(
    pod_type=PodType.CONTAINER,
    app_type="web",
    resource_requirements={
        "cpu_cores": 2.0,
        "memory_mb": 4096
    }
)

# Using protocols
class MySessionManager:
    async def create_session(self, session_type, repo_url, repo_ref=None, pr_number=None, ttl_minutes=None):
        # Implementation
        pass
    
    async def destroy_session(self, session_id):
        # Implementation
        pass
    
    async def get_session_logs(self, session_id, service_name="main", lines=100):
        # Implementation
        pass

# This class implements the SessionManagerInterface protocol
my_manager: SessionManagerInterface = MySessionManager()
```

## Integration Example

Here's how all components work together:

```python
from src.orchestrator.orchestrator import AdvancedOrchestrator
from src.scheduler.scheduler import Scheduler
from src.storage.storage_manager import StorageManager
from src.streaming.streaming_server import StreamingManager

# Initialize all components
orchestrator = AdvancedOrchestrator()
scheduler = Scheduler(orchestrator)
storage_manager = StorageManager()
streaming_manager = StreamingManager()

# Initialize managers
await storage_manager.initialize()
await streaming_manager.initialize()

# Add compute nodes to scheduler
scheduler.add_node(compute_node)

# Create a pod specification with GPU requirements
pod_spec = PodSpec(
    pod_type=PodType.HYBRID,
    app_type="gpu-accelerated-app",
    resource_requirements=ResourceRequirements(
        cpu_cores=4.0,
        memory_mb=8192,
        storage_gb=50,
        gpu_resources=GPUResource(gpu_type=GPUType.NVIDIA_A100, count=1)
    ),
    gpu_required=True
)

# Schedule the pod
pod_id = await scheduler.submit_pod_request(pod_spec, priority=1)

# Create storage for the pod
volume = await storage_manager.create_ephemeral_volume(pod_id, size_gb=20)

# Start streaming for the pod
stream_session_id = await streaming_manager.start_pod_streaming(pod_id)

# Later, clean up resources
await streaming_manager.stop_pod_streaming(pod_id)
await storage_manager.cleanup_pod_volumes(pod_id)
await orchestrator.destroy_pod(pod_id)
```

This documentation covers the advanced components of the disposable compute platform, showing how they integrate to provide a comprehensive solution for disposable compute environments with VM and GPU support.