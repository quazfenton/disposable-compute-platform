"""
Preview Environments implementation for disposable compute platform
"""
import asyncio
import os
import tempfile
import yaml
import logging
from git import Repo
from typing import Dict, List, Optional, Any
from datetime import datetime
import subprocess
import json

from src.models.session import Session, ServiceDefinition
from src.types.platform_types import SessionStatus
from src.models.environment import Environment
from src.services.platform import SessionManager
from src.containers.orchestrator import ContainerOrchestrator
from src.networking.router import NetworkManager
from src.utils.input_validation import validate_repo_url, validate_ref_name

logger = logging.getLogger(__name__)

class PreviewConfig:
    """Handles parsing and validation of .preview.yaml files"""
    
    def __init__(self):
        self.default_config = {
            'services': {},
            'entrypoints': {}
        }
    
    async def parse_from_repo(self, repo_url: Optional[str], repo_ref: Optional[str] = None) -> Dict[str, Any]:
        """Parse .preview.yaml from a repository"""
        if not repo_url:
            return self.default_config
            
        # Sanitize inputs
        is_valid, error = validate_repo_url(repo_url)
        if not is_valid:
            logger.error(f"Invalid repo URL in preview: {error}")
            return self.default_config
            
        if repo_ref:
            is_valid, error = validate_ref_name(repo_ref)
            if not is_valid:
                logger.error(f"Invalid repo ref in preview: {error}")
                return self.default_config

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                # Clone the repository
                await asyncio.to_thread(Repo.clone_from, repo_url, tmp_dir)
                if repo_ref:
                    repo = Repo(tmp_dir)
                    await asyncio.to_thread(repo.git.checkout, repo_ref)
                
                preview_yaml_path = os.path.join(tmp_dir, '.preview.yaml')
                if not os.path.exists(preview_yaml_path):
                    return self.default_config
                
                with open(preview_yaml_path, 'r') as f:
                    config = yaml.safe_load(f)
                    return config or self.default_config
            except Exception as e:
                logger.error(f"Error parsing .preview.yaml: {e}")
                return self.default_config

    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate the preview configuration"""
        required_keys = ['services']
        for key in required_keys:
            if key not in config:
                return False
        
        # Validate service definitions
        for service_name, service_def in config['services'].items():
            if not isinstance(service_def, dict):
                return False
            
            # Check for required service fields based on type
            service_type = service_def.get('type', 'web')
            if service_type in ['web', 'worker', 'cron']:
                # These types should have an image
                if 'image' not in service_def:
                    return False
            elif service_type in ['postgres', 'mysql', 'redis']:
                # Database types should have an image
                if 'image' not in service_def:
                    return False
        
        return True


class DatabaseManager:
    """Manages database services for preview environments"""
    
    def __init__(self):
        self.created_volumes = set()
    
    async def create_database_volume(self, db_name: str, pr_number: int) -> str:
        """Create a named Docker volume for a database"""
        volume_name = f"db-preview-pr{pr_number}-{db_name}"
        
        # In a real implementation, we would create the Docker volume
        # For now, we'll just return the name
        self.created_volumes.add(volume_name)
        
        return volume_name
    
    async def seed_database(self, volume_name: str, seed_source: str):
        """Seed a database from a source (migration, dump, etc.)"""
        # In a real implementation, this would run seeding operations
        # For now, we'll just simulate
        print(f"Seeding database volume {volume_name} from {seed_source}")


class CronManager:
    """Manages cron jobs for preview environments"""
    
    def __init__(self):
        self.active_crons = {}
    
    async def setup_cron_job(self, job_name: str, schedule: str, command: str, container_id: str):
        """Setup a cron job in a container"""
        # In a real implementation, this would install and configure cron
        # For now, we'll just track the job
        self.active_crons[job_name] = {
            'schedule': schedule,
            'command': command,
            'container_id': container_id,
            'created_at': datetime.now()
        }
        
        print(f"Setup cron job {job_name} with schedule {schedule} in container {container_id}")
    
    async def cleanup_cron_job(self, job_name: str):
        """Remove a cron job"""
        if job_name in self.active_crons:
            del self.active_crons[job_name]


class PreviewEnvironmentManager:
    """Manages the creation and lifecycle of preview environments"""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self.preview_config = PreviewConfig()
        self.db_manager = DatabaseManager()
        self.cron_manager = CronManager()
    
    async def create_preview_environment(self, session: Session) -> Environment:
        """Create a complete preview environment for a PR"""
        # Parse the preview configuration from the repository
        preview_config = await self.preview_config.parse_from_repo(
            session.repo_url, session.repo_ref
        )
        
        if not self.preview_config.validate_config(preview_config):
            raise ValueError("Invalid preview configuration")
        
        # Create environment
        environment = Environment(
            id=f"env-{session.id}",
            name=f"preview-{session.id}",
            session_id=session.id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=session.expires_at
        )
        
        # Process services from the preview config
        services = []
        for service_name, service_def in preview_config['services'].items():
            service = await self._create_service_definition(
                service_name, service_def, session.pr_number
            )
            services.append(service)
        
        environment.services = services
        
        # Create isolated network
        network_name = self.session_manager.network_manager.create_isolated_network(environment.id)
        environment.network_name = network_name
        
        # Set up internal DNS
        internal_dns = self.session_manager.network_manager.setup_internal_dns(
            network_name, services
        )
        environment.metadata['internal_dns'] = json.dumps(internal_dns)
        
        # Create containers for all services
        container_ids = self.session_manager.container_orchestrator.create_environment_containers(environment)
        
        # Handle special service types
        await self._setup_special_services(
            session, preview_config, container_ids, session.pr_number
        )

        
        # Create external access URLs
        external_urls = []
        for service_def in services:
            service = ServiceDefinition(**service_def)
            if service.port:
                url = self.session_manager.network_manager.create_external_access(
                    session.id, service.port, self.session_manager.config.domain
                )
                external_urls.append(url)
        
        # Update session with environment info
        session.container_id = json.dumps(container_ids)
        session.network_id = network_name
        session.ports = {svc['name']: svc.get('port', 0) for svc in services if svc.get('port')}
        session.status = SessionStatus.RUNNING
        
        return environment
    
    async def _create_service_definition(self, name: str, definition: Dict[str, Any], pr_number: Optional[int]) -> Dict[str, Any]:
        """Create a service definition from the preview config"""
        service_type = definition.get('type', 'web')
        
        # Determine image
        image = definition.get('image')
        if not image:
            # Default images based on service type
            if service_type == 'postgres':
                image = f"postgres:{definition.get('version', '15')}-alpine"
            elif service_type == 'mysql':
                image = f"mysql:{definition.get('version', '8.0')}"
            elif service_type == 'redis':
                image = 'redis:alpine'
            elif service_type == 'web':
                image = 'node:18-alpine'  # Default for web services
            else:
                image = 'alpine:latest'  # Default fallback
        
        # Determine command
        command = definition.get('run') or definition.get('command')
        
        # Handle database volumes
        volumes = []
        if service_type in ['postgres', 'mysql']:
            if pr_number is not None:
                volume_name = await self.db_manager.create_database_volume(name, pr_number)
                if service_type == 'postgres':
                    volumes.append(f"{volume_name}:/var/lib/postgresql/data")
                else:  # mysql
                    volumes.append(f"{volume_name}:/var/lib/mysql")
        
        # Create service definition
        service_def = {
            'name': name,
            'type': service_type,
            'image': image,
            'command': command,
            'port': definition.get('port'),
            'env': definition.get('env', {}),
            'volumes': volumes
        }
        
        return service_def
    
    async def _setup_special_services(self, session: Session, preview_config: Dict[str, Any], container_ids: Dict[str, Dict[str, Any]], pr_number: Optional[int]):
        """Setup special services like cron jobs"""
        # Handle cron jobs
        cron_job_names = []
        for service_name, service_def in preview_config.get('services', {}).items():
            if service_def.get('type') == 'cron' and 'schedule' in service_def:
                cron_container_data = container_ids.get(service_name)
                cron_container_id = cron_container_data.get('id') if cron_container_data else None
                cron_command = service_def.get('run') or service_def.get('command')
                if cron_container_id and cron_command:

                    cron_job_name = f"cron-{service_name}-{pr_number or 'default'}"
                    await self.cron_manager.setup_cron_job(
                        cron_job_name,
                        service_def['schedule'],
                        cron_command,
                        cron_container_id
                    )
                    cron_job_names.append(cron_job_name)

        # Store cron job names in session metadata for cleanup
        if cron_job_names:
            session.metadata['cron_jobs'] = ','.join(cron_job_names)
    
    async def destroy_preview_environment(self, session: Session):
        """Clean up a preview environment"""
        # Clean up cron jobs
        cron_job_names_str = session.metadata.get('cron_jobs')
        if cron_job_names_str:
            cron_job_names = cron_job_names_str.split(',')
            for cron_job_name in cron_job_names:
                await self.cron_manager.cleanup_cron_job(cron_job_name)

        # The base session manager will handle container and network cleanup
        await self.session_manager.destroy_session(session.id)
    
    async def get_preview_urls(self, session: Session) -> Dict[str, str]:
        """Get all accessible URLs for a preview environment"""
        urls = {}
        
        if session.ports:
            for service_name, port in session.ports.items():
                if port:
                    urls[service_name] = f"https://{session.id[:8]}.{self.session_manager.config.domain}:{port}"
        
        return urls


# Integration with the main SessionManager
async def extend_session_manager_with_preview(session_manager: SessionManager):
    """Extend the session manager with preview environment capabilities"""
    preview_manager = PreviewEnvironmentManager(session_manager)
    
    async def new_create_preview_session(session: Session):
        await preview_manager.create_preview_environment(session)
    
    session_manager._create_preview_session = new_create_preview_session