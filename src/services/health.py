"""
Health Check Service for disposable compute platform
Monitors system health and dependencies
"""
import asyncio
import logging
import shutil
import os
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import docker

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheck:
    """Result of a health check"""
    name: str
    status: HealthStatus
    message: str
    latency_ms: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class HealthReport:
    """Overall health report"""
    status: HealthStatus
    timestamp: datetime
    checks: List[HealthCheck]
    version: str = "1.0.0"
    uptime_seconds: float = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "checks": [check.to_dict() for check in self.checks]
        }


class DependencyHealthChecker:
    """Base class for dependency health checkers"""
    
    def __init__(self, name: str, timeout_seconds: float = 5.0):
        self.name = name
        self.timeout_seconds = timeout_seconds
        self.last_check: Optional[datetime] = None
        self.last_status: HealthStatus = HealthStatus.UNKNOWN
        self.consecutive_failures = 0
    
    async def check(self) -> HealthCheck:
        """Perform health check"""
        start_time = datetime.utcnow()
        
        try:
            result = await asyncio.wait_for(
                self._check(),
                timeout=self.timeout_seconds
            )
            
            self.last_check = datetime.utcnow()
            self.last_status = result.status
            self.consecutive_failures = 0
            
            # Calculate latency
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            result.latency_ms = latency_ms
            
            return result
            
        except asyncio.TimeoutError:
            self.consecutive_failures += 1
            return HealthCheck(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after {self.timeout_seconds}s",
                details={"timeout": self.timeout_seconds}
            )
        except Exception as e:
            self.consecutive_failures += 1
            logger.error(f"Health check failed for {self.name}: {e}")
            return HealthCheck(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                details={"error_type": type(e).__name__}
            )
    
    async def _check(self) -> HealthCheck:
        """Implement specific health check logic"""
        raise NotImplementedError


class DockerHealthChecker(DependencyHealthChecker):
    """Check Docker daemon connectivity"""
    
    def __init__(self, timeout_seconds: float = 5.0):
        super().__init__("docker", timeout_seconds)
        self.docker_client = docker.from_env()
    
    async def _check(self) -> HealthCheck:
        try:
            # Ping Docker
            self.docker_client.ping()
            
            # Get Docker info
            info = self.docker_client.info()
            
            return HealthCheck(
                name="docker",
                status=HealthStatus.HEALTHY,
                message="Docker daemon is running",
                details={
                    "version": info.get("ServerVersion"),
                    "containers_running": info.get("ContainersRunning", 0),
                    "containers_paused": info.get("ContainersPaused", 0),
                    "containers_stopped": info.get("ContainersStopped", 0),
                    "images": info.get("Images", 0)
                }
            )
        except Exception as e:
            return HealthCheck(
                name="docker",
                status=HealthStatus.UNHEALTHY,
                message=f"Docker daemon not accessible: {str(e)}",
                details={"error": str(e)}
            )


class DatabaseHealthChecker(DependencyHealthChecker):
    """Check database connectivity"""
    
    def __init__(self, database: Any = None, timeout_seconds: float = 5.0):
        super().__init__("database", timeout_seconds)
        self.database = database
    
    async def _check(self) -> HealthCheck:
        if not self.database:
            return HealthCheck(
                name="database",
                status=HealthStatus.UNKNOWN,
                message="Database not configured"
            )
        
        try:
            # Try to execute a simple query
            start = datetime.utcnow()
            
            if hasattr(self.database, 'execute'):
                await self.database.execute("SELECT 1")
            elif hasattr(self.database, 'fetchval'):
                await self.database.fetchval("SELECT 1")
            else:
                return HealthCheck(
                    name="database",
                    status=HealthStatus.UNKNOWN,
                    message="Unknown database interface"
                )
            
            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
            
            return HealthCheck(
                name="database",
                status=HealthStatus.HEALTHY,
                message="Database connection healthy",
                details={"latency_ms": latency_ms}
            )
        except Exception as e:
            return HealthCheck(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {str(e)}",
                details={"error": str(e)}
            )


class RedisHealthChecker(DependencyHealthChecker):
    """Check Redis connectivity"""
    
    def __init__(self, redis_client: Any = None, timeout_seconds: float = 5.0):
        super().__init__("redis", timeout_seconds)
        self.redis_client = redis_client
    
    async def _check(self) -> HealthCheck:
        if not self.redis_client:
            return HealthCheck(
                name="redis",
                status=HealthStatus.UNKNOWN,
                message="Redis not configured"
            )
        
        try:
            start = datetime.utcnow()
            
            # Ping Redis
            await self.redis_client.ping()
            
            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
            
            # Get Redis info
            info = await self.redis_client.info()
            
            return HealthCheck(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Redis connection healthy",
                details={
                    "latency_ms": latency_ms,
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory", 0),
                    "version": info.get("redis_version")
                }
            )
        except Exception as e:
            return HealthCheck(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection failed: {str(e)}",
                details={"error": str(e)}
            )


class StorageHealthChecker(DependencyHealthChecker):
    """Check storage availability and space"""
    
    def __init__(self, storage_path: str, min_free_gb: float = 1.0, timeout_seconds: float = 5.0):
        super().__init__("storage", timeout_seconds)
        self.storage_path = storage_path
        self.min_free_gb = min_free_gb
    
    async def _check(self) -> HealthCheck:
        try:
            # Check if path exists
            if not os.path.exists(self.storage_path):
                return HealthCheck(
                    name="storage",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Storage path does not exist: {self.storage_path}"
                )
            
            # Get disk usage
            stat = shutil.disk_usage(self.storage_path)
            free_gb = stat.free / (1024 ** 3)
            total_gb = stat.total / (1024 ** 3)
            used_gb = stat.used / (1024 ** 3)
            
            # Check free space
            if free_gb < self.min_free_gb:
                return HealthCheck(
                    name="storage",
                    status=HealthStatus.DEGRADED,
                    message=f"Low disk space: {free_gb:.2f}GB free (minimum: {self.min_free_gb}GB)",
                    details={
                        "free_gb": free_gb,
                        "total_gb": total_gb,
                        "used_gb": used_gb,
                        "usage_percent": (stat.used / stat.total) * 100
                    }
                )
            
            return HealthCheck(
                name="storage",
                status=HealthStatus.HEALTHY,
                message=f"Storage healthy: {free_gb:.2f}GB free",
                details={
                    "free_gb": free_gb,
                    "total_gb": total_gb,
                    "used_gb": used_gb,
                    "usage_percent": (stat.used / stat.total) * 100
                }
            )
        except Exception as e:
            return HealthCheck(
                name="storage",
                status=HealthStatus.UNHEALTHY,
                message=f"Storage check failed: {str(e)}",
                details={"error": str(e)}
            )


class APIHealthChecker(DependencyHealthChecker):
    """Check API responsiveness"""
    
    def __init__(self, timeout_seconds: float = 5.0):
        super().__init__("api", timeout_seconds)
        self.request_count = 0
        self.error_count = 0
    
    async def _check(self) -> HealthCheck:
        # This is a self-check, always healthy if we get here
        return HealthCheck(
            name="api",
            status=HealthStatus.HEALTHY,
            message="API is responding",
            details={
                "requests_processed": self.request_count,
                "errors": self.error_count
            }
        )
    
    def record_request(self):
        self.request_count += 1
    
    def record_error(self):
        self.error_count += 1


class NetworkHealthChecker(DependencyHealthChecker):
    """Check network connectivity"""
    
    def __init__(self, timeout_seconds: float = 5.0):
        super().__init__("network", timeout_seconds)
    
    async def _check(self) -> HealthCheck:
        import socket
        
        try:
            # Test DNS resolution
            start = datetime.utcnow()
            socket.gethostbyname("google.com")
            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
            
            return HealthCheck(
                name="network",
                status=HealthStatus.HEALTHY,
                message="Network connectivity healthy",
                details={"dns_latency_ms": latency_ms}
            )
        except Exception as e:
            return HealthCheck(
                name="network",
                status=HealthStatus.UNHEALTHY,
                message=f"Network connectivity issue: {str(e)}",
                details={"error": str(e)}
            )


class HealthChecker:
    """Main health checker that coordinates all dependency checkers"""
    
    def __init__(
        self,
        docker_client: Any = None,
        database: Any = None,
        redis_client: Any = None,
        storage_path: str = "/tmp"
    ):
        self.checkers: List[DependencyHealthChecker] = []
        self.start_time = datetime.utcnow()
        
        # Add default checkers
        if docker_client:
            self.checkers.append(DockerHealthChecker())
        else:
            try:
                self.checkers.append(DockerHealthChecker())
            except Exception:
                logger.warning("Docker not available, skipping Docker health check")
        
        if database:
            self.checkers.append(DatabaseHealthChecker(database))
        
        if redis_client:
            self.checkers.append(RedisHealthChecker(redis_client))
        
        self.checkers.append(StorageHealthChecker(storage_path))
        self.checkers.append(APIHealthChecker())
        self.checkers.append(NetworkHealthChecker())
        
        # Background health check task
        self._background_task: Optional[asyncio.Task] = None
        self._last_report: Optional[HealthReport] = None
        
        logger.info(f"HealthChecker initialized with {len(self.checkers)} checkers")
    
    async def check_all(self) -> HealthReport:
        """Run all health checks"""
        checks = []
        
        # Run all checks in parallel
        tasks = [checker.check() for checker in self.checkers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                checks.append(HealthCheck(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=str(result)
                ))
            elif isinstance(result, HealthCheck):
                checks.append(result)
        
        # Determine overall status
        statuses = [check.status for check in checks]
        
        if HealthStatus.UNHEALTHY in statuses:
            overall_status = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall_status = HealthStatus.DEGRADED
        elif HealthStatus.UNKNOWN in statuses:
            overall_status = HealthStatus.UNKNOWN
        else:
            overall_status = HealthStatus.HEALTHY
        
        # Calculate uptime
        uptime_seconds = (datetime.utcnow() - self.start_time).total_seconds()
        
        report = HealthReport(
            status=overall_status,
            timestamp=datetime.utcnow(),
            checks=checks,
            uptime_seconds=uptime_seconds
        )
        
        self._last_report = report
        
        return report
    
    async def start_background_checks(self, interval_seconds: int = 30):
        """Start background health check task"""
        async def background_task():
            while True:
                try:
                    await self.check_all()
                    await asyncio.sleep(interval_seconds)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Background health check error: {e}")
                    await asyncio.sleep(interval_seconds)
        
        self._background_task = asyncio.create_task(background_task())
        logger.info(f"Started background health checks every {interval_seconds}s")
    
    async def stop_background_checks(self):
        """Stop background health check task"""
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped background health checks")
    
    def get_last_report(self) -> Optional[HealthReport]:
        """Get last health report"""
        return self._last_report
    
    def is_healthy(self) -> bool:
        """Check if system is healthy"""
        if not self._last_report:
            return False
        return self._last_report.status == HealthStatus.HEALTHY
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get quick status summary"""
        if not self._last_report:
            return {"status": "unknown", "message": "No health checks run yet"}
        
        return {
            "status": self._last_report.status.value,
            "timestamp": self._last_report.timestamp.isoformat(),
            "uptime_seconds": self._last_report.uptime_seconds,
            "checks_count": len(self._last_report.checks),
            "healthy_checks": sum(1 for c in self._last_report.checks if c.status == HealthStatus.HEALTHY),
            "degraded_checks": sum(1 for c in self._last_report.checks if c.status == HealthStatus.DEGRADED),
            "unhealthy_checks": sum(1 for c in self._last_report.checks if c.status == HealthStatus.UNHEALTHY)
        }


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get global health checker"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


def init_health_checker(
    docker_client: Any = None,
    database: Any = None,
    redis_client: Any = None,
    storage_path: str = "/tmp"
) -> HealthChecker:
    """Initialize global health checker"""
    global _health_checker
    _health_checker = HealthChecker(
        docker_client=docker_client,
        database=database,
        redis_client=redis_client,
        storage_path=storage_path
    )
    return _health_checker
