import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import psutil
from prometheus_client import Counter, Gauge, Histogram, start_http_server
import threading

from ..types.config import settings
from ..orchestrator.orchestrator import PodOrchestrator
from ..scheduler.scheduler import Scheduler


# Prometheus metrics
# Pod metrics
pods_total = Gauge('disposable_compute_pods_total', 'Total number of pods', ['status'])
pods_created = Counter('disposable_compute_pods_created_total', 'Total pods created')
pods_terminated = Counter('disposable_compute_pods_terminated_total', 'Total pods terminated')

# Resource metrics
cpu_usage = Gauge('disposable_compute_cpu_usage_percent', 'CPU usage percentage')
memory_usage = Gauge('disposable_compute_memory_usage_percent', 'Memory usage percentage')
disk_usage = Gauge('disposable_compute_disk_usage_percent', 'Disk usage percentage')

# Request metrics
request_duration = Histogram('disposable_compute_request_duration_seconds', 'Request duration in seconds')
api_requests = Counter('disposable_compute_api_requests_total', 'Total API requests', ['endpoint', 'method'])


class MonitoringService:
    """Service for monitoring platform health and performance"""
    
    def __init__(self, orchestrator: PodOrchestrator, scheduler: Scheduler):
        self.orchestrator = orchestrator
        self.scheduler = scheduler
        self.running = False
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Initialize metrics
        self._initialize_metrics()
    
    def _initialize_metrics(self):
        """Initialize Prometheus metrics"""
        # Initialize pod counts
        for status in ['REQUESTED', 'SCHEDULING', 'SCHEDULED', 'PROVISIONING', 'STARTING', 'STREAMING', 'TERMINATING', 'TERMINATED', 'FAILED', 'CANCELLED']:
            pods_total.labels(status=status).set(0)
    
    def start_monitoring(self, port: int = 9090):
        """Start the monitoring service"""
        # Start Prometheus metrics server in a separate thread
        def run_metrics_server():
            start_http_server(port)
        
        thread = threading.Thread(target=run_metrics_server, daemon=True)
        thread.start()
        
        # Start internal monitoring loop
        self.running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        logging.info(f"Monitoring service started on port {port}")
    
    def stop_monitoring(self):
        """Stop the monitoring service"""
        self.running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
        
        logging.info("Monitoring service stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                # Update system metrics
                await self._update_system_metrics()
                
                # Update pod metrics
                await self._update_pod_metrics()
                
                # Update scheduler metrics
                await self._update_scheduler_metrics()
                
                # Wait before next update
                await asyncio.sleep(settings.gpu_monitoring_interval)
                
            except Exception as e:
                logging.error(f"Error in monitoring loop: {e}")
    
    async def _update_system_metrics(self):
        """Update system resource metrics"""
        try:
            # CPU usage - run blocking call in thread pool
            loop = asyncio.get_event_loop()
            cpu_percent = await loop.run_in_executor(None, lambda: psutil.cpu_percent(interval=1))
            cpu_usage.set(cpu_percent)

            # Memory usage
            memory = psutil.virtual_memory()
            memory_usage.set(memory.percent)

            # Disk usage
            disk = psutil.disk_usage('/')
            disk_usage.set(disk.percent)

        except Exception as e:
            logging.error(f"Error updating system metrics: {e}")
    
    async def _update_pod_metrics(self):
        """Update pod-related metrics"""
        try:
            # Count pods by status
            status_counts: Dict[str, int] = {}
            for pod_state in self.orchestrator.pods.values():
                status = pod_state.status.value if hasattr(pod_state.status, 'value') else str(pod_state.status)
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Update metrics
            for status, count in status_counts.items():
                pods_total.labels(status=status).set(count)
        
        except Exception as e:
            logging.error(f"Error updating pod metrics: {e}")
    
    async def _update_scheduler_metrics(self):
        """Update scheduler-related metrics"""
        try:
            # Update metrics about nodes and resources
            nodes = self.scheduler.resource_pool.get_all_nodes()
            
            total_cpu = sum(node.cpu_total for node in nodes)
            available_cpu = sum(node.cpu_available for node in nodes)
            cpu_utilization = (total_cpu - available_cpu) / total_cpu if total_cpu > 0 else 0
            
            total_memory = sum(node.memory_total_gb for node in nodes)
            available_memory = sum(node.memory_available_gb for node in nodes)
            memory_utilization = (total_memory - available_memory) / total_memory if total_memory > 0 else 0
            
            total_vram = sum(node.gpu_vram_total_gb for node in nodes)
            available_vram = sum(node.gpu_vram_available_gb for node in nodes)
            vram_utilization = (total_vram - available_vram) / total_vram if total_vram > 0 else 0
            
            # In a real implementation, you would create custom metrics for these
            logging.debug(f"Scheduler utilization - CPU: {cpu_utilization:.2%}, Memory: {memory_utilization:.2%}, VRAM: {vram_utilization:.2%}")
        
        except Exception as e:
            logging.error(f"Error updating scheduler metrics: {e}")
    
    def record_api_request(self, endpoint: str, method: str, duration: float):
        """Record an API request"""
        api_requests.labels(endpoint=endpoint, method=method).inc()
        request_duration.observe(duration)
    
    def record_pod_created(self):
        """Record a pod creation"""
        pods_created.inc()
    
    def record_pod_terminated(self):
        """Record a pod termination"""
        pods_terminated.inc()

    async def get_health_status(self) -> Dict[str, Any]:
        """Get overall health status of the platform"""
        try:
            # System health - run blocking calls in thread pool
            loop = asyncio.get_event_loop()
            cpu_percent = await loop.run_in_executor(None, lambda: psutil.cpu_percent(interval=1))
            memory = await loop.run_in_executor(None, psutil.virtual_memory)
            disk = await loop.run_in_executor(None, psutil.disk_usage, '/')

            # Service health
            orchestrator_healthy = True  # Placeholder
            scheduler_healthy = True  # Placeholder
            storage_healthy = True  # Placeholder

            # Pod health
            total_pods = len(self.orchestrator.pods)
            active_pods = len([p for p in self.orchestrator.pods.values()
                              if p.status.value in ['starting', 'running']])

            health_status = {
                "timestamp": datetime.now().isoformat(),
                "system": {
                    "cpu_usage_percent": cpu_percent,
                    "memory_usage_percent": memory.percent,
                    "disk_usage_percent": disk.percent,
                    "healthy": cpu_percent < 80 and memory.percent < 80 and disk.percent < 80
                },
                "services": {
                    "orchestrator": orchestrator_healthy,
                    "scheduler": scheduler_healthy,
                    "storage": storage_healthy,
                    "healthy": all([orchestrator_healthy, scheduler_healthy, storage_healthy])
                },
                "pods": {
                    "total": total_pods,
                    "active": active_pods,
                    "healthy": total_pods >= 0  # Placeholder
                },
                "overall_healthy": True  # Placeholder
            }

            return health_status

        except Exception as e:
            logging.error(f"Error getting health status: {e}")
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "overall_healthy": False
            }