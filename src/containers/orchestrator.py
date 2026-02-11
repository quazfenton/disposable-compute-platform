"""
Container orchestration service for disposable compute platform
"""
import docker
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
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
    volumes: List[str] = field(default_factory=list)
    network: Optional[str] = None
    resource_limits: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.environment is None:
            self.environment = {}
        if self.ports is None:
            self.ports = {}


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
    
    def create_container(self, config: ContainerConfig) -> Dict[str, Any]:
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
            
            # Get the assigned host ports from container attributes
            host_port_mapping = container.attrs['NetworkSettings']['Ports'] if container.attrs.get('NetworkSettings') else {}
            
            return {
                'id': container.id,
                'ports': host_port_mapping
            }
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
    
    def create_environment_containers(self, environment: Environment) -> Dict[str, Dict[str, Any]]:
        """Create all containers for an environment"""
        container_info = {}

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

            container_result = self.create_container(config)
            container_info[service.name] = container_result

            # Connect to environment network
            if environment.network_name:
                network = self.client.networks.get(environment.network_name)
                network.connect(container_result['id'])

        return container_info
    
    def destroy_environment(self, environment: Environment, container_info: Dict[str, Dict[str, Any]]):
        """Destroy all containers and network for an environment"""
        # Stop and remove all containers
        for container_data in container_info.values():
            container_id = container_data['id'] if isinstance(container_data, dict) else container_data
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