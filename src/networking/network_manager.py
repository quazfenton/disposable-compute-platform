import asyncio
import logging
import socket
import ssl
from typing import Optional, Dict, Any, List
from contextlib import closing
import websockets
from dataclasses import dataclass

from ..types.config import settings


@dataclass
class StreamingSession:
    pod_id: str
    websocket: websockets.WebSocketServerProtocol
    client_ip: str
    started_at: float
    last_activity: float
    input_queue: asyncio.Queue
    port: Optional[int] = None


class NetworkManager:
    def __init__(self):
        self.assigned_ports = set()
        self.streaming_sessions: Dict[str, StreamingSession] = {}
        self.port_range_start = settings.streaming_port_range_start
        self.port_range_end = settings.streaming_port_range_end
        
        # Initialize available ports
        self.available_ports = set(range(self.port_range_start, self.port_range_end))
        self.available_ports -= self.assigned_ports
    
    def is_port_available(self, port: int) -> bool:
        """Check if a specific port is available"""
        return port in self.available_ports
    
    def allocate_port(self) -> Optional[int]:
        """Allocate an available port for streaming"""
        if not self.available_ports:
            return None
        
        port = self.available_ports.pop()
        self.assigned_ports.add(port)
        return port
    
    def release_port(self, port: int):
        """Release a port back to the available pool"""
        if port in self.assigned_ports:
            self.assigned_ports.remove(port)
            self.available_ports.add(port)
    
    def get_available_port_count(self) -> int:
        """Get the number of available ports"""
        return len(self.available_ports)
    
    async def check_port_availability(self, host: str, port: int, timeout: float = 1.0) -> bool:
        """Check if a port is available on a host"""
        try:
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                sock.settimeout(timeout)
                result = sock.connect_ex((host, port))
                return result != 0  # Port is available if connect_ex returns non-zero
        except Exception:
            return True  # Assume available if we can't check
    
    async def find_free_port(self, host: str = "localhost") -> Optional[int]:
        """Find a free port on the host"""
        for port in range(self.port_range_start, self.port_range_end):
            if await self.check_port_availability(host, port):
                return port
        return None
    
    def register_streaming_session(self, session: StreamingSession):
        """Register a new streaming session"""
        self.streaming_sessions[session.pod_id] = session
    
    def unregister_streaming_session(self, pod_id: str):
        """Unregister a streaming session"""
        if pod_id in self.streaming_sessions:
            del self.streaming_sessions[pod_id]
    
    def get_streaming_session(self, pod_id: str) -> Optional[StreamingSession]:
        """Get a streaming session by pod ID"""
        return self.streaming_sessions.get(pod_id)
    
    def get_all_streaming_sessions(self) -> Dict[str, StreamingSession]:
        """Get all active streaming sessions"""
        return self.streaming_sessions.copy()
    
    async def validate_network_access(self, pod_id: str, client_ip: str) -> bool:
        """Validate if a client can access a pod's streaming session"""
        # In a real implementation, this would check ACLs, IP whitelists, etc.
        # For now, we'll allow access if the session exists
        session = self.get_streaming_session(pod_id)
        return session is not None
    
    async def setup_streaming_endpoint(self, pod_id: str) -> Optional[str]:
        """Set up a streaming endpoint for a pod"""
        try:
            # Allocate a port for streaming
            port = self.allocate_port()
            if not port:
                logging.error(f"No available ports for streaming pod {pod_id}")
                return None

            # Create a streaming session with the allocated port
            session = StreamingSession(
                pod_id=pod_id,
                websocket=None,  # Will be set when actual connection is established
                client_ip="",  # Will be set when client connects
                started_at=0,  # Will be set when connection is established
                last_activity=0,  # Will be set when connection is established
                input_queue=asyncio.Queue(),
                port=port
            )

            self.register_streaming_session(session)

            # Construct the streaming URL
            # In a real implementation, this would set up the actual streaming server
            streaming_url = f"wss://{settings.api_host}:{port}/stream/{pod_id}"

            return streaming_url
        except Exception as e:
            logging.error(f"Error setting up streaming endpoint for pod {pod_id}: {e}")
            return None
    
    async def cleanup_streaming_endpoint(self, pod_id: str):
        """Clean up streaming endpoint for a pod"""
        try:
            # Get the streaming session to access the port
            session = self.get_streaming_session(pod_id)
            if session and session.port:
                # Release the port back to the pool
                self.release_port(session.port)

            # Remove the streaming session
            self.unregister_streaming_session(pod_id)

            # In a real implementation, this would shut down the actual streaming server

        except Exception as e:
            logging.error(f"Error cleaning up streaming endpoint for pod {pod_id}: {e}")
    
    async def monitor_network_health(self) -> Dict[str, Any]:
        """Monitor network health and statistics"""
        active_sessions = len(self.streaming_sessions)
        total_ports = self.port_range_end - self.port_range_start
        used_ports = len(self.assigned_ports)
        available_ports = len(self.available_ports)
        
        return {
            "active_streaming_sessions": active_sessions,
            "total_ports_available": total_ports,
            "ports_used": used_ports,
            "ports_available": available_ports,
            "port_utilization_percent": (used_ports / total_ports) * 100 if total_ports > 0 else 0
        }
    
    async def enforce_network_policy(self, pod_id: str, policy: Dict[str, Any]) -> bool:
        """Enforce network policies for a pod"""
        # In a real implementation, this would set up iptables rules, etc.
        # For now, we'll just validate the policy format
        required_keys = ["allowed_ips", "bandwidth_limit", "connection_limit"]
        return all(key in policy for key in required_keys)
    
    async def setup_pod_network_isolation(self, pod_id: str) -> bool:
        """Set up network isolation for a pod"""
        try:
            # In a real implementation, this would create network namespaces, etc.
            # For now, we'll just log the action
            logging.info(f"Setting up network isolation for pod {pod_id}")
            return True
        except Exception as e:
            logging.error(f"Error setting up network isolation for pod {pod_id}: {e}")
            return False
    
    async def teardown_pod_network_isolation(self, pod_id: str) -> bool:
        """Tear down network isolation for a pod"""
        try:
            # In a real implementation, this would remove network namespaces, etc.
            # For now, we'll just log the action
            logging.info(f"Tearing down network isolation for pod {pod_id}")
            return True
        except Exception as e:
            logging.error(f"Error tearing down network isolation for pod {pod_id}: {e}")
            return False