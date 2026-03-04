"""
Input validation and security utilities for disposable compute platform
"""
import re
import socket
import logging
from typing import Optional, List, Tuple, Dict, Any
from urllib.parse import urlparse
from datetime import timedelta
from pydantic import BaseModel, validator, HttpUrl, Field

logger = logging.getLogger(__name__)


# Constants
ALLOWED_REPO_HOSTS = [
    'github.com',
    'gitlab.com', 
    'bitbucket.org',
    'gitea.com',
    'gist.github.com'
]

PRIVATE_IP_RANGES = [
    ('10.0.0.0', '10.255.255.255'),
    ('172.16.0.0', '172.31.255.255'),
    ('192.168.0.0', '192.168.255.255'),
    ('127.0.0.0', '127.255.255.255'),
    ('169.254.0.0', '169.254.255.255'),  # Link-local
    ('0.0.0.0', '0.255.255.255'),
]

# TTL constraints
MIN_TTL_MINUTES = 5
MAX_TTL_MINUTES = 1440  # 24 hours
DEFAULT_TTL_MINUTES = 30

# Repository URL patterns
REPO_URL_PATTERN = re.compile(
    r'^https?://(github\.com|gitlab\.com|bitbucket\.org|gitea\.com|gist\.github\.com)/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+(\.git)?(/)?$'
)

# Branch/tag patterns
REF_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_./-]+$')


def ip_to_int(ip: str) -> int:
    """Convert IP address to integer for comparison"""
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return 0
        return sum(int(part) << (8 * (3 - i)) for i, part in enumerate(parts))
    except (ValueError, AttributeError):
        return 0


def is_private_ip(ip: str) -> bool:
    """Check if an IP address is in a private range"""
    try:
        ip_int = ip_to_int(ip)
        
        for start, end in PRIVATE_IP_RANGES:
            start_int = ip_to_int(start)
            end_int = ip_to_int(end)
            
            if start_int <= ip_int <= end_int:
                return True
        
        return False
    except Exception:
        return False


def validate_repo_url(url: str) -> Tuple[bool, str]:
    """
    Validate repository URL to prevent SSRF and shell injection attacks
    """
    if not url:
        return False, "Repository URL is required"
    
    # Strictly enforce HTTP(S) and prevent data/file/etc schemes
    if not url.startswith(('http://', 'https://')):
        return False, "URL must start with http:// or https://"
    
    # Prevent shell injection characters in URL
    dangerous_chars = [';', '&', '|', '>', '<', '$', '(', ')', '`', '\n', '\r']
    for char in dangerous_chars:
        if char in url:
            return False, "URL contains dangerous characters"

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"
    
    # ... rest of the logic
    
    # Validate scheme
    if parsed.scheme not in ['http', 'https']:
        return False, "Only HTTP and HTTPS URLs are allowed"
    
    # Validate host
    if not parsed.hostname:
        return False, "Invalid URL: missing hostname"
    
    # Check against allowed hosts
    if parsed.hostname.lower() not in [h.lower() for h in ALLOWED_REPO_HOSTS]:
        return False, f"Repository host not allowed. Allowed hosts: {', '.join(ALLOWED_REPO_HOSTS)}"
    
    # Resolve hostname and check for private IPs
    try:
        ip_addresses = socket.gethostbyname_ex(parsed.hostname)[2]
        
        for ip in ip_addresses:
            if is_private_ip(ip):
                logger.warning(f"Repository URL resolves to private IP: {ip}")
                return False, "Repository URL resolves to private network"
    except socket.gaierror:
        # DNS resolution failed - allow it through (will fail later if invalid)
        logger.warning(f"DNS resolution failed for {parsed.hostname}, allowing for now")
        pass
    except Exception as e:
        logger.error(f"Error checking IP address: {e}")
    
    # Check URL pattern
    if not REPO_URL_PATTERN.match(url):
        return False, "Invalid repository URL format"
    
    return True, "Valid"


def validate_ref_name(ref: str) -> Tuple[bool, str]:
    """
    Validate Git reference name (branch, tag, commit)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not ref:
        return True, "Optional ref not provided"
    
    if len(ref) > 256:
        return False, "Reference name too long (max 256 characters)"
    
    if not REF_NAME_PATTERN.match(ref):
        return False, "Invalid reference name format"
    
    # Check for dangerous patterns
    dangerous_patterns = ['../', '..\\', '~', '^', ':', '?', '*', '[']
    for pattern in dangerous_patterns:
        if pattern in ref:
            return False, f"Reference name contains invalid character: {pattern}"
    
    return True, "Valid"


def validate_ttl(ttl_minutes: Optional[int]) -> Tuple[int, str]:
    """
    Validate and clamp TTL to safe range
    
    Returns:
        Tuple of (clamped_ttl, warning_message)
    """
    if ttl_minutes is None:
        return DEFAULT_TTL_MINUTES, "Using default TTL"
    
    if not isinstance(ttl_minutes, int):
        try:
            ttl_minutes = int(ttl_minutes)
        except (ValueError, TypeError):
            return DEFAULT_TTL_MINUTES, "Invalid TTL format, using default"
    
    if ttl_minutes < MIN_TTL_MINUTES:
        logger.warning(f"TTL {ttl_minutes} minutes too short, clamping to {MIN_TTL_MINUTES}")
        return MIN_TTL_MINUTES, f"TTL too short, minimum is {MIN_TTL_MINUTES} minutes"
    
    if ttl_minutes > MAX_TTL_MINUTES:
        logger.warning(f"TTL {ttl_minutes} minutes too long, clamping to {MAX_TTL_MINUTES}")
        return MAX_TTL_MINUTES, f"TTL too long, maximum is {MAX_TTL_MINUTES} minutes"
    
    return ttl_minutes, "Valid"


def validate_pr_number(pr_number: Optional[int]) -> Tuple[Optional[int], str]:
    """Validate PR number"""
    if pr_number is None:
        return None, "Optional PR number not provided"
    
    if not isinstance(pr_number, int):
        try:
            pr_number = int(pr_number)
        except (ValueError, TypeError):
            return None, "Invalid PR number format"
    
    if pr_number < 1:
        return None, "PR number must be positive"
    
    if pr_number > 1000000:
        return None, "PR number seems unrealistic"
    
    return pr_number, "Valid"


def validate_session_type(session_type: str) -> Tuple[bool, str]:
    """Validate session type"""
    allowed_types = ['preview', 'run_repo', 'fork_gui']
    
    if not session_type:
        return False, "Session type is required"
    
    if session_type not in allowed_types:
        return False, f"Invalid session type. Allowed: {', '.join(allowed_types)}"
    
    return True, "Valid"


def sanitize_string(value: str, max_length: int = 1024) -> str:
    """Sanitize a string value"""
    if not value:
        return ""
    
    # Convert to string if not already
    value = str(value)
    
    # Truncate if too long
    if len(value) > max_length:
        value = value[:max_length]
    
    # Remove null bytes
    value = value.replace('\x00', '')
    
    # Strip whitespace
    value = value.strip()
    
    return value


def validate_metadata(metadata: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Validate and sanitize metadata"""
    if not metadata:
        return {}
    
    if not isinstance(metadata, dict):
        logger.warning("Metadata is not a dictionary")
        return {}
    
    sanitized = {}
    
    for key, value in metadata.items():
        # Sanitize key
        if not isinstance(key, str):
            key = str(key)
        
        key = sanitize_string(key, max_length=256)
        
        # Validate key format
        if not re.match(r'^[a-zA-Z0-9_-]+$', key):
            logger.warning(f"Invalid metadata key format: {key}")
            continue
        
        # Sanitize value
        if not isinstance(value, str):
            value = str(value)
        
        value = sanitize_string(value, max_length=4096)
        
        sanitized[key] = value
    
    return sanitized


class CreateSessionValidator(BaseModel):
    """Pydantic validator for session creation requests"""
    
    type: str = Field(..., description="Session type")
    repo_url: str = Field(..., description="Repository URL")
    repo_ref: Optional[str] = Field(None, description="Git reference (branch/tag/commit)")
    pr_number: Optional[int] = Field(None, description="Pull request number")
    ttl_minutes: Optional[int] = Field(None, description="Time to live in minutes")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata")
    
    @validator('type')
    def validate_type(cls, v):
        is_valid, message = validate_session_type(v)
        if not is_valid:
            raise ValueError(message)
        return v
    
    @validator('repo_url')
    def validate_repo_url(cls, v):
        is_valid, message = validate_repo_url(v)
        if not is_valid:
            raise ValueError(message)
        return v
    
    @validator('repo_ref')
    def validate_repo_ref(cls, v):
        if v:
            is_valid, message = validate_ref_name(v)
            if not is_valid:
                raise ValueError(message)
        return v
    
    @validator('pr_number')
    def validate_pr_number(cls, v):
        if v is not None:
            v, _ = validate_pr_number(v)
        return v
    
    @validator('ttl_minutes')
    def validate_ttl(cls, v):
        v, _ = validate_ttl(v)
        return v
    
    @validator('metadata')
    def validate_metadata(cls, v):
        return validate_metadata(v)


class InputValidator:
    """General purpose input validator"""
    
    @staticmethod
    def validate_create_session_request(
        session_type: str,
        repo_url: str,
        repo_ref: Optional[str] = None,
        pr_number: Optional[int] = None,
        ttl_minutes: Optional[int] = None,
        metadata: Optional[Dict[str, str]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate all inputs for session creation
        
        Returns:
            Tuple of (is_valid, error_message, sanitized_inputs)
        """
        errors = []
        sanitized = {}
        
        # Validate session type
        is_valid, message = validate_session_type(session_type)
        if not is_valid:
            errors.append(f"Session type: {message}")
        else:
            sanitized['session_type'] = session_type
        
        # Validate repo URL
        is_valid, message = validate_repo_url(repo_url)
        if not is_valid:
            errors.append(f"Repository URL: {message}")
        else:
            sanitized['repo_url'] = repo_url
        
        # Validate ref
        if repo_ref:
            is_valid, message = validate_ref_name(repo_ref)
            if not is_valid:
                errors.append(f"Repository ref: {message}")
            else:
                sanitized['repo_ref'] = repo_ref
        
        # Validate PR number
        if pr_number is not None:
            pr_number, _ = validate_pr_number(pr_number)
            sanitized['pr_number'] = pr_number
        
        # Validate TTL
        ttl_minutes, warning = validate_ttl(ttl_minutes)
        sanitized['ttl_minutes'] = ttl_minutes
        if warning and "Valid" not in warning:
            logger.info(f"TTL validation warning: {warning}")
        
        # Validate metadata
        sanitized['metadata'] = validate_metadata(metadata)
        
        if errors:
            return False, "; ".join(errors), {}
        
        return True, "Valid", sanitized


# Rate limiting helper
class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = {}
    
    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed for identifier"""
        import time
        
        now = time.time()
        window_start = now - self.window_seconds
        
        # Initialize or clean old requests
        if identifier not in self._requests:
            self._requests[identifier] = []
        
        self._requests[identifier] = [
            ts for ts in self._requests[identifier]
            if ts > window_start
        ]
        
        # Check limit
        if len(self._requests[identifier]) >= self.max_requests:
            return False
        
        # Record request
        self._requests[identifier].append(now)
        
        return True
    
    def get_retry_after(self, identifier: str) -> Optional[int]:
        """Get seconds until rate limit resets"""
        if identifier not in self._requests:
            return None
        
        if not self._requests[identifier]:
            return None
        
        oldest = min(self._requests[identifier])
        retry_after = int(oldest + self.window_seconds - __import__('time').time())
        
        return max(0, retry_after)
