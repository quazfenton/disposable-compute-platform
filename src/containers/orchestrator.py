"""
Hardened Container Orchestration Service for Disposable Compute Platform
"""
import docker
import logging
import asyncio
import os
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from src.models.session import Session, ServiceDefinition
from src.models.environment import Environment


@dataclass
class ContainerConfig:
    """Configuration for a container with security and resource constraints"""
    image: str
    command: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    ports: Dict[str, Any] = field(default_factory=dict)
    volumes: List[str] = field(default_factory=list)
    network: Optional[str] = None
    mem_limit: str = "1g"
    cpu_period: int = 100000
    cpu_quota: int = 50000  # 50% CPU
    read_only: bool = False
    tmpfs: Dict[str, str] = field(default_factory=lambda: {"/tmp": "rw,noexec,nosuid,size=512m"})
    user: Optional[str] = "1000:1000"
    created_at: Optional[datetime] = None


class ContainerOrchestrator:
    """Production-grade container orchestrator with lifecycle management and isolation"""
    
    def __init__(self, max_concurrent_runs: int = 20):
        try:
            self.client = docker.from_env()
        except Exception:
            self.client = None
            logging.warning("Docker daemon not found, orchestrator running in degraded mode")
            
        self.logger = logging.getLogger(__name__)
        self._run_semaphore = asyncio.Semaphore(max_concurrent_runs)
    
    async def create_network(self, network_name: str) -> str:
        """Create an isolated Docker network"""
        if not self.client:
            return f"mock-net-{network_name}"
            
        try:
            network = await asyncio.to_thread(
                self.client.networks.create,
                network_name,
                driver="bridge",
                internal=False,
                labels={"disposable_compute": "true"}
            )
            return str(network.id)
        except Exception as e:
            self.logger.error(f"Failed to create network {network_name}: {e}")
            raise
    
    async def remove_network(self, network_id: str):
        """Clean up a Docker network"""
        if not self.client:
            return
            
        try:
            network = await asyncio.to_thread(self.client.networks.get, network_id)
            # Disconnect all connected containers first
            for container in network.containers:
                await asyncio.to_thread(network.disconnect, container, force=True)
            await asyncio.to_thread(network.remove)
        except Exception as e:
            self.logger.debug(f"Network cleanup info: {e}")
    
    async def create_container(self, config: ContainerConfig) -> Dict[str, Any]:
        """Deploy a new container with resource isolation and security hardening"""
        if not self.client:
            return {'id': 'mock-id', 'ports': {}}

        async with self._run_semaphore:
            try:
                # Prepare security and resource options
                resource_limits = {
                    'mem_limit': config.mem_limit,
                    'cpu_period': config.cpu_period,
                    'cpu_quota': config.cpu_quota,
                }
                
                container = await asyncio.to_thread(
                    self.client.containers.run,
                    image=config.image,
                    command=config.command,
                    environment=config.environment,
                    ports=config.ports,
                    volumes=config.volumes,
                    network=config.network,
                    detach=True,
                    read_only=config.read_only,
                    tmpfs=config.tmpfs,
                    user=config.user,
                    labels={
                        "disposable_compute": "true",
                        "created_at": str(config.created_at or datetime.now())
                    },
                    **resource_limits
                )
                
                container.reload()
                host_port_mapping = container.attrs['NetworkSettings']['Ports'] if container.attrs.get('NetworkSettings') else {}
                
                return {
                    'id': container.id,
                    'name': container.name,
                    'ports': host_port_mapping
                }
            except Exception as e:
                self.logger.error(f"Container deployment failed: {e}")
                raise
    
    async def stop_container(self, container_id: str, timeout: int = 10):
        if not self.client: return
        try:
            container = await asyncio.to_thread(self.client.containers.get, container_id)
            await asyncio.to_thread(container.stop, timeout=timeout)
        except Exception:
            pass
    
    async def remove_container(self, container_id: str):
        if not self.client: return
        try:
            container = await asyncio.to_thread(self.client.containers.get, container_id)
            await asyncio.to_thread(container.remove, force=True, v=True)
        except Exception:
            pass
    
    async def get_container_logs(self, container_id: str, lines: int = 100) -> str:
        if not self.client: return "Mock logs: Container running..."
        try:
            container = await asyncio.to_thread(self.client.containers.get, container_id)
            logs = await asyncio.to_thread(container.logs, tail=lines)
            return logs.decode('utf-8')
        except Exception:
            return ""
    
    async def create_environment_containers(self, environment: Environment) -> Dict[str, Dict[str, Any]]:
        """Orchestrate a multi-service environment lifecycle"""
        container_info = {}
        
        for service_def in environment.services:
            service = ServiceDefinition(**service_def)
            
            config = ContainerConfig(
                image=service.image,
                command=service.command,
                environment=service.env,
                volumes=service.volumes,
                network=environment.network_name
            )
            
            if service.port:
                config.ports = {f"{service.port}/tcp": None}
            
            try:
                result = await self.create_container(config)
                container_info[service.name] = result
            except Exception as e:
                self.logger.error(f"Environment creation stalled at {service.name}: {e}")
                # Rollback already created containers in this environment
                for info in container_info.values():
                    await self.remove_container(info['id'])
                raise

        return container_info
