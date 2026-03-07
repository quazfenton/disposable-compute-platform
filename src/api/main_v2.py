"""
Production-ready API for Disposable Compute Platform
"""
import os
import asyncio
import logging
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field, validator

# Internal imports
from src.api.auth import AuthManager, User, UserTier
from src.metrics.metrics import get_metrics, get_health_checker
from src.metrics.alerting import get_alert_manager
from src.services.platform import SessionManager, PlatformConfig, SessionType
from src.database.db import init_database, close_database, Database

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
        
        # Alerting
        self.pagerduty_key = os.getenv("PAGERDUTY_API_KEY")
        self.opsgenie_key = os.getenv("OPSGENIE_API_KEY")


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


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    checks: Dict[str, Any]


# ============== Application State ==============

class AppState:
    """Global application state"""
    def __init__(self):
        self.platform: Optional[SessionManager] = None
        self.auth_manager: Optional[AuthManager] = None
        self.database: Optional[Database] = None


state = AppState()


# ============== Lifespan ==============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting Vanish Compute (VNC) API...")

    # Initialize database
    try:
        state.database = await init_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed: {e}")

    # Initialize Auth
    state.auth_manager = AuthManager(database=state.database)

    # Initialize Platform
    platform_config = PlatformConfig(
        domain=config.domain,
        default_ttl=config.default_ttl,
        max_ttl=config.max_ttl,
        max_concurrent_sessions=config.max_concurrent_sessions
    )
    state.platform = SessionManager(platform_config)

    # Configure Alerting
    alert_mgr = get_alert_manager()
    if alert_mgr:
        if config.pagerduty_key:
            alert_mgr.configure_pagerduty(config.pagerduty_key)
        if config.opsgenie_key:
            alert_mgr.configure_opsgenie(config.opsgenie_key)

    # Initialize Health Checker
    try:
        health_checker = get_health_checker()
        await health_checker.run_checks()  # Initial health check
        asyncio.create_task(health_checker.start_background_checks(interval_seconds=30))
        app.state.health_checker = health_checker
        logger.info("✅ Health checks initialized")
    except Exception as e:
        logger.warning(f"Health checker initialization failed: {e}")

    # Start background tasks
    if state.platform:
        asyncio.create_task(state.platform.cleanup_expired_sessions())

    logger.info("API Lifespan initialized successfully")

    yield

    # Shutdown: Stop health checks
    if hasattr(app.state, 'health_checker'):
        try:
            await app.state.health_checker.stop_background_checks()
            logger.info("Health checks stopped")
        except Exception as e:
            logger.error(f"Error stopping health checks: {e}")

    if state.database:
        await close_database()
    logger.info("API Shutdown complete")


# ============== FastAPI App ==============

app = FastAPI(
    title="Vanish Compute (VNC) API",
    version="2.0.0",
    description="Production-ready API for ephemeral compute environments",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============== Dependencies ==============

async def get_user(request: Request) -> User:
    """Get the current authenticated user"""
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        # For development, return default user if no auth provided
        return User(id="dev-user", email="dev@example.com", tier=UserTier.ENTERPRISE)
    
    return await state.auth_manager.get_current_user_from_request(request)


# ============== API Endpoints ==============

@app.post("/api/v1/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_session(
    request: CreateSessionRequest,
    user: User = Depends(get_user)
):
    """Create a new disposable session"""
    session_type_map = {
        "preview": SessionType.PREVIEW,
        "run_repo": SessionType.RUN_REPO,
        "fork_gui": SessionType.FORK_GUI
    }
    
    try:
        session = await state.platform.create_session(
            session_type=session_type_map[request.type],
            repo_url=request.repo_url,
            repo_ref=request.repo_ref,
            pr_number=request.pr_number,
            ttl_minutes=request.ttl_minutes
        )
        
        return CreateSessionResponse(
            session_id=session.id,
            status=session.status.value,
            created_at=session.created_at.isoformat(),
            expires_at=session.expires_at.isoformat() if session.expires_at else ""
        )
    except Exception as e:
        logger.error(f"Session creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/sessions/{session_id}", response_model=SessionResponse)
async def get_session_details(session_id: str, user: User = Depends(get_user)):
    """Get session details"""
    if state.platform is None:
        raise HTTPException(status_code=503, detail="Platform not initialized")
        
    if session_id not in state.platform.sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = state.platform.sessions[session_id]
    return SessionResponse(
        id=session.id,
        type=session.type.value,
        status=session.status.value,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        expires_at=session.expires_at.isoformat() if session.expires_at else None,
        repo_url=session.repo_url,
        stream_url=session.metadata.get('stream_url'),
        pod_id=f"pod-{session.id}",
        node_id=session.metadata.get('node_id'),
        metadata=session.metadata
    )


@app.delete("/api/v1/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, user: User = Depends(get_user)):
    """Destroy a session"""
    if state.platform is None:
        raise HTTPException(status_code=503, detail="Platform not initialized")
        
    await state.platform.destroy_session(session_id)
    return Response(status_code=204)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    health = get_health_checker()
    result = await health.run_checks()
    return HealthResponse(**result)


@app.get("/metrics")
async def get_platform_metrics():
    """Prometheus metrics endpoint"""
    metrics = get_metrics()
    return Response(content=metrics.registry.export_prometheus(), media_type="text/plain")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
