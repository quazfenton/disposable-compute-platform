# Pod Lifecycle Pseudocode

## 1. Overview

This document outlines the complete lifecycle of a disposable compute pod, from request to destruction, including snapshot and reload capabilities.

## 2. Pod State Machine

```
          ┌─────────────────┐
          │   REQUESTED     │
          └─────────┬───────┘
                    │
                    ▼
          ┌─────────────────┐
          │   SCHEDULING    │
          └─────────┬───────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
┌──────────────┐┌─────────┐┌──────────────┐
│  SCHEDULED   ││ FAILED  ││  CANCELLED   │
└──────┬───────┘└─────────┘└──────────────┘
       │
       ▼
┌──────────────┐
│  PROVISIONING│
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   STARTING   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│   STREAMING  │
└──────┬───────┘
       │
       ├─────────────────► ┌──────────────┐
       │                   │  SNAPSHOT    │
       │                   │  CREATING    │
       │                   └──────┬───────┘
       │                          │
       │                          ▼
       │                   ┌──────────────┐
       │                   │  SNAPSHOT    │
       │                   │  COMPLETE    │
       │                   └──────────────┘
       │
       ├─────────────────► ┌──────────────┐
       │                   │  EXPORTING   │
       │                   │  PROJECT     │
       │                   └──────┬───────┘
       │                          │
       │                          ▼
       │                   ┌──────────────┐
       │                   │  EXPORT      │
       │                   │  COMPLETE    │
       │                   └──────────────┘
       │
       ▼
┌──────────────┐
│  TERMINATING │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  TERMINATED  │
└──────────────┘
```

## 3. Pod Lifecycle Functions

### 3.1 Pod Request Handler

```
FUNCTION handle_pod_request(user_request):
    INPUT: user_request (app_type, app_version, gpu_required, etc.)
    OUTPUT: pod_id or error
    
    // Validate request
    IF NOT validate_request(user_request):
        RETURN error("Invalid request parameters")
    
    // Create pod specification
    pod_spec = create_pod_spec(user_request)
    
    // Store request in queue
    request_queue.enqueue(pod_spec)
    
    // Generate unique pod ID
    pod_id = generate_unique_id()
    
    // Initialize pod state
    pod_state = {
        id: pod_id,
        spec: pod_spec,
        status: "REQUESTED",
        created_at: current_timestamp(),
        user_id: user_request.user_id
    }
    
    // Store pod state
    store_pod_state(pod_id, pod_state)
    
    RETURN pod_id
```

### 3.2 Scheduler Integration

```
FUNCTION process_scheduling_queue():
    WHILE request_queue.has_items():
        pod_spec = request_queue.dequeue()
        
        // Attempt to schedule pod
        scheduling_result = attempt_schedule(pod_spec)
        
        IF scheduling_result.success:
            update_pod_state(pod_spec.id, {
                status: "SCHEDULED",
                assigned_node: scheduling_result.node,
                scheduled_at: current_timestamp()
            })
            
            // Trigger provisioning
            trigger_provisioning(pod_spec.id, scheduling_result.node)
        ELSE:
            update_pod_state(pod_spec.id, {
                status: "FAILED",
                failure_reason: scheduling_result.reason,
                failed_at: current_timestamp()
            })
```

### 3.3 Pod Provisioning

```
FUNCTION provision_pod(pod_id, node):
    INPUT: pod_id, node (where pod will run)
    OUTPUT: success or failure
    
    // Update pod state
    update_pod_state(pod_id, {status: "PROVISIONING"})
    
    // Get pod specification
    pod_spec = get_pod_spec(pod_id)
    
    // Prepare node resources
    resources_reserved = reserve_node_resources(node, pod_spec.resources)
    IF NOT resources_reserved:
        update_pod_state(pod_id, {
            status: "FAILED",
            failure_reason: "Could not reserve node resources"
        })
        RETURN false
    
    // Create pod environment based on app type
    IF pod_spec.app_type == "linux":
        success = create_linux_container_pod(pod_id, node, pod_spec)
    ELSE IF pod_spec.app_type == "windows":
        success = create_windows_vm_pod(pod_id, node, pod_spec)
    ELSE IF pod_spec.app_type == "macos":
        success = create_macos_vm_pod(pod_id, node, pod_spec)
    ELSE:
        success = false
    
    IF success:
        update_pod_state(pod_id, {status: "STARTING"})
        RETURN true
    ELSE:
        update_pod_state(pod_id, {
            status: "FAILED",
            failure_reason: "Pod creation failed"
        })
        release_node_resources(node, pod_spec.resources)
        RETURN false
```

### 3.4 Linux Container Pod Creation

```
FUNCTION create_linux_container_pod(pod_id, node, pod_spec):
    INPUT: pod_id, node, pod_spec
    OUTPUT: success or failure
    
    // Pull container image
    image_pulled = pull_container_image(pod_spec.image)
    IF NOT image_pulled:
        LOG_ERROR("Failed to pull image: " + pod_spec.image)
        RETURN false
    
    // Prepare container configuration
    container_config = {
        image: pod_spec.image,
        env: pod_spec.environment,
        gpu_enabled: pod_spec.gpu_required,
        gpu_config: pod_spec.gpu_config,
        memory_limit: pod_spec.memory_limit,
        cpu_limit: pod_spec.cpu_limit,
        mounts: prepare_mounts(pod_spec.mounts),
        network_mode: "bridge"
    }
    
    // Create X11 virtual display
    IF pod_spec.gpu_required:
        container_config.env["DISPLAY"] = ":0"
        container_config.privileged = true  // For GPU access
    
    // Create and start container
    container_id = create_container(container_config)
    IF container_id IS NULL:
        LOG_ERROR("Failed to create container")
        RETURN false
    
    // Start the application inside container
    app_started = start_application_in_container(container_id, pod_spec.app_command)
    IF NOT app_started:
        LOG_ERROR("Failed to start application in container")
        stop_container(container_id)
        RETURN false
    
    // Store container ID with pod state
    update_pod_state(pod_id, {
        container_id: container_id,
        node: node,
        status: "STARTING"
    })
    
    RETURN true
```

### 3.5 Windows VM Pod Creation

```
FUNCTION create_windows_vm_pod(pod_id, node, pod_spec):
    INPUT: pod_id, node, pod_spec
    OUTPUT: success or failure
    
    // Prepare VM configuration
    vm_config = {
        os_type: "windows",
        cpu_cores: pod_spec.cpu_limit,
        memory_gb: pod_spec.memory_limit,
        gpu_passthrough: pod_spec.gpu_required,
        disk_size_gb: pod_spec.storage_limit,
        network: "bridge"
    }
    
    // Create VM disk from base image
    vm_disk_path = create_vm_disk_from_base(pod_spec.base_image, pod_spec.storage_limit)
    IF vm_disk_path IS NULL:
        LOG_ERROR("Failed to create VM disk")
        RETURN false
    
    // Configure GPU passthrough if required
    IF pod_spec.gpu_required:
        gpu_configured = configure_gpu_passthrough(vm_config)
        IF NOT gpu_configured:
            LOG_ERROR("Failed to configure GPU passthrough")
            cleanup_vm_disk(vm_disk_path)
            RETURN false
    
    // Create and start VM
    vm_id = create_vm(vm_config, vm_disk_path)
    IF vm_id IS NULL:
        LOG_ERROR("Failed to create VM")
        cleanup_vm_disk(vm_disk_path)
        RETURN false
    
    // Wait for VM to boot and install guest agent
    vm_ready = wait_for_vm_ready(vm_id)
    IF NOT vm_ready:
        LOG_ERROR("VM failed to become ready")
        destroy_vm(vm_id)
        cleanup_vm_disk(vm_disk_path)
        RETURN false
    
    // Start the application inside VM
    app_started = start_application_in_vm(vm_id, pod_spec.app_command)
    IF NOT app_started:
        LOG_ERROR("Failed to start application in VM")
        destroy_vm(vm_id)
        cleanup_vm_disk(vm_disk_path)
        RETURN false
    
    // Store VM ID with pod state
    update_pod_state(pod_id, {
        vm_id: vm_id,
        node: node,
        status: "STARTING"
    })
    
    RETURN true
```

### 3.6 Pod Startup and Streaming

```
FUNCTION start_pod_streaming(pod_id):
    INPUT: pod_id
    OUTPUT: success or failure
    
    // Get pod state
    pod_state = get_pod_state(pod_id)
    
    // Update state
    update_pod_state(pod_id, {status: "STREAMING"})
    
    // Start streaming agent based on pod type
    IF pod_state.container_id:
        streaming_agent = start_container_streaming_agent(pod_state.container_id)
    ELSE IF pod_state.vm_id:
        streaming_agent = start_vm_streaming_agent(pod_state.vm_id)
    
    IF streaming_agent IS NULL:
        LOG_ERROR("Failed to start streaming agent")
        update_pod_state(pod_id, {
            status: "FAILED",
            failure_reason: "Streaming agent failed to start"
        })
        RETURN false
    
    // Store streaming agent info
    update_pod_state(pod_id, {
        streaming_agent: streaming_agent,
        streaming_url: generate_streaming_url(pod_id),
        started_at: current_timestamp()
    })
    
    // Start monitoring and health checks
    start_pod_monitoring(pod_id)
    
    RETURN true
```

### 3.7 Pod Monitoring and Health Checks

```
FUNCTION start_pod_monitoring(pod_id):
    INPUT: pod_id
    
    // Start resource monitoring
    start_resource_monitoring(pod_id)
    
    // Start health checks
    start_health_checks(pod_id)
    
    // Start idle timeout monitoring
    start_idle_timeout_monitor(pod_id)
    
    // Start session duration monitoring
    start_session_duration_monitor(pod_id)

FUNCTION resource_monitoring_loop(pod_id):
    WHILE pod_is_running(pod_id):
        resources = get_pod_resources(pod_id)
        
        // Check for resource violations
        IF resources.vram_usage > resources.vram_limit * 0.95:
            trigger_resource_violation(pod_id, "VRAM over limit")
        
        IF resources.cpu_usage > resources.cpu_limit * 0.95:
            trigger_resource_violation(pod_id, "CPU over limit")
        
        IF resources.memory_usage > resources.memory_limit * 0.95:
            trigger_resource_violation(pod_id, "Memory over limit")
        
        SLEEP(5 seconds)  // Check every 5 seconds

FUNCTION health_check_loop(pod_id):
    WHILE pod_is_running(pod_id):
        health_status = check_pod_health(pod_id)
        
        IF health_status == "UNHEALTHY":
            update_pod_state(pod_id, {health_status: "UNHEALTHY"})
            // Optionally restart or terminate pod
            handle_unhealthy_pod(pod_id)
        
        SLEEP(30 seconds)  // Check every 30 seconds
```

### 3.8 Snapshot Creation

```
FUNCTION create_pod_snapshot(pod_id, snapshot_name, snapshot_type):
    INPUT: pod_id, snapshot_name, snapshot_type ("disk", "memory", "project")
    OUTPUT: snapshot_id or error
    
    // Validate pod is in streaming state
    pod_state = get_pod_state(pod_id)
    IF pod_state.status != "STREAMING":
        RETURN error("Pod must be in streaming state to create snapshot")
    
    // Pause pod temporarily for consistent snapshot
    pause_pod(pod_id)
    
    // Create snapshot based on type
    IF snapshot_type == "disk":
        snapshot_result = create_disk_snapshot(pod_id)
    ELSE IF snapshot_type == "memory":
        snapshot_result = create_memory_snapshot(pod_id)  // Advanced feature
    ELSE IF snapshot_type == "project":
        snapshot_result = create_project_snapshot(pod_id)
    ELSE:
        unpause_pod(pod_id)
        RETURN error("Invalid snapshot type")
    
    IF snapshot_result.success:
        // Store snapshot metadata
        snapshot_id = generate_unique_id()
        snapshot_metadata = {
            id: snapshot_id,
            pod_id: pod_id,
            name: snapshot_name,
            type: snapshot_type,
            created_at: current_timestamp(),
            size: snapshot_result.size,
            location: snapshot_result.location
        }
        
        store_snapshot_metadata(snapshot_metadata)
        
        // Resume pod
        unpause_pod(pod_id)
        
        // Update pod state
        add_snapshot_to_pod_state(pod_id, snapshot_metadata)
        
        RETURN snapshot_id
    ELSE:
        unpause_pod(pod_id)
        RETURN error("Snapshot creation failed: " + snapshot_result.error)
```

### 3.9 Pod Termination

```
FUNCTION terminate_pod(pod_id, termination_reason):
    INPUT: pod_id, termination_reason ("user_request", "timeout", "resource_violation", etc.)
    
    // Get current pod state
    pod_state = get_pod_state(pod_id)
    
    // Update state to terminating
    update_pod_state(pod_id, {
        status: "TERMINATING",
        termination_reason: termination_reason,
        terminating_at: current_timestamp()
    })
    
    // Stop streaming agent
    IF pod_state.streaming_agent:
        stop_streaming_agent(pod_state.streaming_agent)
    
    // Stop monitoring
    stop_pod_monitoring(pod_id)
    
    // Stop the pod based on type
    IF pod_state.container_id:
        stop_container(pod_state.container_id)
        cleanup_container_resources(pod_state.container_id)
    ELSE IF pod_state.vm_id:
        stop_vm(pod_state.vm_id)
        cleanup_vm_resources(pod_state.vm_id)
    
    // Release node resources
    release_node_resources(pod_state.node, pod_state.spec.resources)
    
    // Update final state
    update_pod_state(pod_id, {
        status: "TERMINATED",
        terminated_at: current_timestamp()
    })
    
    // Log termination
    log_pod_termination(pod_id, termination_reason)
```

### 3.10 Pod Cleanup and Resource Reclamation

```
FUNCTION cleanup_pod_resources(pod_id):
    INPUT: pod_id
    
    pod_state = get_pod_state(pod_id)
    
    // Clean up container resources if applicable
    IF pod_state.container_id:
        remove_container(pod_state.container_id)
        cleanup_container_volumes(pod_state.container_id)
    
    // Clean up VM resources if applicable
    IF pod_state.vm_id:
        delete_vm_disk(pod_state.vm_disk_path)
        cleanup_vm_network(pod_state.vm_id)
    
    // Clean up network resources
    cleanup_pod_network(pod_id)
    
    // Clean up any temporary files
    cleanup_temporary_files(pod_id)
    
    // Remove pod state from storage
    remove_pod_state(pod_id)
    
    LOG_INFO("Pod resources cleaned up: " + pod_id)

FUNCTION garbage_collect_old_pods():
    // Find terminated pods older than cleanup threshold
    old_pods = find_pods_with_status_older_than("TERMINATED", 24 hours)
    
    FOR each pod_id in old_pods:
        cleanup_pod_resources(pod_id)
```

### 3.11 Pod Restoration from Snapshot

```
FUNCTION restore_pod_from_snapshot(snapshot_id, user_request):
    INPUT: snapshot_id, user_request
    OUTPUT: new_pod_id or error
    
    // Get snapshot metadata
    snapshot_metadata = get_snapshot_metadata(snapshot_id)
    IF snapshot_metadata IS NULL:
        RETURN error("Snapshot not found")
    
    // Create new pod specification based on snapshot
    pod_spec = create_pod_spec_from_snapshot(snapshot_metadata, user_request)
    
    // Create new pod
    new_pod_id = generate_unique_id()
    
    // Initialize pod state
    pod_state = {
        id: new_pod_id,
        spec: pod_spec,
        status: "REQUESTED",
        created_at: current_timestamp(),
        user_id: user_request.user_id,
        restored_from_snapshot: snapshot_id
    }
    
    store_pod_state(new_pod_id, pod_state)
    
    // Queue for scheduling
    request_queue.enqueue(pod_spec)
    
    RETURN new_pod_id

FUNCTION create_pod_spec_from_snapshot(snapshot_metadata, user_request):
    INPUT: snapshot_metadata, user_request
    OUTPUT: pod_spec
    
    // Create pod spec based on original snapshot
    pod_spec = {
        app_type: snapshot_metadata.app_type,
        app_version: snapshot_metadata.app_version,
        gpu_required: snapshot_metadata.gpu_required,
        resources: snapshot_metadata.resources,
        environment: snapshot_metadata.environment,
        // Restore from snapshot instead of fresh install
        restore_from_snapshot: snapshot_metadata.id
    }
    
    RETURN pod_spec
```

## 4. Error Handling and Recovery

### 4.1 Pod Failure Handling

```
FUNCTION handle_pod_failure(pod_id, failure_reason):
    INPUT: pod_id, failure_reason
    
    pod_state = get_pod_state(pod_id)
    
    // Log failure
    log_pod_failure(pod_id, failure_reason)
    
    // Update state
    update_pod_state(pod_id, {
        status: "FAILED",
        failure_reason: failure_reason,
        failed_at: current_timestamp()
    })
    
    // Perform cleanup
    cleanup_pod_resources(pod_id)
    
    // Trigger any necessary notifications
    notify_user_of_failure(pod_state.user_id, pod_id, failure_reason)
```

### 4.2 Node Failure Handling

```
FUNCTION handle_node_failure(node_id):
    INPUT: node_id
    
    // Get all pods assigned to failed node
    affected_pods = get_pods_on_node(node_id)
    
    FOR each pod_id in affected_pods:
        pod_state = get_pod_state(pod_id)
        
        // Mark pod as failed due to node failure
        update_pod_state(pod_id, {
            status: "FAILED",
            failure_reason: "Node failure: " + node_id,
            failed_at: current_timestamp()
        })
        
        // Attempt to reschedule if possible
        IF pod_state.spec.can_reschedule:
            reschedule_pod(pod_id)
        ELSE:
            cleanup_pod_resources(pod_id)
```

This pseudocode provides a comprehensive framework for managing the complete lifecycle of disposable compute pods, from initial request through scheduling, provisioning, streaming, snapshot creation, and termination.