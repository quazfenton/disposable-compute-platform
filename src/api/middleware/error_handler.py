"""
Centralized Error Handling Middleware for disposable compute platform
Provides consistent error responses and logging
"""
import logging
import traceback
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import json

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base API error"""
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or f"ERROR_{status_code}"
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(APIError):
    """Resource not found"""
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            message=f"{resource} not found: {resource_id}",
            status_code=404,
            error_code="NOT_FOUND",
            details={"resource": resource, "resource_id": resource_id}
        )


class ValidationError(APIError):
    """Validation error"""
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message=message,
            status_code=400,
            error_code="VALIDATION_ERROR",
            details={"field": field} if field else {}
        )


class AuthenticationError(APIError):
    """Authentication error"""
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_ERROR"
        )


class AuthorizationError(APIError):
    """Authorization error"""
    def __init__(self, message: str = "Access denied"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="AUTHORIZATION_ERROR"
        )


class RateLimitError(APIError):
    """Rate limit exceeded"""
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            status_code=429,
            error_code="RATE_LIMIT_EXCEEDED",
            details={"retry_after": retry_after}
        )


class ResourceExhaustedError(APIError):
    """Resources exhausted"""
    def __init__(self, resource: str, limit: int):
        super().__init__(
            message=f"Resource limit exceeded: {resource} (limit: {limit})",
            status_code=429,
            error_code="RESOURCE_EXHAUSTED",
            details={"resource": resource, "limit": limit}
        )


class ContainerError(APIError):
    """Container operation error"""
    def __init__(self, operation: str, message: str):
        super().__init__(
            message=f"Container {operation} failed: {message}",
            status_code=500,
            error_code="CONTAINER_ERROR",
            details={"operation": operation}
        )


class DatabaseError(APIError):
    """Database operation error"""
    def __init__(self, operation: str, message: str):
        super().__init__(
            message=f"Database {operation} failed: {message}",
            status_code=500,
            error_code="DATABASE_ERROR",
            details={"operation": operation}
        )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle API errors"""
    error_response = {
        "error": True,
        "type": exc.error_code,
        "message": exc.message,
        "details": exc.details,
        "path": request.url.path,
        "method": request.method,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Log error
    log_level = logging.WARNING if exc.status_code < 500 else logging.ERROR
    logger.log(
        log_level,
        f"API Error: {exc.error_code} - {exc.message} - {request.method} {request.url.path}"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions"""
    error_response = {
        "error": True,
        "type": f"HTTP_{exc.status_code}",
        "message": exc.detail,
        "path": request.url.path,
        "method": request.method,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Add headers if present
    if exc.headers:
        error_response["headers"] = exc.headers
    
    # Log error
    log_level = logging.WARNING if exc.status_code < 500 else logging.ERROR
    logger.log(
        log_level,
        f"HTTP Exception: {exc.status_code} - {exc.detail} - {request.method} {request.url.path}"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response,
        headers=exc.headers if exc.headers else None
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle validation errors"""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(x) for x in error.get("loc", [])),
            "message": error.get("msg"),
            "type": error.get("type")
        })
    
    error_response = {
        "error": True,
        "type": "VALIDATION_ERROR",
        "message": "Request validation failed",
        "details": {
            "errors": errors
        },
        "path": request.url.path,
        "method": request.method,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.warning(f"Validation error: {errors} - {request.method} {request.url.path}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response
    )


async def pydantic_validation_handler(request: Request, exc: ValidationError) -> JSONResponse:
    """Handle Pydantic validation errors"""
    error_response = {
        "error": True,
        "type": "VALIDATION_ERROR",
        "message": "Response validation failed",
        "details": {
            "errors": str(exc)
        },
        "path": request.url.path,
        "method": request.method,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.error(f"Pydantic validation error: {exc} - {request.method} {request.url.path}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions"""
    # Get stack trace
    stack_trace = traceback.format_exc()
    
    # Generate error ID for tracking
    import hashlib
    error_id = hashlib.md5(
        f"{datetime.utcnow().isoformat()}{stack_trace}".encode()
    ).hexdigest()[:8]
    
    error_response = {
        "error": True,
        "type": "INTERNAL_ERROR",
        "message": "An unexpected error occurred",
        "details": {
            "error_id": error_id,
            "hint": "Please contact support if this error persists"
        },
        "path": request.url.path,
        "method": request.method,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Log full error with stack trace
    logger.error(
        f"Unhandled exception [Error ID: {error_id}]: {exc}\n{stack_trace}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response
    )


class ErrorHandlerMiddleware:
    """Middleware for error tracking and handling"""
    
    def __init__(self):
        self.error_counts: Dict[str, int] = {}
        self.start_time = datetime.utcnow()
    
    async def __call__(self, request: Request, call_next):
        """Track errors and add error context"""
        # Add request ID
        import uuid
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        try:
            response = await call_next(request)
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Add request ID to error context
            logger.error(f"Request {request_id} failed: {e}")
            raise


def setup_error_handlers(app):
    """Setup all error handlers for FastAPI app"""
    
    # Add middleware
    app.add_middleware(ErrorHandlerMiddleware)
    
    # Add exception handlers
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    
    logger.info("Error handlers configured")


class ErrorTracker:
    """Track and aggregate errors"""
    
    def __init__(self):
        self.errors: list = []
        self.max_errors = 1000
        self.error_counts: Dict[str, int] = {}
    
    def record_error(
        self,
        error_type: str,
        message: str,
        path: str,
        method: str,
        status_code: int,
        user_id: Optional[str] = None
    ):
        """Record an error"""
        error = {
            "type": error_type,
            "message": message,
            "path": path,
            "method": method,
            "status_code": status_code,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.errors.append(error)
        
        # Trim if too many
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors:]
        
        # Update counts
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        logger.error(f"Error recorded: {error_type} - {message}")
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get error summary"""
        return {
            "total_errors": len(self.errors),
            "error_counts": self.error_counts,
            "recent_errors": self.errors[-10:],
            "start_time": self.start_time.isoformat() if hasattr(self, 'start_time') else None
        }
    
    def get_errors_by_type(self, error_type: str) -> list:
        """Get errors by type"""
        return [e for e in self.errors if e["type"] == error_type]
    
    def clear(self):
        """Clear all errors"""
        self.errors = []
        self.error_counts = {}


# Global error tracker
_error_tracker = ErrorTracker()


def get_error_tracker() -> ErrorTracker:
    """Get global error tracker"""
    return _error_tracker
