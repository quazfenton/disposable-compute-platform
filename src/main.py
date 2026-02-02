"""
Main application entry point for disposable compute platform
Integrates all three components: Preview Environments, Run This Repo, and Forkable GUI Sessions
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional

from src.services.platform import SessionManager, PlatformConfig
from src.services.preview import extend_session_manager_with_preview
from src.services.run_repo import extend_session_manager_with_run_repo
from src.services.fork_gui import extend_session_manager_with_forkable_gui
from src.utils.security import integrate_security_manager
from src.api.main import app, session_manager


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
        
        # Component managers
        self.preview_manager = None
        self.run_repo_manager = None
        self.fork_gui_manager = None
    
    async def initialize(self):
        """Initialize all platform components"""
        if self.initialized:
            return
        
        logger.info("Initializing Disposable Compute Platform...")
        
        # Extend session manager with all capabilities
        await extend_session_manager_with_preview(self.session_manager)
        await extend_session_manager_with_run_repo(self.session_manager)
        await extend_session_manager_with_forkable_gui(self.session_manager)
        await integrate_security_manager(self.session_manager)
        
        # Set up component managers (these are now integrated into the session manager)
        from .services.preview import PreviewEnvironmentManager
        from .services.run_repo import RunRepoManager
        from .services.fork_gui import ForkableSessionManager
        
        self.preview_manager = PreviewEnvironmentManager(self.session_manager)
        self.run_repo_manager = RunRepoManager(self.session_manager)
        self.fork_gui_manager = ForkableSessionManager(
            self.session_manager, 
            self.session_manager.snapshot_manager
        )
        
        self.initialized = True
        logger.info("Disposable Compute Platform initialized successfully")
    
    async def create_preview_environment(self, repo_url: str, repo_ref: str, pr_number: int) -> str:
        """Create a preview environment for a PR"""
        session = await self.session_manager.create_session(
            session_type="preview",
            repo_url=repo_url,
            repo_ref=repo_ref,
            pr_number=pr_number
        )
        return session.id
    
    async def run_repo(self, repo_url: str, repo_ref: Optional[str] = None, ttl_minutes: int = 30) -> str:
        """Run a repository in a disposable environment"""
        session = await self.session_manager.create_session(
            session_type="run_repo",
            repo_url=repo_url,
            repo_ref=repo_ref,
            ttl_minutes=ttl_minutes
        )
        return session.id
    
    async def create_forkable_gui_session(self, app_type: str, repo_url: Optional[str] = None, 
                                        repo_ref: Optional[str] = None) -> str:
        """Create a forkable GUI session"""
        session = await self.session_manager.create_session(
            session_type="fork_gui",
            repo_url=repo_url or "https://github.com/example/gui-app.git",
            repo_ref=repo_ref,
            ttl_minutes=120  # 2 hours for GUI sessions
        )
        # Set app type in session metadata
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
            "urls": await self._get_session_urls(session)
        }
    
    async def _get_session_urls(self, session) -> List[str]:
        """Get accessible URLs for a session"""
        urls = []
        if session.ports:
            for service_name, port in session.ports.items():
                if port:
                    urls.append(f"https://{session.id[:8]}.{self.config.domain}:{port}")
        return urls
    
    async def destroy_session(self, session_id: str):
        """Destroy a session and all its resources"""
        await self.session_manager.destroy_session(session_id)
    
    async def cleanup_expired_sessions(self):
        """Clean up all expired sessions"""
        return await self.session_manager.cleanup_expired_sessions()


# Global platform instance for the API
platform = DisposableComputePlatform()


# Function to start the platform
async def start_platform():
    """Start the disposable compute platform"""
    await platform.initialize()
    
    # Start background tasks
    asyncio.create_task(run_background_tasks())
    
    logger.info("Disposable Compute Platform started successfully")


async def run_background_tasks():
    """Run background maintenance tasks"""
    while True:
        try:
            # Clean up expired sessions every 5 minutes
            expired = await platform.cleanup_expired_sessions()
            if expired:
                logger.info(f"Cleaned up {len(expired)} expired sessions")
            
            # Wait 5 minutes
            await asyncio.sleep(300)
        except Exception as e:
            logger.error(f"Error in background tasks: {e}")
            await asyncio.sleep(60)  # Wait 1 minute before retrying


# Platform should be initialized explicitly by calling start_platform()
# in an async context, e.g., during FastAPI lifespan or uvicorn startup


# Example usage functions
async def example_usage():
    """Example of how to use the platform"""
    # Initialize platform
    await platform.initialize()
    
    # Example 1: Create a preview environment for a PR
    preview_id = await platform.create_preview_environment(
        repo_url="https://github.com/example/myapp.git",
        repo_ref="feature/new-feature",
        pr_number=142
    )
    print(f"Created preview environment: {preview_id}")
    
    # Example 2: Run a repository
    run_id = await platform.run_repo(
        repo_url="https://github.com/example/hello-world.git"
    )
    print(f"Created run-repo session: {run_id}")
    
    # Example 3: Create a forkable GUI session
    gui_id = await platform.create_forkable_gui_session(
        app_type="threejs-editor",
        repo_url="https://github.com/example/3d-editor.git"
    )
    print(f"Created forkable GUI session: {gui_id}")
    
    # Check status
    status = await platform.get_session_status(preview_id)
    print(f"Preview status: {status}")


if __name__ == "__main__":
    # For testing purposes
    asyncio.run(example_usage())