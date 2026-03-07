"""
GPU-aware scheduler for disposable compute platform
Implements production-grade scheduling with resource management,
constraint validation, and priority-based placement.
"""
import logging
import heapq
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import math
import time
import threading

from src.models.pod import PodSpec, GPUResource, ComputeNode
from src.models.gpu import GPUDevice, GPUStatus, GPUFamily



class SchedulingStatus(Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    FAILED = "failed"
    PREEMPTED = "preempted"


class NodeStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    DRAINING = "draining"


@dataclass
class Node:
    """Represents a compute node in the cluster"""
    id: str
    hostname: str
    ip_address: str
    status: NodeStatus
    
    # Resources
    cpu_total: float
    cpu_available: float
    memory_total_mb: int
    memory_available_mb: int
    storage_total_gb: int
    storage_available_gb: int
    
    # GPU info
    gpu_devices: List[GPUDevice] = field(default_factory=list)
    gpu_vram_total_mb: int = 0
    gpu_vram_available_mb: int = 0
    
    # Metrics
    cpu_load_avg: float = 0.0
    gpu_load_avg: float = 0.0
    memory_load_avg: float = 0.0
    temperature_celsius: float = 0.0
    max_safe_temp: float = 85.0
    
    # Capabilities
    capabilities: List[str] = field(default_factory=list)  # gpu, vm, container, windows, linux
    os_type: str = "linux"
    
    # Location
    region: str = "us-east-1"
    availability_zone: str = "us-east-1a"
    latitude: float = 0.0
    longitude: float = 0.0
    
    # Tracking
    assigned_pods: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    
    # Thread safety
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    
    @property
    def resource_lock(self):
        return self._lock
    
    def update_metrics(self, cpu_load: float, memory_load: float, gpu_load: Optional[float] = None, temperature: Optional[float] = None):
        """Update node metrics"""
        with self._lock:
            self.cpu_load_avg = cpu_load
            self.memory_load_avg = memory_load
            if gpu_load is not None:
                self.gpu_load_avg = gpu_load
            if temperature is not None:
                self.temperature_celsius = temperature
            self.last_heartbeat = datetime.now()



@dataclass
class PodRequest:
    """Represents a scheduling request for a pod"""
    id: str
    pod_spec: PodSpec
    user_id: str
    user_tier: str = "free"  # free, pro, enterprise
    priority: int = 50
    created_at: datetime = field(default_factory=datetime.now)
    
    # Constraints
    required_capabilities: List[str] = field(default_factory=list)
    preferred_region: Optional[str] = None
    
    # Scheduling result
    status: SchedulingStatus = SchedulingStatus.PENDING
    assigned_node_id: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    failure_reason: Optional[str] = None


@dataclass
class ScoringWeights:
    """Weights for node scoring"""
    resource: float = 0.4
    load: float = 0.3
    proximity: float = 0.2
    reliability: float = 0.1


class ConstraintValidator:
    """Validates scheduling constraints"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate(self, node: Node, request: PodRequest) -> Tuple[bool, str]:
        """Validate that a node can satisfy all pod constraints"""
        spec = request.pod_spec
        resources = spec.resource_requirements
        
        # Check node status
        if node.status != NodeStatus.ACTIVE:
            return False, f"Node status is {node.status.value}"
        
        # Check required capabilities
        for cap in request.required_capabilities:
            if cap not in node.capabilities:
                return False, f"Node lacks required capability: {cap}"
        
        # Check GPU requirements
        if spec.gpu_required:
            if "gpu" not in node.capabilities:
                return False, "Node does not have GPU capability"
            
            if spec.gpu_config:
                required_vram = spec.gpu_config.memory_mb * spec.gpu_config.count
                if node.gpu_vram_available_mb < required_vram:
                    return False, f"Insufficient GPU VRAM: need {required_vram}MB, have {node.gpu_vram_available_mb}MB"
                
                # Check GPU type compatibility
                available_gpus = [g for g in node.gpu_devices 
                                  if g.status == GPUStatus.AVAILABLE]
                if len(available_gpus) < spec.gpu_config.count:
                    return False, f"Insufficient GPUs: need {spec.gpu_config.count}, have {len(available_gpus)}"
        
        # Check CPU cores
        if node.cpu_available < resources.cpu_cores:
            return False, f"Insufficient CPU: need {resources.cpu_cores} cores, have {node.cpu_available}"
        
        # Check memory
        if node.memory_available_mb < resources.memory_mb:
            return False, f"Insufficient memory: need {resources.memory_mb}MB, have {node.memory_available_mb}MB"
        
        # Check storage
        if node.storage_available_gb < resources.storage_gb:
            return False, f"Insufficient storage: need {resources.storage_gb}GB, have {node.storage_available_gb}GB"
        
        # Check thermal limits
        if node.temperature_celsius > node.max_safe_temp:
            return False, f"Node temperature too high: {node.temperature_celsius}°C"
        
        # Check load thresholds
        if node.cpu_load_avg > 0.90:
            return False, f"CPU load too high: {node.cpu_load_avg * 100:.1f}%"
        
        if node.memory_load_avg > 0.90:
            return False, f"Memory load too high: {node.memory_load_avg * 100:.1f}%"
        
        if node.gpu_load_avg > 0.85:
            return False, f"GPU load too high: {node.gpu_load_avg * 100:.1f}%"
        
        return True, "Valid"


class NodeScorer:
    """Scores nodes for scheduling decisions"""
    
    def __init__(self, weights: Optional[ScoringWeights] = None):
        self.weights = weights or ScoringWeights()
        self.logger = logging.getLogger(__name__)
    
    def score(self, node: Node, request: PodRequest, user_location: Optional[Tuple[float, float]] = None) -> float:
        """Score a node for a pod request (higher is better)"""
        
        resource_score = self._calculate_resource_score(node, request)
        load_score = self._calculate_load_score(node, request)
        proximity_score = self._calculate_proximity_score(node, user_location)
        reliability_score = self._calculate_reliability_score(node)


        
        # Weighted combination
        total_score = (
            self.weights.resource * resource_score +
            self.weights.load * load_score +
            self.weights.proximity * proximity_score +
            self.weights.reliability * reliability_score
        )
        
        return min(1.0, max(0.0, total_score))
    
    def _calculate_resource_score(self, node: Node, request: PodRequest) -> float:
        """Calculate score based on resource availability"""
        spec = request.pod_spec
        resources = spec.resource_requirements
        
        scores = []
        
        # GPU VRAM score (most critical for desktop apps)
        if spec.gpu_required and spec.gpu_config:
            required_vram = spec.gpu_config.memory_mb * spec.gpu_config.count
            if node.gpu_vram_total_mb > 0:
                vram_util = (node.gpu_vram_total_mb - node.gpu_vram_available_mb) / node.gpu_vram_total_mb
                vram_score = max(0.0, 1.0 - vram_util)
                scores.append(("vram", vram_score, 0.5))
        
        # CPU score
        cpu_util = node.cpu_total / max(node.cpu_available, 0.1) if node.cpu_available > 0 else 1.0
        cpu_score = max(0.0, min(1.0, 1.0 - cpu_util + 1))
        scores.append(("cpu", cpu_score, 0.2))
        
        # Memory score
        mem_util = node.memory_total_mb / max(node.memory_available_mb, 1) if node.memory_available_mb > 0 else 1.0
        mem_score = max(0.0, min(1.0, 1.0 - mem_util + 1))
        scores.append(("memory", mem_score, 0.2))
        
        # Storage score
        storage_util = node.storage_total_gb / max(node.storage_available_gb, 1) if node.storage_available_gb > 0 else 1.0
        storage_score = max(0.0, min(1.0, 1.0 - storage_util + 1))
        scores.append(("storage", storage_score, 0.1))
        
        # Calculate weighted average
        if not scores:
            return 0.5
        
        total_weight = sum(s[2] for s in scores)
        weighted_sum = sum(s[1] * s[2] for s in scores)
        
        return weighted_sum / total_weight if total_weight > 0 else 0.5
    
    def _calculate_load_score(self, node: Node, request: PodRequest) -> float:
        """Calculate score based on current node load"""
        # Lower load = higher score
        load_factors = []
        
        if node.cpu_load_avg > 0:
            load_factors.append(node.cpu_load_avg)
        if node.memory_load_avg > 0:
            load_factors.append(node.memory_load_avg)
        if node.gpu_load_avg > 0 and request.pod_spec.gpu_required:
            load_factors.append(node.gpu_load_avg)
        
        if not load_factors:
            return 0.8  # Default to good score if no load data
        
        avg_load = sum(load_factors) / len(load_factors)
        return max(0.0, 1.0 - avg_load)
    
    def _calculate_proximity_score(self, node: Node, user_location: Optional[Tuple[float, float]]) -> float:
        """Calculate score based on geographic proximity to user"""
        if user_location is None:
            return 0.7  # Neutral score if location unknown

        
        distance = self._haversine_distance(
            node.latitude, node.longitude,
            user_location[0], user_location[1]
        )
        
        # Score based on distance
        if distance < 50:
            return 1.0
        elif distance < 200:
            return 0.8
        elif distance < 500:
            return 0.6
        elif distance < 1000:
            return 0.4
        else:
            return 0.2
    
    def _calculate_reliability_score(self, node: Node) -> float:
        """Calculate score based on node reliability"""
        # Check heartbeat freshness
        heartbeat_age = (datetime.now() - node.last_heartbeat).total_seconds()
        
        if heartbeat_age > 300:  # 5 minutes
            return 0.0
        elif heartbeat_age > 60:  # 1 minute
            return 0.5
        else:
            return 1.0
    
    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in km"""
        R = 6371  # Earth's radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c


class ResourceManager:
    """Manages resource reservations and releases"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def reserve(self, node: Node, request: PodRequest) -> bool:
        """Reserve resources for a pod on a node"""
        spec = request.pod_spec
        resources = spec.resource_requirements
        
        with node.resource_lock:
            # Double-check availability (race condition)
            available_gpus = len([g for g in node.gpu_devices if g.status == GPUStatus.AVAILABLE])
            
            if spec.gpu_required and spec.gpu_config:
                required_vram = spec.gpu_config.memory_mb * spec.gpu_config.count
                if node.gpu_vram_available_mb < required_vram:
                    self.logger.warning(f"Race condition: VRAM no longer available on {node.id}")
                    return False
                if available_gpus < spec.gpu_config.count:
                    self.logger.warning(f"Race condition: GPUs no longer available on {node.id}")
                    return False
            
            if node.cpu_available < resources.cpu_cores:
                self.logger.warning(f"Race condition: CPU no longer available on {node.id}")
                return False
            
            if node.memory_available_mb < resources.memory_mb:
                self.logger.warning(f"Race condition: Memory no longer available on {node.id}")
                return False
            
            if node.storage_available_gb < resources.storage_gb:
                self.logger.warning(f"Race condition: Storage no longer available on {node.id}")
                return False
            
            # Reserve GPU resources
            if spec.gpu_required and spec.gpu_config:
                # Find and reserve specific GPUs
                reserved_gpus = []
                for gpu in node.gpu_devices:
                    if gpu.status == GPUStatus.AVAILABLE and len(reserved_gpus) < spec.gpu_config.count:
                        gpu.status = GPUStatus.ALLOCATED
                        gpu.allocated_to_pod = request.id
                        reserved_gpus.append(gpu.id)
                
                node.gpu_vram_available_mb -= spec.gpu_config.memory_mb * spec.gpu_config.count
            
            # Reserve CPU, memory, storage
            node.cpu_available -= resources.cpu_cores
            node.memory_available_mb -= resources.memory_mb
            node.storage_available_gb -= resources.storage_gb
            
            # Track assignment
            node.assigned_pods[request.id] = {
                "pod_spec": spec,
                "reservation_time": datetime.now(),
                "estimated_runtime": 60,  # Default estimate
            }
            
            self.logger.info(f"Reserved resources for {request.id} on {node.id}")
            return True
    
    def release(self, node: Node, pod_id: str) -> bool:
        """Release resources when pod terminates"""
        with node.resource_lock:
            if pod_id not in node.assigned_pods:
                self.logger.warning(f"Pod {pod_id} not found in node {node.id}")
                return False
            
            pod_info = node.assigned_pods[pod_id]
            spec = pod_info["pod_spec"]
            resources = spec.resource_requirements
            
            # Release GPU resources
            if spec.gpu_required and spec.gpu_config:
                for gpu in node.gpu_devices:
                    if gpu.allocated_to_pod == pod_id:
                        gpu.status = GPUStatus.AVAILABLE
                        gpu.allocated_to_pod = None
                
                node.gpu_vram_available_mb += spec.gpu_config.memory_mb * spec.gpu_config.count
            
            # Release CPU, memory, storage
            node.cpu_available += resources.cpu_cores
            node.memory_available_mb += resources.memory_mb
            node.storage_available_gb += resources.storage_gb
            
            # Remove tracking
            del node.assigned_pods[pod_id]
            
            self.logger.info(f"Released resources for {pod_id} on {node.id}")
            return True


class PreemptionManager:
    """Manages pod preemption for high-priority workloads"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def find_preemption_candidates(self, node: Node, request: PodRequest) -> List[str]:
        """Find pods that can be preempted to make room for request"""
        candidates = []
        
        # Calculate resources needed
        spec = request.pod_spec
        resources = spec.resource_requirements
        
        needed = {
            "cpu": resources.cpu_cores,
            "memory": resources.memory_mb,
            "storage": resources.storage_gb,
            "vram": 0,
            "gpu_count": 0
        }
        
        if spec.gpu_required and spec.gpu_config:
            needed["vram"] = spec.gpu_config.memory_mb * spec.gpu_config.count
            needed["gpu_count"] = spec.gpu_config.count
        
        # Sort current pods by priority (ascending, lowest first)
        current_pods = list(node.assigned_pods.items())
        current_pods.sort(key=lambda x: x[1].get("priority", 50))
        
        for pod_id, pod_info in current_pods:
            # Don't preempt higher or equal priority pods
            if pod_info.get("priority", 50) >= request.priority:
                continue
            
            # Don't preempt if user tier is higher
            if pod_info.get("user_tier", "free") in ["enterprise", "pro"]:
                continue
            
            pod_spec = pod_info["pod_spec"]
            pod_resources = pod_spec.resource_requirements
            
            candidates.append(pod_id)
            
            # Subtract from needed resources
            needed["cpu"] -= pod_resources.cpu_cores
            needed["memory"] -= pod_resources.memory_mb
            needed["storage"] -= pod_resources.storage_gb
            
            if pod_spec.gpu_required and pod_spec.gpu_config:
                needed["vram"] -= pod_spec.gpu_config.memory_mb * pod_spec.gpu_config.count
                needed["gpu_count"] -= pod_spec.gpu_config.count
            
            # Check if we have enough
            if all(v <= 0 for v in needed.values()):
                return candidates
        
        return candidates
    
    def _gpu_compatible(self, gpu_req: GPUResource, node: ComputeNode) -> bool:
        """Check if node's GPU capabilities match requirements"""
        if not node.resources.gpu_type:
            return False
        
        # Check if GPU family is compatible
        if gpu_req.gpu_type == GPUFamily.TESLA and node.resources.gpu_type in [
            GPUFamily.TESLA, GPUFamily.A100, GPUFamily.H100, GPUFamily.V100
        ]:
            return True
        elif gpu_req.gpu_type == node.resources.gpu_type:
            return True
        
        return False
    
    def _calculate_node_score(self, pod_spec: PodSpec, node: ComputeNode) -> float:
        """Calculate a score for how well a node fits the pod requirements"""
        score = 0.0
        
        req = pod_spec.resource_requirements
        
        # CPU utilization score (prefer nodes with more available CPU)
        cpu_utilization = (req.cpu_cores / node.resources.total_cpu_cores)
        score += (1.0 - cpu_utilization) * 0.3
        
        # Memory utilization score (prefer nodes with more available memory)
        mem_utilization = (req.memory_mb / node.resources.total_memory_mb)
        score += (1.0 - mem_utilization) * 0.3
        
        # GPU availability score (if GPU required)
        if pod_spec.gpu_required and req.gpu_resources:
            gpu_utilization = (req.gpu_resources.count / node.resources.total_gpus) if node.resources.total_gpus > 0 else 1.0
            score += (1.0 - gpu_utilization) * 0.4
        
        # Affinity/anti-affinity considerations could be added here
        # For now, just return the resource-based score
        
        return score


class GPUTopologyManager:
    """Manages GPU topology and placement decisions"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def select_gpus_for_pod(self, 
                           pod_spec: PodSpec, 
                           available_gpus: List[GPUDevice], 
                           node_gpus: List[GPUDevice]) -> List[GPUDevice]:
        """Select specific GPUs for a pod based on topology and requirements"""
        if not pod_spec.gpu_required or not pod_spec.resource_requirements.gpu_resources:
            return []
        
        gpu_req = pod_spec.resource_requirements.gpu_resources
        selected_gpus = []
        
        # Filter GPUs that match requirements
        compatible_gpus = [
            gpu for gpu in available_gpus
            if gpu.spec.family == gpu_req.gpu_type and gpu.status == GPUStatus.AVAILABLE
        ][:gpu_req.count]
        
        if len(compatible_gpus) < gpu_req.count:
            self.logger.warning(f"Insufficient compatible GPUs. Requested: {gpu_req.count}, Available: {len(compatible_gpus)}")
            return compatible_gpus
        
        # For now, return the first compatible GPUs
        # In a real implementation, we would consider topology, memory requirements, etc.
        return compatible_gpus[:gpu_req.count]


class PriorityQueue:
    """Priority queue for scheduling requests"""
    
    def __init__(self):
        self.queue = []
        self.counter = 0  # To handle ties in priority
    
    def push(self, request: PodRequest):
        """Add a request to the queue"""
        # Use negative priority because heapq is a min-heap
        # Also use counter to handle ties
        heapq.heappush(self.queue, (-request.priority, self.counter, request))
        self.counter += 1
    
    def pop(self) -> Optional[PodRequest]:
        """Remove and return the highest priority request"""
        if self.queue:
            _, _, request = heapq.heappop(self.queue)
            return request
        return None
    
    def peek(self) -> Optional[PodRequest]:
        """Return the highest priority request without removing it"""
        if self.queue:
            _, _, request = self.queue[0]
            return request
        return None

    
    def is_empty(self) -> bool:
        """Check if the queue is empty"""
        return len(self.queue) == 0

class Scheduler:
    """Main scheduler for disposable compute platform"""
    
    def __init__(self, orchestrator: Any = None):
        self.nodes: Dict[str, Node] = {}
        self.pending_requests: Dict[str, PodRequest] = {}
        self.scheduled_pods: Dict[str, str] = {}  # pod_id -> node_id
        self.orchestrator = orchestrator
        
        self.validator = ConstraintValidator()
        self.scorer = NodeScorer()
        self.resource_manager = ResourceManager()
        self.preemption_manager = PreemptionManager()
        
        self.logger = logging.getLogger(__name__)
        
        # Metrics
        self.metrics: Dict[str, Any] = {
            "total_scheduled": 0,
            "total_failed": 0,
            "total_preemptions": 0,
            "avg_scheduling_time_ms": 0.0,
        }


    
    def register_node(self, node: Node):
        """Register a compute node with the scheduler"""
        self.nodes[node.id] = node
        self.logger.info(f"Registered node {node.id} ({node.hostname})")
    
    def unregister_node(self, node_id: str):
        """Unregister a compute node"""
        if node_id in self.nodes:
            del self.nodes[node_id]
            self.logger.info(f"Unregistered node {node_id}")
    
    async def schedule(self, request: PodRequest, user_location: Optional[Tuple[float, float]] = None) -> Tuple[bool, str, Optional[str]]:
        """
        Schedule a pod request to a node.
        Returns (success, message, node_id)
        """
        start_time = time.time()
        
        # Get available nodes
        available_nodes = [n for n in self.nodes.values() if n.status == NodeStatus.ACTIVE]
        
        if not available_nodes:
            request.status = SchedulingStatus.FAILED
            request.failure_reason = "No available nodes"
            self.metrics["total_failed"] += 1
            return False, "No available nodes", None
        
        # Filter nodes by constraints
        valid_nodes = []
        for node in available_nodes:
            is_valid, reason = self.validator.validate(node, request)
            if is_valid:
                valid_nodes.append(node)
            else:
                self.logger.debug(f"Node {node.id} rejected: {reason}")
        
        if not valid_nodes:
            # Try preemption for high priority requests
            if request.priority >= 70:
                return await self._try_preemption(request, available_nodes, user_location)
            
            request.status = SchedulingStatus.FAILED
            request.failure_reason = "No nodes meet resource requirements"
            self.metrics["total_failed"] += 1
            return False, "No nodes meet resource requirements", None
        
        # Score and rank nodes
        scored_nodes = []
        for node in valid_nodes:
            score = self.scorer.score(node, request, user_location)
            scored_nodes.append((node, score))

        
        # Sort by score (descending)
        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        
        # Try to reserve on best node
        for node, score in scored_nodes:
            if score < 0.1:
                self.logger.warning(f"Best node {node.id} has low score: {score:.2f}")
                continue
            
            if self.resource_manager.reserve(node, request):
                # Update request status
                request.status = SchedulingStatus.SCHEDULED
                request.assigned_node_id = node.id
                request.scheduled_at = datetime.now()
                
                # Track scheduling
                self.scheduled_pods[request.id] = node.id
                self.metrics["total_scheduled"] += 1
                
                # Update metrics
                elapsed_ms = (time.time() - start_time) * 1000
                self._update_avg_scheduling_time(elapsed_ms)
                
                self.logger.info(f"Scheduled {request.id} to {node.id} (score: {score:.2f}, time: {elapsed_ms:.1f}ms)")
                return True, "Successfully scheduled", node.id
        
        request.status = SchedulingStatus.FAILED
        request.failure_reason = "Failed to reserve resources on any node"
        self.metrics["total_failed"] += 1
        return False, "Failed to reserve resources", None
    
    async def _try_preemption(self, request: PodRequest, nodes: List[Node], 
                             user_location: Optional[Tuple[float, float]] = None) -> Tuple[bool, str, Optional[str]]:
        """Try to preempt lower priority pods to make room"""
        if self.orchestrator is None:
            return False, "Orchestrator not available for preemption", None

        for node in nodes:
            if node.status != NodeStatus.ACTIVE:
                continue
            
            candidates = self.preemption_manager.find_preemption_candidates(node, request)
            
            if candidates:
                self.logger.info(f"Preempting {len(candidates)} pods on {node.id} for {request.id}")
                
                for pod_id in candidates:
                    try:
                        await self.orchestrator.destroy_pod(pod_id)
                        self.unschedule(pod_id)
                    except Exception as e:
                        self.logger.error(f"Failed to preempt pod {pod_id}: {e}")
                
                # Re-attempt reservation after clearing space
                if self.resource_manager.reserve(node, request):
                    request.status = SchedulingStatus.SCHEDULED
                    request.assigned_node_id = node.id
                    request.scheduled_at = datetime.now()
                    self.scheduled_pods[request.id] = node.id
                    self.metrics["total_scheduled"] += 1
                    self.metrics["total_preemptions"] += 1
                    return True, "Preempted and scheduled", node.id
        
        return False, "No nodes available even with preemption", None

    
    def unschedule(self, pod_id: str) -> bool:
        """Remove a pod from scheduling (release resources)"""
        if pod_id not in self.scheduled_pods:
            self.logger.warning(f"Pod {pod_id} not found in scheduled pods")
            return False
        
        node_id = self.scheduled_pods[pod_id]
        if node_id not in self.nodes:
            self.logger.warning(f"Node {node_id} not found for pod {pod_id}")
            del self.scheduled_pods[pod_id]
            return False
        
        node = self.nodes[node_id]
        success = self.resource_manager.release(node, pod_id)
        
        if success:
            del self.scheduled_pods[pod_id]
            self.logger.info(f"Unscheduled pod {pod_id} from node {node_id}")
        
        return success
    
    def get_node_status(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a node"""
        if node_id not in self.nodes:
            return None
        
        node = self.nodes[node_id]
        
        return {
            "id": node.id,
            "hostname": node.hostname,
            "status": node.status.value,
            "cpu_available": node.cpu_available,
            "cpu_total": node.cpu_total,
            "memory_available_mb": node.memory_available_mb,
            "memory_total_mb": node.memory_total_mb,
            "storage_available_gb": node.storage_available_gb,
            "storage_total_gb": node.storage_total_gb,
            "gpu_vram_available_mb": node.gpu_vram_available_mb,
            "gpu_vram_total_mb": node.gpu_vram_total_mb,
            "pod_count": len(node.assigned_pods),
            "last_heartbeat": node.last_heartbeat.isoformat(),
        }
    
    def get_cluster_status(self) -> Dict[str, Any]:
        """Get overall cluster status"""
        total_pods = sum(len(n.assigned_pods) for n in self.nodes.values())
        active_nodes = [n for n in self.nodes.values() if n.status == NodeStatus.ACTIVE]
        
        return {
            "total_nodes": len(self.nodes),
            "active_nodes": len(active_nodes),
            "total_pods": total_pods,
            "total_scheduled": self.metrics["total_scheduled"],
            "total_failed": self.metrics["total_failed"],
            "total_preemptions": self.metrics["total_preemptions"],
            "avg_scheduling_time_ms": round(self.metrics["avg_scheduling_time_ms"], 2),
            "nodes": {nid: self.get_node_status(nid) for nid in self.nodes.keys()}
        }
    
    def _update_avg_scheduling_time(self, elapsed_ms: float):
        """Update rolling average of scheduling time"""
        current = self.metrics["avg_scheduling_time_ms"]
        count = self.metrics["total_scheduled"]
        
        if count == 1:
            self.metrics["avg_scheduling_time_ms"] = elapsed_ms
        else:
            self.metrics["avg_scheduling_time_ms"] = current + (elapsed_ms - current) / count
