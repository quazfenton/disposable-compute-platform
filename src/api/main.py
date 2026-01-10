"""
API layer for disposable compute platform
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import json
from datetime import datetime

from src.models.session import SessionType, SessionStatus
from src.services.platform import SessionManager, PlatformConfig


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


# Initialize the API
app = FastAPI(title="Disposable Compute Platform API", version="1.0.0")

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


@app.get("/")
async def root():
    return {"message": "Disposable Compute Platform API", "version": "1.0.0"}


@app.post("/sessions", response_model=CreateSessionResponse)
async def create_session(request: CreateSessionRequest):
    """Create a new disposable session"""
    try:
        # Convert string type to enum
        session_type_map = {
            "preview": SessionType.PREVIEW,
            "run_repo": SessionType.RUN_REPO,
            "fork_gui": SessionType.FORK_GUI
        }
        
        if request.type not in session_type_map:
            raise HTTPException(status_code=400, detail="Invalid session type")
        
        session = await session_manager.create_session(
            session_type=session_type_map[request.type],
            repo_url=request.repo_url,
            repo_ref=request.repo_ref,
            pr_number=request.pr_number,
            ttl_minutes=request.ttl_minutes
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Get session details"""
    if session_id not in session_manager.sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = session_manager.sessions[session_id]
    
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
async def destroy_session(session_id: str):
    """Destroy a session"""
    try:
        await session_manager.destroy_session(session_id)
        return {"message": f"Session {session_id} destroyed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}/logs")
async def get_session_logs(session_id: str, service: str = "main", lines: int = 100):
    """Get logs from a session"""
    logs = await session_manager.get_session_logs(session_id, service, lines)
    return LogResponse(service=service, logs=logs)


@app.websocket("/ws/logs/{session_id}")
async def websocket_logs(websocket: WebSocket, session_id: str, service: str = "main"):
    """WebSocket endpoint for real-time logs"""
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
            await asyncio.sleep(5)  # Update every 5 seconds
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)


@app.post("/sessions/{session_id}/fork", response_model=ForkSessionResponse)
async def fork_session(request: ForkSessionRequest, session_id: str):
    """Fork a session (for GUI sessions)"""
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


# Background task to cleanup expired sessions
@app.on_event("startup")
async def startup_event():
    """Initialize background tasks"""
    asyncio.create_task(cleanup_expired_sessions())


async def cleanup_expired_sessions():
    """Background task to cleanup expired sessions"""
    while True:
        await asyncio.sleep(300)  # Run every 5 minutes
        expired = await session_manager.cleanup_expired_sessions()
        if expired:
            print(f"Cleaned up {len(expired)} expired sessions: {expired}")