# Vanish Compute (VNC)

A comprehensive platform for ephemeral compute environments supporting three core capabilities:

1. **Preview Environments for Everything** - Ephemeral environments for every PR
2. **"Run This Repo" Button** - Instant runnable environments 
3. **Forkable GUI Sessions** - Forkable live GUI application sessions


## Table of Contents
- [Features](#features)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Usage Examples](#usage-examples)
- [API Documentation](#api-documentation)
- [Development](#development)
- [Deployment](#deployment)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)

## Features

### Preview Environments for Everything
- Complete ephemeral environments for every PR
- Support for databases, workers, cron jobs, and caches
- Automatic cleanup on PR close
- Isolated networks per environment
- Database volume management per PR

### "Run This Repo" Button
- Single-click runnable environments for any repository
- Automatic runtime detection (Node.js, Python, Go, Rust, Java)
- Real Docker image building via SDK
- Shareable links with configurable TTL

### Forkable GUI Sessions
- Forkable live GUI application sessions
- **Selective Forwarding Unit (SFU)** for multi-client streaming
- **WebRTC** base with STUN/TURN integration
- State capture and restoration using bit-level Docker snapshots
- Adapter architecture for Three.js, Audio, and Generic GUIs
- Advanced input handling (Gamepad, Multi-touch)

### Advanced Virtualization & Isolation
- **Firecracker MicroVMs**: High-density, high-isolation pod type
- **KVM/Libvirt Support**: Full VM virtualization with GPU passthrough
- **GPU-Aware Scheduling**: Priority-based placement and active preemption
- **Hardware Acceleration**: Automated GPU discovery and allocation

### Shared Platform Layer
- Unified session management with **Redis Caching**
- Multi-runtime orchestration (Container, VM, MicroVM)
- **Event Streaming**: Redis PubSub for real-time lifecycle tracking
- **Nginx Ingress**: Dynamic subdomain routing with WebSocket support
- Structured JSON logging with `structlog`

### Reliability & Observability
- **Enterprise Alerting**: Integrated PagerDuty and OpsGenie support
- **Automated Health Checks**: Self-healing with critical alert triggers
- **Security Scans**: Image vulnerability scanning using **Trivy**
- **Runtime Monitoring**: Suspicious process detection inside pods
- **Database Migrations**: Versioned schema management via **Alembic**


## Architecture

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

### Key Components

- **Session Management**: Core lifecycle management for all session types
- **Container Orchestration**: Docker-based container management
- **Network Management**: Isolated networks and routing
- **Security Management**: Resource isolation and access control
- **Snapshot Management**: State capture and restoration
- **Image Builder**: Repository-specific image building

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Python 3.8+
- Git

### Quick Start

1. **Clone the repository**
```bash
git clone https://github.com/your-org/vanish-compute.git
cd vanish-compute
```


2. **Start the platform**
```bash
docker-compose up --build
```

3. **Access the API**
- API: http://localhost:8000
- Documentation: http://localhost:8000/docs

### Manual Installation

1. **Set up Python environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Start the development server**
```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

## Usage Examples

### Preview Environments

Create a preview environment for a PR:

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "preview",
    "repo_url": "https://github.com/example/myapp.git",
    "repo_ref": "feature/new-feature",
    "pr_number": 142,
    "ttl_minutes": 120
  }'
```

### "Run This Repo"

Run any repository with one click:

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "run_repo",
    "repo_url": "https://github.com/example/hello-world.git",
    "ttl_minutes": 60
  }'
```

### Forkable GUI Sessions

Create a forkable GUI session:

```bash
curl -X POST http://localhost:8000/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "type": "fork_gui",
    "repo_url": "https://github.com/example/3d-editor.git",
    "ttl_minutes": 180
  }'
```

### Get Session Details

```bash
curl http://localhost:8000/sessions/sess-20231201-123456-abcd
```

### Get Session Logs

```bash
curl "http://localhost:8000/sessions/sess-20231201-123456-abcd/logs?lines=50"
```

### Fork a GUI Session

```bash
curl -X POST http://localhost:8000/sessions/sess-20231201-123456-abcd/fork \
  -H "Content-Type: application/json" \
  -d '{}'
```

## API Documentation

### Base URL
`http://localhost:8000` (or your deployment URL)

### Key Endpoints

- `POST /sessions` - Create new session
- `GET /sessions/{session_id}` - Get session details
- `DELETE /sessions/{session_id}` - Destroy session
- `GET /sessions/{session_id}/logs` - Get session logs
- `POST /sessions/{session_id}/fork` - Fork GUI session
- `WS /ws/logs/{session_id}` - Real-time logs
- `GET /health` - Health check

For complete API documentation, visit: http://localhost:8000/docs

## Development

### Project Structure

```
vanish-compute/
├── src/                    # Source code

│   ├── models/            # Data models
│   ├── services/          # Business logic
│   ├── containers/        # Container orchestration
│   ├── networking/        # Network management
│   ├── api/              # API layer
│   └── utils/            # Utilities
├── tests/                 # Test files
├── docs/                  # Documentation
├── requirements.txt       # Python dependencies
├── Dockerfile            # Container image
└── docker-compose.yml    # Deployment configuration
```

### Running Tests

```bash
# Install test dependencies
pip install pytest

# Run all tests
pytest

# Run with coverage
pytest --cov=src
```

### Code Formatting

```bash
# Install formatting tools
pip install black flake8

# Format code
black src/
flake8 src/
```

## Deployment

### Production Deployment

For production, use the provided docker-compose configuration:

```bash
# Production deployment
docker-compose -f docker-compose.prod.yml up -d
```

### Environment Variables

Configure the platform with environment variables:

```bash
# .env file
DOMAIN=preview.yourcompany.com
DEFAULT_TTL=120
MAX_TTL=1440
STORAGE_PATH=/data/disposable-storage
MAX_CONCURRENT_SESSIONS=50
```

### Scaling

The platform supports horizontal scaling:

- Multiple API instances behind load balancer
- Shared storage for session state
- Distributed container orchestration

## Security

### Isolation Features

- **Resource Limits**: CPU, memory, and disk quotas per session
- **Network Isolation**: Separate Docker networks per environment
- **Access Control**: Token-based session access
- **Security Scanning**: Vulnerability scanning of images
- **System Call Filtering**: Restricted system calls via seccomp

### Security Best Practices

- Regular security audits
- Image scanning for vulnerabilities
- Network traffic rate limiting
- Automatic cleanup of expired sessions
- Read-only filesystems where possible

## Contributing

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Add tests for your changes
5. Run tests: `pytest`
6. Format code: `black src/`
7. Commit your changes: `git commit -m "Add amazing feature"`
8. Push to the branch: `git push origin feature/amazing-feature`
9. Open a pull request

### Code Standards

- Follow PEP 8 style guide
- Use type hints
- Write comprehensive tests
- Document public APIs
- Keep functions focused and small

## Roadmap

### Completed Features
- [x] Basic run-repo functionality with real Docker builds
- [x] Preview environments with multiple services and dynamic config
- [x] Forkable GUI sessions with SFU and WebRTC
- [x] Firecracker MicroVM and KVM virtualization
- [x] GPU-aware scheduling and preemption
- [x] Enterprise alerting (PagerDuty/OpsGenie)
- [x] Nginx Ingress and subdomain routing
- [x] Security scanning (Trivy) and runtime monitoring
- [x] Database migrations (Alembic)

### Planned Features
- [ ] Multi-region cluster orchestration
- [ ] Cost-based resource optimization
- [ ] Integration with GitHub Actions / GitLab CI
- [ ] Advanced Service Mesh (mTLS/Tracing)


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For support, please open an issue in the GitHub repository or contact the maintainers.

---

Built with ❤️ for the vanish compute community.


This platform provides a solid foundation for all three disposable compute concepts with a shared platform layer that enables rapid iteration and feature development.