"""
Resource optimization module for disposable compute platform
"""
import asyncio
import heapq
import statistics
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import logging
import psutil


@dataclass
class ResourcePrediction:
    """Predicted resource usage for a pod"""
    cpu_percent: float
    memory_mb: int
    disk_gb: float
    network_mbps: float
    prediction_timestamp: datetime
    confidence: float  # 0.0 to 1.0


@dataclass
class ResourceQuota:
    """Resource quota for a user or organization"""
    user_id: str
    max_cpu_cores: float
    max_memory_mb: int
    max_storage_gb: int
    max_gpus: int
    used_cpu_cores: float = 0.0
    used_memory_mb: int = 0
    used_storage_gb: int = 0
    used_gpus: int = 0
    period_start: datetime = None
    
    def __post_init__(self):
        if self.period_start is None:
            self.period_start = datetime.now()


@dataclass
class OptimizationRecommendation:
    """Recommendation for resource optimization"""
    pod_id: str
    recommendation_type: str  # resize, reschedule, etc.
    current_resources: Dict[str, Any]
    recommended_resources: Dict[str, Any]
    expected_benefit: float  # Expected improvement (0.0 to 1.0)
    confidence: float  # Confidence in recommendation (0.0 to 1.0)


class ResourcePredictor:
    """Predicts future resource usage based on historical data"""
    
    def __init__(self):
        self.historical_data: Dict[str, List[Tuple[datetime, Dict[str, float]]]] = {}
        self.logger = logging.getLogger(__name__)
    
    def record_usage(self, pod_id: str, usage: Dict[str, float], timestamp: datetime = None):
        """Record resource usage for a pod"""
        if timestamp is None:
            timestamp = datetime.now()
        
        if pod_id not in self.historical_data:
            self.historical_data[pod_id] = []
        
        self.historical_data[pod_id].append((timestamp, usage))
        
        # Keep only the last 1000 data points to prevent memory issues
        if len(self.historical_data[pod_id]) > 1000:
            self.historical_data[pod_id] = self.historical_data[pod_id][-1000:]
    
    def predict_usage(self, pod_id: str, look_ahead_minutes: int = 15) -> Optional[ResourcePrediction]:
        """Predict resource usage for a pod"""
        if pod_id not in self.historical_data or len(self.historical_data[pod_id]) < 2:
            return None
        
        # Get historical data for this pod
        data = self.historical_data[pod_id]
        
        # Calculate average usage
        cpu_values = [d[1].get('cpu_percent', 0) for d in data]
        memory_values = [d[1].get('memory_mb', 0) for d in data]
        disk_values = [d[1].get('disk_gb', 0) for d in data]
        network_values = [d[1].get('network_mbps', 0) for d in data]
        
        # Use the most recent values as the prediction (simple approach)
        # In a real implementation, this would use more sophisticated ML models
        predicted_cpu = statistics.mean(cpu_values[-5:]) if cpu_values else 0
        predicted_memory = statistics.mean(memory_values[-5:]) if memory_values else 0
        predicted_disk = statistics.mean(disk_values[-5:]) if disk_values else 0
        predicted_network = statistics.mean(network_values[-5:]) if network_values else 0
        
        # Calculate confidence based on data availability and consistency
        cpu_stdev = statistics.stdev(cpu_values) if len(cpu_values) > 1 else 0
        confidence = max(0.0, 1.0 - (cpu_stdev / max(predicted_cpu, 1)))
        
        return ResourcePrediction(
            cpu_percent=predicted_cpu,
            memory_mb=int(predicted_memory),
            disk_gb=predicted_disk,
            network_mbps=predicted_network,
            prediction_timestamp=datetime.now() + timedelta(minutes=look_ahead_minutes),
            confidence=min(1.0, confidence)
        )


class QuotaManager:
    """Manages resource quotas for users and organizations"""
    
    def __init__(self):
        self.quotas: Dict[str, ResourceQuota] = {}
        self.logger = logging.getLogger(__name__)
    
    def set_quota(self, user_id: str, max_cpu_cores: float, max_memory_mb: int, 
                  max_storage_gb: int, max_gpus: int):
        """Set resource quota for a user"""
        self.quotas[user_id] = ResourceQuota(
            user_id=user_id,
            max_cpu_cores=max_cpu_cores,
            max_memory_mb=max_memory_mb,
            max_storage_gb=max_storage_gb,
            max_gpus=max_gpus
        )
        self.logger.info(f"Set quota for user {user_id}")
    
    def get_quota(self, user_id: str) -> Optional[ResourceQuota]:
        """Get resource quota for a user"""
        return self.quotas.get(user_id)
    
    def check_quota(self, user_id: str, requested_resources: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Check if requested resources are within quota"""
        quota = self.quotas.get(user_id)
        if not quota:
            return True, []  # No quota set, allow request
        
        violations = []
        
        # Check CPU
        cpu_requested = requested_resources.get('cpu_cores', 0)
        if quota.used_cpu_cores + cpu_requested > quota.max_cpu_cores:
            violations.append(f"CPU quota exceeded: {quota.used_cpu_cores + cpu_requested}/{quota.max_cpu_cores}")
        
        # Check memory
        memory_requested = requested_resources.get('memory_mb', 0)
        if quota.used_memory_mb + memory_requested > quota.max_memory_mb:
            violations.append(f"Memory quota exceeded: {quota.used_memory_mb + memory_requested}/{quota.max_memory_mb}")
        
        # Check storage
        storage_requested = requested_resources.get('storage_gb', 0)
        if quota.used_storage_gb + storage_requested > quota.max_storage_gb:
            violations.append(f"Storage quota exceeded: {quota.used_storage_gb + storage_requested}/{quota.max_storage_gb}")
        
        # Check GPUs
        gpu_requested = requested_resources.get('gpu_count', 0)
        if quota.used_gpus + gpu_requested > quota.max_gpus:
            violations.append(f"GPU quota exceeded: {quota.used_gpus + gpu_requested}/{quota.max_gpus}")
        
        return len(violations) == 0, violations
    
    def allocate_resources(self, user_id: str, resources: Dict[str, Any]) -> bool:
        """Allocate resources to a user's quota"""
        quota = self.quotas.get(user_id)
        if not quota:
            return True  # No quota to enforce
        
        # Check if allocation would exceed quota
        can_allocate, violations = self.check_quota(user_id, resources)
        if not can_allocate:
            self.logger.warning(f"Resource allocation denied for {user_id}: {violations}")
            return False
        
        # Update used resources
        quota.used_cpu_cores += resources.get('cpu_cores', 0)
        quota.used_memory_mb += resources.get('memory_mb', 0)
        quota.used_storage_gb += resources.get('storage_gb', 0)
        quota.used_gpus += resources.get('gpu_count', 0)
        
        self.logger.info(f"Allocated resources for user {user_id}: {resources}")
        return True
    
    def release_resources(self, user_id: str, resources: Dict[str, Any]):
        """Release resources from a user's quota"""
        quota = self.quotas.get(user_id)
        if not quota:
            return
        
        # Update used resources (with floor at 0)
        quota.used_cpu_cores = max(0, quota.used_cpu_cores - resources.get('cpu_cores', 0))
        quota.used_memory_mb = max(0, quota.used_memory_mb - resources.get('memory_mb', 0))
        quota.used_storage_gb = max(0, quota.used_storage_gb - resources.get('storage_gb', 0))
        quota.used_gpus = max(0, quota.used_gpus - resources.get('gpu_count', 0))
        
        self.logger.info(f"Released resources for user {user_id}: {resources}")


class AutoScaler:
    """Automatically scales resources based on usage"""
    
    def __init__(self, resource_predictor: ResourcePredictor):
        self.resource_predictor = resource_predictor
        self.scaling_policies = {}
        self.logger = logging.getLogger(__name__)
    
    def set_scaling_policy(self, pod_id: str, min_resources: Dict[str, Any], 
                          max_resources: Dict[str, Any], target_utilization: float = 0.7):
        """Set scaling policy for a pod"""
        self.scaling_policies[pod_id] = {
            'min_resources': min_resources,
            'max_resources': max_resources,
            'target_utilization': target_utilization
        }
        self.logger.info(f"Set scaling policy for pod {pod_id}")
    
    async def evaluate_scaling(self, pod_id: str, current_usage: Dict[str, float]) -> Optional[Dict[str, Any]]:
        """Evaluate if scaling is needed for a pod"""
        if pod_id not in self.scaling_policies:
            return None
        
        policy = self.scaling_policies[pod_id]
        
        # Get predicted usage
        prediction = self.resource_predictor.predict_usage(pod_id)
        if not prediction:
            return None
        
        # Calculate if scaling is needed
        cpu_utilization = current_usage.get('cpu_percent', 0) / 100.0
        memory_utilization = current_usage.get('memory_used_mb', 0) / max(current_usage.get('memory_total_mb', 1), 1)
        
        # Use the higher of CPU or memory utilization for scaling decision
        current_utilization = max(cpu_utilization, memory_utilization)
        
        # Calculate scaling factor
        if current_utilization > policy['target_utilization'] * 1.2:  # Scale up if utilization is 20% above target
            # Scale up
            scale_factor = min(1.5, current_utilization / policy['target_utilization'])  # Max 1.5x scale up
            return self._calculate_scaled_resources(policy['max_resources'], scale_factor)
        elif current_utilization < policy['target_utilization'] * 0.8:  # Scale down if utilization is 20% below target
            # Scale down
            scale_factor = max(0.5, current_utilization / policy['target_utilization'])  # Min 0.5x scale down
            return self._calculate_scaled_resources(policy['min_resources'], scale_factor)
        
        return None  # No scaling needed
    
    def _calculate_scaled_resources(self, base_resources: Dict[str, Any], scale_factor: float) -> Dict[str, Any]:
        """Calculate scaled resources based on a scale factor"""
        scaled = {}
        for key, value in base_resources.items():
            if isinstance(value, (int, float)):
                scaled[key] = int(value * scale_factor) if isinstance(value, int) else value * scale_factor
            else:
                scaled[key] = value  # Keep non-numeric values as is
        return scaled


class CostOptimizer:
    """Optimizes resource allocation to minimize cost"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.pricing = {
            'cpu_hour': 0.02,  # $0.02 per CPU core per hour
            'memory_hour': 0.004,  # $0.004 per GB memory per hour
            'storage_hour': 0.001,  # $0.001 per GB storage per hour
            'gpu_hour': 0.5  # $0.50 per GPU per hour
        }
    
    def calculate_pod_cost(self, pod_resources: Dict[str, Any], duration_hours: float) -> float:
        """Calculate the cost of running a pod for a given duration"""
        cost = 0.0
        
        # CPU cost
        cpu_cores = pod_resources.get('cpu_cores', 0)
        cost += cpu_cores * self.pricing['cpu_hour'] * duration_hours
        
        # Memory cost
        memory_gb = pod_resources.get('memory_mb', 0) / 1024.0
        cost += memory_gb * self.pricing['memory_hour'] * duration_hours
        
        # Storage cost
        storage_gb = pod_resources.get('storage_gb', 0)
        cost += storage_gb * self.pricing['storage_hour'] * duration_hours
        
        # GPU cost
        gpu_count = pod_resources.get('gpu_count', 0)
        cost += gpu_count * self.pricing['gpu_hour'] * duration_hours
        
        return cost
    
    def optimize_resources(self, pod_id: str, current_resources: Dict[str, Any], 
                          performance_requirements: Dict[str, Any]) -> OptimizationRecommendation:
        """Optimize resources for cost while meeting performance requirements"""
        # This is a simplified optimization algorithm
        # In a real implementation, this would use more sophisticated techniques
        
        # Start with current resources
        recommended_resources = current_resources.copy()
        
        # Try to reduce resources while meeting performance requirements
        # For example, if CPU usage is consistently low, reduce CPU allocation
        expected_benefit = 0.1  # 10% cost savings
        confidence = 0.8  # 80% confidence in recommendation
        
        return OptimizationRecommendation(
            pod_id=pod_id,
            recommendation_type="resize",
            current_resources=current_resources,
            recommended_resources=recommended_resources,
            expected_benefit=expected_benefit,
            confidence=confidence
        )


class ResourceManager:
    """Main resource manager that coordinates optimization activities"""
    
    def __init__(self):
        self.resource_predictor = ResourcePredictor()
        self.quota_manager = QuotaManager()
        self.auto_scaler = AutoScaler(self.resource_predictor)
        self.cost_optimizer = CostOptimizer()
        self.logger = logging.getLogger(__name__)
        
        # Set default quotas for demonstration
        self.quota_manager.set_quota(
            user_id="default",
            max_cpu_cores=16.0,
            max_memory_mb=32768,  # 32 GB
            max_storage_gb=500,
            max_gpus=4
        )
    
    def record_resource_usage(self, pod_id: str, usage: Dict[str, float]):
        """Record resource usage for optimization"""
        self.resource_predictor.record_usage(pod_id, usage)
    
    def check_quota(self, user_id: str, requested_resources: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Check if requested resources are within quota"""
        return self.quota_manager.check_quota(user_id, requested_resources)
    
    def allocate_resources(self, user_id: str, resources: Dict[str, Any]) -> bool:
        """Allocate resources to a user"""
        return self.quota_manager.allocate_resources(user_id, resources)
    
    def release_resources(self, user_id: str, resources: Dict[str, Any]):
        """Release resources from a user"""
        self.quota_manager.release_resources(user_id, resources)
    
    async def evaluate_scaling(self, pod_id: str, current_usage: Dict[str, float]) -> Optional[Dict[str, Any]]:
        """Evaluate if scaling is needed for a pod"""
        return await self.auto_scaler.evaluate_scaling(pod_id, current_usage)
    
    def set_scaling_policy(self, pod_id: str, min_resources: Dict[str, Any], 
                          max_resources: Dict[str, Any], target_utilization: float = 0.7):
        """Set scaling policy for a pod"""
        self.auto_scaler.set_scaling_policy(pod_id, min_resources, max_resources, target_utilization)
    
    def calculate_pod_cost(self, pod_resources: Dict[str, Any], duration_hours: float) -> float:
        """Calculate the cost of running a pod"""
        return self.cost_optimizer.calculate_pod_cost(pod_resources, duration_hours)
    
    def optimize_resources(self, pod_id: str, current_resources: Dict[str, Any], 
                          performance_requirements: Dict[str, Any]) -> OptimizationRecommendation:
        """Optimize resources for a pod"""
        return self.cost_optimizer.optimize_resources(pod_id, current_resources, performance_requirements)
    
    def get_system_resource_usage(self) -> Dict[str, Any]:
        """Get overall system resource usage"""
        # Get system-level resource usage
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'cpu_percent': cpu_percent,
            'memory_used_mb': memory.used // (1024 * 1024),
            'memory_total_mb': memory.total // (1024 * 1024),
            'memory_percent': memory.percent,
            'disk_used_gb': disk.used / (1024**3),
            'disk_total_gb': disk.total / (1024**3),
            'disk_percent': disk.percent
        }