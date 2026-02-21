"""
Production-ready API for Disposable Compute Platform
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, validator

# Internal imports
from src.scheduler.scheduler import Scheduler, Node, NodeStatus, PodRequest, SchedulingStatus
from src.scheduler.scheduler import ResourceManager, NodeScorer, ConstraintValidator
from src.models.pod import PodSpec, PodType, ResourceRequirements
from src.models.gpu import GPUDevice, GPUStatus, GPUAllocation, GPUConfiguration, GPUCluster
from src.orchestrator.orchestrator import AdvancedOrchestrator
from src.streaming.streaming_server import StreamingManager
from src.storage.storage_manager import StorageManager
from src.api.auth import AuthManager, AuthConfig, User
from src.metrics.metrics import get_metrics, get_health_checker, HealthChecker

# Database imports
from src.database.db import Database, DatabaseConfig, init_database, close_database, get_database
from src.database.models import SessionType, SessionStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": %(message)s}'
)
logger = logging.getLogger(__name__)


# ============== Configuration ==============

class Config:
    """Application configuration"""
    def __init__(self):
        self.domain = os.getenv("DOMAIN", "preview.yourapp.dev")
        self.default_ttl = int(os.getenv("DEFAULT_TTL", "60"))
        self.max_ttl = int(os.getenv("MAX_TTL", "1440"))
        self.max_concurrent_sessions = int(os.getenv("MAX_CONCURRENT_SESSIONS", "100"))
        self.rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
        
        # Feature flags
        self.enable_gpu = os.getenv("ENABLE_GPU", "false").lower() == "true"
        self.enable_vm = os.getenv("ENABLE_VM", "false").lower() == "true"
        self.enable_streaming = os.getenv("ENABLE_STREAMING", "true").lower() == "true"


config = Config()


# ============== Request/Response Models ==============

class CreateSessionRequest(BaseModel):
    """Request to create a new session"""
    type: str = Field(..., description="Session type: preview, run_repo, fork_gui")
    repo_url: str = Field(..., description="Git repository URL")
    repo_ref: Optional[str] = Field(None, description="Git reference (branch/tag)")
    pr_number: Optional[int] = Field(None, description="Pull request number")
    ttl_minutes: Optional[int] = Field(None, description="Session TTL in minutes")
    config: Optional[Dict[str, Any]] = Field(None, description="Additional configuration")
    
    @validator('type')
    def validate_type(cls, v):
        if v not in ['preview', 'run_repo', 'fork_gui']:
            raise ValueError('type must be preview, run_repo, or fork_gui')
        return v
    
    @validator('ttl_minutes')
    def validate_ttl(cls, v):
        if v is not None and v > config.max_ttl:
            raise ValueError(f'ttl_minutes cannot exceed {config.max_ttl}')
        return v


class CreateSessionResponse(BaseModel):
    """Response for session creation"""
    session_id: str
    status: str
    stream_url: Optional[str] = None
    created_at: str
    expires_at: str


class SessionResponse(BaseModel):
    """Full session details"""
    id: str
    type: str
    status: str
    created_at: str
    updated_at: str
    expires_at: Optional[str]
    repo_url: Optional[str]
    stream_url: Optional[str]
    pod_id: Optional[str]
    node_id: Optional[str]
    metadata: Dict[str, Any]


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


class MetricsResponse(BaseModel):
    """Prometheus metrics response"""
    metrics: str


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    checks: Dict[str, Any]


class CreateSnapshotRequest(BaseModel):
    """Request to create a snapshot"""
    description: Optional[str] = None
    type: str = "disk"  # disk, memory, project


class CreateAPIKeyRequest(BaseModel):
    """Request to create an API key"""
    name: str
    expires_days: Optional[int] = None
    scopes: Optional[List[str]] = None


class APIKeyResponse(BaseModel):
    """Response with API key"""
    key: str
    name: str
    created_at: str
    expires_at: Optional[str]


# ============== Application State ==============

class AppState:
    """Global application state"""
    def __init__(self):
        self.scheduler: Optional[Scheduler] = None
        self.orchestrator: Optional[AdvancedOrchestrator] = None
        self.streaming_manager: Optional[StreamingManager] = None
        self.storage_manager: Optional[StorageManager] = None
        self.auth_manager: Optional[AuthManager] = None
        self.database: Optional[Database] = None
        self.sessions: Dict[str, Dict] = {}  # In-memory session cache


state = AppState()


# ============== Lifespan ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting Disposable Compute Platform...")
    
    # Initialize database
    try:
        state.database = await init_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed, using in-memory: {e}")
    
    # Initialize auth manager
    state.auth_manager = AuthManager()
    
    # Create default admin user for development
    if os.getenv("ENVIRONMENT", "development") == "development":
        state.auth_manager.create_user("user-001", "admin@example.com", "enterprise")
        logger.info("Created development admin user")
    
    # Initialize scheduler
    state.scheduler = Scheduler()
    logger.info("Scheduler initialized")
    
    # Initialize orchestrator
    try:
        state.orchestrator = AdvancedOrchestrator()
        logger.info("Orchestrator initialized")
    except Exception as e:
        logger.warning(f"Orchestrator initialization failed: {e}")
    
    # Initialize streaming manager
    if config.enable_streaming:
        state.streaming_manager = StreamingManager()
        await state.streaming_manager.initialize()
        logger.info("Streaming manager initialized")
    
    # Initialize storage manager
    state.storage_manager = StorageManager()
    await state.storage_manager.initialize()
    logger.info("Storage manager initialized")
    
    # Register health checks
    health = get_health_checker()
    health.register("database", check_database_health)
    health.register("scheduler", check_scheduler_health)
    health.register("storage", check_storage_health)
    
    # Start background tasks
    asyncio.create_task(cleanup_expired_sessions())
    asyncio.create_task(update_metrics())
    
    logger.info("Disposable Compute Platform started successfully")
    
    yield
    
    # Cleanup
    logger.info("Shutting down Disposable Compute Platform...")
    
    if state.streaming_manager:
        # Cleanup streaming sessions
        pass
    
    if state.database:
        await close_database()
    
    logger.info("Shutdown complete")


# ============== FastAPI App ==============

app = FastAPI(
    title="Disposable Compute Platform API",
    version="2.0.0",
    description="Production-ready API for disposable compute environments",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer(auto_error=False)


# ============== Dependencies ==============

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    request: Request = None
) -> Optional[User]:
    """Get the current authenticated user"""
    if credentials:
        token = credentials.credentials
        user = state.auth_manager.token_manager.get_user_from_token(token)
        if user:
            return user
    
    # Try API key
    if request:
        api_key = request.headers.get("X-API-Key")
        if api_key:
            key = state.auth_manager.api_key_manager.verify_key(api_key)
            if key:
                return state.auth_manager.get_user(key.user_id)
    
    return None


async def require_user(user: Optional[User] = Depends(get_current_user)) -> User:
    """Require authentication"""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_tier(required_tier: str):
    """Require specific tier"""
    async def check_tier(user: User = Depends(require_user)) -> User:
        tier_levels = {"free": 0, "pro": 1, "enterprise": 2}
        if tier_levels.get(user.tier, 0) < tier_levels.get(required_tier, 0):
            raise HTTPException(status_code=403, detail=f"Requires {required_tier} tier")
        return user
    return check_tier


# ============== Health Checks ==============

async def check_database_health() -> Dict[str, Any]:
    """Check database health"""
    try:
        if state.database and state.database._connected:
            return {"status": "healthy", "type": "connected"}
        return {"status": "healthy", "type": "in-memory"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def check_scheduler_health() -> Dict[str, Any]:
    """Check scheduler health"""
    try:
        if state.scheduler:
            status = state.scheduler.get_cluster_status()
            return {"status": "healthy", "nodes": status["total_nodes"]}
        return {"status": "unhealthy", "error": "Scheduler not initialized"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


async def check_storage_health() -> Dict[str, Any]:
    """Check storage health"""
    try:
        if state.storage_manager:
            usage = await state.storage_manager.get_storage_usage()
            return {"status": "healthy", "volumes": usage["total_volumes"]}
        return {"status": "unhealthy", "error": "Storage not initialized"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ============== Background Tasks ==============

async def cleanup_expired_sessions():
    """Periodically cleanup expired sessions"""
    while True:
        try:
            await asyncio.sleep(300)  # Every 5 minutes
            
            # Cleanup from database
            if state.database:
                expired = await state.database.cleanup_expired_sessions()
                if expired:
                    logger.info(f"Cleaned up {len(expired)} expired sessions from database")
            
            # Cleanup in-memory
            now = datetime.utcnow()
            expired_in_memory = [
                sid for sid, sess in state.sessions.items()
                if sess.get("expires_at") and datetime.fromisoformat(sess["expires_at"]) < now
            ]
            
            for sid in expired_in_memory:
                await destroy_session_resources(sid)
                del state.sessions[sid]
                get_metrics().record_session_destroyed(
                    state.sessions[sid].get("type", "unknown"),
                    "expired"
                )
            
            if expired_in_memory:
                logger.info(f"Cleaned up {len(expired_in_memory)} expired sessions from memory")
                
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")


async def update_metrics():
    """Periodically update metrics"""
    while True:
        try:
            await asyncio.sleep(60)  # Every minute
            
            metrics = get_metrics()
            
            # Update session counts
            active_count = sum(
                1 for s in state.sessions.values()
                if s.get("status") == "running"
            )
            metrics.set_active_sessions(active_count)
            
            # Update scheduler metrics
            if state.scheduler:
                cluster = state.scheduler.get_cluster_status()
                metrics.set_active_pods(cluster["total_pods"])
                
        except Exception as e:
            logger.error(f"Error in metrics update: {e}")


async def destroy_session_resources(session_id: str):
    """Destroy all resources for a session"""
    session = state.sessions.get(session_id)
    if not session:
        return
    
    # Stop streaming
    if state.streaming_manager and session.get("pod_id"):
        try:
            await state.streaming_manager.stop_pod_streaming(session["pod_id"])
        except Exception as e:
            logger.warning(f"Error stopping stream: {e}")
    
    # Destroy pod
    if state.orchestrator and session.get("pod_id"):
        try:
            await state.orchestrator.destroy_pod(session["pod_id"])
        except Exception as e:
            logger.warning(f"Error destroying pod: {e}")
    
    # Unschedule
    if state.scheduler and session.get("pod_id"):
        state.scheduler.unschedule(session["pod_id"])
    
    # Cleanup storage
    if state.storage_manager and session.get("pod_id"):
        await state.storage_manager.cleanup_pod_volumes(session["pod_id"])


# ============== API Endpoints ==============

@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint"""
    return {
        "name": "Disposable Compute Platform",
        "version": "2.0.0",
        "docs": "/docs"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    health = get_health_checker()
    result = await health.run_checks()
    return HealthResponse(**result)


@app.get("/metrics", response_class=Response)
async def metrics():
    """Prometheus metrics endpoint"""
    metrics = get_metrics()
    return Response(
        content=metrics.registry.export_prometheus(),
        media_type="text/plain"
    )


# ============== Session Endpoints ==============

@app.post("/api/v1/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    request: CreateSessionRequest,
    user: User = Depends(require_user)
):
    """Create a new session"""
    metrics = get_metrics()
    
    # Check quota
    can_create, reason = state.auth_manager.check_session_quota(user)
    if not can_create:
        raise HTTPException(status_code=429, detail=reason)
    
    # Validate TTL
    ttl = request.ttl_minutes or config.default_ttl
    max_ttl = min(user.get_max_ttl(), config.max_ttl)
    if ttl > max_ttl:
        ttl = max_ttl
    
    # Create session in database
    session_type_map = {
        "preview": SessionType.PREVIEW,
        "run_repo": SessionType.RUN_REPO,
        "fork_gui": SessionType.FORK_GUI
    }
    
    if state.database:
        db_session = await state.database.create_session(
            session_type=session_type_map[request.type],
            user_id=user.id,
            config=request.config or {},
            ttl_minutes=ttl,
            repo_url=request.repo_url,
            repo_ref=request.repo_ref,
            pr_number=request.pr_number
        )
        session_id = str(db_session.id)
    else:
        import uuid
        session_id = str(uuid.uuid4())
    
    # Create pod spec
    pod_spec = PodSpec(
        pod_type=PodType.CONTAINER,
        app_type="linux",
        image="ubuntu:22.04",
        resource_requirements=ResourceRequirements(
            cpu_cores=2.0,
            memory_mb=4096,
            storage_gb=20
        )
    )
    
    # Create scheduling request
    pod_request = PodRequest(
        id=f"pod-{session_id}",
        pod_spec=pod_spec,
        user_id=user.id,
        user_tier=user.tier,
        priority=70 if user.tier == "enterprise" else 50
    )
    
    # Schedule pod
    success, message, node_id = await state.scheduler.schedule(pod_request)
    
    if not success:
        metrics.record_session_failed(request.type, message)
        raise HTTPException(status_code=503, detail=f"Failed to schedule: {message}")
    
    # Create pod
    try:
        await state.orchestrator.create_pod(pod_spec)
    except Exception as e:
        state.scheduler.unschedule(pod_request.id)
        metrics.record_session_failed(request.type, str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create pod: {e}")
    
    # Start streaming
    stream_url = None
    if state.streaming_manager and config.enable_streaming:
        try:
            await state.streaming_manager.start_pod_streaming(pod_request.id)
            stream_url = await state.streaming_manager.get_stream_url(pod_request.id)
        except Exception as e:
            logger.warning(f"Failed to start streaming: {e}")
    
    # Update session status
    if state.database:
        await state.database.update_session_status(session_id, SessionStatus.RUNNING)
    
    # Store in memory
    expires_at = datetime.utcnow() + timedelta(minutes=ttl)
    state.sessions[session_id] = {
        "id": session_id,
        "type": request.type,
        "status": "running",
        "pod_id": pod_request.id,
        "node_id": node_id,
        "user_id": user.id,
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat(),
        "repo_url": request.repo_url,
        "stream_url": stream_url
    }
    
    # Record metrics
    metrics.record_session_created(request.type, user.tier)
    state.auth_manager.record_session_created(user.id)
    
    logger.info(f"Created session {session_id} for user {user.id}")
    
    return CreateSessionResponse(
        session_id=session_id,
        status="running",
        stream_url=stream_url,
        created_at=datetime.utcnow().isoformat(),
        expires_at=expires_at.isoformat()
    )


@app.get("/api/v1/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user: User = Depends(require_user)
):
    """Get session details"""
    # Check database first
    if state.database:
        db_session = await state.database.get_session(session_id)
        if db_session:
            # Verify ownership
            if db_session.user_id != user.id and user.tier != "enterprise":
                raise HTTPException(status_code=404, detail="Session not found")
            
            return SessionResponse(
                id=str(db_session.id),
                type=db_session.type.value,
                status=db_session.status.value,
                created_at=db_session.created_at.isoformat(),
                updated_at=db_session.updated_at.isoformat(),
                expires_at=db_session.expires_at.isoformat() if db_session.expires_at else None,
                repo_url=db_session.repo_url,
                metadata=db_session.metadata or {}
            )
    
    # Check in-memory
    session = state.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Verify ownership
    if session.get("user_id") != user.id and user.tier != "enterprise":
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(
        id=session["id"],
        type=session["type"],
        status=session["status"],
        created_at=session["created_at"],
        updated_at=session["created_at"],  # TODO: track updates
        expires_at=session.get("expires_at"),
        repo_url=session.get("repo_url"),
        stream_url=session.get("stream_url"),
        pod_id=session.get("pod_id"),
        node_id=session.get("node_id"),
        metadata={}
    )


@app.delete("/api/v1/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user: User = Depends(require_user)
):
    """Destroy a session"""
    session = state.sessions.get(session_id)
    
    if not session:
        # Check database
        if state.database:
            db_session = await state.database.get_session(session_id)
            if db_session:
                if db_session.user_id != user.id and user.tier != "enterprise":
                    raise HTTPException(status_code=404, detail="Session not found")
                await state.database.delete_session(session_id)
                return
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Verify ownership
    if session.get("user_id") != user.id and user.tier != "enterprise":
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Destroy resources
    await destroy_session_resources(session_id)
    
    # Update database
    if state.database:
        await state.database.update_session_status(session_id, SessionStatus.DESTROYED)
    
    # Remove from memory
    del state.sessions[session_id]
    
    # Record metrics
    get_metrics().record_session_destroyed(session["type"], "user_initiated")
    
    logger.info(f"Destroyed session {session_id}")


@app.post("/api/v1/sessions/{session_id}/snapshot", status_code=201)
async def create_snapshot(
    session_id: str,
    request: CreateSnapshotRequest,
    user: User = Depends(require_tier("pro"))
):
    """Create a snapshot of a session"""
    session = state.sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if not session.get("pod_id"):
        raise HTTPException(status_code=400, detail="Session has no pod")
    
    # Create snapshot
    pod_id = session["pod_id"]
    
    # Create volume for snapshot
    volume = await state.storage_manager.create_ephemeral_volume(pod_id, 10)
    
    # Create snapshot record
    snapshot_id = await state.database.create_snapshot(
        pod_id=pod_id,
        snapshot_type=request.type,
        storage_path=volume.path,
        metadata={"description": request.description}
    )
    
    return {
        "snapshot_id": str(snapshot_id.id),
        "pod_id": pod_id,
        "type": request.type,
        "created_at": datetime.utcnow().isoformat()
    }


# ============== Node Endpoints ==============

@app.get("/api/v1/nodes")
async def list_nodes(user: User = Depends(require_tier("enterprise"))):
    """List compute nodes (enterprise only)"""
    if not state.scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    
    return state.scheduler.get_cluster_status()


@app.get("/api/v1/nodes/{node_id}")
async def get_node(node_id: str, user: User = Depends(require_tier("enterprise"))):
    """Get node details"""
    if not state.scheduler:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    
    status = state.scheduler.get_node_status(node_id)
    if not status:
        raise HTTPException(status_code=404, detail="Node not found")
    
    return status


# ============== Auth Endpoints ==============

@app.post("/api/v1/auth/login")
async def login(email: str, password: str):
    """Login and get JWT token"""
    result = state.auth_manager.login(email, password)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token, user = result
    return {
        "token": token,
        "user": {
            "id": user.id,
            "email": user.email,
            "tier": user.tier
        }
    }


@app.post("/api/v1/auth/api-keys", response_model=APIKeyResponse, status_code=201)
async def create_api_key(
    request: CreateAPIKeyRequest,
    user: User = Depends(require_user)
):
    """Create an API key"""
    api_key = state.auth_manager.create_api_key(
        user_id=user.id,
        name=request.name,
        expires_days=request.expires_days
    )
    
    return APIKeyResponse(
        key=api_key.key,
        name=api_key.name,
        created_at=api_key.created_at.isoformat(),
        expires_at=api_key.expires_at.isoformat() if api_key.expires_at else None
    )


@app.get("/api/v1/auth/api-keys")
async def list_api_keys(user: User = Depends(require_user)):
    """List user's API keys"""
    keys = state.auth_manager.api_key_manager.list_user_keys(user.id)
    return {
        "keys": [
            {
                "name": k.name,
                "created_at": k.created_at.isoformat(),
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "scopes": k.scopes
            }
            for k in keys
        ]
    }


# ============== WebSocket Endpoints ==============

@app.websocket("/ws/logs/{session_id}")
async def websocket_logs(websocket: WebSocket, session_id: str):
    """Real-time logs for a session"""
    await websocket.accept()
    
    try:
        while True:
            # In production, stream actual logs from container/VM
            await websocket.send_json({
                "session_id": session_id,
                "log": "Session running...",
                "timestamp": datetime.utcnow().isoformat()
            })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")


@app.websocket("/ws/stream/{session_id}")
async def websocket_stream(websocket: WebSocket, session_id: str):
    """WebRTC signaling for streaming"""
    await websocket.accept()
    
    session = state.sessions.get(session_id)
    if not session:
        await websocket.close(code=1008, reason="Session not found")
        return
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # Handle WebRTC signaling
            if data.get("type") == "offer":
                # Would handle WebRTC offer
                await websocket.send_json({
                    "type": "answer",
                    "sdp": "..."  # WebRTC answer
                })
            elif data.get("type") == "ice-candidate":
                # Would handle ICE candidate
                pass
            elif data.get("type") == "input":
                # Would forward input to pod
                if state.streaming_manager:
                    await state.streaming_manager.stream_server.handle_client_input(
                        session.get("pod_id"),
                        data.get("event", {})
                    )
                    
    except WebSocketDisconnect:
        logger.info(f"Stream WebSocket disconnected for session {session_id}")


# ============== Error Handlers ==============

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )
