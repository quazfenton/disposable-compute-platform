# Scheduler Algorithm Design

## 1. Overview

The scheduler is responsible for allocating compute resources to user requests while maintaining system stability and performance. It must handle the unique requirements of GPU-intensive desktop applications like TouchDesigner and Unreal Engine 5.

## 2. Core Principles

### Resource Constraints
- Never overcommit GPU VRAM
- Respect CPU and memory limits
- Account for I/O bandwidth
- Consider thermal and power limits

### Performance Goals
- Minimize pod startup time
- Maximize resource utilization
- Ensure consistent performance
- Maintain low streaming latency

## 3. Scheduler Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           Main Scheduler                                        │
│                                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │  Pod Request    │  │  Node          │  │  Resource       │                 │
│  │  Queue          │  │  Selector       │  │  Calculator     │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
│         │                       │                       │                       │
│         ▼                       ▼                       ▼                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐                 │
│  │  Priority       │  │  Scoring        │  │  Constraint     │                 │
│  │  Evaluator      │  │  Engine         │  │  Validator      │                 │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## 4. Pod Request Processing

### Request Structure
```python
class PodRequest:
    app_type: str          # "linux", "windows", "macos"
    app_name: str          # "ue5", "touchdesigner", "blender"
    app_version: str       # "5.0", "099", etc.
    gpu_required: bool     # Whether GPU is required
    gpu_profile: str       # "gaming", "professional", "none"
    min_vram_gb: int       # Minimum VRAM required
    min_cpu_cores: int     # Minimum CPU cores
    min_memory_gb: int     # Minimum RAM
    storage_gb: int        # Storage requirement
    duration_estimate: int # Estimated runtime in minutes
    snapshot_id: str       # Optional: restore from snapshot
    project_files: list    # Optional: project files to mount
```

## 5. Node Selection Algorithm

### 5.1 Node Scoring Function

```python
def score_node(node: Node, pod_request: PodRequest) -> float:
    """
    Score a node for a pod request (higher is better)
    Returns a score between 0.0 and 1.0
    """
    
    # Base score components
    resource_score = calculate_resource_score(node, pod_request)
    load_score = calculate_load_score(node, pod_request)
    proximity_score = calculate_proximity_score(node, user_location)
    reliability_score = calculate_reliability_score(node)
    
    # Weighted combination
    total_score = (
        0.4 * resource_score +      # 40% - Resource availability
        0.3 * load_score +          # 30% - Current load
        0.2 * proximity_score +     # 20% - Geographic proximity
        0.1 * reliability_score     # 10% - Historical reliability
    )
    
    return total_score
```

### 5.2 Resource Score Calculation

```python
def calculate_resource_score(node: Node, pod_request: PodRequest) -> float:
    """
    Calculate score based on resource availability
    """
    # GPU VRAM availability (most critical for desktop apps)
    if pod_request.gpu_required:
        if node.gpu_vram_available < pod_request.min_vram_gb:
            return 0.0  # Cannot schedule on this node
        
        vram_utilization = (node.gpu_vram_total - node.gpu_vram_available) / node.gpu_vram_total
        vram_score = max(0.0, 1.0 - vram_utilization)
    else:
        vram_score = 1.0
    
    # CPU availability
    cpu_utilization = node.cpu_used / node.cpu_total
    cpu_score = max(0.0, 1.0 - cpu_utilization)
    
    # Memory availability
    mem_utilization = node.memory_used / node.memory_total
    mem_score = max(0.0, 1.0 - mem_utilization)
    
    # Storage availability
    storage_utilization = node.storage_used / node.storage_total
    storage_score = max(0.0, 1.0 - storage_utilization)
    
    # Weighted average (VRAM is most critical for desktop apps)
    resource_score = (
        0.5 * vram_score +      # 50% - GPU VRAM (critical for UE5/TouchDesigner)
        0.2 * cpu_score +       # 20% - CPU
        0.2 * mem_score +       # 20% - Memory
        0.1 * storage_score     # 10% - Storage
    )
    
    return resource_score
```

### 5.3 Load Score Calculation

```python
def calculate_load_score(node: Node, pod_request: PodRequest) -> float:
    """
    Calculate score based on current node load
    """
    # Calculate current load factors
    current_gpu_load = node.gpu_load_avg
    current_cpu_load = node.cpu_load_avg
    current_memory_load = node.memory_load_avg
    
    # Apply load thresholds to prevent overloading
    if current_gpu_load > 0.85:  # GPU load too high
        return 0.0
    if current_cpu_load > 0.90:  # CPU load too high
        return 0.0
    if current_memory_load > 0.90:  # Memory load too high
        return 0.0
    
    # Calculate load score (lower load = higher score)
    load_factor = (current_gpu_load + current_cpu_load + current_memory_load) / 3
    load_score = max(0.0, 1.0 - load_factor)
    
    return load_score
```

### 5.4 Proximity Score Calculation

```python
def calculate_proximity_score(node: Node, user_location: Location) -> float:
    """
    Calculate score based on geographic proximity to user
    """
    distance_km = calculate_distance(node.location, user_location)
    
    # Score based on distance (closer = better)
    if distance_km < 50:      # Within 50km
        return 1.0
    elif distance_km < 200:   # Within 200km
        return 0.8
    elif distance_km < 500:   # Within 500km
        return 0.6
    elif distance_km < 1000:  # Within 1000km
        return 0.4
    else:                     # Beyond 1000km
        return 0.2
```

## 6. Constraint Validation

### 6.1 Pre-scheduling Validation

```python
def validate_constraints(node: Node, pod_request: PodRequest) -> tuple[bool, str]:
    """
    Validate that a node can satisfy all pod constraints
    Returns (is_valid, reason_if_invalid)
    """
    # GPU VRAM check (critical constraint)
    if pod_request.gpu_required and node.gpu_vram_available < pod_request.min_vram_gb:
        return False, f"Insufficient GPU VRAM: need {pod_request.min_vram_gb}GB, have {node.gpu_vram_available}GB"
    
    # CPU cores check
    if node.cpu_available < pod_request.min_cpu_cores:
        return False, f"Insufficient CPU cores: need {pod_request.min_cpu_cores}, have {node.cpu_available}"
    
    # Memory check
    if node.memory_available < pod_request.min_memory_gb:
        return False, f"Insufficient memory: need {pod_request.min_memory_gb}GB, have {node.memory_available}GB"
    
    # Storage check
    if node.storage_available < pod_request.storage_gb:
        return False, f"Insufficient storage: need {pod_request.storage_gb}GB, have {node.storage_available}GB"
    
    # GPU type compatibility
    if pod_request.gpu_required and not is_gpu_compatible(node.gpu_type, pod_request.app_name):
        return False, f"GPU type {node.gpu_type} incompatible with {pod_request.app_name}"
    
    # OS compatibility
    if not is_os_compatible(node.os_type, pod_request.app_type):
        return False, f"Node OS {node.os_type} incompatible with app type {pod_request.app_type}"
    
    # Thermal limits
    if node.temperature > node.max_safe_temp:
        return False, f"Node temperature too high: {node.temperature}°C"
    
    return True, "Valid"
```

## 7. Scheduling Algorithm

### 7.1 Main Scheduling Loop

```python
def schedule_pod(pod_request: PodRequest) -> tuple[bool, str, Node]:
    """
    Main scheduling function
    Returns (success, reason, assigned_node)
    """
    # Get all available nodes
    available_nodes = get_available_nodes()
    
    # Filter nodes that meet basic constraints
    valid_nodes = []
    for node in available_nodes:
        is_valid, reason = validate_constraints(node, pod_request)
        if is_valid:
            valid_nodes.append(node)
    
    if not valid_nodes:
        return False, "No nodes available that meet resource requirements", None
    
    # Score all valid nodes
    scored_nodes = []
    for node in valid_nodes:
        score = score_node(node, pod_request)
        scored_nodes.append((node, score))
    
    # Sort by score (descending)
    scored_nodes.sort(key=lambda x: x[1], reverse=True)
    
    # Select the highest-scoring node
    best_node, best_score = scored_nodes[0]
    
    if best_score < 0.1:  # Minimum acceptable score
        return False, f"Best available node has low score: {best_score:.2f}", None
    
    # Reserve resources on the selected node
    success = reserve_resources(best_node, pod_request)
    if not success:
        return False, "Failed to reserve resources on selected node", None
    
    return True, "Successfully scheduled", best_node
```

## 8. Resource Reservation & Tracking

### 8.1 Resource Reservation

```python
def reserve_resources(node: Node, pod_request: PodRequest) -> bool:
    """
    Reserve resources for a pod on a node
    """
    # Acquire lock on node resources
    with node.resource_lock:
        # Check if resources are still available (race condition check)
        is_valid, _ = validate_constraints(node, pod_request)
        if not is_valid:
            return False
        
        # Reserve resources
        if pod_request.gpu_required:
            node.gpu_vram_available -= pod_request.min_vram_gb
            node.gpu_pods_scheduled += 1
        
        node.cpu_available -= pod_request.min_cpu_cores
        node.memory_available -= pod_request.min_memory_gb
        node.storage_available -= pod_request.storage_gb
        
        # Track pod assignment
        pod_id = generate_pod_id()
        node.assigned_pods[pod_id] = {
            'pod_request': pod_request,
            'reservation_time': time.time(),
            'estimated_runtime': pod_request.duration_estimate
        }
        
        return True
```

### 8.2 Resource Release

```python
def release_resources(node: Node, pod_id: str) -> bool:
    """
    Release resources when pod terminates
    """
    with node.resource_lock:
        if pod_id not in node.assigned_pods:
            return False
        
        pod_info = node.assigned_pods[pod_id]
        pod_request = pod_info['pod_request']
        
        # Release resources
        if pod_request.gpu_required:
            node.gpu_vram_available += pod_request.min_vram_gb
            node.gpu_pods_scheduled -= 1
        
        node.cpu_available += pod_request.min_cpu_cores
        node.memory_available += pod_request.min_memory_gb
        node.storage_available += pod_request.storage_gb
        
        # Remove pod assignment
        del node.assigned_pods[pod_id]
        
        return True
```

## 9. Advanced Scheduling Features

### 9.1 Priority-Based Scheduling

```python
def calculate_priority(pod_request: PodRequest, user_tier: str) -> int:
    """
    Calculate scheduling priority for a pod request
    """
    base_priority = 50  # Default
    
    # User tier adjustments
    if user_tier == "premium":
        base_priority += 20
    elif user_tier == "enterprise":
        base_priority += 30
    
    # Resource demand adjustments
    if pod_request.gpu_required:
        base_priority -= 10  # GPU requests are more expensive
    
    if pod_request.min_vram_gb > 8:  # High VRAM demand
        base_priority -= 5
    
    # Urgency adjustments
    if pod_request.duration_estimate < 30:  # Short sessions get priority
        base_priority += 5
    
    return max(1, min(100, base_priority))  # Clamp to 1-100 range
```

### 9.2 Preemption Logic

```python
def consider_preemption(node: Node, high_priority_pod: PodRequest) -> list[str]:
    """
    Determine which pods to preempt to make room for high-priority pod
    Returns list of pod IDs to terminate
    """
    preemption_targets = []
    
    # Sort current pods by priority (ascending)
    current_pods = list(node.assigned_pods.items())
    current_pods.sort(key=lambda x: x[1]['pod_request'].priority)
    
    # Calculate resources needed
    needed_vram = high_priority_pod.min_vram_gb
    needed_cpu = high_priority_pod.min_cpu_cores
    needed_memory = high_priority_pod.min_memory_gb
    
    # Try to free up resources by preemption
    for pod_id, pod_info in current_pods:
        pod_request = pod_info['pod_request']
        
        # Don't preempt higher priority pods
        if pod_request.priority >= high_priority_pod.priority:
            continue
        
        # Add pod to preemption targets
        preemption_targets.append(pod_id)
        
        # Add freed resources
        needed_vram -= pod_request.min_vram_gb if pod_request.gpu_required else 0
        needed_cpu -= pod_request.min_cpu_cores
        needed_memory -= pod_request.min_memory_gb
        
        # Check if we've freed enough resources
        if needed_vram <= 0 and needed_cpu <= 0 and needed_memory <= 0:
            break
    
    # If we haven't freed enough resources, clear the preemption targets
    if needed_vram > 0 or needed_cpu > 0 or needed_memory > 0:
        return []
    
    return preemption_targets
```

## 10. Load Balancing & Optimization

### 10.1 Node Load Balancing

```python
def rebalance_nodes():
    """
    Periodically rebalance pods across nodes to optimize resource utilization
    """
    nodes = get_all_nodes()
    
    # Identify overloaded and underloaded nodes
    overloaded_nodes = [n for n in nodes if is_node_overloaded(n)]
    underloaded_nodes = [n for n in nodes if is_node_underloaded(n)]
    
    for overloaded_node in overloaded_nodes:
        if not underloaded_nodes:
            break
            
        # Find pods that could be moved to underloaded nodes
        movable_pods = find_movable_pods(overloaded_node)
        
        for pod_id, pod_info in movable_pods:
            for underloaded_node in underloaded_nodes:
                if can_migrate_pod(pod_id, pod_info, underloaded_node):
                    migrate_pod(pod_id, overloaded_node, underloaded_node)
                    break
```

This scheduler algorithm ensures efficient resource utilization while maintaining the performance requirements for GPU-intensive desktop applications like TouchDesigner and Unreal Engine 5.