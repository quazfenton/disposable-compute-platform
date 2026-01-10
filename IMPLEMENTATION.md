# Disposable Compute Platform

A comprehensive platform for disposable compute environments supporting three core capabilities:

1. **Preview Environments for Everything** - Ephemeral environments for every PR
2. **"Run This Repo" Button** - Instant runnable environments
3. **Forkable GUI Sessions** - Forkable live GUI application sessions

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    API Layer                                │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │  Preview API    │  │  Run Repo API   │  │  GUI API    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                Shared Platform Layer                        │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │Session Mgmt  │  │Container Orch.   │  │Network Mgmt  │ │
│  └──────────────┘  └──────────────────┘  └──────────────┘ │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │Security Mgmt │  │Snapshot Mgmt     │  │Image Builder │ │
│  └──────────────┘  └──────────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│               Component Implementations                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │Preview Environ. │  │Run This Repo    │  │Forkable GUI │ │
│  │(PR Environments)│  │(Repo Runner)    │  │(GUI Forking)│ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Preview Environments for Everything

**Purpose**: Create complete ephemeral environments for every PR, including databases, workers, cron jobs, and caches.

**Key Features**:
- Parses `.preview.yaml` for service definitions
- Supports multiple service types (web, worker, db, cron, cache)
- Isolated networks per environment
- Automatic cleanup on PR close
- Database volume management per PR

**Implementation**:
- `src/services/preview.py` - Main preview environment manager
- Supports services: web, worker, postgres, mysql, redis, cron
- Database volumes named by PR number for isolation
- Cron job management with scheduling

### 2. "Run This Repo" Button

**Purpose**: Single-click runnable environments for any repository.

**Key Features**:
- Runtime detection (Node.js, Python, Go, Rust, Java)
- Automatic Docker image building
- Default entrypoint resolution
- Shareable links with TTL

**Implementation**:
- `src/services/run_repo.py` - Run repo session manager
- Runtime detector with support for multiple languages
- Image builder for repository-specific images
- Terminal session management

### 3. Forkable GUI Sessions

**Purpose**: Forkable live GUI application sessions with state capture and restoration.

**Key Features**:
- State capture and restoration for GUI apps
- Session forking with independent divergence
- Adapter system for different GUI types
- Lineage tracking between forks

**Implementation**:
- `src/services/fork_gui.py` - Forkable GUI session manager
- State capture adapters (Generic, Three.js, Audio)
- Snapshot management system
- Fork lineage tracking

## Shared Platform Layer

### Data Models (`src/models/`)
- `session.py` - Core session and service definitions
- `environment.py` - Environment and resource management

### Services (`src/services/`)
- `platform.py` - Core platform manager with session lifecycle
- `preview.py` - Preview environment implementation
- `run_repo.py` - Run repo functionality
- `fork_gui.py` - Forkable GUI sessions

### Infrastructure (`src/containers/`, `src/networking/`)
- `orchestrator.py` - Container orchestration
- `router.py` - Networking and routing

### Security (`src/utils/security.py`)
- Resource isolation with cgroups
- Network security and firewall rules
- Access control with tokens
- Security scanning integration

## API Endpoints

### Session Management
- `POST /sessions` - Create new disposable session
- `GET /sessions/{session_id}` - Get session details
- `DELETE /sessions/{session_id}` - Destroy session
- `GET /sessions/{session_id}/logs` - Get session logs
- `WEBSOCKET /ws/logs/{session_id}` - Real-time logs

### Specialized Endpoints
- `POST /sessions/{session_id}/fork` - Fork a GUI session

## Implementation Details

### Preview Environments
The system parses `.preview.yaml` files to understand the services needed:

```yaml
services:
  api:
    type: web
    port: 3000
    run: npm run dev
  worker:
    type: worker
    run: python worker.py
  db:
    type: postgres
    version: "15"
entrypoints:
  terminal: api
```

### Run This Repo
Automatic runtime detection:
1. Check for `package.json` → Node.js
2. Check for `requirements.txt` → Python
3. Check for `go.mod` → Go
4. Fallback to generic

### Forkable GUI Sessions
State capture adapters allow different types of GUI applications to be forked:
- Generic adapter for basic GUI state
- Three.js adapter for 3D applications
- Audio editor adapter for DAW applications

## Security & Isolation

- Container resource limits (CPU, memory, disk)
- Network isolation with rate limiting
- Read-only filesystems where appropriate
- Restricted system calls via seccomp
- Access tokens with TTL
- Automatic cleanup of resources

## Getting Started

### Prerequisites
- Docker
- Python 3.8+
- FastAPI dependencies

### Setup
```bash
pip install -r requirements.txt
```

### Running the API Server
```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## Extending the Platform

The modular architecture allows for easy extension:

1. **New Service Types**: Add to `ServiceDefinition` and implement in orchestrator
2. **New Runtime Detection**: Extend `RuntimeDetector` in run_repo module
3. **New GUI Adapters**: Implement `StateCaptureAdapter` interface
4. **New Security Policies**: Extend `SecurityPolicy` class

## Roadmap

### Phase 1: MVP
- [x] Basic run-repo functionality
- [x] Simple terminal access
- [x] Shareable links
- [x] Automatic cleanup

### Phase 2: Preview Environments
- [x] Multi-service environments
- [x] Database support
- [x] Worker and cron jobs
- [x] Network isolation

### Phase 3: Advanced Features
- [x] Forkable GUI sessions
- [x] State capture and restoration
- [x] Session forking
- [x] Advanced security isolation

## Deployment

The platform can be deployed using the provided Dockerfile and docker-compose.yml, with support for scaling and high availability configurations.

This implementation provides a solid foundation for all three disposable compute concepts with a shared platform layer that enables rapid iteration and feature development.