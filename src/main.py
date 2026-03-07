"""
Main application entry point for disposable compute platform
Integrates all three components: Preview Environments, Run This Repo, and Forkable GUI Sessions
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

from src.services.platform import SessionManager, PlatformConfig, SessionType
from src.utils.security import integrate_security_manager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DisposableComputePlatform:
    """Main platform class that orchestrates all components"""
    
    def __init__(self, config: Optional[PlatformConfig] = None):
        self.config = config or PlatformConfig()
        self.session_manager = SessionManager(self.config)
        self.initialized = False
    
    async def initialize(self):
        """Initialize all platform components"""
        if self.initialized:
            return
        
        logger.info("Initializing Vanish Compute (VNC)...")
        await integrate_security_manager(self.session_manager)
        
        self.initialized = True
        logger.info("Vanish Compute (VNC) initialized successfully")
    
    async def create_preview_environment(self, repo_url: str, repo_ref: str, pr_number: int) -> str:
        """Create a preview environment for a PR"""
        session = await self.session_manager.create_session(
            session_type=SessionType.PREVIEW,
            repo_url=repo_url,
            repo_ref=repo_ref,
            pr_number=pr_number
        )
        return session.id
    
    async def run_repo(self, repo_url: str, repo_ref: Optional[str] = None, ttl_minutes: int = 30) -> str:
        """Run a repository in a disposable environment"""
        session = await self.session_manager.create_session(
            session_type=SessionType.RUN_REPO,
            repo_url=repo_url,
            repo_ref=repo_ref,
            ttl_minutes=ttl_minutes
        )
        return session.id
    
    async def create_forkable_gui_session(self, app_type: str, repo_url: Optional[str] = None, 
                                        repo_ref: Optional[str] = None) -> str:
        """Create a forkable GUI session"""
        session = await self.session_manager.create_session(
            session_type=SessionType.FORK_GUI,
            repo_url=repo_url or "https://github.com/example/gui-app.git",
            repo_ref=repo_ref,
            ttl_minutes=120  # 2 hours for GUI sessions
        )

        session.metadata['app_type'] = app_type
        return session.id
    
    async def get_session_status(self, session_id: str) -> Dict:
        """Get the status of a session"""
        if session_id not in self.session_manager.sessions:
            return {"error": "Session not found"}
        
        session = self.session_manager.sessions[session_id]
        return {
            "id": session.id,
            "type": session.type.value,
            "status": session.status.value,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat() if session.expires_at else None,
            "ports": session.ports,
        }
    
    async def destroy_session(self, session_id: str):
        """Destroy a session and all its resources"""
        await self.session_manager.destroy_session(session_id)
    
    async def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        now = datetime.now()
        expired_sessions = [
            sid for sid, session in self.session_manager.sessions.items()
            if session.expires_at and session.expires_at < now
        ]
        
        for session_id in expired_sessions:
            await self.destroy_session(session_id)
            if session_id in self.session_manager.sessions:
                del self.session_manager.sessions[session_id]
        
        return expired_sessions

    async def get_session_logs(self, session_id: str, service_name: str = "main", lines: int = 100) -> str:
        """Get logs from a session's service"""
        # Get pod_id from session metadata
        if session_id in self.session_manager.sessions:
            session = self.session_manager.sessions[session_id]
            pod_id = session.metadata.get('pod_id')
            if pod_id:
                return await self.session_manager.orchestrator.container_orchestrator.get_container_logs(
                    pod_id, lines
                )
        return "Logs not available"


# Global platform instance
platform = DisposableComputePlatform()

def get_platform():
    return platform

async def start_platform():
    await platform.initialize()
    asyncio.create_task(run_background_tasks())
    logger.info("Vanish Compute (VNC) started successfully")

async def run_background_tasks():
    while True:
        try:
            expired = await platform.cleanup_expired_sessions()
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sessions")
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Error in background tasks: {e}")
            await asyncio.sleep(60)
