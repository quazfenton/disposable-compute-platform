"""
Scheduler for disposable compute platform with GPU-aware scheduling
"""
import asyncio
import heapq
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import random

from src.models.pod import Pod, PodSpec, ResourceRequirements, GPUResource, ComputeNode
from src.models.gpu import GPUDevice, GPUStatus, GPUFamily, GPUVendor
from src.orchestrator.orchestrator import AdvancedOrchestrator


@dataclass
class SchedulingRequest:
    """Represents a request for scheduling a pod"""
    pod_spec: PodSpec
    priority: int = 1  # Lower number means higher priority
    submission_time: datetime = None
    
    def __post_init__(self):
        if self.submission_time is None:
            self.submission_time = datetime.now()


@dataclass
class SchedulingResult:
    """Result of a scheduling decision"""
    success: bool
    node_id: Optional[str] = None
    reason: Optional[str] = None
    score: float = 0.0  # Higher score means better fit


class NodeSelector:
    """Selects the best node for pod placement based on resource requirements"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def find_best_node(self, 
                      pod_spec: PodSpec, 
                      available_nodes: List[ComputeNode]) -> SchedulingResult:
        """Find the best node for placing a pod"""
        if not available_nodes:
            return SchedulingResult(success=False, reason="No available nodes")
        
        # Filter nodes that meet basic requirements
        candidate_nodes = self._filter_candidate_nodes(pod_spec, available_nodes)
        
        if not candidate_nodes:
            return SchedulingResult(success=False, reason="No nodes meet resource requirements")
        
        # Score each candidate node
        scored_nodes = []
        for node in candidate_nodes:
            score = self._calculate_node_score(pod_spec, node)
            scored_nodes.append((score, node))
        
        # Sort by score (highest first)
        scored_nodes.sort(key=lambda x: x[0], reverse=True)
        
        best_score, best_node = scored_nodes[0]
        
        return SchedulingResult(
            success=True,
            node_id=best_node.id,
            score=best_score
        )
    
    def _filter_candidate_nodes(self, 
                               pod_spec: PodSpec, 
                               nodes: List[ComputeNode]) -> List[ComputeNode]:
        """Filter nodes that can potentially accommodate the pod"""
        candidates = []
        
        for node in nodes:
            req = pod_spec.resource_requirements
            
            # Check basic resources
            if (node.resources.available_cpu_cores >= req.cpu_cores and
                node.resources.available_memory_mb >= req.memory_mb and
                node.resources.available_storage_gb >= req.storage_gb):
                
                # Check GPU requirements if needed
                if pod_spec.gpu_required and req.gpu_resources:
                    if (node.resources.available_gpus >= req.gpu_resources.count and
                        node.resources.gpu_type and
                        self._gpu_compatible(req.gpu_resources, node)):
                        candidates.append(node)
                elif not pod_spec.gpu_required:
                    # If no GPU required, any node with basic resources qualifies
                    candidates.append(node)
        
        return candidates
    
    def _gpu_compatible(self, gpu_req: GPUResource, node: ComputeNode) -> bool:
        """Check if node's GPU capabilities match requirements"""
        if not node.resources.gpu_type:
            return False
        
        # Check if GPU family is compatible
        if gpu_req.gpu_type == GPUFamily.NVIDIA_TESLA and node.resources.gpu_type in [
            GPUFamily.NVIDIA_TESLA, GPUFamily.NVIDIA_A100, GPUFamily.NVIDIA_H100, GPUFamily.NVIDIA_V100
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
    
    def push(self, request: SchedulingRequest):
        """Add a request to the queue"""
        # Use negative priority because heapq is a min-heap
        # Also use counter to handle ties
        heapq.heappush(self.queue, (-request.priority, self.counter, request))
        self.counter += 1
    
    def pop(self) -> Optional[SchedulingRequest]:
        """Remove and return the highest priority request"""
        if self.queue:
            _, _, request = heapq.heappop(self.queue)
            return request
        return None
    
    def peek(self) -> Optional[SchedulingRequest]:
        """Return the highest priority request without removing it"""
        if self.queue:
            _, _, request = self.queue[0]
            return request
        return None
    
    def is_empty(self) -> bool:
        """Check if the queue is empty"""
        return len(self.queue) == 0


class Scheduler:
    """Main scheduler for the disposable compute platform"""
    
    def __init__(self, orchestrator: AdvancedOrchestrator):
        self.orchestrator = orchestrator
        self.request_queue = PriorityQueue()
        self.node_selector = NodeSelector()
        self.gpu_topology_manager = GPUTopologyManager()
        self.nodes: Dict[str, ComputeNode] = {}
        self.scheduled_pods: Dict[str, str] = {}  # pod_id -> node_id
        self.running_pods: Dict[str, str] = {}    # pod_id -> node_id
        self.logger = logging.getLogger(__name__)
        
        # Start the scheduling loop
        self.scheduler_task = None
    
    async def start_scheduler(self):
        """Start the scheduling loop"""
        if self.scheduler_task is None:
            self.scheduler_task = asyncio.create_task(self._scheduling_loop())
    
    async def stop_scheduler(self):
        """Stop the scheduling loop"""
        if self.scheduler_task:
            self.scheduler_task.cancel()
            try:
                await self.scheduler_task
            except asyncio.CancelledError:
                pass
            self.scheduler_task = None
    
    async def submit_pod_request(self, pod_spec: PodSpec, priority: int = 1) -> str:
        """Submit a pod for scheduling"""
        request = SchedulingRequest(pod_spec, priority)
        self.request_queue.push(request)
        
        # Return a placeholder pod ID
        # In a real implementation, this would be handled by the orchestrator
        pod_id = f"sched-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{random.randint(1000, 9999)}"
        return pod_id
    
    async def _scheduling_loop(self):
        """Main scheduling loop"""
        while True:
            try:
                # Process requests in the queue
                while not self.request_queue.is_empty():
                    request = self.request_queue.pop()
                    
                    if request:
                        await self._schedule_request(request)
                
                # Sleep briefly before checking again
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                self.logger.info("Scheduler loop cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in scheduling loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _schedule_request(self, request: SchedulingRequest):
        """Schedule a single request"""
        try:
            # Get available nodes
            available_nodes = list(self.nodes.values())
            
            # Find the best node for this pod
            result = self.node_selector.find_best_node(request.pod_spec, available_nodes)
            
            if result.success:
                # Assign the pod to the selected node
                pod_id = await self.orchestrator.create_pod(request.pod_spec)
                self.scheduled_pods[pod_id] = result.node_id
                
                # Update node resources
                await self._update_node_resources(result.node_id, request.pod_spec, allocate=True)
                
                self.logger.info(f"Scheduled pod {pod_id} on node {result.node_id} with score {result.score:.2f}")
                
                # Start the pod
                await self.orchestrator.start_pod(pod_id)
                self.running_pods[pod_id] = result.node_id
            else:
                self.logger.warning(f"Failed to schedule pod: {result.reason}")
                # In a real implementation, we might requeue or handle differently
                # For now, we'll just log the failure
        
        except Exception as e:
            self.logger.error(f"Error scheduling request: {e}")
    
    async def _update_node_resources(self, node_id: str, pod_spec: PodSpec, allocate: bool = True):
        """Update node resources based on pod allocation or deallocation"""
        if node_id not in self.nodes:
            return
        
        node = self.nodes[node_id]
        req = pod_spec.resource_requirements
        
        multiplier = 1 if allocate else -1
        
        # Update CPU
        node.resources.available_cpu_cores -= req.cpu_cores * multiplier
        
        # Update memory
        node.resources.available_memory_mb -= req.memory_mb * multiplier
        
        # Update storage
        node.resources.available_storage_gb -= req.storage_gb * multiplier
        
        # Update GPU resources if applicable
        if pod_spec.gpu_required and req.gpu_resources:
            node.resources.available_gpus -= req.gpu_resources.count * multiplier
    
    async def unschedule_pod(self, pod_id: str):
        """Unschedule a pod and free up resources"""
        # Remove from running pods
        if pod_id in self.running_pods:
            node_id = self.running_pods.pop(pod_id)
            
            # Get the pod spec to determine resource requirements
            # In a real implementation, we'd store this information
            # For now, we'll skip resource deallocation
            
            self.logger.info(f"Unscheduled pod {pod_id} from node {node_id}")
    
    def add_node(self, node: ComputeNode):
        """Add a compute node to the scheduler"""
        self.nodes[node.id] = node
        self.logger.info(f"Added node {node.id} with {node.resources.available_cpu_cores} CPUs, "
                         f"{node.resources.available_memory_mb}MB memory, "
                         f"{node.resources.available_gpus} GPUs")
    
    def remove_node(self, node_id: str):
        """Remove a compute node from the scheduler"""
        if node_id in self.nodes:
            del self.nodes[node_id]
            self.logger.info(f"Removed node {node_id}")
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get the status of the scheduler"""
        return {
            "queued_requests": len(self.request_queue.queue),
            "scheduled_pods": len(self.scheduled_pods),
            "running_pods": len(self.running_pods),
            "nodes": len(self.nodes),
            "nodes_detail": {
                node_id: {
                    "cpu_available": node.resources.available_cpu_cores,
                    "memory_available": node.resources.available_memory_mb,
                    "gpus_available": node.resources.available_gpus
                }
                for node_id, node in self.nodes.items()
            }
        }