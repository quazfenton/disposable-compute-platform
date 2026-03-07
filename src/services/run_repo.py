"""
"Run This Repo" implementation for disposable compute platform
"""
import asyncio
import tempfile
import os
import docker
import logging
from git import Repo
from typing import Dict, Optional, Any
from datetime import datetime
import json

from src.models.session import Session, SessionStatus
from src.models.environment import Environment
from src.services.platform import SessionManager
from src.utils.input_validation import validate_repo_url, validate_ref_name

logger = logging.getLogger(__name__)

class ImageBuilder:
    """Builds Docker images for repositories"""
    
    def __init__(self):
        self.client = docker.from_env()
        self.build_cache = {}
        self._build_semaphore = asyncio.Semaphore(5)  # Limit concurrent builds
    
    async def build_image_for_repo(self, repo_url: str, repo_ref: Optional[str] = None, 
                                 runtime_info: Optional[Dict[str, Any]] = None) -> str:
        """Build a Docker image for a repository"""
        # Sanitize inputs
        is_valid, error = validate_repo_url(repo_url)
        if not is_valid:
            raise ValueError(f"Invalid repository URL: {error}")
            
        if repo_ref:
            is_valid, error = validate_ref_name(repo_ref)
            if not is_valid:
                raise ValueError(f"Invalid repository reference: {error}")

        # Create a unique image name based on repo and timestamp
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        image_tag = f"run-repo-{repo_name.lower()}:{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        async with self._build_semaphore:
            with tempfile.TemporaryDirectory() as tmp_dir:
                # Clone the repository
                try:
                    await asyncio.to_thread(Repo.clone_from, repo_url, tmp_dir)
                    if repo_ref:
                        repo = Repo(tmp_dir)
                        await asyncio.to_thread(repo.git.checkout, repo_ref)
                except Exception as e:
                    logger.error(f"Failed to clone repository {repo_url}: {e}")
                    raise RuntimeError(f"Cloning failed: {e}")
                
                # Create a simple Dockerfile if one doesn't exist
                dockerfile_path = os.path.join(tmp_dir, 'Dockerfile')
                if not os.path.exists(dockerfile_path) and runtime_info:
                    with open(dockerfile_path, 'w') as f:
                        f.write(f"FROM {runtime_info['image']}\n")
                        f.write("WORKDIR /app\n")
                        f.write("COPY . .\n")
                        if runtime_info.get('files') and 'package.json' in runtime_info['files']:
                            f.write("RUN npm install\n")
                        f.write(f"EXPOSE {runtime_info.get('port', 8080)}\n")
                        f.write(f"CMD {runtime_info['default_command']}\n")
                
                # Build the image
                logger.info(f"Building image {image_tag} from {repo_url}")
                try:
                    image, logs = await asyncio.to_thread(
                        self.client.images.build, path=tmp_dir, tag=image_tag, rm=True
                    )
                except Exception as e:
                    logger.error(f"Docker build failed for {image_tag}: {e}")
                    raise RuntimeError(f"Docker build failed: {e}")
                
                # Store in cache
                self.build_cache[image_tag] = {
                    'repo_url': repo_url,
                    'repo_ref': repo_ref,
                    'built_at': datetime.now()
                }
                
                return image_tag



class RunRepoManager:
    """Manages the "Run This Repo" functionality"""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.runtime_detector = RuntimeDetector()
        self.image_builder = ImageBuilder()
    
    async def create_run_repo_session(self, session: Session) -> Environment:
        """Create a run-repo session for a repository"""
        # Detect runtime from repository
        runtime_info = await self.runtime_detector.detect_runtime(
            session.repo_url, session.repo_ref
        )
        
        if not runtime_info:
            raise ValueError(f"Unsupported runtime for repository: {session.repo_url}")
        
        # Get entrypoint command
        command = await self.runtime_detector.get_entrypoint_command(
            session.repo_url, session.repo_ref, runtime_info
        )
        
        # Build image for the repository
        image_name = await self.image_builder.build_image_for_repo(
            session.repo_url, session.repo_ref, runtime_info
        )
        
        # Create service definition
        service = {
            'name': 'app',
            'type': 'web',
            'image': image_name,  # Use the built image
            'command': command,
            'port': runtime_info.get('port', 8080),
            'env': {
                'PORT': str(runtime_info.get('port', 8080)),
                'NODE_ENV': 'production' if runtime_info.get('image', '').startswith('node:') else ''
            }
        }
        
        # Create environment
        environment = Environment(
            id=f"env-{session.id}",
            name=f"run-{session.id}",
            session_id=session.id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=session.expires_at,
            services=[service]
        )
        
        # Create isolated network
        network_name = self.session_manager.network_manager.create_isolated_network(environment.id)
        environment.network_name = network_name
        
        # Create containers
        container_ids = self.session_manager.container_orchestrator.create_environment_containers(environment)
        
        # Update session with container info
        session.container_id = json.dumps(container_ids)
        session.network_id = network_name
        session.status = SessionStatus.RUNNING

        # Create external access
        if service.get('port'):
            url = self.session_manager.network_manager.create_external_access(
                session.id, service['port'], self.session_manager.config.domain
            )
            session.ports = {service['name']: service['port']}
        
        return environment
    
    async def get_repo_metadata(self, repo_url: str, repo_ref: Optional[str] = None) -> Dict[str, str]:
        """Get metadata about a repository"""
        # In a real implementation, this would fetch repository metadata
        # For now, return simulated metadata
        return {
            'language': 'JavaScript',
            'framework': 'Express.js',
            'description': 'A sample Node.js application',
            'last_updated': datetime.now().isoformat()
        }


class TerminalSessionManager:
    """Manages terminal access for run-repo sessions"""
    
    def __init__(self):
        self.active_terminals = {}
    
    async def create_terminal_session(self, session_id: str, container_id: str) -> str:
        """Create a terminal session for a container"""
        terminal_id = f"terminal-{session_id}-{datetime.now().strftime('%H%M%S')}"
        
        # In a real implementation, this would set up a WebSocket terminal connection
        # For now, we'll just track the terminal
        self.active_terminals[terminal_id] = {
            'session_id': session_id,
            'container_id': container_id,
            'created_at': datetime.now()
        }
        
        return terminal_id
    
    async def destroy_terminal_session(self, terminal_id: str):
        """Destroy a terminal session"""
        if terminal_id in self.active_terminals:
            del self.active_terminals[terminal_id]


# Integration with the main SessionManager
async def extend_session_manager_with_run_repo(session_manager: SessionManager):
    """Extend the session manager with run-repo capabilities"""
    run_repo_manager = RunRepoManager(session_manager)
    terminal_manager = TerminalSessionManager()
    
    # Override the run-repo session creation method
    original_create_run_repo = session_manager._create_run_repo_session

    async def new_create_run_repo_session(session: Session):
        # Call the original method first if it exists
        if original_create_run_repo:
            await original_create_run_repo(session)
        # Then run our custom logic
        await run_repo_manager.create_run_repo_session(session)

    session_manager._create_run_repo_session = new_create_run_repo_session