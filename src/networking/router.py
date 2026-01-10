"""
Networking and routing service for disposable compute platform
"""
import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
import socket
from contextlib import closing


@dataclass
class Route:
    """Represents a route to a service"""
    path: str
    target_port: int
    session_id: str
    service_name: str
    domain: str


class IngressRouter:
    """Manages routing to disposable environments"""
    
    def __init__(self):
        self.routes: Dict[str, Route] = {}
        self.logger = logging.getLogger(__name__)
    
    def register_route(self, route: Route) -> str:
        """Register a new route and return the external URL"""
        # Generate a unique subdomain for this session
        subdomain = f"{route.session_id[:8]}"
        external_url = f"https://{subdomain}.{route.domain}{route.path}"
        
        self.routes[external_url] = route
        self.logger.info(f"Registered route: {external_url} -> {route.target_port}")
        
        return external_url
    
    def unregister_route(self, external_url: str):
        """Remove a route"""
        if external_url in self.routes:
            del self.routes[external_url]
            self.logger.info(f"Unregistered route: {external_url}")
    
    def get_available_port(self, start_port: int = 8000, end_port: int = 9000) -> Optional[int]:
        """Find an available port in the specified range"""
        for port in range(start_port, end_port):
            if self.is_port_available(port):
                return port
        return None
    
    def is_port_available(self, port: int) -> bool:
        """Check if a port is available"""
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return True
            except OSError:
                return False


class NetworkManager:
    """Manages network isolation and connectivity for environments"""
    
    def __init__(self):
        self.router = IngressRouter()
        self.logger = logging.getLogger(__name__)
    
    def create_isolated_network(self, environment_id: str) -> str:
        """Create an isolated network for an environment"""
        network_name = f"env-{environment_id[:12]}"
        # This would integrate with the ContainerOrchestrator to create actual networks
        return network_name
    
    def setup_internal_dns(self, network_name: str, services: List[Dict]) -> Dict[str, str]:
        """Set up internal DNS for services within a network"""
        dns_mapping = {}
        for service in services:
            service_name = service.get('name', 'default')
            dns_mapping[service_name] = f"{service_name}.{network_name}.internal"
        return dns_mapping
    
    def create_external_access(self, session_id: str, service_port: int, domain: str) -> str:
        """Create external access URL for a service"""
        route = Route(
            path="/",
            target_port=service_port,
            session_id=session_id,
            service_name="main",
            domain=domain
        )
        return self.router.register_route(route)
    
    def cleanup_network(self, environment_id: str, external_urls: List[str]):
        """Clean up network resources for an environment"""
        for url in external_urls:
            self.router.unregister_route(url)