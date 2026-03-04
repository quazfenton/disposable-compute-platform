# Technical Plan V2: Production Readiness & Advanced Integrations

This plan outlines the next phase of development for the Disposable Compute Platform, focusing on replacing mock implementations, hardening security, and wiring advanced SDK integrations.

## 1. Core Infrastructure Hardening

### 1.1 Triggering Preemption in Scheduler
- **File**: `src/scheduler/scheduler.py`
- **Action**: Modify `_try_preemption` to actually invoke `orchestrator.destroy_pod` on the candidates.
- **Code Change**:
```python
async def _try_preemption(self, request: PodRequest, nodes: List[Node], ...):
    for node in nodes:
        candidates = self.preemption_manager.find_preemption_candidates(node, request)
        if candidates:
            for pod_id in candidates:
                await self.orchestrator.destroy_pod(pod_id)
                self.unschedule(pod_id)
            # Re-attempt reservation after clearing space
            if self.resource_manager.reserve(node, request):
                return True, "Preempted and scheduled", node.id
```

### 1.2 Real Docker Build in Run-Repo
- **File**: `src/services/run_repo.py`
- **Action**: Implement `ImageBuilder.build_image_for_repo` using the Docker SDK.
- **Requirement**: Needs `git` installed on the host or a cloning utility.

## 2. Advanced SDK & AI Integration

### 2.1 Wiring Composio for Agentic Environments
- **File**: `src/ai/environment_generator.py`
- **Action**: Refactor to use `Composio` and `OpenAIProvider`.
- **New Capability**: Enable the agent to use the `GITHUB` toolkit to clone and inspect repositories before generating the `docker-compose.yml`.

### 2.2 Dynamic .preview.yaml Parsing
- **File**: `src/services/preview.py`
- **Action**: Use `GitPython` or a subprocess to clone the repo and parse the actual `.preview.yaml`.

## 3. Networking & Security Refinement

### 3.1 Nginx Ingress Controller Integration
- **File**: `src/networking/router.py`
- **Action**: Generate Nginx configuration blocks for each registered route and reload Nginx.

### 3.2 Real Runtime Monitoring
- **File**: `src/utils/security_enhanced.py`
- **Action**: Integrate with `falco` or `trivy` CLI for actual runtime security event detection instead of `secrets.randbelow(10)`.

## 4. Implementation Steps (Phased)

### Phase 1: AI & Service Gaps (Immediate)
1. Refactor `EnvironmentGenerator` with Composio.
2. Implement actual Git cloning in `PreviewConfig`.
3. Fix `RuntimeDetector` to check for specific files.

### Phase 2: Infrastructure & Scheduling
1. Complete the Preemption loop.
2. Implement real image building in `run_repo`.

### Phase 3: Networking & GUI
1. Replace GUI mock adapters with actual state capture logic.
2. Implement Nginx config generation.
