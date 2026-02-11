"""
"Run This Repo" implementation for disposable compute platform
"""
import asyncio
import tempfile
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import subprocess
import json

from src.models.session import Session, ServiceDefinition, SessionStatus
from src.models.environment import Environment
from src.services.platform import SessionManager


class RuntimeDetector:
    """Detects runtime environments from repository files"""
    
    def __init__(self):
        self.runtime_configs = {
            'node': {
                'files': ['package.json'],
                'default_command': 'npm start',
                'image': 'node:18-alpine',
                'port': 3000
            },
            'python': {
                'files': ['requirements.txt', 'pyproject.toml', 'setup.py'],
                'default_command': 'python app.py',
                'image': 'python:3.11-slim',
                'port': 8000
            },
            'go': {
                'files': ['go.mod', 'main.go'],
                'default_command': 'go run main.go',
                'image': 'golang:1.21-alpine',
                'port': 8080
            },
            'rust': {
                'files': ['Cargo.toml', 'src/main.rs'],
                'default_command': 'cargo run',
                'image': 'rust:1.70-alpine',
                'port': 8000
            },
            'java': {
                'files': ['pom.xml', 'build.gradle', 'Main.java'],
                'default_command': 'java -jar app.jar',
                'image': 'openjdk:17-alpine',
                'port': 8080
            }
        }
    
    async def detect_runtime(self, repo_url: str, repo_ref: Optional[str] = None) -> Optional[Dict[str, str]]:
        """Detect the runtime from a repository"""
        # In a real implementation, this would clone the repo and inspect files
        # For now, we'll simulate by checking for common files
        
        # Simulate checking for runtime files
        # This is a simplified version - in reality, you'd inspect the actual repository
        detected_runtime = None
        
        # For simulation purposes, let's assume we detected Node.js
        # In a real implementation, you'd check the actual files in the repo
        detected_runtime = 'node'
        
        if detected_runtime and detected_runtime in self.runtime_configs:
            return self.runtime_configs[detected_runtime]
        
        return None
    
    async def get_entrypoint_command(self, repo_url: str, repo_ref: Optional[str] = None, 
                                   runtime_info: Optional[Dict[str, str]] = None) -> str:
        """Get the entrypoint command for a repository"""
        if not runtime_info:
            runtime_info = await self.detect_runtime(repo_url, repo_ref)
        
        if not runtime_info:
            return "echo 'No supported runtime detected'"
        
        # Check for run.yaml first
        # In a real implementation, this would check the actual repo
        # For now, we'll simulate
        
        # Default to runtime's default command
        return runtime_info['default_command']


class ImageBuilder:
    """Builds Docker images for repositories"""
    
    def __init__(self):
        self.build_cache = {}
    
    async def build_image_for_repo(self, repo_url: str, repo_ref: Optional[str] = None, 
                                 runtime_info: Optional[Dict[str, str]] = None) -> str:
        """Build a Docker image for a repository"""
        # Create a unique image name based on repo and timestamp
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        image_name = f"run-repo-{repo_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.urandom(4).hex()}"
        
        # In a real implementation, this would:
        # 1. Clone the repository
        # 2. Create a Dockerfile based on the runtime
        # 3. Build the image
        
        # For simulation, return a placeholder image
        if runtime_info:
            base_image = runtime_info['image']
        else:
            base_image = 'alpine:latest'
        
        # This would be the actual Docker build process
        print(f"Building image {image_name} from {repo_url} with base {base_image}")
        
        # Store in cache
        self.build_cache[image_name] = {
            'repo_url': repo_url,
            'repo_ref': repo_ref,
            'base_image': base_image,
            'built_at': datetime.now()
        }
        
        return image_name


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