"""
Authentication and Authorization module for disposable compute platform
"""
import os
import secrets
import jwt
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from functools import wraps
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from enum import Enum

logger = logging.getLogger(__name__)

# Security schemes
security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class User(BaseModel):
    """User model"""
    id: str
    email: str
    tier: UserTier = UserTier.FREE
    session_quota: int = 5
    max_session_ttl: int = 60  # minutes
    created_at: datetime = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """Create user from dictionary"""
        return cls(**data)


class TokenData(BaseModel):
    """JWT token payload"""
    user_id: str
    email: str
    tier: str
    exp: datetime
    iat: datetime


class AuthManager:
    """Manages authentication and authorization"""
    
    def __init__(
        self, 
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        token_expiry_minutes: int = 1440,  # 24 hours
        database: Any = None
    ):
        self.secret_key = secret_key or os.getenv("AUTH_SECRET_KEY", secrets.token_urlsafe(32))
        self.algorithm = algorithm
        self.token_expiry_minutes = token_expiry_minutes
        self.database = database
        
        # Rate limiting
        self._failed_attempts: Dict[str, List[datetime]] = {}
        self._rate_limit_window = 300  # 5 minutes
        self._max_failed_attempts = 5
        
        logger.info(f"AuthManager initialized with algorithm {algorithm}")
    
    def hash_password(self, password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against a hash"""
        try:
            return pwd_context.verify(plain_password, hashed_password)
        except Exception:
            return False
    
    def create_access_token(self, user_id: str, email: str, tier: str = "free") -> str:
        """Create JWT access token"""
        expire = datetime.utcnow() + timedelta(minutes=self.token_expiry_minutes)
        to_encode = {
            "sub": user_id,
            "email": email,
            "tier": tier,
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": secrets.token_hex(16)  # Unique token ID
        }
        
        try:
            encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
            logger.info(f"Created access token for user {user_id}")
            return encoded_jwt
        except Exception as e:
            logger.error(f"Failed to create access token: {e}")
            raise
    
    def verify_token(self, token: str) -> TokenData:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Validate required fields
            required_fields = ["sub", "email", "exp", "iat"]
            for field in required_fields:
                if field not in payload:
                    raise HTTPException(401, "Invalid token: missing required fields")
            
            return TokenData(
                user_id=payload["sub"],
                email=payload["email"],
                tier=payload.get("tier", "free"),
                exp=datetime.fromtimestamp(payload["exp"]),
                iat=datetime.fromtimestamp(payload["iat"])
            )
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise HTTPException(401, "Token expired", headers={"WWW-Authenticate": "Bearer"})
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"})
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            raise HTTPException(401, "Token verification failed", headers={"WWW-Authenticate": "Bearer"})
    
    def _check_rate_limit(self, identifier: str) -> bool:
        """Check if identifier is rate limited"""
        now = datetime.utcnow()
        
        # Clean old entries
        if identifier in self._failed_attempts:
            self._failed_attempts[identifier] = [
                attempt for attempt in self._failed_attempts[identifier]
                if (now - attempt).total_seconds() < self._rate_limit_window
            ]
        
        # Check limit
        if len(self._failed_attempts.get(identifier, [])) >= self._max_failed_attempts:
            return False  # Rate limited
        
        return True
    
    def _record_failed_attempt(self, identifier: str):
        """Record a failed authentication attempt"""
        now = datetime.utcnow()
        
        if identifier not in self._failed_attempts:
            self._failed_attempts[identifier] = []
        
        self._failed_attempts[identifier].append(now)
    
    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user with email and password"""
        # Check rate limit
        if not self._check_rate_limit(email):
            logger.warning(f"Rate limit exceeded for {email}")
            raise HTTPException(429, "Too many failed attempts. Please try again later.")
        
        try:
            if not self.database:
                logger.error("Database not configured for authentication")
                return None
            
            # Get user from database
            user = await self.database.get_user_by_email(email)
            
            if not user:
                self._record_failed_attempt(email)
                return None
            
            # Verify password
            if not hasattr(user, 'password_hash'):
                logger.error(f"User {email} has no password hash")
                return None
            
            if not self.verify_password(password, user.password_hash):
                self._record_failed_attempt(email)
                return None
            
            # Clear failed attempts on success
            if email in self._failed_attempts:
                del self._failed_attempts[email]
            
            return User(
                id=user.id,
                email=user.email,
                tier=user.tier,
                session_quota=user.session_quota if hasattr(user, 'session_quota') else 5,
                max_session_ttl=user.max_session_ttl if hasattr(user, 'max_session_ttl') else 60
            )
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return None
    
    async def get_current_user(
        self, 
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> User:
        """Get current user from JWT token"""
        if credentials is None:
            raise HTTPException(
                401, 
                "Not authenticated", 
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        token = credentials.credentials
        token_data = self.verify_token(token)
        
        # Get user from database
        if self.database:
            user = await self.database.get_user(token_data.user_id)
            if not user:
                raise HTTPException(401, "User not found")
            
            return User(
                id=user.id,
                email=user.email,
                tier=user.tier,
                session_quota=getattr(user, 'session_quota', 5),
                max_session_ttl=getattr(user, 'max_session_ttl', 60)
            )
        else:
            # Return user from token if no database (development mode)
            logger.warning("Using token-based user without database validation")
            return User(
                id=token_data.user_id,
                email=token_data.email,
                tier=token_data.tier
            )
    
    async def get_current_user_from_request(self, request: Request) -> User:
        """Extract and validate user from request"""
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(401, "Missing or invalid authorization header")
        
        token = auth_header.split(" ")[1]
        token_data = self.verify_token(token)
        
        # Get user from database
        if self.database:
            user = await self.database.get_user(token_data.user_id)
            if not user:
                raise HTTPException(401, "User not found")
            
            return User(
                id=user.id,
                email=user.email,
                tier=user.tier,
                session_quota=getattr(user, 'session_quota', 5),
                max_session_ttl=getattr(user, 'max_session_ttl', 60)
            )
        else:
            return User(
                id=token_data.user_id,
                email=token_data.email,
                tier=token_data.tier
            )


def require_auth(func):
    """Decorator to require authentication for an endpoint"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Get request from kwargs or args
        request = kwargs.get('request')
        if not request:
            # Try to find request in args (usually second argument after self)
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        
        if not request:
            raise HTTPException(500, "Request not available for authentication")
        
        # Get auth manager from app state
        auth_manager = getattr(request.app.state, 'auth_manager', None)
        if not auth_manager:
            raise HTTPException(500, "Authentication not configured")
        
        # Get current user
        try:
            current_user = await auth_manager.get_current_user_from_request(request)
        except HTTPException:
            raise
        
        # Add user to kwargs
        kwargs['current_user'] = current_user
        
        return await func(*args, **kwargs)
    
    return wrapper


def require_tier(required_tiers: List[UserTier]):
    """Decorator to require specific user tiers"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            if not current_user:
                raise HTTPException(401, "Authentication required")
            
            if current_user.tier not in required_tiers:
                raise HTTPException(
                    403, 
                    f"Access denied. Required tier: {', '.join(required_tiers)}"
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def require_quota_check(func):
    """Decorator to check user session quota before creating sessions"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        current_user = kwargs.get('current_user')
        if not current_user:
            raise HTTPException(401, "Authentication required")
        
        # Get session manager from request
        request = kwargs.get('request')
        if not request:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        
        if request:
            session_manager = getattr(request.app.state, 'session_manager', None)
            if session_manager:
                # Count active sessions for user
                user_sessions = [
                    s for s in session_manager.sessions.values()
                    if s.metadata.get('user_id') == current_user.id
                    and s.status.value in ['running', 'creating']
                ]
                
                if len(user_sessions) >= current_user.session_quota:
                    raise HTTPException(
                        429, 
                        f"Session quota exceeded. Maximum: {current_user.session_quota}"
                    )
        
        return await func(*args, **kwargs)
    return wrapper


# Request/Response models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: User


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    tier: UserTier = UserTier.FREE


class TokenRefreshRequest(BaseModel):
    refresh_token: str


class TokenRefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

# Global default instance for FastAPI dependency injection
default_auth_manager = AuthManager()

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """Dependency for getting the current user from token."""
    return await default_auth_manager.get_current_user(credentials)
