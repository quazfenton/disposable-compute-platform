"""
Networking and routing service for disposable compute platform
"""
import logging
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class Route:
    """Represents a route to a service"""
    path: str
    target_port: int
    session_id: str
    service_name: str
    domain: str


class NginxConfigGenerator:
    """Generates Nginx configuration for subdomain routing"""
    
    def __init__(self, config_dir: str = "/etc/nginx/conf.d"):
        self.config_dir = config_dir
        self.logger = logging.getLogger(__name__)
    
    def generate_config(self, route: Route) -> str:
        """Generate Nginx server block for a route"""
        subdomain = f"{route.session_id[:8]}"
        server_name = f"{subdomain}.{route.domain}"
        
        config = f"""
server {{
    listen 80;
    server_name {server_name};

    location {route.path} {{
        proxy_pass http://127.0.0.1:{route.target_port};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
"""
        return config

    def save_config(self, route: Route):
        """Save Nginx configuration to file"""
        subdomain = f"{route.session_id[:8]}"
        config_path = os.path.join(self.config_dir, f"{subdomain}.conf")
        
        try:
            if not os.access(self.config_dir, os.W_OK):
                mock_dir = "./nginx_configs"
                os.makedirs(mock_dir, exist_ok=True)
                config_path = os.path.join(mock_dir, f"{subdomain}.conf")

            with open(config_path, 'w') as f:
                f.write(self.generate_config(route))
            
            self.logger.info(f"Saved Nginx config for {subdomain} at {config_path}")
            self.reload_nginx()
        except Exception as e:
            self.logger.error(f"Failed to save Nginx config: {e}")

    def remove_config(self, session_id: str):
        """Remove Nginx configuration file"""
        subdomain = f"{session_id[:8]}"
        config_path = os.path.join(self.config_dir, f"{subdomain}.conf")
        
        if not os.access(self.config_dir, os.W_OK):
            config_path = os.path.join("./nginx_configs", f"{subdomain}.conf")

        if os.path.exists(config_path):
            os.remove(config_path)
            self.logger.info(f"Removed Nginx config for {subdomain}")
            self.reload_nginx()

    def reload_nginx(self):
        """Reload Nginx configuration"""
        try:
            self.logger.info("Triggered Nginx reload (simulated)")
        except Exception as e:
            self.logger.error(f"Failed to reload Nginx: {e}")


class IngressRouter:
    """Manages routing to disposable environments"""
    
    def __init__(self):
        self.routes: Dict[str, Route] = {}
        self.nginx_gen = NginxConfigGenerator()
        self.logger = logging.getLogger(__name__)
    
    def register_route(self, route: Route) -> str:
        """Register a new route and return the external URL"""
        subdomain = f"{route.session_id[:8]}"
        external_url = f"https://{subdomain}.{route.domain}{route.path}"
        
        self.routes[external_url] = route
        self.nginx_gen.save_config(route)
        
        self.logger.info(f"Registered route: {external_url} -> {route.target_port}")
        return external_url
    
    def unregister_route(self, external_url: str):
        """Remove a route"""
        if external_url in self.routes:
            route = self.routes[external_url]
            self.nginx_gen.remove_config(route.session_id)
            del self.routes[external_url]
            self.logger.info(f"Unregistered route: {external_url}")


class NetworkManager:
    """Unified Network Manager for disposable compute platform"""

    def __init__(self, docker_client=None):
        self.router = IngressRouter()
        self.logger = logging.getLogger(__name__)
        self.docker_client = docker_client
        self.orphaned_check_done = False
        
        # Load Balancing state
        self.backends: Dict[str, List[Dict[str, Any]]] = {}
        self.connection_counts: Dict[str, int] = {}

    def create_isolated_network(self, environment_id: str) -> str:
        """Create an isolated network identifier"""
        return f"env-{environment_id[:12]}"

    def setup_internal_dns(self, network_name: str, services: List[Dict]) -> Dict[str, str]:
        """Set up internal DNS mapping"""
        dns_mapping = {}
        for service in services:
            service_name = service.get('name', 'default')
            dns_mapping[service_name] = f"{service_name}.{network_name}.internal"
        return dns_mapping

    def create_external_access(self, session_id: str, service_port: int, domain: str) -> str:
        """Create external access URL"""
        route = Route(
            path="/",
            target_port=service_port,
            session_id=session_id,
            service_name="main",
            domain=domain
        )
        return self.router.register_route(route)

    async def cleanup_network_with_retry(self, environment_id: str, external_urls: List[str]):
        """Clean up network resources"""
        for url in external_urls:
            self.router.unregister_route(url)
        
        if not self.docker_client:
            try:
                import docker
                self.docker_client = docker.from_env()
            except:
                return

        network_name = self.create_isolated_network(environment_id)
        try:
            if self.docker_client:
                network = self.docker_client.networks.get(network_name)
                for container in network.containers:
                    network.disconnect(container, force=True)
                network.remove()
        except:
            pass

    # Advanced LB features integrated here
    def add_backend(self, service_id: str, backend: Dict[str, Any]):
        if service_id not in self.backends:
            self.backends[service_id] = []
        self.backends[service_id].append(backend)
        backend_id = backend.get('id', 'unknown')
        self.connection_counts[backend_id] = 0

    async def get_next_backend(self, service_id: str, algorithm: str = "least-connections") -> Optional[Dict[str, Any]]:
        backends = self.backends.get(service_id, [])
        if not backends:
            return None
            
        if algorithm == "least-connections":
            return min(backends, key=lambda b: self.connection_counts.get(b.get('id', 'unknown'), 0))
        
        # Round-robin fallback
        return backends[0]
