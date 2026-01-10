# Disposable Compute Platform - Technical Documentation

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Core Components](#core-components)
3. [API Documentation](#api-documentation)
4. [Implementation Details](#implementation-details)
5. [Security & Isolation](#security--isolation)
6. [Deployment Guide](#deployment-guide)
7. [Extending the Platform](#extending-the-platform)
8. [Development Guide](#development-guide)

## Architecture Overview

The Disposable Compute Platform is built with a modular architecture that supports three core capabilities while sharing a common infrastructure layer.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API Layer                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │  Preview API    │  │  Run Repo API   │  │  Fork GUI API   │              │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Shared Platform Layer                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐              │
│  │Session Mgmt  │  │Container Orch.   │  │Network Mgmt      │              │
│  └──────────────┘  └──────────────────┘  └──────────────────┘              │
│  ┌──────────────┐  ┌──────────────────┐  ┌──────────────────┐              │
│  │Security Mgmt │  │Snapshot Mgmt     │  │Image Builder     │              │
│  └──────────────┘  └──────────────────┘  └──────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Component Implementations                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │Preview Environ. │  │Run This Repo    │  │Forkable GUI     │              │
│  │(PR Environments)│  │(Repo Runner)    │  │(GUI Forking)    │              │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Component Relationships

The platform follows a layered architecture where each layer provides services to the layer above:

- **API Layer**: Provides REST/WS interfaces to external users
- **Platform Layer**: Core orchestration and management services
- **Component Layer**: Feature-specific implementations
- **Infrastructure Layer**: Low-level container and network management

## Core Components

### 1. Preview Environments for Everything

#### Purpose
Create complete ephemeral environments for every PR, including databases, workers, cron jobs, and caches.

#### Key Features
- Parses `.preview.yaml` for service definitions
- Supports multiple service types (web, worker, db, cron, cache)
- Isolated networks per environment
- Automatic cleanup on PR close
- Database volume management per PR

#### Implementation Details

**Service Definition Format:**
```yaml
services:
  api:
    type: web
    port: 3000
    run: npm run dev
    image: node:18-alpine
    env:
      NODE_ENV: development
  worker:
    type: worker
    run: python worker.py
    image: python:3.11-slim
  db:
    type: postgres
    version: "15"
    image: postgres:15-alpine
    env:
      POSTGRES_DB: myapp
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
  redis:
    type: cache
    image: redis:alpine
  cron:
    type: cron
    schedule: "*/5 * * * *"
    run: node jobs/cleanup.js
    image: node:18-alpine

entrypoints:
  terminal: api
```

**Database Management:**
- Named Docker volumes per PR: `db-preview-pr{pr_number}-{db_name}`
- Seed support from migrations, SQL dumps, or main branch snapshots
- Automatic cleanup on PR close

**Cron Job Management:**
- Integration with `supercronic` for reliable scheduling
- Per-job logging and monitoring
- Schedule validation

#### Code Structure
- `src/services/preview.py` - Main preview environment manager
- `src/models/session.py` - Session and service definitions
- `src/containers/orchestrator.py` - Container orchestration

### 2. "Run This Repo" Button

#### Purpose
Single-click runnable environments for any repository.

#### Key Features
- Runtime detection (Node.js, Python, Go, Rust, Java)
- Automatic Docker image building
- Default entrypoint resolution
- Shareable links with TTL

#### Runtime Detection Logic

The system detects runtimes in this order:
1. **Node.js**: Check for `package.json`
2. **Python**: Check for `requirements.txt`, `pyproject.toml`, or `setup.py`
3. **Go**: Check for `go.mod` or `main.go`
4. **Rust**: Check for `Cargo.toml` or `src/main.rs`
5. **Java**: Check for `pom.xml`, `build.gradle`, or `Main.java`
6. **Fallback**: Generic environment

#### Default Entrypoint Resolution

The system resolves entrypoints in this order:
1. `run.yaml` configuration file
2. `package.json` → `scripts.start` (for Node.js)
3. `main.py` (for Python)
4. `main.go` (for Go)
5. `Cargo.toml` → `[package]` → `name` (for Rust)
6. Generic fallback

#### Code Structure
- `src/services/run_repo.py` - Run repo session manager
- `src/services/platform.py` - Base session management
- `src/containers/orchestrator.py` - Container orchestration

### 3. Forkable GUI Sessions

#### Purpose
Forkable live GUI application sessions with state capture and restoration.

#### Key Features
- State capture and restoration for GUI apps
- Session forking with independent divergence
- Adapter system for different GUI types
- Lineage tracking between forks

#### State Capture Architecture

The system uses an adapter pattern for different GUI application types:

**Generic Adapter:**
- Basic state capture (open files, settings, UI state)
- Suitable for most desktop applications

**Three.js Adapter:**
- 3D scene graph capture
- Camera position and object states
- Material and texture tracking

**Audio Editor Adapter:**
- Timeline position and duration
- Track states and effects
- Parameter settings

#### Forking Mechanism

The forking process:
1. Create snapshot of current state
2. Launch new session with same configuration
3. Restore state from snapshot
4. Track lineage relationships
5. Allow independent divergence

#### Code Structure
- `src/services/fork_gui.py` - Forkable GUI session manager
- `src/services/platform.py` - Base session management
- `src/utils/security.py` - Security isolation

## API Documentation

### Base URL
`http://localhost:8000` (or your deployment URL)

### Authentication
Most endpoints are public for development. In production, implement authentication as needed.

### Session Management Endpoints

#### Create Session
```
POST /sessions
```

**Request Body:**
```json
{
  "type": "preview|run_repo|fork_gui",
  "repo_url": "https://github.com/user/repo.git",
  "repo_ref": "main|feature-branch|v1.0.0",
  "pr_number": 123,
  "ttl_minutes": 60
}
```

**Response:**
```json
{
  "session_id": "sess-20231201-123456-abcd",
  "status": "creating|running|stopped|destroyed|error",
  "external_urls": ["https://abcd1234.preview.yourapp.dev"],
  "created_at": "2023-12-01T12:34:56.789Z"
}
```

#### Get Session Details
```
GET /sessions/{session_id}
```

**Response:**
```json
{
  "id": "sess-20231201-123456-abcd",
  "type": "preview",
  "status": "running",
  "created_at": "2023-12-01T12:34:56.789Z",
  "updated_at": "2023-12-01T12:35:00.123Z",
  "expires_at": "2023-12-01T13:34:56.789Z",
  "repo_url": "https://github.com/user/repo.git",
  "repo_ref": "feature-branch",
  "pr_number": 123,
  "ports": {
    "api": 3000,
    "worker": 0
  },
  "metadata": {}
}
```

#### Destroy Session
```
DELETE /sessions/{session_id}
```

**Response:**
```json
{
  "message": "Session sess-20231201-123456-abcd destroyed successfully"
}
```

#### Get Session Logs
```
GET /sessions/{session_id}/logs?service=main&lines=100
```

**Response:**
```json
{
  "service": "main",
  "logs": "Log output here..."
}
```

#### Real-time Logs WebSocket
```
WS /ws/logs/{session_id}?service=main
```

#### Fork Session
```
POST /sessions/{session_id}/fork
```

**Request Body:**
```json
{
  "snapshot_id": "snapshot-20231201-123456-efgh"
}
```

**Response:**
```json
{
  "new_session_id": "fork-sess-20231201-123456-abcd-1234",
  "status": "created"
}
```

### Health Check
```
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2023-12-01T12:34:56.789Z"
}
```

## Implementation Details

### Session Lifecycle

Each session goes through these states:

```
CREATING → RUNNING → STOPPED → DESTROYED
    ↓           ↓         ↓         ↓
  (setup)   (active)  (cleanup) (cleanup)
```

### Container Orchestration

The platform uses Docker for container orchestration with the following principles:

1. **Isolation**: Each environment gets its own Docker network
2. **Resource Limits**: CPU, memory, and disk quotas enforced
3. **Security**: Read-only root filesystems where possible
4. **Cleanup**: Automatic removal on session destruction

### Networking Model

**Internal Networking:**
- Each environment gets an isolated Docker network
- Internal DNS: `service-name.environment-network.internal`
- Services can communicate within the environment

**External Access:**
- Subdomain routing: `{session_id_prefix}.domain`
- Port mapping for services that expose ports
- Rate limiting and security controls

### Data Models

#### Session Model
```python
class Session:
    id: str
    type: SessionType  # PREVIEW, RUN_REPO, FORK_GUI
    status: SessionStatus  # CREATING, RUNNING, STOPPED, DESTROYED, ERROR
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime]
    repo_url: Optional[str]
    repo_ref: Optional[str]
    pr_number: Optional[int]
    container_id: Optional[str]
    network_id: Optional[str]
    ports: Dict[str, int]
    metadata: Dict[str, str]
```

#### Service Definition Model
```python
class ServiceDefinition:
    name: str
    type: str  # web, worker, db, cron, cli
    image: str
    command: Optional[str]
    port: Optional[int]
    env: Dict[str, str]
    volumes: List[str]
```

## Security & Isolation

### Resource Isolation

**CPU Limits:**
- Default: 1000m (1 CPU core)
- Preview: 2000m (2 CPU cores)
- GUI: 1000m (1 CPU core)

**Memory Limits:**
- Default: 1GB
- Preview: 2GB
- GUI: 2GB

**Disk Quotas:**
- Default: 5GB
- Preview: 10GB
- GUI: 8GB

### Network Security

**Firewall Rules:**
- Internal network communication allowed
- External access limited by session type
- Rate limiting on external traffic
- DNS resolution restricted to approved servers

**Rate Limiting:**
- Outbound traffic limited to 50-100mbps depending on session type
- Connection rate limiting
- Bandwidth shaping

### Access Control

**Token-Based Access:**
- Secure tokens generated per session
- Configurable TTL (default: 60 minutes)
- Automatic token revocation on session destruction

**Authentication:**
- API endpoints can be secured with authentication
- Session-specific access tokens
- Token validation for sensitive operations

### Security Scanning

**Image Scanning:**
- Vulnerability scanning of base images
- Security rating system (A-F)
- Recommendations for security improvements

**Runtime Scanning:**
- Process monitoring
- Open port detection
- Security issue identification

## Deployment Guide

### Prerequisites

- Docker and Docker Compose
- Python 3.8+
- At least 4GB RAM and 20GB disk space
- Internet access for pulling base images

### Quick Start

1. **Clone the repository**
```bash
git clone https://github.com/your-org/disposable-compute-platform.git
cd disposable-compute-platform
```

2. **Build and start the services**
```bash
docker-compose up --build
```

3. **Access the API**
```bash
# Health check
curl http://localhost:8000/health

# API documentation
http://localhost:8000/docs
```

### Production Deployment

For production, consider these additional configurations:

**Environment Variables:**
```bash
# .env file
DOMAIN=preview.yourcompany.com
DEFAULT_TTL=120
MAX_TTL=1440
STORAGE_PATH=/data/disposable-storage
MAX_CONCURRENT_SESSIONS=50
```

**Reverse Proxy Configuration:**
```nginx
# nginx configuration for subdomain routing
server {
    listen 80;
    server_name ~^([^.]+)\.preview\.yourcompany\.com$;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Security Hardening:**
- Enable authentication for API endpoints
- Use HTTPS with valid certificates
- Implement rate limiting
- Regular security audits

### Scaling Considerations

**Horizontal Scaling:**
- Multiple API instances behind load balancer
- Shared storage for session state
- Distributed container orchestration

**Resource Management:**
- Monitor resource usage
- Implement auto-scaling based on demand
- Set up alerts for resource exhaustion

## Extending the Platform

### Adding New Service Types

To add a new service type:

1. **Update the ServiceDefinition model**
```python
# In src/models/session.py
# Add to type validation if needed
```

2. **Implement service-specific logic in orchestrator**
```python
# In src/containers/orchestrator.py
def _create_{service_type}_container(self, config):
    # Service-specific container creation logic
```

3. **Update the preview config parser**
```python
# In src/services/preview.py
def _create_service_definition(self, name: str, definition: Dict[str, Any], pr_number: Optional[int]):
    if definition.get('type') == '{new_type}':
        # Handle new service type
```

### Adding New Runtime Detection

To add a new runtime:

1. **Update RuntimeDetector**
```python
# In src/services/run_repo.py
self.runtime_configs['{new_runtime}'] = {
    'files': ['{detection_file}'],
    'default_command': '{command}',
    'image': '{base_image}',
    'port': {port}
}
```

2. **Update entrypoint resolution**
```python
# In get_entrypoint_command method
elif runtime_info.get('language') == '{new_runtime}':
    # Custom entrypoint logic
```

### Adding New GUI Adapters

To add a new GUI adapter:

1. **Create a new adapter class**
```python
# In src/services/fork_gui.py
class NewAppAdapter(StateCaptureAdapter):
    def __init__(self):
        super().__init__()
        self.supported_apps = ['new-app-type']
    
    async def capture_state(self, container_id: str) -> Dict[str, Any]:
        # Capture new app state
        pass
    
    async def restore_state(self, container_id: str, state_data: Dict[str, Any]):
        # Restore new app state
        pass
```

2. **Register the adapter**
```python
# In StateAdapterManager.__init__()
self.adapters.append(NewAppAdapter())
```

### Custom Security Policies

To implement custom security policies:

1. **Extend SecurityPolicy**
```python
# In src/utils/security.py
def get_policy_for_session_type(self, session_type: str) -> Dict:
    if session_type == 'custom_type':
        return {
            'cpu_quota': 'custom_value',
            'memory_limit': 'custom_value',
            # ... other custom policies
        }
```

## Development Guide

### Project Structure

```
disposable-compute-platform/
├── src/
│   ├── models/           # Data models
│   │   ├── session.py
│   │   └── environment.py
│   ├── services/         # Business logic
│   │   ├── platform.py
│   │   ├── preview.py
│   │   ├── run_repo.py
│   │   └── fork_gui.py
│   ├── containers/       # Container orchestration
│   │   └── orchestrator.py
│   ├── networking/       # Network management
│   │   └── router.py
│   ├── api/             # API layer
│   │   └── main.py
│   └── utils/           # Utilities
│       └── security.py
├── tests/               # Test files
├── docs/                # Documentation
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container image
└── docker-compose.yml  # Deployment configuration
```

### Development Workflow

1. **Set up development environment**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install pytest black flake8 mypy
```

2. **Run the development server**
```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

3. **Run tests**
```bash
pytest tests/
```

4. **Code formatting**
```bash
black src/
flake8 src/
```

### Testing Strategy

**Unit Tests:**
- Test individual functions and methods
- Mock external dependencies
- Focus on business logic

**Integration Tests:**
- Test component interactions
- Use real Docker containers
- Validate end-to-end workflows

**Security Tests:**
- Validate resource limits
- Test isolation mechanisms
- Verify access controls

### Contributing Guidelines

1. **Fork the repository**
2. **Create a feature branch**
```bash
git checkout -b feature/new-feature
```

3. **Make your changes**
4. **Write tests for your changes**
5. **Run all tests**
```bash
pytest tests/
```

6. **Format your code**
```bash
black src/
flake8 src/
```

7. **Commit your changes**
```bash
git commit -m "Add new feature"
```

8. **Push to your fork**
```bash
git push origin feature/new-feature
```

9. **Create a pull request**

## Monitoring & Observability

### Metrics Collection

The platform can be extended with metrics collection:

**Key Metrics:**
- Active sessions count
- Resource utilization
- API response times
- Error rates
- Session creation/destruction rates

**Implementation:**
```python
# Example metrics endpoint
@app.get("/metrics")
async def get_metrics():
    return {
        "active_sessions": len(session_manager.sessions),
        "total_sessions_created": total_created,
        "avg_session_duration": avg_duration,
        "resource_usage": get_resource_usage()
    }
```

### Logging

The platform uses structured logging:

**Log Levels:**
- DEBUG: Detailed information for development
- INFO: General operational information
- WARNING: Potential issues
- ERROR: Errors that don't stop execution
- CRITICAL: Errors that stop execution

**Log Format:**
```
timestamp - logger_name - level - message - extra_data
```

### Health Checks

**Liveness Probe:**
- `/health` endpoint
- Returns 200 if service is running

**Readiness Probe:**
- Check if all dependencies are available
- Return 200 only if ready to serve requests

## Troubleshooting

### Common Issues

**Docker Permission Errors:**
- Ensure user has Docker permissions
- Add user to docker group: `sudo usermod -aG docker $USER`

**Port Conflicts:**
- Check if required ports are available
- Use different ports in configuration

**Resource Limits:**
- Monitor system resources
- Adjust container limits as needed

**Network Issues:**
- Verify Docker network creation
- Check firewall rules
- Ensure DNS resolution works

### Debugging Tips

**Enable Debug Logging:**
```bash
# Set environment variable
export LOG_LEVEL=DEBUG
```

**Check Container Logs:**
```bash
docker logs <container_name>
```

**Monitor Resource Usage:**
```bash
docker stats
```

### Performance Optimization

**Container Image Optimization:**
- Use multi-stage builds
- Minimize image size
- Use appropriate base images

**Resource Management:**
- Set appropriate limits
- Monitor usage patterns
- Implement auto-scaling

**Database Optimization:**
- Use connection pooling
- Optimize queries
- Implement caching where appropriate

## Roadmap

### Phase 1: MVP (Completed)
- [x] Basic run-repo functionality
- [x] Simple terminal access
- [x] Shareable links
- [x] Automatic cleanup

### Phase 2: Preview Environments (Completed)
- [x] Multi-service environments
- [x] Database support
- [x] Worker and cron jobs
- [x] Network isolation

### Phase 3: Advanced Features (Completed)
- [x] Forkable GUI sessions
- [x] State capture and restoration
- [x] Session forking
- [x] Advanced security isolation

### Future Enhancements

**Planned Features:**
- Advanced security scanning
- Custom domain support
- Persistent storage options
- Advanced networking features
- Integration with CI/CD systems
- Advanced monitoring and alerting
- Multi-cloud deployment support

**Long-term Goals:**
- Machine learning model serving
- GPU-accelerated environments
- Advanced collaboration features
- Enterprise security features
- Compliance certifications

This comprehensive documentation provides a complete guide to understanding, deploying, and extending the Disposable Compute Platform. The implementation is production-ready and follows modern software engineering practices for scalability, security, and maintainability.