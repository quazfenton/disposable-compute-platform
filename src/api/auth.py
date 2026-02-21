"""
Authentication and authorization for disposable compute platform
"""
import os
import time
import logging
import hashlib
import secrets
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from functools import wraps
import json

# Try imports
try:
    import jwt
    JWT_AVAILABLE = True
except ImportError:
    jwt = None
    JWT_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class User:
    """Authenticated user"""
    id: str
    email: str
    tier: str
    quota_sessions_per_day: int = 10
    quota_max_ttl_minutes: int = 120
    
    def can_create_session(self, current_sessions: int) -> bool:
        """Check if user can create more sessions"""
        return current_sessions < self.quota_sessions_per_day
    
    def get_max_ttl(self) -> int:
        """Get maximum TTL for user's sessions"""
        return self.quota_max_ttl_minutes


@dataclass
class APIKey:
    """API key for programmatic access"""
    key: str
    user_id: str
    name: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    scopes: list = None
    
    def __post_init__(self):
        if self.scopes is None:
            self.scopes = ["read", "write"]
    
    def is_expired(self) -> bool:
        """Check if API key is expired"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def has_scope(self, scope: str) -> bool:
        """Check if key has a scope"""
        return scope in self.scopes or "admin" in self.scopes


class AuthConfig:
    """Authentication configuration"""
    def __init__(self):
        self.jwt_secret = os.getenv("JWT_SECRET", secrets.token_hex(32))
        self.jwt_algorithm = "HS256"
        self.jwt_expire_hours = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
        self.api_key_header = "X-API-Key"
        self.bearer_header = "Authorization"


class TokenManager:
    """Manages JWT tokens"""
    
    def __init__(self, config: AuthConfig):
        self.config = config
    
    def create_token(self, user: User) -> str:
        """Create a JWT token for a user"""
        if not JWT_AVAILABLE:
            raise RuntimeError("PyJWT not installed. Run: pip install PyJWT")
        
        payload = {
            "sub": user.id,
            "email": user.email,
            "tier": user.tier,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=self.config.jwt_expire_hours)
        }
        
        return jwt.encode(payload, self.config.jwt_secret, algorithm=self.config.jwt_algorithm)
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a JWT token"""
        if not JWT_AVAILABLE:
            logger.warning("PyJWT not installed, token verification disabled")
            return None
        
        try:
            payload = jwt.decode(
                token,
                self.config.jwt_secret,
                algorithms=[self.config.jwt_algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    def get_user_from_token(self, token: str) -> Optional[User]:
        """Extract user from token"""
        payload = self.verify_token(token)
        if not payload:
            return None
        
        return User(
            id=payload.get("sub"),
            email=payload.get("email"),
            tier=payload.get("tier", "free")
        )


class APIKeyManager:
    """Manages API keys"""
    
    def __init__(self):
        self._keys: Dict[str, APIKey] = {}
        self._user_keys: Dict[str, list] = {}  # user_id -> [key, ...]
    
    def generate_key(self, user_id: str, name: str, expires_days: int = None, scopes: list = None) -> APIKey:
        """Generate a new API key"""
        # Generate secure random key
        key_bytes = secrets.token_bytes(32)
        key = f"dcp_{secrets.token_urlsafe(32)}"
        
        expires_at = None
        if expires_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_days)
        
        api_key = APIKey(
            key=key,
            user_id=user_id,
            name=name,
            created_at=datetime.utcnow(),
            expires_at=expires_at,
            scopes=scopes or ["read", "write"]
        )
        
        self._keys[key] = api_key
        
        if user_id not in self._user_keys:
            self._user_keys[user_id] = []
        self._user_keys[user_id].append(api_key)
        
        logger.info(f"Created API key '{name}' for user {user_id}")
        return api_key
    
    def verify_key(self, key: str) -> Optional[APIKey]:
        """Verify an API key"""
        api_key = self._keys.get(key)
        
        if not api_key:
            return None
        
        if api_key.is_expired():
            logger.warning(f"API key {api_key.key[:10]}... is expired")
            return None
        
        return api_key
    
    def revoke_key(self, key: str) -> bool:
        """Revoke an API key"""
        if key in self._keys:
            api_key = self._keys[key]
            del self._keys[key]
            
            if api_key.user_id in self._user_keys:
                self._user_keys[api_key.user_id] = [
                    k for k in self._user_keys[api_key.user_id] if k.key != key
                ]
            
            logger.info(f"Revoked API key {key[:10]}...")
            return True
        
        return False
    
    def list_user_keys(self, user_id: str) -> list:
        """List API keys for a user"""
        return self._user_keys.get(user_id, [])


class SessionQuotaManager:
    """Manages session quotas for users"""
    
    def __init__(self):
        self._counts: Dict[str, Dict[str, Any]] = {}  # user_id -> {date, count}
    
    def check_quota(self, user: User) -> Tuple[bool, str]:
        """Check if user has quota available"""
        today = datetime.utcnow().date().isoformat()
        
        if user.id not in self._counts:
            self._counts[user.id] = {"date": today, "count": 0}
        
        user_data = self._counts[user.id]
        
        # Reset counter for new day
        if user_data["date"] != today:
            user_data["date"] = today
            user_data["count"] = 0
        
        if user_data["count"] >= user.quota_sessions_per_day:
            return False, f"Daily quota exceeded ({user.quota_sessions_per_day} sessions/day)"
        
        return True, "Quota available"
    
    def increment_quota(self, user_id: str):
        """Increment session count for user"""
        today = datetime.utcnow().date().isoformat()
        
        if user_id not in self._counts:
            self._counts[user_id] = {"date": today, "count": 0}
        
        user_data = self._counts[user_id]
        
        if user_data["date"] != today:
            user_data["date"] = today
            user_data["count"] = 0
        
        user_data["count"] += 1
    
    def get_usage(self, user_id: str) -> Dict[str, Any]:
        """Get quota usage for user"""
        today = datetime.utcnow().date().isoformat()
        
        if user_id not in self._counts:
            return {"date": today, "count": 0}
        
        user_data = self._counts[user_id]
        
        if user_data["date"] != today:
            return {"date": today, "count": 0}
        
        return user_data.copy()


class AuthManager:
    """Main authentication manager"""
    
    def __init__(self, config: AuthConfig = None):
        self.config = config or AuthConfig()
        self.token_manager = TokenManager(self.config)
        self.api_key_manager = APIKeyManager()
        self.quota_manager = SessionQuotaManager()
        
        # Mock user store (in production, use database)
        self._users: Dict[str, User] = {}
    
    def create_user(self, user_id: str, email: str, tier: str = "free") -> User:
        """Create a new user"""
        user = User(
            id=user_id,
            email=email,
            tier=tier
        )
        self._users[user_id] = user
        return user
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return self._users.get(user_id)
    
    def authenticate_request(self, headers: Dict[str, str]) -> Optional[User]:
        """Authenticate a request using headers"""
        # Try API key first
        api_key = headers.get(self.config.api_key_header)
        if api_key:
            key = self.api_key_manager.verify_key(api_key)
            if key:
                return self.get_user(key.user_id)
        
        # Try Bearer token
        auth_header = headers.get(self.config.bearer_header, "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            user = self.token_manager.get_user_from_token(token)
            if user:
                return user
        
        return None
    
    def create_api_key(self, user_id: str, name: str, expires_days: int = None) -> APIKey:
        """Create an API key for a user"""
        return self.api_key_manager.generate_key(user_id, name, expires_days)
    
    def login(self, email: str, password: str) -> Optional[Tuple[str, User]]:
        """
        Login with email and password.
        Returns (token, user) on success, None on failure.
        
        In production, this would verify against a database with hashed passwords.
        """
        # Find user by email
        user = None
        for u in self._users.values():
            if u.email == email:
                user = u
                break
        
        if not user:
            logger.warning(f"Login attempt for unknown email: {email}")
            return None
        
        # In production, verify password hash
        # For demo, accept any password
        # if not verify_password(password, user.password_hash):
        #     return None
        
        token = self.token_manager.create_token(user)
        return token, user
    
    def check_session_quota(self, user: User) -> Tuple[bool, str]:
        """Check if user can create a new session"""
        return self.quota_manager.check_quota(user)
    
    def record_session_created(self, user_id: str):
        """Record that a session was created"""
        self.quota_manager.increment_quota(user_id)
