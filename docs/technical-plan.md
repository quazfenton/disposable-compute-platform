# Disposable Interactive Desktop Compute as a Service
## Technical Plan

### 1. Executive Summary

This document outlines the technical architecture for a "Disposable Interactive Desktop Compute as a Service" platform. The platform enables users to run native Windows/Mac/Linux desktop applications (such as TouchDesigner, Unreal Engine 5, etc.) inside ephemeral disposable compute pods, with Docker-based isolation, reloadable workloads, and a non-overloaded core VM.

The platform streams the desktop application UI to the browser without requiring local installation, ensuring fast spin-up, hard isolation, and automatic teardown of compute resources.

### 2. Core Design Goals

#### Primary Objectives
- Run native Windows/Mac/Linux desktop apps in disposable containers/VMs
- Stream UI to the browser (no local install)
- Ensure fast spin-up, hard isolation, automatic teardown
- Reloadable workloads (snapshots, project state restore)
- Keep host/core VM lightweight
- Horizontal scale across machines/regions

#### Non-Goals
- Persistent user desktops
- Multi-tenant GUI sharing inside a single container

### 3. High-Level Architecture

```
Browser
  │
  ├── WebRTC / QUIC Stream (video + input)
  │
API Gateway (Control Plane)
  │
  ├── Auth / Session Manager
  ├── Pod Orchestrator
  ├── Snapshot Registry
  │
Compute Cluster
  │
  ├── Core Host VMs (minimal OS)
  │     ├── GPU Passthrough / vGPU
  │     ├── Container Runtime
  │     └── Hypervisor (optional)
  │
  ├── Disposable Compute Pods
  │     ├── Desktop App Container/VM
  │     ├── Streaming Agent
  │     └── Ephemeral Filesystem
```

### 4. Container vs VM Reality (Critical)

> TouchDesigner & UE5 cannot realistically run in Linux containers alone

#### Correct approach:
- App Type: Isolation
- Linux GUI apps: Docker + X11/Wayland
- Windows apps: Windows VM per pod
- Mac apps: Mac bare-metal or Apple HVF VM

#### Unified abstraction:
> Every "pod" is either:
- a container
- a microVM (Firecracker / Hyper-V / QEMU)

All treated identically by orchestration.

### 5. Pod Types

#### A. Linux Desktop Pod (Fastest)
- Docker container
- Xvfb / Wayland
- GPU via NVIDIA Container Toolkit
- Apps: Blender, Linux TouchDesigner

#### B. Windows Desktop Pod (UE5, TouchDesigner)
- Windows Server Core / Windows 11 image
- Hyper-V / KVM / QEMU
- GPU passthrough or vGPU
- Docker inside VM optional

#### C. Mac Desktop Pod
- macOS VM (Apple Silicon only)
- Bare metal allocation (no oversubscription)

### 6. Disposable Pod Lifecycle

Request → Schedule → Boot → Stream → Snapshot (optional) → Destroy

#### Steps
1. User selects app + version
2. API requests pod
3. Scheduler picks least-loaded host
4. Pod boots from golden base image
5. Streaming agent starts
6. Browser connects
7. On exit:
   - Destroy pod
   - OR snapshot state
   - OR export project files

### 7. Reloadable Workloads (Key Feature)

#### Snapshot Types
| Snapshot Type | Use |
|---------------|-----|
| Disk snapshot | Resume app state |
| Project bundle | Reload content only |
| Memory snapshot | Ultra-fast resume (advanced) |

#### Implementation

##### Disk Snapshot
- ZFS / Btrfs / qcow2 backing files
- Copy-on-write
- ~1–5s restore

##### Memory Snapshot (Advanced)
- Firecracker VM snapshots
- QEMU savevm
- App resumes instantly (experimental)

### 8. Core VM Protection (No Overload)

#### Strict resource isolation
- CPU pinning
- GPU slices
- RAM hard limits
- IO throttling

#### Scheduler constraints
- Never overcommit GPU VRAM
- Predict UE5 load via profile
- Drain host before overload

#### Core VM services only:
- Container runtime
- VM launcher
- Metrics agent
- No user workloads

### 9. Streaming Stack (Browser UI)

#### Recommended
- WebRTC + GPU hardware encoding

#### Components
- NVENC / AMF / VideoToolbox
- WebRTC SFU or direct P2P
- Input capture (mouse, keyboard, gamepad)

#### Options
| Tool | Notes |
|------|-------|
| Sunshine + Moonlight | Extremely low latency |
| WebRTC + GStreamer | Custom control |
| NICE DCV | Enterprise-grade |
| Parsec | Proprietary |

### 10. Storage Model

#### Ephemeral by default
- tmpfs / overlayfs
- Destroyed after session

#### Persistent options
- Object storage (S3 / R2)
- Network block storage
- Git-like project snapshots

#### Data Flow
User Upload → Object Store → Mounted at Runtime

### 11. Orchestration Layer

#### Not plain Kubernetes
- GUI + GPU + VMs ≠ K8s native

#### Hybrid orchestrator
- Custom scheduler
- Firecracker / QEMU driver
- Docker runtime
- GPU awareness

#### Control Plane Services
- Session API
- Resource scheduler
- Image registry
- Snapshot registry

### 12. Security Model

#### Hard isolation
- No shared kernel for Windows/Mac
- No shared home directories
- One user per pod

#### Network sandbox
- No inbound ports
- Egress allow-list
- DNS isolation

#### Auto-destroy on:
- Idle timeout
- Network abuse
- Resource breach

### 13. Image Strategy

#### Golden Images
- Pre-installed apps
- Pre-compiled shaders
- Cached assets

#### Layering
```
Base OS
  └── App Layer
        └── User Project
```

#### Image size optimization
- Deduplicated blocks
- Read-only base
- Writable overlay

### 14. Example Pod Stack (Windows UE5)

```
Host VM
 ├── Hypervisor
 ├── GPU Driver
 ├── Pod VM
 │    ├── Windows 11
 │    ├── UE5 Installed
 │    ├── NVENC Stream Agent
 │    └── Project Mount
```

### 15. Scaling Strategy

#### Horizontal
- Add more hosts
- Regional clusters
- GPU pools

#### Vertical
- Larger GPU instances
- Multi-GPU pods (rare)

#### Burst
- Cold pool of pre-booted VMs
- Warm snapshot restores

### 16. Failure & Recovery

| Failure | Handling |
|---------|----------|
| Pod crash | Restart from snapshot |
| Host overload | Drain + reschedule |
| GPU fault | Evict host |
| Stream drop | Reconnect without pod reset |

### 17. What Makes This Hard (Reality Check)

- Windows GPU passthrough stability
- UE5 shader compile times
- Licensing compliance
- macOS legal constraints
- Memory snapshots at scale