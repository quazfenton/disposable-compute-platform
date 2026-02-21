"""
Metrics and observability for disposable compute platform
Integrates with Prometheus for monitoring
"""
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass, field
from contextlib import contextmanager
import threading

# Try to import prometheus client
try:
    from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, REGISTRY, generate_latest
    PROMETHEUS_AVAILABLE = True
except ImportError:
    Counter = Gauge = Histogram = CollectorRegistry = REGISTRY = None
    PROMETHEUS_AVAILABLE = False
    generate_latest = None


logger = logging.getLogger(__name__)


@dataclass
class MetricValue:
    """A single metric value"""
    name: str
    value: float
    labels: Dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class MetricsRegistry:
    """Registry for metrics"""
    
    def __init__(self, namespace: str = "dcp"):
        self.namespace = namespace
        self._metrics: Dict[str, Any] = {}
        self._lock = threading.Lock()
        
        # In-memory storage for when Prometheus is not available
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        
        if PROMETHEUS_AVAILABLE:
            self._prometheus_registry = CollectorRegistry()
        else:
            self._prometheus_registry = None
    
    def counter(self, name: str, description: str, labels: List[str] = None) -> Counter:
        """Get or create a counter metric"""
        full_name = f"{self.namespace}_{name}"
        
        with self._lock:
            if full_name not in self._metrics:
                if PROMETHEUS_AVAILABLE:
                    self._metrics[full_name] = Counter(
                        full_name,
                        description,
                        labels or [],
                        registry=self._prometheus_registry
                    )
                else:
                    self._metrics[full_name] = None
                    self._counters[full_name] = 0.0
            
            return self._metrics.get(full_name)
    
    def gauge(self, name: str, description: str, labels: List[str] = None) -> Gauge:
        """Get or create a gauge metric"""
        full_name = f"{self.namespace}_{name}"
        
        with self._lock:
            if full_name not in self._metrics:
                if PROMETHEUS_AVAILABLE:
                    self._metrics[full_name] = Gauge(
                        full_name,
                        description,
                        labels or [],
                        registry=self._prometheus_registry
                    )
                else:
                    self._metrics[full_name] = None
                    self._gauges[full_name] = 0.0
            
            return self._metrics.get(full_name)
    
    def histogram(self, name: str, description: str, labels: List[str] = None, 
                  buckets: List[float] = None) -> Histogram:
        """Get or create a histogram metric"""
        full_name = f"{self.namespace}_{name}"
        
        with self._lock:
            if full_name not in self._metrics:
                if PROMETHEUS_AVAILABLE:
                    self._metrics[full_name] = Histogram(
                        full_name,
                        description,
                        labels or [],
                        buckets=buckets or [0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
                        registry=self._prometheus_registry
                    )
                else:
                    self._metrics[full_name] = None
                    self._histograms[full_name] = []
            
            return self._metrics.get(full_name)
    
    def increment(self, name: str, value: float = 1.0, labels: Dict[str, str] = None):
        """Increment a counter"""
        full_name = f"{self.namespace}_{name}"
        
        if PROMETHEUS_AVAILABLE and full_name in self._metrics:
            metric = self._metrics[full_name]
            if metric:
                if labels:
                    metric.labels(**labels).inc(value)
                else:
                    metric.inc(value)
        else:
            with self._lock:
                if full_name not in self._counters:
                    self._counters[full_name] = 0.0
                self._counters[full_name] += value
    
    def set_gauge(self, name: str, value: float, labels: Dict[str, str] = None):
        """Set a gauge value"""
        full_name = f"{self.namespace}_{name}"
        
        if PROMETHEUS_AVAILABLE and full_name in self._metrics:
            metric = self._metrics[full_name]
            if metric:
                if labels:
                    metric.labels(**labels).set(value)
                else:
                    metric.set(value)
        else:
            with self._lock:
                self._gauges[full_name] = value
    
    def observe(self, name: str, value: float, labels: Dict[str, str] = None):
        """Observe a value for histogram"""
        full_name = f"{self.namespace}_{name}"
        
        if PROMETHEUS_AVAILABLE and full_name in self._metrics:
            metric = self._metrics[full_name]
            if metric:
                if labels:
                    metric.labels(**labels).observe(value)
                else:
                    metric.observe(value)
        else:
            with self._lock:
                if full_name not in self._histograms:
                    self._histograms[full_name] = []
                self._histograms[full_name].append(value)
    
    def get_counter_value(self, name: str) -> float:
        """Get counter value (for non-Prometheus mode)"""
        full_name = f"{self.namespace}_{name}"
        return self._counters.get(full_name, 0.0)
    
    def get_gauge_value(self, name: str) -> float:
        """Get gauge value (for non-Prometheus mode)"""
        full_name = f"{self.namespace}_{name}"
        return self._gauges.get(full_name, 0.0)
    
    def export_prometheus(self) -> bytes:
        """Export metrics in Prometheus format"""
        if PROMETHEUS_AVAILABLE and self._prometheus_registry:
            return generate_latest(self._prometheus_registry)
        else:
            # Return simple text format
            lines = []
            for name, value in self._counters.items():
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name} {value}")
            for name, value in self._gauges.items():
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value}")
            return "\n".join(lines).encode()


class PlatformMetrics:
    """Platform-wide metrics"""
    
    def __init__(self, registry: MetricsRegistry = None):
        self.registry = registry or MetricsRegistry()
        self._setup_metrics()
    
    def _setup_metrics(self):
        """Set up all metrics"""
        # Session metrics
        self.registry.counter(
            "sessions_created_total",
            "Total number of sessions created",
            ["type", "tier"]
        )
        
        self.registry.counter(
            "sessions_destroyed_total",
            "Total number of sessions destroyed",
            ["type", "reason"]
        )
        
        self.registry.counter(
            "sessions_failed_total",
            "Total number of failed sessions",
            ["type", "error"]
        )
        
        self.registry.gauge(
            "sessions_active",
            "Number of active sessions",
            ["type"]
        )
        
        self.registry.histogram(
            "session_duration_seconds",
            "Duration of sessions in seconds",
            ["type"]
        )
        
        # Pod metrics
        self.registry.counter(
            "pods_created_total",
            "Total number of pods created",
            ["pod_type"]
        )
        
        self.registry.counter(
            "pods_destroyed_total",
            "Total number of pods destroyed"
        )
        
        self.registry.gauge(
            "pods_active",
            "Number of active pods",
            ["node_id"]
        )
        
        self.registry.histogram(
            "pod_startup_seconds",
            "Time to start a pod in seconds",
            ["pod_type"]
        )
        
        # Scheduler metrics
        self.registry.counter(
            "scheduling_requests_total",
            "Total scheduling requests",
            ["result"]
        )
        
        self.registry.histogram(
            "scheduling_duration_seconds",
            "Time to schedule a pod in seconds"
        )
        
        # GPU metrics
        self.registry.gauge(
            "gpu_available",
            "Number of available GPUs",
            ["node_id", "gpu_type"]
        )
        
        self.registry.gauge(
            "gpu_vram_available_bytes",
            "Available GPU VRAM in bytes",
            ["node_id", "gpu_id"]
        )
        
        self.registry.gauge(
            "gpu_utilization",
            "GPU utilization percentage",
            ["node_id", "gpu_id"]
        )
        
        # API metrics
        self.registry.counter(
            "api_requests_total",
            "Total API requests",
            ["method", "endpoint", "status"]
        )
        
        self.registry.histogram(
            "api_request_duration_seconds",
            "API request duration in seconds",
            ["method", "endpoint"]
        )
        
        # Streaming metrics
        self.registry.gauge(
            "streaming_sessions_active",
            "Number of active streaming sessions"
        )
        
        self.registry.histogram(
            "streaming_latency_seconds",
            "Streaming latency in seconds"
        )
        
        self.registry.counter(
            "streaming_errors_total",
            "Total streaming errors",
            ["error_type"]
        )
    
    # Session methods
    def record_session_created(self, session_type: str, tier: str = "free"):
        self.registry.increment("sessions_created_total", labels={"type": session_type, "tier": tier})
    
    def record_session_destroyed(self, session_type: str, reason: str = "expired"):
        self.registry.increment("sessions_destroyed_total", labels={"type": session_type, "reason": reason})
    
    def record_session_failed(self, session_type: str, error: str):
        self.registry.increment("sessions_failed_total", labels={"type": session_type, "error": error})
    
    def set_active_sessions(self, count: int, session_type: str = "all"):
        self.registry.set_gauge("sessions_active", count, labels={"type": session_type})
    
    def record_session_duration(self, duration_seconds: float, session_type: str):
        self.registry.observe("session_duration_seconds", duration_seconds, labels={"type": session_type})
    
    # Pod methods
    def record_pod_created(self, pod_type: str):
        self.registry.increment("pods_created_total", labels={"pod_type": pod_type})
    
    def record_pod_destroyed(self):
        self.registry.increment("pods_destroyed_total")
    
    def set_active_pods(self, count: int, node_id: str = "all"):
        self.registry.set_gauge("pods_active", count, labels={"node_id": node_id})
    
    def record_pod_startup(self, startup_seconds: float, pod_type: str):
        self.registry.observe("pod_startup_seconds", startup_seconds, labels={"pod_type": pod_type})
    
    # Scheduler methods
    def record_scheduling_result(self, result: str):  # success, failed, preempted
        self.registry.increment("scheduling_requests_total", labels={"result": result})
    
    def record_scheduling_duration(self, duration_seconds: float):
        self.registry.observe("scheduling_duration_seconds", duration_seconds)
    
    # GPU methods
    def set_gpu_available(self, count: int, node_id: str, gpu_type: str):
        self.registry.set_gauge("gpu_available", count, labels={"node_id": node_id, "gpu_type": gpu_type})
    
    def set_gpu_vram_available(self, bytes_available: int, node_id: str, gpu_id: str):
        self.registry.set_gauge("gpu_vram_available_bytes", bytes_available, 
                               labels={"node_id": node_id, "gpu_id": gpu_id})
    
    def set_gpu_utilization(self, utilization: float, node_id: str, gpu_id: str):
        self.registry.set_gauge("gpu_utilization", utilization, 
                               labels={"node_id": node_id, "gpu_id": gpu_id})
    
    # API methods
    @contextmanager
    def track_api_request(self, method: str, endpoint: str):
        """Context manager to track API request duration"""
        start = time.time()
        status = "500"
        try:
            yield lambda s: setattr(self, '_status', s) or setattr(self.__class__, '_status', s)  # Allow setting status
            status = getattr(self, '_status', '200')
        except Exception:
            status = "500"
            raise
        finally:
            duration = time.time() - start
            self.registry.increment("api_requests_total", 
                                   labels={"method": method, "endpoint": endpoint, "status": status})
            self.registry.observe("api_request_duration_seconds", duration,
                                 labels={"method": method, "endpoint": endpoint})
    
    # Streaming methods
    def set_active_streaming_sessions(self, count: int):
        self.registry.set_gauge("streaming_sessions_active", count)
    
    def record_streaming_latency(self, latency_seconds: float):
        self.registry.observe("streaming_latency_seconds", latency_seconds)
    
    def record_streaming_error(self, error_type: str):
        self.registry.increment("streaming_errors_total", labels={"error_type": error_type})


class HealthChecker:
    """Health check aggregator"""
    
    def __init__(self):
        self._checks: Dict[str, callable] = {}
    
    def register(self, name: str, check_func: callable):
        """Register a health check"""
        self._checks[name] = check_func
    
    async def run_checks(self) -> Dict[str, Any]:
        """Run all health checks"""
        results = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }
        
        for name, check_func in self._checks.items():
            try:
                if hasattr(check_func, '__call__'):
                    import asyncio
                    if asyncio.iscoroutinefunction(check_func):
                        check_result = await check_func()
                    else:
                        check_result = check_func()
                else:
                    check_result = {"status": "unknown"}
                
                results["checks"][name] = check_result
                
                if check_result.get("status") != "healthy":
                    results["status"] = "degraded"
            except Exception as e:
                results["checks"][name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
                results["status"] = "unhealthy"
        
        return results


# Global metrics instance
_metrics: Optional[PlatformMetrics] = None
_health_checker: Optional[HealthChecker] = None


def get_metrics() -> PlatformMetrics:
    """Get the global metrics instance"""
    global _metrics
    if _metrics is None:
        _metrics = PlatformMetrics()
    return _metrics


def get_health_checker() -> HealthChecker:
    """Get the global health checker instance"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker
