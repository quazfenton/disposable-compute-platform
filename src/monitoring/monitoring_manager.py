"""
Monitoring and observability module for disposable compute platform
"""
import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import logging
from dataclasses import dataclass
import psutil
import GPUtil
from prometheus_client import Counter, Histogram, Gauge, Summary, start_http_server
from contextlib import asynccontextmanager

from src.models.pod import Pod
from src.models.session import Session
from src.types.platform_types import HealthStatusDTO


@dataclass
class Metric:
    """Represents a single metric"""
    name: str
    value: float
    labels: Dict[str, str]
    timestamp: datetime


@dataclass
class ResourceUsage:
    """Resource usage for a pod or system"""
    cpu_percent: float
    memory_mb_used: int
    memory_mb_total: int
    disk_gb_used: float
    disk_gb_total: float
    network_rx_bytes: int
    network_tx_bytes: int
    gpu_utilization: Optional[float] = None
    gpu_memory_used_mb: Optional[int] = None
    gpu_memory_total_mb: Optional[int] = None


class MetricsCollector:
    """Collects and exports metrics for the platform"""
    
    def __init__(self, port: int = 8001):
        self.port = port
        self.metrics: Dict[str, Any] = {}
        self.logger = logging.getLogger(__name__)
        
        # Prometheus metrics
        self.request_count = Counter(
            'dcp_requests_total', 
            'Total requests', 
            ['method', 'endpoint']
        )
        
        self.request_duration = Histogram(
            'dcp_request_duration_seconds', 
            'Request duration in seconds',
            ['method', 'endpoint']
        )
        
        self.active_sessions = Gauge(
            'dcp_active_sessions', 
            'Number of active sessions'
        )
        
        self.active_pods = Gauge(
            'dcp_active_pods',
            'Number of active pods'
        )
        
        self.cpu_usage = Gauge(
            'dcp_cpu_usage_percent',
            'CPU usage percentage',
            ['node_id']
        )
        
        self.memory_usage = Gauge(
            'dcp_memory_usage_bytes',
            'Memory usage in bytes',
            ['node_id']
        )
        
        self.gpu_utilization = Gauge(
            'dcp_gpu_utilization_percent',
            'GPU utilization percentage',
            ['gpu_id']
        )
        
        self.pod_resource_usage = Summary(
            'dcp_pod_resource_usage',
            'Resource usage per pod',
            ['pod_id', 'resource_type']
        )
    
    def start_server(self):
        """Start the metrics server"""
        start_http_server(self.port)
        self.logger.info(f"Metrics server started on port {self.port}")
    
    def increment_request_count(self, method: str, endpoint: str):
        """Increment request counter"""
        self.request_count.labels(method=method, endpoint=endpoint).inc()
    
    def record_request_duration(self, method: str, endpoint: str, duration: float):
        """Record request duration"""
        self.request_duration.labels(method=method, endpoint=endpoint).observe(duration)
    
    def set_active_sessions(self, count: int):
        """Set the number of active sessions"""
        self.active_sessions.set(count)
    
    def set_active_pods(self, count: int):
        """Set the number of active pods"""
        self.active_pods.set(count)
    
    def set_cpu_usage(self, node_id: str, usage: float):
        """Set CPU usage for a node"""
        self.cpu_usage.labels(node_id=node_id).set(usage)
    
    def set_memory_usage(self, node_id: str, usage_bytes: int):
        """Set memory usage for a node"""
        self.memory_usage.labels(node_id=node_id).set(usage_bytes)
    
    def set_gpu_utilization(self, gpu_id: str, utilization: float):
        """Set GPU utilization"""
        self.gpu_utilization.labels(gpu_id=gpu_id).set(utilization)
    
    def record_pod_resource_usage(self, pod_id: str, resource_type: str, value: float):
        """Record resource usage for a pod"""
        self.pod_resource_usage.labels(pod_id=pod_id, resource_type=resource_type).observe(value)


class ResourceMonitor:
    """Monitors resource usage for pods and the system"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.logger = logging.getLogger(__name__)
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
    
    async def start_monitoring_pod(self, pod: Pod):
        """Start monitoring a pod's resource usage"""
        if pod.id in self.monitoring_tasks:
            self.logger.warning(f"Monitoring already active for pod {pod.id}")
            return
        
        task = asyncio.create_task(self._monitor_pod_resources(pod))
        self.monitoring_tasks[pod.id] = task
        self.logger.info(f"Started monitoring for pod {pod.id}")
    
    async def stop_monitoring_pod(self, pod_id: str):
        """Stop monitoring a pod's resource usage"""
        if pod_id in self.monitoring_tasks:
            task = self.monitoring_tasks[pod_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.monitoring_tasks[pod_id]
            self.logger.info(f"Stopped monitoring for pod {pod_id}")
    
    async def _monitor_pod_resources(self, pod: Pod):
        """Monitor resource usage for a single pod"""
        while True:
            try:
                usage = await self.get_pod_resource_usage(pod)
                
                # Record metrics
                if usage:
                    self.metrics_collector.record_pod_resource_usage(
                        pod.id, 'cpu_percent', usage.cpu_percent
                    )
                    self.metrics_collector.record_pod_resource_usage(
                        pod.id, 'memory_mb_used', usage.memory_mb_used
                    )
                    
                    if usage.gpu_utilization is not None:
                        self.metrics_collector.record_pod_resource_usage(
                            pod.id, 'gpu_utilization', usage.gpu_utilization
                        )
                
                # Wait before next measurement
                await asyncio.sleep(5)  # Monitor every 5 seconds
                
            except asyncio.CancelledError:
                self.logger.info(f"Monitoring cancelled for pod {pod.id}")
                break
            except Exception as e:
                self.logger.error(f"Error monitoring pod {pod.id}: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def get_pod_resource_usage(self, pod: Pod) -> Optional[ResourceUsage]:
        """Get resource usage for a pod"""
        # This is a simplified implementation
        # In a real system, this would interface with container runtime or hypervisor
        
        try:
            # Get system-level resource usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # For GPU usage, use GPUtil if available
            gpu_utilization = None
            gpu_memory_used_mb = None
            gpu_memory_total_mb = None
            
            gpus = GPUtil.getGPUs()
            if gpus:
                # For simplicity, return stats for the first GPU
                gpu = gpus[0]
                gpu_utilization = gpu.load * 100
                gpu_memory_used_mb = gpu.memoryUsed
                gpu_memory_total_mb = gpu.memoryTotal
            
            # Calculate disk usage (simplified)
            disk_usage = psutil.disk_usage('/')
            disk_gb_used = disk_usage.used / (1024**3)
            disk_gb_total = disk_usage.total / (1024**3)
            
            # Calculate network usage (simplified)
            net_io = psutil.net_io_counters()
            network_rx_bytes = net_io.bytes_recv
            network_tx_bytes = net_io.bytes_sent
            
            return ResourceUsage(
                cpu_percent=cpu_percent,
                memory_mb_used=memory.used // (1024 * 1024),
                memory_mb_total=memory.total // (1024 * 1024),
                disk_gb_used=disk_gb_used,
                disk_gb_total=disk_gb_total,
                network_rx_bytes=network_rx_bytes,
                network_tx_bytes=network_tx_bytes,
                gpu_utilization=gpu_utilization,
                gpu_memory_used_mb=gpu_memory_used_mb,
                gpu_memory_total_mb=gpu_memory_total_mb
            )
        except Exception as e:
            self.logger.error(f"Error getting resource usage for pod {pod.id}: {e}")
            return None
    
    async def get_system_resource_usage(self) -> ResourceUsage:
        """Get overall system resource usage"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # For GPU usage
        gpu_utilization = None
        gpu_memory_used_mb = None
        gpu_memory_total_mb = None
        
        gpus = GPUtil.getGPUs()
        if gpus:
            # Average across all GPUs
            total_load = sum(gpu.load for gpu in gpus)
            total_memory_used = sum(gpu.memoryUsed for gpu in gpus)
            total_memory_total = sum(gpu.memoryTotal for gpu in gpus)
            
            gpu_utilization = (total_load / len(gpus)) * 100
            gpu_memory_used_mb = total_memory_used
            gpu_memory_total_mb = total_memory_total
        
        # Calculate disk usage
        disk_usage = psutil.disk_usage('/')
        disk_gb_used = disk_usage.used / (1024**3)
        disk_gb_total = disk_usage.total / (1024**3)
        
        # Calculate network usage
        net_io = psutil.net_io_counters()
        network_rx_bytes = net_io.bytes_recv
        network_tx_bytes = net_io.bytes_sent
        
        return ResourceUsage(
            cpu_percent=cpu_percent,
            memory_mb_used=memory.used // (1024 * 1024),
            memory_mb_total=memory.total // (1024 * 1024),
            disk_gb_used=disk_gb_used,
            disk_gb_total=disk_gb_total,
            network_rx_bytes=network_rx_bytes,
            network_tx_bytes=network_tx_bytes,
            gpu_utilization=gpu_utilization,
            gpu_memory_used_mb=gpu_memory_used_mb,
            gpu_memory_total_mb=gpu_memory_total_mb
        )


class HealthChecker:
    """Performs health checks on the platform components"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.checks: Dict[str, Callable] = {}
    
    def register_check(self, name: str, check_func: Callable):
        """Register a health check function"""
        self.checks[name] = check_func
    
    async def run_all_checks(self) -> Dict[str, HealthStatusDTO]:
        """Run all registered health checks"""
        results = {}
        
        for name, check_func in self.checks.items():
            try:
                result = await check_func() if asyncio.iscoroutinefunction(check_func) else check_func()
                status = "healthy" if result else "unhealthy"
                details = result if isinstance(result, dict) else {}
            except Exception as e:
                status = "error"
                details = {"error": str(e)}
            
            results[name] = HealthStatusDTO(
                service=name,
                status=status,
                timestamp=datetime.now(),
                details=details
            )
        
        return results
    
    async def check_system_health(self) -> bool:
        """Check overall system health"""
        try:
            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 90:
                return {"status": "warning", "cpu_percent": cpu_percent, "message": "High CPU usage"}
            
            # Check memory usage
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                return {"status": "warning", "memory_percent": memory.percent, "message": "High memory usage"}
            
            # Check disk usage
            disk = psutil.disk_usage('/')
            if disk.percent > 90:
                return {"status": "warning", "disk_percent": disk.percent, "message": "High disk usage"}
            
            return {"status": "healthy", "cpu_percent": cpu_percent, "memory_percent": memory.percent}
        except Exception as e:
            self.logger.error(f"Error checking system health: {e}")
            return {"status": "error", "error": str(e)}
    
    async def check_docker_health(self) -> bool:
        """Check Docker daemon health"""
        try:
            import docker
            client = docker.from_env()
            client.ping()  # Check if Docker daemon is responsive
            return {"status": "healthy", "version": client.version()}
        except Exception as e:
            self.logger.error(f"Error checking Docker health: {e}")
            return {"status": "error", "error": str(e)}
    
    async def check_libvirt_health(self) -> bool:
        """Check libvirt daemon health"""
        try:
            import libvirt
            conn = libvirt.open('qemu:///system')
            if conn is None:
                return {"status": "error", "message": "Cannot connect to libvirt"}
            
            # Get basic info to verify connection
            info = conn.getInfo()
            conn.close()
            
            return {
                "status": "healthy", 
                "hypervisor": info[0] if info else "unknown",
                "memory_kb": info[1] if len(info) > 1 else 0
            }
        except Exception as e:
            self.logger.error(f"Error checking libvirt health: {e}")
            return {"status": "error", "error": str(e)}


class MonitoringManager:
    """Main monitoring manager that coordinates all monitoring activities"""
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.resource_monitor = ResourceMonitor(self.metrics_collector)
        self.health_checker = HealthChecker()
        self.logger = logging.getLogger(__name__)
        
        # Register default health checks
        self.health_checker.register_check("system", self.health_checker.check_system_health)
        self.health_checker.register_check("docker", self.health_checker.check_docker_health)
        self.health_checker.register_check("libvirt", self.health_checker.check_libvirt_health)
    
    async def initialize(self):
        """Initialize the monitoring manager"""
        self.metrics_collector.start_server()
        self.logger.info("Monitoring manager initialized")
    
    async def start_pod_monitoring(self, pod: Pod):
        """Start monitoring for a pod"""
        await self.resource_monitor.start_monitoring_pod(pod)
    
    async def stop_pod_monitoring(self, pod_id: str):
        """Stop monitoring for a pod"""
        await self.resource_monitor.stop_monitoring_pod(pod_id)
    
    async def get_platform_health(self) -> Dict[str, HealthStatusDTO]:
        """Get overall platform health"""
        return await self.health_checker.run_all_checks()
    
    async def get_resource_usage(self) -> ResourceUsage:
        """Get overall platform resource usage"""
        return await self.resource_monitor.get_system_resource_usage()
    
    def record_api_call(self, method: str, endpoint: str, duration: float):
        """Record an API call for metrics"""
        self.metrics_collector.increment_request_count(method, endpoint)
        self.metrics_collector.record_request_duration(method, endpoint, duration)
    
    def update_session_count(self, count: int):
        """Update the active session count"""
        self.metrics_collector.set_active_sessions(count)
    
    def update_pod_count(self, count: int):
        """Update the active pod count"""
        self.metrics_collector.set_active_pods(count)