# Source Code Structure

This directory contains the source code for the Disposable Compute Platform.

## Directory Structure

```
src/
├── api/                 # API layer (FastAPI endpoints)
├── containers/          # Container orchestration
├── models/              # Data models
│   ├── session.py       # Session and service definitions
│   ├── environment.py   # Environment definitions
│   ├── pod.py           # Pod model for VM/container orchestration
│   ├── vm.py            # VM model for virtual machines
│   └── gpu.py           # GPU model for GPU resource management
├── networking/          # Network management
├── orchestrator/        # Advanced orchestration (VMs, GPU support)
│   └── orchestrator.py  # Advanced orchestrator with VM and GPU support
├── scheduler/           # Scheduling logic
│   └── scheduler.py     # GPU-aware scheduler
├── services/            # Core platform services
│   ├── platform.py      # Main platform manager
│   ├── preview.py       # Preview environment manager
│   ├── run_repo.py      # Run-repo functionality
│   └── fork_gui.py      # Forkable GUI sessions
├── storage/             # Storage management
│   └── storage_manager.py # Volume, snapshot, and backup management
├── streaming/           # GUI streaming
│   └── streaming_server.py # WebRTC/VNC streaming server
├── types/               # Type definitions
│   └── platform_types.py # Enums, DTOs, and protocols
└── utils/               # Utility functions
    ├── security.py      # Security and isolation
    ├── monitoring.py    # Monitoring utilities
    └── helpers.py       # Helper functions
```

## Key Components

### Core Models
- **Session**: Represents a disposable compute session
- **Pod**: Represents a compute unit (container, VM, or hybrid)
- **VM**: Represents a virtual machine
- **GPU**: Represents GPU resources and devices

### Orchestration
- **ContainerOrchestrator**: Manages Docker containers
- **AdvancedOrchestrator**: Manages both containers and VMs with GPU support
- **Scheduler**: Intelligent placement of workloads based on resources

### Storage
- **StorageManager**: Manages volumes, snapshots, and backups
- **VolumeManager**: Handles individual storage volumes
- **SnapshotManager**: Manages point-in-time copies of volumes

### Streaming
- **StreamingManager**: Provides real-time GUI application streaming
- **StreamServer**: Handles WebRTC/VNC connections
- **InputHandler**: Processes client input events

### Types
- **platform_types**: Standardized type definitions, enums, and protocols

## Architecture

The platform follows a modular architecture where each component has a specific responsibility:

1. **API Layer**: Provides REST/WS interfaces
2. **Services**: Implements business logic for each feature
3. **Orchestrator**: Manages compute resources (containers, VMs, GPUs)
4. **Storage**: Manages persistent and ephemeral storage
5. **Streaming**: Handles GUI application streaming
6. **Models**: Defines data structures
7. **Utils**: Provides helper functions and utilities

This architecture allows for easy extension and maintenance of the platform.