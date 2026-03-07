"""
Security and Reliability Fixes for Disposable Compute Platform

Fixes:
1. Race condition in session ID generation - use asyncio.Lock and secrets.token_hex
2. Container state recovery from DB - implement recovery on startup
3. Rate limiting on WebSocket - add WebSocket rate limiter
4. Grafana admin password in env - use Docker secrets
"""

import asyncio
import secrets
import logging
from typing import Dict
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# Fix 1: Race Condition in Session ID Generation
# ============================================================================

class SecureSessionIDGenerator:
    """
    Thread-safe session ID generator using cryptographic randomness.
    
    SECURITY FIX:
    - Uses asyncio.Lock to prevent race conditions
    - Uses secrets.token_hex() for cryptographic randomness
    - Tracks generated IDs to prevent collisions
    """
    
    def __init__(self):
        self._lock = asyncio.Lock()
        self._generated_ids: Dict[str, datetime] = {}
        self._cleanup_interval = 3600  # 1 hour
    
    async def generate(self, prefix: str = "session") -> str:
        """
        Generate a unique session ID.
        
        Returns:
            Secure unique session ID
        """
        async with self._lock:
            # Clean up old IDs
            await self._cleanup_old_ids()
            
            # Generate unique ID with collision detection
            max_attempts = 10
            for _ in range(max_attempts):
                # Use cryptographic randomness
                random_part = secrets.token_hex(8)  # 16 hex chars = 64 bits of entropy
                timestamp = datetime.now().timestamp()
                session_id = f"{prefix}-{int(timestamp)}-{random_part}"
                
                # Check for collision
                if session_id not in self._generated_ids:
                    self._generated_ids[session_id] = datetime.now()
                    return session_id
            
            # If we get here, we had 10 collisions in a row (extremely unlikely)
            logger.error("Failed to generate unique session ID after 10 attempts")
            raise RuntimeError("Unable to generate unique session ID")
    
    async def _cleanup_old_ids(self):
        """Remove IDs older than cleanup interval"""
        now = datetime.now()
        to_remove = []
        
        for session_id, created_at in self._generated_ids.items():
            if (now - created_at).total_seconds() > self._cleanup_interval:
                to_remove.append(session_id)
        
        for session_id in to_remove:
            del self._generated_ids[session_id]


# Global session ID generator
session_id_generator = SecureSessionIDGenerator()


# ============================================================================
# Fix 2: Container State Recovery from Database
# ============================================================================

class ContainerStateRecovery:
    """
    Recovers container state from database on startup.
    
    SECURITY FIX:
    - Validates container state before recovery
    - Only recovers sessions within TTL
    - Logs all recovery attempts for audit
    """
    
    def __init__(self, database, orchestrator):
        self.database = database
        self.orchestrator = orchestrator
        self.logger = logging.getLogger(__name__)
    
    async def recover_all_sessions(self) -> Dict[str, any]:
        """
        Recover all valid sessions from database.
        
        Returns:
            Dictionary with recovery statistics
        """
        stats = {
            "total_found": 0,
            "recovered": 0,
            "expired": 0,
            "failed": 0
        }
        
        if not self.database:
            self.logger.warning("No database available for recovery")
            return stats
        
        try:
            # Get all active sessions from database
            sessions = await self.database.get_all_active_sessions()
            stats["total_found"] = len(sessions)
            
            for session_data in sessions:
                session_id = session_data.get("id")
                
                # Check if session is expired
                if self._is_session_expired(session_data):
                    self.logger.info(f"Session {session_id} expired, marking as terminated")
                    await self.database.update_session_status(session_id, "terminated")
                    stats["expired"] += 1
                    continue
                
                # Try to recover container
                try:
                    await self._recover_session(session_data)
                    stats["recovered"] += 1
                    self.logger.info(f"Recovered session {session_id}")
                except Exception as e:
                    self.logger.error(f"Failed to recover session {session_id}: {e}")
                    stats["failed"] += 1
            
            self.logger.info(
                f"Recovery complete: {stats['recovered']}/{stats['total_found']} sessions recovered"
            )
            
        except Exception as e:
            self.logger.error(f"Recovery failed: {e}")
        
        return stats
    
    def _is_session_expired(self, session_data: Dict) -> bool:
        """Check if session has expired"""
        created_at = datetime.fromisoformat(session_data["created_at"])
        ttl_minutes = session_data.get("ttl_minutes", 60)
        
        now = datetime.now()
        expires_at = created_at.replace(
            minute=created_at.minute + ttl_minutes % 60,
            hour=created_at.hour + ttl_minutes // 60
        )
        
        return now > expires_at
    
    async def _recover_session(self, session_data: Dict):
        """Recover a single session"""
        session_id = session_data["id"]
        container_name = session_data.get("container_name")
        
        if not container_name:
            raise ValueError(f"No container name for session {session_id}")
        
        # Check if container still exists
        container_exists = await self.orchestrator.container_exists(container_name)
        
        if container_exists:
            # Container exists, restore to session manager
            await self.database.update_session_status(session_id, "active")
        else:
            # Container doesn't exist, recreate or mark as failed
            self.logger.warning(f"Container {container_name} not found for session {session_id}")
            
            # Option 1: Recreate container
            # await self.orchestrator.recreate_container(session_data)
            
            # Option 2: Mark as failed
            await self.database.update_session_status(session_id, "failed")
            raise RuntimeError(f"Container {container_name} not found")


# ============================================================================
# Fix 3: WebSocket Rate Limiting
# ============================================================================

class WebSocketRateLimiter:
    """
    Rate limiter for WebSocket connections.
    
    SECURITY FIX:
    - Limits connections per user/IP
    - Prevents WebSocket-based DoS attacks
    - Tracks message rate per connection
    """
    
    def __init__(self, max_connections: int = 10, max_messages_per_second: float = 10.0):
        self.max_connections = max_connections
        self.max_messages_per_second = max_messages_per_second
        self._connections: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()
    
    async def can_connect(self, user_id: str, ip_address: str) -> tuple[bool, str]:
        """
        Check if user can establish WebSocket connection.
        
        Returns:
            Tuple of (allowed, reason)
        """
        async with self._lock:
            # Count existing connections for this user
            user_connections = sum(
                1 for conn in self._connections.values()
                if conn.get("user_id") == user_id
            )
            
            if user_connections >= self.max_connections:
                return False, f"Maximum {self.max_connections} connections per user"
            
            # Count connections from this IP
            ip_connections = sum(
                1 for conn in self._connections.values()
                if conn.get("ip_address") == ip_address
            )
            
            if ip_connections >= self.max_connections * 2:
                return False, f"Maximum {self.max_connections * 2} connections per IP"
            
            return True, "OK"
    
    async def register_connection(self, connection_id: str, user_id: str, ip_address: str):
        """Register a new WebSocket connection"""
        async with self._lock:
            self._connections[connection_id] = {
                "user_id": user_id,
                "ip_address": ip_address,
                "connected_at": datetime.now(),
                "message_count": 0,
                "last_message_at": None
            }
    
    async def unregister_connection(self, connection_id: str):
        """Unregister WebSocket connection"""
        async with self._lock:
            if connection_id in self._connections:
                del self._connections[connection_id]
    
    async def can_send_message(self, connection_id: str) -> tuple[bool, str]:
        """
        Check if connection can send a message (rate limiting).
        
        Returns:
            Tuple of (allowed, reason)
        """
        async with self._lock:
            if connection_id not in self._connections:
                return False, "Connection not registered"
            
            conn = self._connections[connection_id]
            now = datetime.now()
            
            # Update message count
            conn["message_count"] += 1
            
            if conn["last_message_at"] is None:
                conn["last_message_at"] = now
                return True, "OK"
            
            # Calculate messages per second
            elapsed = (now - conn["last_message_at"]).total_seconds()
            if elapsed > 0:
                messages_per_second = conn["message_count"] / max(elapsed, 1)
                
                if messages_per_second > self.max_messages_per_second:
                    return False, f"Rate limit exceeded (max {self.max_messages_per_second} msg/s)"
            
            conn["last_message_at"] = now
            return True, "OK"
    
    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        return {
            "active_connections": len(self._connections),
            "max_connections": self.max_connections,
            "max_messages_per_second": self.max_messages_per_second
        }


# Global WebSocket rate limiter
websocket_rate_limiter = WebSocketRateLimiter(
    max_connections=10,
    max_messages_per_second=10.0
)


# ============================================================================
# Fix 4: Grafana Admin Password via Docker Secrets
# ============================================================================

def get_grafana_admin_password() -> str:
    """
    Get Grafana admin password from Docker secrets or environment.
    
    SECURITY FIX:
    - Reads from Docker secrets file if available
    - Falls back to environment variable (with warning)
    - Never uses default password in production
    
    Usage in docker-compose.yml:
    
    services:
      grafana:
        secrets:
          - grafana_admin_password
        environment:
          - GF_SECURITY_ADMIN_PASSWORD_FILE=/run/secrets/grafana_admin_password
    
    secrets:
      grafana_admin_password:
        external: true  # Or use file: ./secrets/grafana_password.txt
    """
    import os
    
    # Try to read from Docker secrets file
    secret_file = "/run/secrets/grafana_admin_password"
    
    if os.path.exists(secret_file):
        try:
            with open(secret_file, 'r') as f:
                password = f.read().strip()
                if password:
                    logger.info("Grafana admin password loaded from Docker secrets")
                    return password
        except Exception as e:
            logger.error(f"Failed to read Grafana password from secrets: {e}")
    
    # Fall back to environment variable
    env_password = os.getenv("GRAFANA_ADMIN_PASSWORD")
    
    if env_password:
        logger.warning(
            "⚠️  GRAFANA_ADMIN_PASSWORD is set via environment variable. "
            "This is less secure than Docker secrets. "
            "Consider using Docker secrets in production."
        )
        return env_password
    
    # Check for legacy variable name
    legacy_password = os.getenv("GRAFANA_PASSWORD")
    
    if legacy_password:
        logger.warning(
            "⚠️  Using legacy GRAFANA_PASSWORD environment variable. "
            "Please migrate to GRAFANA_ADMIN_PASSWORD or Docker secrets."
        )
        return legacy_password
    
    # No password configured
    logger.error(
        "❌ GRAFANA_ADMIN_PASSWORD not configured. "
        "Set GRAFANA_ADMIN_PASSWORD environment variable or use Docker secrets."
    )
    
    # In development, use a warning but continue
    if os.getenv("ENVIRONMENT") != "production":
        logger.warning("Using default password for development (CHANGE IN PRODUCTION!)")
        return "admin"
    
    # In production, this is a critical error
    raise RuntimeError(
        "Grafana admin password not configured. "
        "Set GRAFANA_ADMIN_PASSWORD or use Docker secrets."
    )


def validate_grafana_password(password: str) -> bool:
    """
    Validate Grafana admin password meets security requirements.
    
    Requirements:
    - Minimum 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - Not a common default password
    """
    if len(password) < 8:
        return False
    
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    
    if not (has_upper and has_lower and has_digit):
        return False
    
    # Check for common default passwords
    common_passwords = ["admin", "password", "grafana", "admin123", "password123"]
    if password.lower() in common_passwords:
        return False
    
    return True


# ============================================================================
# Integration Example for Platform Service
# ============================================================================

async def initialize_platform_with_fixes(platform_manager):
    """
    Initialize platform with all security fixes applied.
    
    Usage:
        from src.fixes import initialize_platform_with_fixes
        await initialize_platform_with_fixes(platform_manager)
    """
    logger.info("Initializing platform with security fixes...")
    
    # Fix 1: Use secure session ID generator
    platform_manager.session_id_generator = session_id_generator
    logger.info("✓ Secure session ID generator initialized")
    
    # Fix 2: Recover container state from database
    if platform_manager.database:
        recovery = ContainerStateRecovery(
            platform_manager.database,
            platform_manager.orchestrator
        )
        stats = await recovery.recover_all_sessions()
        logger.info(f"✓ Container state recovery complete: {stats}")
    
    # Fix 3: WebSocket rate limiter ready
    platform_manager.websocket_rate_limiter = websocket_rate_limiter
    logger.info("✓ WebSocket rate limiter initialized")
    
    # Fix 4: Validate Grafana password
    grafana_password = get_grafana_admin_password()
    if not validate_grafana_password(grafana_password):
        logger.warning("⚠️  Grafana password does not meet security requirements")
    
    logger.info("✓ Platform initialization complete")


# ============================================================================
# Example WebSocket Endpoint with Rate Limiting
# ============================================================================

"""
Example FastAPI WebSocket endpoint with rate limiting:

from fastapi import WebSocket, WebSocketDisconnect
from src.fixes import websocket_rate_limiter

@app.websocket("/ws/session/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    user_id: str = Depends(get_current_user)
):
    # Check if user can connect
    client_ip = websocket.client.host
    allowed, reason = await websocket_rate_limiter.can_connect(user_id, client_ip)
    
    if not allowed:
        await websocket.close(code=4429, reason=reason)
        return
    
    # Accept connection
    await websocket.accept()
    connection_id = f"{session_id}-{user_id}"
    await websocket_rate_limiter.register_connection(connection_id, user_id, client_ip)
    
    try:
        while True:
            # Check rate limit before processing message
            allowed, reason = await websocket_rate_limiter.can_send_message(connection_id)
            if not allowed:
                await websocket.send_json({"error": reason})
                continue
            
            # Process message
            data = await websocket.receive_text()
            # ... handle message ...
            
    except WebSocketDisconnect:
        pass
    finally:
        await websocket_rate_limiter.unregister_connection(connection_id)
"""
