"""
Container orchestration service for disposable compute platform
"""
import docker
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from src.models.session import Session, ServiceDefinition
from src.models.environment import Environment


from datetime import datetime

@dataclass
class ContainerConfig:
    """Configuration for a container"""
    image: str
    command: Optional[str] = None
    environment: Dict[str, str] = None
    ports: Dict[str, int] = None
    volumes: List[str] = None
    network: Optional[str] = None
    resource_limits: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.environment is None:
            self.environment = {}
        if self.ports is None:
            self.ports = {}
        if self.volumes is None:
            self.volumes = []


class ContainerOrchestrator:
    """Manages container lifecycle for disposable environments"""
    
    def __init__(self):
        self.client = docker.from_env()
        self.logger = logging.getLogger(__name__)
    
    def create_network(self, network_name: str) -> str:
        """Create an isolated network for an environment"""
        try:
            network = self.client.networks.create(
                network_name,
                driver="bridge",
                internal=False  # Allow external access
            )
            return network.id
        except Exception as e:
            self.logger.error(f"Failed to create network {network_name}: {e}")
            raise
    
    def remove_network(self, network_id: str):
        """Remove a network"""
        try:
            network = self.client.networks.get(network_id)
            network.remove()
        except Exception as e:
            self.logger.error(f"Failed to remove network {network_id}: {e}")
    
    def create_container(self, config: ContainerConfig) -> str:
        """Create a container with the given configuration"""
        try:
            container = self.client.containers.run(
                image=config.image,
                command=config.command,
                environment=config.environment,
                ports=config.ports,
                volumes=config.volumes,
                network=config.network,
                detach=True,
                labels={
                    "disposable_compute": "true",
                    "created_at": str(config.created_at) if config.created_at is not None else str(datetime.now())
                },
                **(config.resource_limits or {})
            )
            return container.id
        except Exception as e:
            self.logger.error(f"Failed to create container: {e}")
            raise
    
    def start_container(self, container_id: str):
        """Start a container"""
        try:
            container = self.client.containers.get(container_id)
            container.start()
        except Exception as e:
            self.logger.error(f"Failed to start container {container_id}: {e}")
            raise
    
    def stop_container(self, container_id: str):
        """Stop a container"""
        try:
            container = self.client.containers.get(container_id)
            container.stop()
        except Exception as e:
            self.logger.error(f"Failed to stop container {container_id}: {e}")
            raise
    
    def remove_container(self, container_id: str):
        """Remove a container"""
        try:
            container = self.client.containers.get(container_id)
            container.remove(force=True)
        except Exception as e:
            self.logger.error(f"Failed to remove container {container_id}: {e}")
            raise
    
    def get_container_logs(self, container_id: str, lines: int = 100) -> str:
        """Get logs from a container"""
        try:
            container = self.client.containers.get(container_id)
            logs = container.logs(tail=lines, follow=False)
            return logs.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Failed to get logs for container {container_id}: {e}")
            return ""
    
    def create_environment_containers(self, environment: Environment) -> Dict[str, str]:
        """Create all containers for an environment"""
        container_ids = {}
        
        for service_def in environment.services:
            service = ServiceDefinition(**service_def)
            
            config = ContainerConfig(
                image=service.image,
                command=service.command,
                environment=service.env,
                volumes=service.volumes
            )
            
            # Map ports if specified
            if service.port:
                config.ports = {f"{service.port}/tcp": None}  # Let Docker assign external port
            
            container_id = self.create_container(config)
            container_ids[service.name] = container_id
            
            # Connect to environment network
            if environment.network_name:
                network = self.client.networks.get(environment.network_name)
                network.connect(container_id)
        
        return container_ids
    
    def destroy_environment(self, environment: Environment, container_ids: Dict[str, str]):
        """Destroy all containers and network for an environment"""
        # Stop and remove all containers
        for container_id in container_ids.values():
            try:
                self.stop_container(container_id)
                self.remove_container(container_id)
            except Exception as e:
                self.logger.error(f"Error removing container {container_id}: {e}")
        
        # Remove network
        if environment.network_name:
            try:
                network = self.client.networks.get(environment.network_name)
                network.remove()
            except Exception as e:
                self.logger.error(f"Error removing network {environment.network_name}: {e}")