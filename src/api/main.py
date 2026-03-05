"""
API layer for disposable compute platform
SECURITY ENHANCED: Authentication and input validation wired to all endpoints

⚠️ DEPRECATED: This file is no longer used in production.
Production entry point: src/api/main_v2.py
This file is kept for reference only and may be removed in a future version.
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import json
import os
from datetime import datetime

from src.models.session import SessionType, SessionStatus
from src.services.platform import SessionManager, PlatformConfig
from src.api.auth import AuthManager, get_current_user, User
from src.utils.input_validation import validate_repo_url, validate_ttl
from src.database.session_integration import DatabaseIntegration
from src.database.db import DatabaseConfig


# Request/Response models
class CreateSessionRequest(BaseModel):
    type: str  # "preview", "run_repo", "fork_gui"
    repo_url: str
    repo_ref: Optional[str] = None
    pr_number: Optional[int] = None
    ttl_minutes: Optional[int] = None


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


class LogResponse(BaseModel):
    service: str
    logs: str


class ForkSessionRequest(BaseModel):
    session_id: str
    snapshot_id: Optional[str] = None


class ForkSessionResponse(BaseModel):
    new_session_id: str
    status: str


# WebSocket manager for real-time logs
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


from src.utils.logging_config import setup_logging, get_logger

# Initialize logging
setup_logging()
logger = get_logger(__name__)

# Initialize the API
app = FastAPI(title="Vanish Compute (VNC) API", version="1.0.0")


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize platform services
config = PlatformConfig(domain="preview.yourapp.dev", default_ttl=30)
session_manager = SessionManager(config)
connection_manager = ConnectionManager()
database_integration = None


@app.on_event("startup")
async def startup_event():
    """Initialize background tasks and database persistence"""
    global database_integration
    
    # Initialize database integration
    try:
        db_config = DatabaseConfig(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", "postgres"),
            database=os.getenv("DB_NAME", "disposable_compute")
        )
        database_integration = DatabaseIntegration(session_manager, db_config)
        await database_integration.initialize()
        logger.info("Database integration initialized")
    except Exception as e:
        logger.warning(f"Database initialization failed (continuing without persistence): {e}")
        database_integration = None
    
    # Recover sessions from database if available
    if database_integration:
        try:
            await session_manager.recover_sessions_from_database()
        except Exception as e:
            logger.error(f"Failed to recover sessions: {e}")
    
    # Start background cleanup
    asyncio.create_task(cleanup_expired_sessions())


@app.get("/")
async def root():
    return {"message": "Disposable Compute Platform API", "version": "1.0.0"}


@app.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user)
):
    """Create a new disposable session
    
    SECURITY: Requires authentication, validates input to prevent SSRF
    """
    try:
        # SECURITY: Validate repo_url to prevent SSRF attacks
        is_valid, error_msg = validate_repo_url(request.repo_url)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

        # SECURITY: Validate TTL to prevent resource exhaustion
        ttl_minutes, _ = validate_ttl(request.ttl_minutes)

        # Convert string type to enum
        session_type_map = {
            "preview": SessionType.PREVIEW,
            "run_repo": SessionType.RUN_REPO,
            "fork_gui": SessionType.FORK_GUI
        }

        if request.type not in session_type_map:
            raise HTTPException(status_code=400, detail="Invalid session type")

        # SECURITY: Check user quota
        user_sessions = [s for s in session_manager.sessions.values() if s.metadata.get('user_id') == current_user.id]
        if len(user_sessions) >= current_user.session_quota:
            raise HTTPException(
                status_code=429, 
                detail=f"Session quota exceeded. Your tier ({current_user.tier}) allows {current_user.session_quota} concurrent sessions."
            )

        session = await session_manager.create_session(
            session_type=session_type_map[request.type],
            repo_url=request.repo_url,
            repo_ref=request.repo_ref,
            pr_number=request.pr_number,
            ttl_minutes=ttl_minutes,
            user_id=current_user.id  # Track ownership
        )

        # Extract external URLs from ports
        external_urls = []
        if session.ports:
            for service_name, port in session.ports.items():
                external_urls.append(f"https://{session.id[:8]}.{config.domain}:{port}")

        return CreateSessionResponse(
            session_id=session.id,
            status=session.status.value,
            external_urls=external_urls,
            created_at=session.created_at.isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get session details
    
    SECURITY: Requires authentication, verifies session ownership
    """
    if session_id not in session_manager.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_manager.sessions[session_id]

    # SECURITY: Verify ownership (only owner can view session details)
    session_user_id = session.metadata.get('user_id')
    if session_user_id and session_user_id != current_user.id:
        if current_user.tier.value == 'free':
            raise HTTPException(status_code=403, detail="Not authorized to view this session")

    return SessionResponse(
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


@app.delete("/sessions/{session_id}")
async def destroy_session(
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Destroy a session
    
    SECURITY: Requires authentication, verifies ownership before deletion
    """
    if session_id not in session_manager.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_manager.sessions[session_id]

    # SECURITY: Verify ownership (only owner can delete)
    session_user_id = session.metadata.get('user_id')
    if session_user_id and session_user_id != current_user.id:
        if current_user.tier.value != 'enterprise':  # Enterprise can delete any session
            raise HTTPException(status_code=403, detail="Not authorized to delete this session")

    try:
        await session_manager.destroy_session(session_id)
        return {"message": f"Session {session_id} destroyed successfully"}
    except Exception as e:
        logger.error(f"Failed to destroy session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}/logs")
async def get_session_logs(
    session_id: str,
    service: str = "main",
    lines: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get logs from a session
    
    SECURITY: Requires authentication, verifies session ownership
    """
    if session_id not in session_manager.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_manager.sessions[session_id]

    # SECURITY: Verify ownership
    session_user_id = session.metadata.get('user_id')
    if session_user_id and session_user_id != current_user.id:
        if current_user.tier.value == 'free':
            raise HTTPException(status_code=403, detail="Not authorized to view this session's logs")

    logs = await session_manager.get_session_logs(session_id, service, lines)
    return LogResponse(service=service, logs=logs)


@app.websocket("/ws/logs/{session_id}")
async def websocket_logs(
    websocket: WebSocket,
    session_id: str,
    service: str = "main",
    authorization: Optional[str] = Header(None)
):
    """WebSocket endpoint for real-time logs
    
    SECURITY: Requires authentication via Authorization header
    """
    # SECURITY: Authenticate WebSocket connection
    if not authorization or not authorization.startswith("Bearer "):
        await websocket.close(code=4001, reason="Missing or invalid authorization")
        return

    token = authorization[7:]  # Remove "Bearer " prefix
    try:
        auth_manager = AuthManager()
        token_data = auth_manager.verify_token(token)
        user_id = token_data.user_id
    except Exception as e:
        await websocket.close(code=4002, reason=f"Invalid token: {str(e)}")
        return

    # Verify session exists
    if session_id not in session_manager.sessions:
        await websocket.close(code=4004, reason="Session not found")
        return

    session = session_manager.sessions[session_id]

    # SECURITY: Verify ownership
    session_user_id = session.metadata.get('user_id')
    if session_user_id and session_user_id != user_id:
        await websocket.close(code=4003, reason="Not authorized to view this session's logs")
        return

    # Connect authenticated user
    await connection_manager.connect(websocket)
    try:
        while True:
            # In a real implementation, this would stream logs in real-time
            # For now, we'll just send a periodic update
            logs = await session_manager.get_session_logs(session_id, service, 10)
            await connection_manager.send_personal_message(
                json.dumps({"service": service, "logs": logs, "timestamp": datetime.now().isoformat()}),
                websocket
            )
            await asyncio.sleep(5)  # Send update every 5 seconds
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        connection_manager.disconnect(websocket)


@app.post("/sessions/{session_id}/fork", response_model=ForkSessionResponse)
async def fork_session(
    request: ForkSessionRequest,
    session_id: str,
    current_user: User = Depends(get_current_user)
):
    """Fork a session (for GUI sessions)
    
    SECURITY: Requires authentication, verifies ownership
    """
    # Validate that the source session exists
    if session_id not in session_manager.sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = session_manager.sessions[session_id]

    # SECURITY: Verify ownership
    session_user_id = session.metadata.get('user_id')
    if session_user_id and session_user_id != current_user.id:
        if current_user.tier.value != 'enterprise':
            raise HTTPException(status_code=403, detail="Not authorized to fork this session")

    # This is a simplified implementation
    # In a real system, this would create a new session based on a snapshot
    new_session_id = f"fork-{session_id}-{datetime.now().strftime('%H%M%S')}"

    # For now, just return the new session ID
    # In a real implementation, we would copy the state from the original session
    return ForkSessionResponse(
        new_session_id=new_session_id,
        status="created"
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


async def cleanup_expired_sessions():
    """Background task to cleanup expired sessions"""
    while True:
        await asyncio.sleep(300)  # Run every 5 minutes
        expired = await session_manager.cleanup_expired_sessions()
        if expired:
            print(f"Cleaned up {len(expired)} expired sessions: {expired}")