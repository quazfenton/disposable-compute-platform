"""
Advanced networking module for disposable compute platform
"""
import asyncio
import socket
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import logging
import subprocess
import json
from contextlib import closing


@dataclass
class NetworkPolicy:
    """Network policy definition"""
    id: str
    name: str
    description: str
    pod_selector: Dict[str, str]  # Labels to select pods
    ingress_rules: List[Dict[str, Any]]
    egress_rules: List[Dict[str, Any]]
    created_at: str
    updated_at: str
    enabled: bool = True


@dataclass
class LoadBalancerConfig:
    """Load balancer configuration"""
    algorithm: str  # round-robin, least-connections, ip-hash
    health_check_path: str
    health_check_interval: int  # seconds
    health_check_timeout: int  # seconds
    max_retries: int
    sticky_sessions: bool = False


@dataclass
class ServiceMeshConfig:
    """Service mesh configuration"""
    enable_mtls: bool
    enable_tracing: bool
    enable_circuit_breaker: bool
    enable_rate_limiting: bool
    traffic_encryption: str  # none, permissive, strict


@dataclass
class CDNConfig:
    """CDN configuration"""
    enabled: bool
    provider: str  # cloudflare, aws-cloudfront, akamai
    cache_ttl: int  # seconds
    allowed_origins: List[str]
    compression_enabled: bool


class NetworkPolicyManager:
    """Manages network policies for pods"""
    
    def __init__(self):
        self.policies: Dict[str, NetworkPolicy] = {}
        self.logger = logging.getLogger(__name__)
    
    def create_policy(self, policy: NetworkPolicy) -> bool:
        """Create a new network policy"""
        self.policies[policy.id] = policy
        self.logger.info(f"Created network policy: {policy.name}")
        return True
    
    def update_policy(self, policy_id: str, policy: NetworkPolicy) -> bool:
        """Update an existing network policy"""
        if policy_id not in self.policies:
            return False
        
        self.policies[policy_id] = policy
        self.logger.info(f"Updated network policy: {policy.name}")
        return True
    
    def delete_policy(self, policy_id: str) -> bool:
        """Delete a network policy"""
        if policy_id in self.policies:
            del self.policies[policy_id]
            self.logger.info(f"Deleted network policy: {policy_id}")
            return True
        return False
    
    def apply_policy_to_pod(self, pod_id: str, policy_id: str) -> bool:
        """Apply a network policy to a pod"""
        if policy_id not in self.policies:
            self.logger.error(f"Policy {policy_id} not found")
            return False
        
        policy = self.policies[policy_id]
        if not policy.enabled:
            self.logger.info(f"Policy {policy_id} is disabled, skipping")
            return True
        
        # In a real implementation, this would configure iptables, CNI, or similar
        # For now, we'll just log the action
        self.logger.info(f"Applied policy {policy.name} to pod {pod_id}")
        
        # Example implementation would configure firewall rules
        # self._configure_firewall_rules(pod_id, policy)
        
        return True
    
    def _configure_firewall_rules(self, pod_id: str, policy: NetworkPolicy):
        """Configure firewall rules for a pod based on policy"""
        # This would implement the actual firewall configuration
        # For example, using iptables, nftables, or a CNI plugin
        pass


class LoadBalancer:
    """Manages load balancing for services"""
    
    def __init__(self):
        self.backends: Dict[str, List[Dict[str, Any]]] = {}  # service_id -> list of backends
        self.configs: Dict[str, LoadBalancerConfig] = {}
        self.health_status: Dict[str, Dict[str, bool]] = {}  # service_id -> backend_id -> status
        self.current_backend_index: Dict[str, int] = {}  # For round-robin
        self.logger = logging.getLogger(__name__)
    
    def add_backend(self, service_id: str, backend: Dict[str, Any]):
        """Add a backend to a service"""
        if service_id not in self.backends:
            self.backends[service_id] = []
            self.health_status[service_id] = {}
            self.current_backend_index[service_id] = 0
        
        self.backends[service_id].append(backend)
        self.health_status[service_id][backend['id']] = True  # Initially healthy
        self.logger.info(f"Added backend {backend['id']} to service {service_id}")
    
    def remove_backend(self, service_id: str, backend_id: str):
        """Remove a backend from a service"""
        if service_id in self.backends:
            self.backends[service_id] = [
                b for b in self.backends[service_id] 
                if b['id'] != backend_id
            ]
            if backend_id in self.health_status[service_id]:
                del self.health_status[service_id][backend_id]
            self.logger.info(f"Removed backend {backend_id} from service {service_id}")
    
    def set_config(self, service_id: str, config: LoadBalancerConfig):
        """Set load balancer configuration for a service"""
        self.configs[service_id] = config
        self.logger.info(f"Set load balancer config for service {service_id}")
    
    async def get_backend(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get the next backend for a request based on the algorithm"""
        if service_id not in self.backends or not self.backends[service_id]:
            return None
        
        # Get healthy backends
        healthy_backends = [
            b for b in self.backends[service_id] 
            if self.health_status[service_id].get(b['id'], True)
        ]
        
        if not healthy_backends:
            self.logger.warning(f"No healthy backends for service {service_id}")
            return None
        
        # Get configuration
        config = self.configs.get(service_id, LoadBalancerConfig(
            algorithm="round-robin",
            health_check_path="/health",
            health_check_interval=30,
            health_check_timeout=5,
            max_retries=3
        ))
        
        # Select backend based on algorithm
        if config.algorithm == "round-robin":
            backend = self._round_robin_select(service_id, healthy_backends)
        elif config.algorithm == "least-connections":
            backend = self._least_connections_select(service_id, healthy_backends)
        elif config.algorithm == "ip-hash":
            # For demo purposes, we'll just use round-robin
            backend = self._round_robin_select(service_id, healthy_backends)
        else:
            backend = healthy_backends[0]  # Default to first
        
        return backend
    
    def _round_robin_select(self, service_id: str, backends: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Select backend using round-robin algorithm"""
        if not backends:
            return None
        
        index = self.current_backend_index[service_id]
        backend = backends[index % len(backends)]
        self.current_backend_index[service_id] = (index + 1) % len(backends)
        return backend
    
    def _least_connections_select(self, service_id: str, backends: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Select backend with least connections (simplified)"""
        # For demo purposes, we'll just return the first backend
        # In a real implementation, this would track connection counts
        return backends[0] if backends else None
    
    async def start_health_checks(self, service_id: str):
        """Start health checks for a service"""
        if service_id not in self.backends:
            return
        
        while True:
            try:
                await self._perform_health_checks(service_id)
                config = self.configs.get(service_id, LoadBalancerConfig(
                    algorithm="round-robin",
                    health_check_path="/health",
                    health_check_interval=30,
                    health_check_timeout=5,
                    max_retries=3
                ))
                await asyncio.sleep(config.health_check_interval)
            except asyncio.CancelledError:
                self.logger.info(f"Health checks stopped for service {service_id}")
                break
            except Exception as e:
                self.logger.error(f"Error in health checks for service {service_id}: {e}")
                await asyncio.sleep(10)  # Wait before retrying
    
    async def _perform_health_checks(self, service_id: str):
        """Perform health checks for all backends of a service"""
        if service_id not in self.backends:
            return
        
        for backend in self.backends[service_id]:
            is_healthy = await self._check_backend_health(backend)
            self.health_status[service_id][backend['id']] = is_healthy
            
            if not is_healthy:
                self.logger.warning(f"Backend {backend['id']} is unhealthy")
            else:
                self.logger.debug(f"Backend {backend['id']} is healthy")


    async def _check_backend_health(self, backend: Dict[str, Any]) -> bool:
        """Check the health of a backend"""
        try:
            # For demo purposes, we'll just check if the port is open
            # In a real implementation, this would make an HTTP request to the health check path
            host = backend.get('host', 'localhost')
            port = backend.get('port', 80)

            # Check if port is open using a thread executor to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, self._sync_check_port, host, port)
            return result == 0
        except Exception:
            return False

    def _sync_check_port(self, host: str, port: int) -> int:
        """Synchronous function to check if a port is open"""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(5)  # 5 second timeout
            return sock.connect_ex((host, port))


class ServiceMeshManager:
    """Manages service mesh features"""
    
    def __init__(self):
        self.mesh_configs: Dict[str, ServiceMeshConfig] = {}
        self.logger = logging.getLogger(__name__)
    
    def configure_mesh(self, service_id: str, config: ServiceMeshConfig):
        """Configure service mesh for a service"""
        self.mesh_configs[service_id] = config
        self.logger.info(f"Configured service mesh for service {service_id}")
        
        # In a real implementation, this would deploy sidecar proxies, configure mTLS, etc.
        # For now, we'll just log the configuration
        self.logger.info(f"Service mesh config for {service_id}: {config}")
    
    def enable_mtls(self, service_id: str):
        """Enable mTLS for a service"""
        if service_id in self.mesh_configs:
            self.mesh_configs[service_id].enable_mtls = True
        else:
            config = ServiceMeshConfig(
                enable_mtls=True,
                enable_tracing=False,
                enable_circuit_breaker=False,
                enable_rate_limiting=False,
                traffic_encryption="strict"
            )
            self.mesh_configs[service_id] = config
        self.logger.info(f"Enabled mTLS for service {service_id}")
    
    def enable_tracing(self, service_id: str):
        """Enable tracing for a service"""
        if service_id in self.mesh_configs:
            self.mesh_configs[service_id].enable_tracing = True
        else:
            config = ServiceMeshConfig(
                enable_mtls=False,
                enable_tracing=True,
                enable_circuit_breaker=False,
                enable_rate_limiting=False,
                traffic_encryption="none"
            )
            self.mesh_configs[service_id] = config
        self.logger.info(f"Enabled tracing for service {service_id}")


class CDNManager:
    """Manages CDN integration"""
    
    def __init__(self):
        self.cdn_configs: Dict[str, CDNConfig] = {}
        self.logger = logging.getLogger(__name__)
    
    def configure_cdn(self, service_id: str, config: CDNConfig):
        """Configure CDN for a service"""
        self.cdn_configs[service_id] = config
        self.logger.info(f"Configured CDN for service {service_id}")
        
        if config.enabled:
            # In a real implementation, this would configure the CDN provider
            # For now, we'll just log the configuration
            self.logger.info(f"CDN enabled for {service_id} with provider {config.provider}")
    
    def invalidate_cache(self, service_id: str, paths: List[str] = None):
        """Invalidate CDN cache for specific paths or all"""
        if service_id not in self.cdn_configs:
            self.logger.warning(f"No CDN config for service {service_id}")
            return
        
        config = self.cdn_configs[service_id]
        if not config.enabled:
            self.logger.info(f"CDN not enabled for {service_id}")
            return
        
        # In a real implementation, this would call the CDN provider's API
        # For now, we'll just log the action
        if paths:
            self.logger.info(f"Invalidated CDN cache for {service_id}, paths: {paths}")
        else:
            self.logger.info(f"Invalidated full CDN cache for {service_id}")


class AdvancedNetworkManager:
    """Main network manager that coordinates all advanced networking features"""
    
    def __init__(self):
        self.policy_manager = NetworkPolicyManager()
        self.load_balancer = LoadBalancer()
        self.service_mesh_manager = ServiceMeshManager()
        self.cdn_manager = CDNManager()
        self.logger = logging.getLogger(__name__)
    
    def apply_network_policy(self, pod_id: str, policy_id: str) -> bool:
        """Apply a network policy to a pod"""
        return self.policy_manager.apply_policy_to_pod(pod_id, policy_id)
    
    def add_service_backend(self, service_id: str, backend: Dict[str, Any]):
        """Add a backend to a service"""
        self.load_balancer.add_backend(service_id, backend)
    
    def remove_service_backend(self, service_id: str, backend_id: str):
        """Remove a backend from a service"""
        self.load_balancer.remove_backend(service_id, backend_id)
    
    def configure_load_balancer(self, service_id: str, config: LoadBalancerConfig):
        """Configure load balancer for a service"""
        self.load_balancer.set_config(service_id, config)
    
    async def get_service_backend(self, service_id: str) -> Optional[Dict[str, Any]]:
        """Get a backend for a service request"""
        return await self.load_balancer.get_backend(service_id)
    
    def start_service_health_checks(self, service_id: str):
        """Start health checks for a service"""
        # This would typically run as a background task
        return self.load_balancer.start_health_checks(service_id)
    
    def configure_service_mesh(self, service_id: str, config: ServiceMeshConfig):
        """Configure service mesh for a service"""
        self.service_mesh_manager.configure_mesh(service_id, config)
    
    def enable_service_mesh_features(self, service_id: str, mtls: bool = False, 
                                   tracing: bool = False):
        """Enable specific service mesh features"""
        if mtls:
            self.service_mesh_manager.enable_mtls(service_id)
        if tracing:
            self.service_mesh_manager.enable_tracing(service_id)
    
    def configure_cdn(self, service_id: str, config: CDNConfig):
        """Configure CDN for a service"""
        self.cdn_manager.configure_cdn(service_id, config)
    
    def invalidate_cdn_cache(self, service_id: str, paths: List[str] = None):
        """Invalidate CDN cache"""
        self.cdn_manager.invalidate_cache(service_id, paths)
    
    def create_network_policy(self, policy: NetworkPolicy) -> bool:
        """Create a network policy"""
        return self.policy_manager.create_policy(policy)
    
    def update_network_policy(self, policy_id: str, policy: NetworkPolicy) -> bool:
        """Update a network policy"""
        return self.policy_manager.update_policy(policy_id, policy)
    
    def delete_network_policy(self, policy_id: str) -> bool:
        """Delete a network policy"""
        return self.policy_manager.delete_policy(policy_id)