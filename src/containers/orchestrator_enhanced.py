"""
Enhanced container orchestrator with security hardening for disposable compute platform
"""
import docker
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from src.models.session import ServiceDefinition
from src.models.environment import Environment

logger = logging.getLogger(__name__)


@dataclass
class ContainerConfig:
    """Configuration for a container with security options"""
    image: str
    command: Optional[str] = None
    environment: Dict[str, str] = None
    ports: Dict[str, int] = None
    volumes: List[str] = None
    network: Optional[str] = None
    resource_limits: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None
    
    # Security options
    security_opt: List[str] = None
    cap_drop: List[str] = None
    cap_add: List[str] = None
    read_only: bool = True
    tmpfs: Dict[str, str] = None
    user: Optional[str] = None
    privileged: bool = False
    init: bool = True
    pid_mode: Optional[str] = None
    ipc_mode: Optional[str] = None
    uts_mode: Optional[str] = None
    sysctls: Dict[str, str] = None
    ulimits: List[Any] = None
    
    # Health check
    healthcheck: Optional[Dict[str, Any]] = None
    
    # Logging
    log_config: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.environment is None:
            self.environment = {}
        if self.ports is None:
            self.ports = {}
        if self.volumes is None:
            self.volumes = []
        if self.security_opt is None:
            self.security_opt = [
                "no-new-privileges:true"
            ]
        if self.cap_drop is None:
            self.cap_drop = ["ALL"]
        if self.cap_add is None:
            self.cap_add = []
        if self.tmpfs is None:
            self.tmpfs = {
                "/tmp": "rw,noexec,nosuid,size=512m,mode=1777",
                "/var/tmp": "rw,noexec,nosuid,size=512m,mode=1777"
            }
        if self.user is None:
            self.user = "1000:1000"  # Non-root user
        if self.sysctls is None:
            self.sysctls = {
                "net.ipv4.ping_group_range": "0 0",  # Disable ping
            }


class EnhancedContainerOrchestrator:
    """Container orchestrator with security hardening"""
    
    def __init__(self, docker_client: docker.DockerClient = None):
        self.client = docker_client or docker.from_env()
        self.logger = logging.getLogger(__name__)
        self._container_info: Dict[str, Dict[str, Any]] = {}
        
        # Verify Docker connection
        try:
            self.client.ping()
            self.logger.info("Connected to Docker daemon")
        except Exception as e:
            self.logger.error(f"Failed to connect to Docker: {e}")
            raise
    
    def create_container(self, config: ContainerConfig) -> Dict[str, Any]:
        """Create a container with security hardening"""
        try:
            # Pull image if not present
            try:
                self.client.images.get(config.image)
                self.logger.info(f"Image {config.image} found locally")
            except docker.errors.ImageNotFound:
                self.logger.info(f"Pulling image {config.image}")
                try:
                    self.client.images.pull(config.image)
                except Exception as pull_error:
                    self.logger.error(f"Failed to pull image {config.image}: {pull_error}")
                    raise Exception(f"Image not found and pull failed: {config.image}")
            
            # Prepare container creation kwargs
            create_kwargs = {
                'image': config.image,
                'command': config.command,
                'environment': config.environment,
                'ports': config.ports,
                'volumes': config.volumes,
                'network': config.network,
                'detach': True,
                'labels': {
                    "disposable_compute": "true",
                    "created_at": str(config.created_at) if config.created_at is not None else str(datetime.now())
                },
                # Security options
                'security_opt': config.security_opt,
                'cap_drop': config.cap_drop,
                'cap_add': config.cap_add,
                'read_only': config.read_only,
                'tmpfs': config.tmpfs,
                'user': config.user,
                'privileged': config.privileged,
                'init': config.init,
                'sysctls': config.sysctls,
            }
            
            # Add resource limits if specified
            if config.resource_limits:
                create_kwargs.update(config.resource_limits)
            
            # Add health check if specified
            if config.healthcheck:
                create_kwargs['healthcheck'] = config.healthcheck
            
            # Add logging config if specified
            if config.log_config:
                create_kwargs['log_config'] = config.log_config
            
            # Add PID mode if specified
            if config.pid_mode:
                create_kwargs['pid_mode'] = config.pid_mode
            
            # Add IPC mode if specified
            if config.ipc_mode:
                create_kwargs['ipc_mode'] = config.ipc_mode
            
            # Add UTS mode if specified
            if config.uts_mode:
                create_kwargs['uts_mode'] = config.uts_mode
            
            # Create container
            container = self.client.containers.run(**create_kwargs)
            
            # Get container info
            container.reload()
            host_port_mapping = container.attrs['NetworkSettings']['Ports'] if container.attrs.get('NetworkSettings') else {}
            
            container_info = {
                'id': container.id,
                'name': container.name,
                'ports': host_port_mapping,
                'status': container.status,
                'created_at': datetime.now(),
                'image': config.image,
                'security': {
                    'read_only': config.read_only,
                    'user': config.user,
                    'cap_drop': config.cap_drop,
                    'cap_add': config.cap_add,
                    'security_opt': config.security_opt
                }
            }
            
            self._container_info[container.id] = container_info
            
            self.logger.info(f"Created container {container.id} with security hardening")
            return container_info
            
        except docker.errors.APIError as e:
            self.logger.error(f"Docker API error: {e.explanation}")
            raise Exception(f"Container creation failed: {e.explanation}")
        except docker.errors.ContainerError as e:
            self.logger.error(f"Container error: {e.stderr}")
            raise Exception(f"Container exited with error: {e.stderr}")
        except Exception as e:
            self.logger.error(f"Unexpected error creating container: {e}")
            raise
    
    def start_container(self, container_id: str) -> bool:
        """Start a container"""
        try:
            container = self.client.containers.get(container_id)
            container.start()
            self.logger.info(f"Started container {container_id}")
            return True
        except docker.errors.NotFound:
            self.logger.error(f"Container {container_id} not found")
            return False
        except Exception as e:
            self.logger.error(f"Error starting container {container_id}: {e}")
            raise
    
    def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """Stop a container with timeout"""
        try:
            container = self.client.containers.get(container_id)
            container.stop(timeout=timeout)
            self.logger.info(f"Stopped container {container_id}")
            return True
        except docker.errors.NotFound:
            self.logger.warning(f"Container {container_id} not found")
            return False
        except Exception as e:
            self.logger.error(f"Error stopping container {container_id}: {e}")
            raise
    
    def remove_container(self, container_id: str, force: bool = True) -> bool:
        """Remove a container"""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=force)
            
            # Remove from tracking
            if container_id in self._container_info:
                del self._container_info[container_id]
            
            self.logger.info(f"Removed container {container_id}")
            return True
        except docker.errors.NotFound:
            self.logger.warning(f"Container {container_id} not found, already removed")
            return False
        except Exception as e:
            self.logger.error(f"Error removing container {container_id}: {e}")
            raise
    
    def get_container_logs(self, container_id: str, lines: int = 100, follow: bool = False) -> str:
        """Get logs from a container"""
        try:
            container = self.client.containers.get(container_id)
            logs = container.logs(tail=lines, follow=follow, stream=False)
            return logs.decode('utf-8') if isinstance(logs, bytes) else logs
        except docker.errors.NotFound:
            self.logger.error(f"Container {container_id} not found")
            return ""
        except Exception as e:
            self.logger.error(f"Error getting logs for container {container_id}: {e}")
            return ""
    
    def get_container_status(self, container_id: str) -> Optional[str]:
        """Get container status"""
        try:
            container = self.client.containers.get(container_id)
            container.reload()
            return container.status
        except docker.errors.NotFound:
            return None
        except Exception as e:
            self.logger.error(f"Error getting container status: {e}")
            return None
    
    def create_environment_containers(
        self, 
        environment: Environment,
        security_profile: str = "default"
    ) -> Dict[str, Dict[str, Any]]:
        """Create all containers for an environment with security hardening"""
        container_info = {}
        
        # Get security profile
        security_config = self._get_security_profile(security_profile)
        
        for service_def in environment.services:
            service = ServiceDefinition(**service_def)
            
            # Create container config with security
            config = ContainerConfig(
                image=service.image,
                command=service.command,
                environment=service.env,
                volumes=service.volumes,
                **security_config
            )
            
            # Map ports if specified
            if service.port:
                config.ports = {f"{service.port}/tcp": None}
            
            # Create container
            try:
                result = self.create_container(config)
                container_info[service.name] = result
                
                # Connect to environment network
                if environment.network_name:
                    try:
                        network = self.client.networks.get(environment.network_name)
                        network.connect(result['id'])
                        self.logger.info(f"Connected container {result['id']} to network {environment.network_name}")
                    except Exception as e:
                        self.logger.warning(f"Failed to connect container to network: {e}")
                
            except Exception as e:
                self.logger.error(f"Failed to create container for service {service.name}: {e}")
                # Cleanup already created containers
                self._cleanup_containers(container_info)
                raise
        
        return container_info
    
    def _get_security_profile(self, profile_name: str) -> Dict[str, Any]:
        """Get security configuration for a profile"""
        profiles = {
            "default": {
                'security_opt': ["no-new-privileges:true"],
                'cap_drop': ["ALL"],
                'cap_add': [],
                'read_only': True,
                'user': "1000:1000",
                'init': True,
            },
            "development": {
                'security_opt': ["no-new-privileges:true"],
                'cap_drop': [],
                'cap_add': ["SYS_PTRACE"],  # Allow debugging
                'read_only': False,
                'user': "1000:1000",
                'init': True,
            },
            "privileged": {
                'security_opt': [],
                'cap_drop': [],
                'cap_add': ["ALL"],
                'read_only': False,
                'privileged': True,
                'user': "root",
                'init': False,
            }
        }
        
        return profiles.get(profile_name, profiles["default"])
    
    def _cleanup_containers(self, container_info: Dict[str, Dict[str, Any]]):
        """Cleanup created containers on failure"""
        for service_name, info in list(container_info.items()):
            container_id = info.get('id')
            if container_id:
                try:
                    self.remove_container(container_id)
                    self.logger.info(f"Cleaned up container {container_id} for service {service_name}")
                except Exception as e:
                    self.logger.error(f"Failed to cleanup container {container_id}: {e}")
    
    def destroy_environment(
        self, 
        environment: Environment, 
        container_info: Dict[str, Dict[str, Any]],
        timeout: int = 30
    ):
        """Destroy all containers and network for an environment with proper cleanup"""
        errors = []
        
        # Stop and remove all containers with timeout
        for service_name, container_data in container_info.items():
            container_id = container_data.get('id') if isinstance(container_data, dict) else container_data
            if container_id:
                try:
                    # Stop with timeout
                    self.stop_container(container_id, timeout=10)
                    # Remove
                    self.remove_container(container_id)
                    self.logger.info(f"Destroyed container {container_id} ({service_name})")
                except Exception as e:
                    self.logger.error(f"Error removing container {container_id}: {e}")
                    errors.append(f"Container {container_id}: {e}")
        
        # Remove network
        if environment.network_name:
            try:
                network = self.client.networks.get(environment.network_name)
                
                # Disconnect all containers first
                for container in network.containers:
                    try:
                        network.disconnect(container, force=True)
                        self.logger.info(f"Disconnected container {container.id} from network")
                    except Exception as e:
                        self.logger.warning(f"Error disconnecting container {container.id}: {e}")
                
                # Remove network
                network.remove()
                self.logger.info(f"Removed network {environment.network_name}")
            except docker.errors.NotFound:
                self.logger.info(f"Network {environment.network_name} already removed")
            except Exception as e:
                self.logger.error(f"Error removing network {environment.network_name}: {e}")
                errors.append(f"Network {environment.network_name}: {e}")
        
        if errors:
            self.logger.warning(f"Environment destruction completed with errors: {errors}")
    
    def get_container_info(self, container_id: str) -> Optional[Dict[str, Any]]:
        """Get stored container info"""
        return self._container_info.get(container_id)
    
    def list_containers(self, all: bool = False) -> List[Dict[str, Any]]:
        """List containers"""
        try:
            containers = self.client.containers.list(all=all, filters={"label": "disposable_compute=true"})
            return [
                {
                    'id': c.id,
                    'name': c.name,
                    'status': c.status,
                    'created': c.attrs.get('Created'),
                    'image': c.attrs.get('Config', {}).get('Image')
                }
                for c in containers
            ]
        except Exception as e:
            self.logger.error(f"Error listing containers: {e}")
            return []
    
    def cleanup_orphaned_containers(self) -> int:
        """Clean up orphaned containers"""
        try:
            containers = self.list_containers(all=True)
            cleaned = 0
            
            for container in containers:
                try:
                    c = self.client.containers.get(container['id'])
                    
                    # Check if container is old (more than 24 hours)
                    created = c.attrs.get('Created', '')
                    if created:
                        from datetime import datetime, timedelta
                        created_time = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        if datetime.now(created_time.tzinfo) - created_time > timedelta(hours=24):
                            self.remove_container(container['id'])
                            cleaned += 1
                            self.logger.info(f"Cleaned up orphaned container {container['id']}")
                except Exception as e:
                    self.logger.warning(f"Error checking container {container['id']}: {e}")
            
            return cleaned
        except Exception as e:
            self.logger.error(f"Error cleaning up orphaned containers: {e}")
            return 0


# Backward compatibility alias
ContainerOrchestrator = EnhancedContainerOrchestrator
