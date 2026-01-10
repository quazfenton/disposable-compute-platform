# Developer Guide

## Getting Started

### Prerequisites
- Python 3.8+
- Docker and Docker Compose
- Git

### Setup Development Environment

1. **Clone the repository**
```bash
git clone https://github.com/your-org/disposable-compute-platform.git
cd disposable-compute-platform
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
pip install pytest black flake8 mypy  # Development dependencies
```

4. **Run the development server**
```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

5. **Access the API**
- API: http://localhost:8000
- Documentation: http://localhost:8000/docs

## Project Structure

```
disposable-compute-platform/
├── src/                    # Source code
│   ├── models/            # Data models
│   │   ├── session.py     # Session and service definitions
│   │   └── environment.py # Environment definitions
│   ├── services/          # Business logic
│   │   ├── platform.py    # Core platform manager
│   │   ├── preview.py     # Preview environments
│   │   ├── run_repo.py    # Run repo functionality
│   │   └── fork_gui.py    # Forkable GUI sessions
│   ├── containers/        # Container orchestration
│   │   └── orchestrator.py # Docker orchestration
│   ├── networking/        # Network management
│   │   └── router.py      # Routing and networking
│   ├── api/              # API layer
│   │   └── main.py        # FastAPI application
│   └── utils/            # Utilities
│       └── security.py    # Security and isolation
├── tests/                 # Test files
├── docs/                  # Documentation
├── requirements.txt       # Python dependencies
├── Dockerfile            # Container image
└── docker-compose.yml    # Deployment configuration
```

## Core Concepts

### Session Types
The platform supports three main session types:

1. **Preview Environments** (`preview`): Complete PR environments with all services
2. **Run Repo** (`run_repo`): Single-click repository execution
3. **Forkable GUI** (`fork_gui`): Forkable GUI application sessions

### Session Lifecycle
```
CREATING → RUNNING → STOPPED → DESTROYED
    ↓         ↓         ↓         ↓
  (setup)  (active)  (cleanup) (cleanup)
```

### Data Models

#### Session Model
```python
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

class SessionType(Enum):
    PREVIEW = "preview"
    RUN_REPO = "run_repo"
    FORK_GUI = "fork_gui"

class SessionStatus(Enum):
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    DESTROYED = "destroyed"
    ERROR = "error"

@dataclass
class Session:
    id: str
    type: SessionType
    status: SessionStatus
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    repo_url: Optional[str] = None
    repo_ref: Optional[str] = None
    pr_number: Optional[int] = None
    container_id: Optional[str] = None
    network_id: Optional[str] = None
    ports: Dict[str, int] = None
    metadata: Dict[str, str] = None
```

#### Service Definition Model
```python
@dataclass
class ServiceDefinition:
    name: str
    type: str  # web, worker, db, cron, cli
    image: str
    command: Optional[str] = None
    port: Optional[int] = None
    env: Dict[str, str] = None
    volumes: List[str] = None
```

## Extending the Platform

### Adding New Service Types

To add a new service type, follow these steps:

1. **Update the ServiceDefinition model** (if needed)
2. **Implement service-specific logic in the orchestrator**
3. **Update the preview config parser**

**Example: Adding a Redis service type**

```python
# In src/containers/orchestrator.py
def _create_redis_container(self, config: ContainerConfig) -> str:
    """Create a Redis container with specific configuration"""
    # Add Redis-specific configuration
    config.environment.update({
        'REDIS_MAXMEMORY': '256mb',
        'REDIS_MAXMEMORY_POLICY': 'allkeys-lru'
    })
    
    return self.create_container(config)
```

### Adding New Runtime Detection

To add support for a new programming language/runtime:

1. **Update RuntimeDetector in run_repo.py**
2. **Add detection logic**
3. **Define default configurations**

**Example: Adding Ruby support**

```python
# In src/services/run_repo.py
class RuntimeDetector:
    def __init__(self):
        self.runtime_configs = {
            # ... existing configs ...
            'ruby': {
                'files': ['Gemfile', 'Gemfile.lock', 'main.rb', 'app.rb'],
                'default_command': 'ruby app.rb',
                'image': 'ruby:3.2-alpine',
                'port': 4567  # Sinatra default port
            }
        }
```

### Adding New GUI Adapters

To add support for a new GUI application type:

1. **Create a new adapter class**
2. **Implement state capture and restoration**
3. **Register the adapter**

**Example: Adding a video editor adapter**

```python
# In src/services/fork_gui.py
class VideoEditorAdapter(StateCaptureAdapter):
    def __init__(self):
        super().__init__()
        self.supported_apps = ['video-editor', 'ffmpeg-gui']
    
    async def capture_state(self, container_id: str) -> Dict[str, Any]:
        """Capture video editor state"""
        return {
            'app_type': 'video-editor',
            'timestamp': datetime.now().isoformat(),
            'timeline': {
                'position': 0,
                'duration': 0,
                'playback_rate': 1.0
            },
            'tracks': [],
            'effects': [],
            'render_settings': {},
            'open_projects': []
        }
    
    async def restore_state(self, container_id: str, state_data: Dict[str, Any]):
        """Restore video editor state"""
        print(f"Restoring video editor state in container {container_id}")
```

## API Development

### Adding New Endpoints

To add a new API endpoint:

1. **Define the request/response models**
2. **Implement the endpoint function**
3. **Add to the FastAPI app**

**Example: Adding a metrics endpoint**

```python
# In src/api/main.py
from pydantic import BaseModel
from typing import Dict, Any

class MetricsResponse(BaseModel):
    active_sessions: int
    total_sessions: int
    resource_usage: Dict[str, Any]

@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get platform metrics"""
    active_count = len(session_manager.sessions)
    total_count = 1000  # Would be calculated from database in real implementation
    
    return MetricsResponse(
        active_sessions=active_count,
        total_sessions=total_count,
        resource_usage={
            'cpu_percent': 45.2,
            'memory_percent': 67.8,
            'disk_percent': 32.1
        }
    )
```

### Adding WebSocket Endpoints

**Example: Adding a metrics WebSocket**

```python
# In src/api/main.py
@app.websocket("/ws/metrics")
async def websocket_metrics(websocket: WebSocket):
    """WebSocket endpoint for real-time metrics"""
    await connection_manager.connect(websocket)
    try:
        while True:
            # Send metrics every 5 seconds
            metrics = await get_metrics()
            await connection_manager.send_personal_message(
                json.dumps(metrics),
                websocket
            )
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
```

## Security Implementation

### Resource Isolation

The platform implements multiple layers of security:

1. **Container resource limits**
2. **Network isolation**
3. **Access control tokens**
4. **Security scanning**

**Example: Adding custom security policy**

```python
# In src/utils/security.py
class SecurityPolicy:
    def get_policy_for_session_type(self, session_type: str) -> Dict:
        policy = self.default_policies.copy()
        
        if session_type == 'high_security':
            policy.update({
                'cpu_quota': '500m',      # Half CPU
                'memory_limit': '512M',   # Half memory
                'disk_quota': '2G',       # Half disk
                'max_processes': 16,      # Fewer processes
                'allowed_syscalls': [     # More restrictive syscalls
                    'read', 'write', 'open', 'close'
                ]
            })
        
        return policy
```

## Testing

### Unit Tests

Create unit tests for individual functions:

```python
# tests/test_session.py
import pytest
from src.models.session import Session, SessionType, SessionStatus
from datetime import datetime

def test_session_creation():
    """Test creating a new session"""
    session = Session(
        id="test-session",
        type=SessionType.RUN_REPO,
        status=SessionStatus.CREATING,
        created_at=datetime.now()
    )
    
    assert session.id == "test-session"
    assert session.type == SessionType.RUN_REPO
    assert session.status == SessionStatus.CREATING

def test_session_defaults():
    """Test session default values"""
    session = Session(
        id="test-session",
        type=SessionType.PREVIEW,
        status=SessionStatus.CREATING,
        created_at=datetime.now()
    )
    
    # Test default values
    assert session.ports == {}
    assert session.metadata == {}
```

### Integration Tests

Test component interactions:

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_create_session():
    """Test creating a session via API"""
    response = client.post("/sessions", json={
        "type": "run_repo",
        "repo_url": "https://github.com/example/test.git"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["status"] == "creating"

def test_get_session():
    """Test getting session details"""
    # First create a session
    create_response = client.post("/sessions", json={
        "type": "run_repo",
        "repo_url": "https://github.com/example/test.git"
    })
    
    session_id = create_response.json()["session_id"]
    
    # Then get session details
    response = client.get(f"/sessions/{session_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["id"] == session_id
    assert data["type"] == "run_repo"
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_session.py

# Run with coverage
pytest --cov=src

# Run with verbose output
pytest -v
```

## Configuration

### Platform Configuration

The platform can be configured using the `PlatformConfig` class:

```python
# In src/services/platform.py
@dataclass
class PlatformConfig:
    domain: str = "preview.yourapp.dev"
    default_ttl: int = 30  # minutes
    max_ttl: int = 1440    # 24 hours
    storage_path: str = "/tmp/disposable-storage"
    max_concurrent_sessions: int = 100
```

### Environment Variables

Use environment variables for configuration:

```python
# In main application
import os

config = PlatformConfig(
    domain=os.getenv('DOMAIN', 'preview.yourapp.dev'),
    default_ttl=int(os.getenv('DEFAULT_TTL', '30')),
    max_ttl=int(os.getenv('MAX_TTL', '1440')),
    storage_path=os.getenv('STORAGE_PATH', '/tmp/disposable-storage'),
    max_concurrent_sessions=int(os.getenv('MAX_CONCURRENT_SESSIONS', '100'))
)
```

## Deployment

### Docker Deployment

Build and run with Docker:

```bash
# Build the image
docker build -t disposable-compute-platform .

# Run the container
docker run -d \
  -p 8000:8000 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e DOMAIN=preview.yourcompany.com \
  disposable-compute-platform
```

### Docker Compose Deployment

Use docker-compose for easier management:

```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - DOMAIN=preview.yourcompany.com
      - DEFAULT_TTL=60
      - MAX_CONCURRENT_SESSIONS=50
    restart: unless-stopped
    depends_on:
      - redis  # If using Redis for session storage

  redis:
    image: redis:alpine
    restart: unless-stopped
```

### Kubernetes Deployment

For production at scale:

```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: disposable-compute-platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: disposable-compute-platform
  template:
    metadata:
      labels:
        app: disposable-compute-platform
    spec:
      containers:
      - name: api
        image: your-registry/disposable-compute-platform:latest
        ports:
        - containerPort: 8000
        env:
        - name: DOMAIN
          value: "preview.yourcompany.com"
        - name: DEFAULT_TTL
          valueFrom:
            configMapKeyRef:
              name: platform-config
              key: default-ttl
        volumeMounts:
        - name: docker-sock
          mountPath: /var/run/docker.sock
      volumes:
      - name: docker-sock
        hostPath:
          path: /var/run/docker.sock
---
apiVersion: v1
kind: Service
metadata:
  name: disposable-compute-platform
spec:
  selector:
    app: disposable-compute-platform
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

## Monitoring and Logging

### Adding Custom Metrics

```python
# In your service
import time
from functools import wraps

def track_execution_time(func):
    """Decorator to track function execution time"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            print(f"{func.__name__} executed in {execution_time:.2f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            print(f"{func.__name__} failed after {execution_time:.2f}s: {e}")
            raise
    return wrapper

# Usage
@track_execution_time
async def create_session(self, ...):
    # Your implementation
    pass
```

### Structured Logging

```python
import logging
import json
from datetime import datetime

class StructuredLogger:
    def __init__(self, name):
        self.logger = logging.getLogger(name)
    
    def info(self, message, **kwargs):
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'level': 'INFO',
            'message': message,
            **kwargs
        }
        self.logger.info(json.dumps(log_data))
    
    def error(self, message, **kwargs):
        log_data = {
            'timestamp': datetime.now().isoformat(),
            'level': 'ERROR',
            'message': message,
            **kwargs
        }
        self.logger.error(json.dumps(log_data))

# Usage
logger = StructuredLogger(__name__)
logger.info("Session created", session_id="abc123", type="run_repo")
```

## Best Practices

### Code Organization
- Keep business logic in service modules
- Keep data models separate
- Use dependency injection where appropriate
- Follow single responsibility principle

### Error Handling
- Use specific exception types
- Provide meaningful error messages
- Log errors appropriately
- Fail gracefully when possible

### Security
- Validate all inputs
- Use parameterized queries
- Implement proper authentication
- Regular security audits

### Performance
- Use async/await for I/O operations
- Implement caching where appropriate
- Monitor resource usage
- Optimize database queries

This developer guide provides comprehensive information for extending and maintaining the Disposable Compute Platform, including examples for common development tasks and best practices.