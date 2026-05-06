"""
Enhanced API layer for disposable compute platform with production features
Integrates: Authentication, Database, Redis, Rate Limiting, Error Handling, Health Checks
"""
import os
import logging
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional, List, Dict, Any

# Import models
from src.models.session import SessionType, SessionStatus
from src.services.platform import SessionManager, PlatformConfig
from src.api.auth import AuthManager, User, get_current_user, require_auth, require_quota_check
from src.api.middleware.rate_limit import rate_limit_middleware, setup_rate_limiting, quota_manager
from src.api.middleware.error_handler import setup_error_handlers, NotFoundError, ValidationError
from src.services.health import init_health_checker, get_health_checker
from src.database.db import DatabaseConfig
from src.database.session_integration import extend_session_manager_with_database, SessionHistory
from src.database.redis_integration import init_redis_store, connect_redis, get_redis_store, RedisConfig
from src.utils.input_validation import InputValidator
from src.utils.logging_config import setup_logging, get_logger

# Request/Response models
from pydantic import BaseModel

logger = get_logger(__name__)

# Initialize logging
setup_logging()

# Initialize the API
app = FastAPI(
    title="Disposable Compute Platform API",
    version="2.0.0",
    description="Production-ready API with authentication, database persistence, and distributed state"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
app.add_middleware(rate_limit_middleware)

# Setup error handlers
setup_error_handlers(app)

# Initialize platform services
config = PlatformConfig(
    domain=os.getenv("DOMAIN", "preview.yourapp.dev"),
    default_ttl=int(os.getenv("DEFAULT_TTL", "30")),
    max_ttl=int(os.getenv("MAX_TTL", "1440")),
    storage_path=os.getenv("STORAGE_PATH", "/tmp/disposable-storage"),
    max_concurrent_sessions=int(os.getenv("MAX_CONCURRENT_SESSIONS", "50")),
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0")
)

session_manager = SessionManager(config)

# Request/Response models
class CreateSessionRequest(BaseModel):
    type: str
    repo_url: str
    repo_ref: Optional[str] = None
    pr_number: Optional[int] = None
    ttl_minutes: Optional[int] = None
    metadata: Optional[Dict[str, str]] = None


class CreateSessionResponse(BaseModel):
    session_id: str
    status: str
    external_urls: List[str]
    created_at: str


class SessionResponse(BaseModel):
    id: str
    type: str
    status: str
    created_at: str
    updated_at: str
    expires_at: Optional[str]
    repo_url: Optional[str]
    repo_ref: Optional[str]
    pr_number: Optional[int]
    ports: Dict[str, int]
    metadata: Dict[str, str]


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


@app.on_event("startup")
async def startup_event():
    """Initialize all services on startup"""
    logger.info("Starting up Disposable Compute Platform API v2.0.0")
    
    try:
        # 1. Initialize Database
        db_config = DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=os.getenv("DB_NAME", "disposable_compute"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "")
        )
        
        db_integration = extend_session_manager_with_database(session_manager, db_config)
        await db_integration.initialize()
        app.state.database = db_integration.database
        app.state.db_integration = db_integration
        
        logger.info("✅ Database initialized")
        
        # 2. Initialize Redis
        redis_config = RedisConfig(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD")
        )
        
        redis_store = init_redis_store(redis_config)
        redis_connected = await connect_redis()
        
        if redis_connected:
            app.state.redis = redis_store
            logger.info("✅ Redis initialized")
        else:
            logger.warning("⚠️ Redis not available, using in-memory state")
        
        # 3. Initialize Auth Manager
        auth_manager = AuthManager(
            secret_key=os.getenv("AUTH_SECRET_KEY"),
            database=app.state.database
        )
        app.state.auth_manager = auth_manager
        logger.info("✅ Authentication initialized")
        
        # 4. Initialize Health Checker
        health_checker = init_health_checker(
            docker_client=None,  # Will auto-detect
            database=app.state.database,
            redis_client=redis_store if redis_connected else None,
            storage_path=config.storage_path
        )
        await health_checker.start_background_checks(interval_seconds=30)
        app.state.health_checker = health_checker
        logger.info("✅ Health checks initialized")
        
        # 5. Setup rate limiting
        setup_rate_limiting()
        logger.info("✅ Rate limiting configured")
        
        # 6. Check for orphaned resources
        if hasattr(session_manager, 'network_manager'):
            cleaned = await session_manager.network_manager.check_orphaned_networks()
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} orphaned networks")
        
        logger.info("🚀 Startup complete - API ready")
        
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down...")
    
    # Close database
    if hasattr(app.state, 'db_integration'):
        await app.state.db_integration.close()
    
    # Close Redis
    if hasattr(app.state, 'redis'):
        await app.state.redis.disconnect()
    
    # Stop health checks
    if hasattr(app.state, 'health_checker'):
        await app.state.health_checker.stop_background_checks()
    
    logger.info("Shutdown complete")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Disposable Compute Platform API",
        "version": "2.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    if not hasattr(app.state, 'health_checker'):
        return {"status": "unknown", "message": "Health checker not initialized"}
    
    report = await app.state.health_checker.check_all()
    return report.to_dict()


@app.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login and get access token"""
    auth_manager = app.state.auth_manager
    
    # Authenticate user
    user = await auth_manager.authenticate_user(request.email, request.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Create access token
    access_token = auth_manager.create_access_token(
        user_id=user.id,
        email=user.email,
        tier=user.tier.value
    )
    
    return LoginResponse(
        access_token=access_token,
        expires_in=auth_manager.token_expiry_minutes * 60,
        user=user
    )


@app.post("/sessions", response_model=CreateSessionResponse)
@require_auth
@require_quota_check("sessions_per_hour")
async def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a new disposable session"""
    # Validate all inputs
    is_valid, error, sanitized = InputValidator.validate_create_session_request(
        session_type=request.type,
        repo_url=request.repo_url,
        repo_ref=request.repo_ref,
        pr_number=request.pr_number,
        ttl_minutes=request.ttl_minutes,
        metadata=request.metadata
    )
    
    if not is_valid:
        raise ValidationError(error)
    
    # Check user quota
    has_quota, remaining = quota_manager.check_quota(
        current_user.id,
        current_user.tier.value,
        "sessions_per_hour"
    )
    
    if not has_quota:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Session quota exceeded. Remaining: {remaining}"
        )
    
    try:
        # Create session
        session = await session_manager.create_session(
            session_type=SessionType(sanitized['session_type']),
            repo_url=sanitized['repo_url'],
            repo_ref=sanitized['repo_ref'],
            pr_number=sanitized['pr_number'],
            ttl_minutes=sanitized['ttl_minutes'],
            user_id=current_user.id
        )
        
        # Add user to session metadata
        session.metadata['user_id'] = current_user.id
        session.metadata['user_tier'] = current_user.tier.value
        
        # Extract external URLs
        external_urls = []
        if session.ports:
            for service_name, port in session.ports.items():
                external_urls.append(
                    f"https://{session.id[:8]}.{config.domain}:{port}"
                )
        
        # Log event
        if hasattr(app.state, 'db_integration'):
            history = SessionHistory(app.state.database)
            await history.log_session_event(
                session.id,
                "created",
                {
                    "user_id": current_user.id,
                    "type": request.type,
                    "repo_url": request.repo_url
                }
            )
        
        return CreateSessionResponse(
            session_id=session.id,
            status=session.status.value,
            external_urls=external_urls,
            created_at=session.created_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Failed to create session: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session: {str(e)}"
        )


@app.get("/sessions/{session_id}", response_model=SessionResponse)
@require_auth
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get session details"""
    # Try Redis cache first
    if hasattr(app.state, 'redis'):
        cached = await app.state.redis.get_session(session_id)
        if cached:
            return SessionResponse(**cached)
    
    # Check in-memory
    if session_id in session_manager.sessions:
        session = session_manager.sessions[session_id]
        
        # Check ownership
        if session.metadata.get('user_id') != current_user.id:
            if current_user.tier.value != 'enterprise':
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to this session"
                )
        
        # Convert to response
        response = SessionResponse(
            id=session.id,
            type=session.type.value,
            status=session.status.value,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            expires_at=session.expires_at.isoformat() if session.expires_at else None,
            repo_url=session.repo_url,
            repo_ref=session.repo_ref,
            pr_number=session.pr_number,
            ports=session.ports,
            metadata=session.metadata
        )
        
        # Cache in Redis
        if hasattr(app.state, 'redis'):
            await app.state.redis.set_session(
                session_id,
                response.dict(),
                ttl_seconds=300
            )
        
        return response
    
    # Not found
    raise NotFoundError("Session", session_id)


@app.delete("/sessions/{session_id}")
@require_auth
async def destroy_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Destroy a session"""
    # Check if session exists
    if session_id not in session_manager.sessions:
        raise NotFoundError("Session", session_id)
    
    session = session_manager.sessions[session_id]
    
    # Check ownership
    if session.metadata.get('user_id') != current_user.id:
        if current_user.tier.value != 'enterprise':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot destroy session owned by another user"
            )
    
    # Destroy session
    await session_manager.destroy_session(session_id)
    
    # Log event
    if hasattr(app.state, 'db_integration'):
        history = SessionHistory(app.state.database)
        await history.log_session_event(
            session_id,
            "destroyed",
            {"user_id": current_user.id}
        )
    
    return {"message": f"Session {session_id} destroyed successfully"}


@app.get("/sessions/{session_id}/logs")
@require_auth
async def get_session_logs(
    session_id: str,
    service: str = "main",
    lines: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get logs from a session"""
    if session_id not in session_manager.sessions:
        raise NotFoundError("Session", session_id)
    
    session = session_manager.sessions[session_id]
    
    # Check ownership
    if session.metadata.get('user_id') != current_user.id:
        if current_user.tier.value != 'enterprise':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this session's logs"
            )
    
    logs = await session_manager.get_session_logs(session_id, service, lines)
    
    return {"service": service, "logs": logs, "lines": lines}


@app.get("/stats")
@require_auth
async def get_stats(current_user: User = Depends(get_current_user)):
    """Get platform statistics"""
    stats = {
        "platform": {},
        "user": {}
    }
    
    # Platform stats
    stats["platform"]["active_sessions"] = len([
        s for s in session_manager.sessions.values()
        if s.status == SessionStatus.RUNNING
    ])
    
    # Redis stats
    if hasattr(app.state, 'redis'):
        stats["redis"] = await app.state.redis.get_stats()
    
    # Health stats
    if hasattr(app.state, 'health_checker'):
        stats["health"] = app.state.health_checker.get_status_summary()
    
    # User stats
    if hasattr(app.state, 'db_integration'):
        history = SessionHistory(app.state.database)
        stats["user"] = await history.get_user_statistics(current_user.id)
    
    return stats


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_enhanced:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
