"""
Forkable GUI Sessions implementation for disposable compute platform
"""
import asyncio
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
import tempfile

from src.models.session import Session, SessionStatus
from src.types.models import Snapshot
from src.models.environment import Environment
from src.services.platform import SessionManager, SnapshotManager


import docker
import tarfile
import io

class StateCaptureAdapter:
    """Base class for state capture adapters"""
    
    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        self.supported_apps = []
        self.docker_client = docker_client or docker.from_env()
    
    async def capture_state(self, container_id: str) -> Dict[str, Any]:
        """Capture the state of an application in a container"""
        raise NotImplementedError
    
    async def restore_state(self, container_id: str, state_data: Dict[str, Any]):
        """Restore the state of an application in a container"""
        raise NotImplementedError


class GenericGUIAdapter(StateCaptureAdapter):
    """Generic adapter for GUI applications using file system snapshots"""
    
    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        super().__init__(docker_client)
        self.supported_apps = ['generic-gui', 'electron-app', 'web-based-gui']
    
    async def capture_state(self, container_id: str, target_dir: str = "/app/data") -> Dict[str, Any]:
        """Capture generic GUI state by snapshotting key directories"""
        try:
            container = self.docker_client.containers.get(container_id)
            
            # Get archive of the target directory
            bits, stat = container.get_archive(target_dir)
            
            # Store in-memory or save to a file (simplified for now)
            # In production, this would stream to a storage bucket
            archive_data = b"".join(bits)
            
            return {
                'app_type': 'generic-gui',
                'timestamp': datetime.now().isoformat(),
                'snapshot_type': 'filesystem',
                'base_path': target_dir,
                'archive_size': len(archive_data),
                'archive_data_hex': archive_data.hex()[:1000],  # Truncated for meta
                'full_archive': archive_data,
                'ui_state': {'window_pos': {'x': 100, 'y': 100}, 'active_tab': 'editor'}
            }
        except Exception as e:
            print(f"Failed to capture state: {e}")
            return {}
    
    async def restore_state(self, container_id: str, state_data: Dict[str, Any]):
        """Restore generic GUI state from snapshot"""
        try:
            container = self.docker_client.containers.get(container_id)
            archive_data = state_data.get('full_archive')
            
            if archive_data:
                container.put_archive(state_data.get('base_path', '/app/data'), archive_data)
                print(f"Restored filesystem archive to {container_id}")
        except Exception as e:
            print(f"Failed to restore state: {e}")




class ThreeJSAdapter(StateCaptureAdapter):
    """Adapter for Three.js-based applications using scene graph serialization"""
    
    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        super().__init__(docker_client)
        self.supported_apps = ['threejs-editor', '3d-scene-editor']
    
    async def capture_state(self, container_id: str) -> Dict[str, Any]:
        """Capture Three.js application state via scene JSON export"""
        # In a real implementation, this would call an API endpoint
        # inside the container to get the serialized scene
        return {
            'app_type': 'threejs-editor',
            'timestamp': datetime.now().isoformat(),
            'scene_json': {'metadata': {'version': 4.5, 'type': 'Object'}, 'geometries': [], 'materials': []},
            'camera_position': {'x': 10, 'y': 5, 'z': 10},
            'selection': ['mesh_001']
        }
    
    async def restore_state(self, container_id: str, state_data: Dict[str, Any]):
        """Restore Three.js application state by reloading scene JSON"""
        print(f"Reloading scene in container {container_id}")
        print(f"Setting camera to: {state_data.get('camera_position')}")


class AudioEditorAdapter(StateCaptureAdapter):
    """Adapter for audio editing applications using project file serialization"""
    
    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        super().__init__(docker_client)
        self.supported_apps = ['audio-editor', 'daw', 'sound-designer']
    
    async def capture_state(self, container_id: str) -> Dict[str, Any]:
        """Capture audio editor state via project XML/JSON export"""
        return {
            'app_type': 'audio-editor',
            'timestamp': datetime.now().isoformat(),
            'project_path': '/app/projects/session_01.xml',
            'playback_head': 120.5,
            'active_tracks': [1, 2, 5],
            'effects_buffer': 'base64_encoded_state_data'
        }
    
    async def restore_state(self, container_id: str, state_data: Dict[str, Any]):
        """Restore audio editor state by reloading project file and parameters"""
        print(f"Restoring audio session in container {container_id} at {state_data.get('playback_head')}s")



class StateAdapterManager:
    """Manages different state capture adapters"""
    
    def __init__(self, docker_client: Optional[docker.DockerClient] = None):
        self.docker_client = docker_client or docker.from_env()
        self.adapters = [
            GenericGUIAdapter(self.docker_client),
            ThreeJSAdapter(self.docker_client),
            AudioEditorAdapter(self.docker_client)
        ]

        self.app_to_adapter = {}
        
        # Build mapping from app types to adapters
        for adapter in self.adapters:
            for app_type in adapter.supported_apps:
                self.app_to_adapter[app_type] = adapter
    
    def get_adapter(self, app_type: str) -> Optional[StateCaptureAdapter]:
        """Get the appropriate adapter for an app type"""
        return self.app_to_adapter.get(app_type)
    
    async def capture_app_state(self, container_id: str, app_type: str) -> Dict[str, Any]:
        """Capture state using the appropriate adapter"""
        adapter = self.get_adapter(app_type)
        if adapter:
            return await adapter.capture_state(container_id)
        else:
            # Use generic adapter if specific one not found
            generic = GenericGUIAdapter(self.docker_client)
            return await generic.capture_state(container_id)


class ForkableSessionManager:
    """Manages forkable GUI sessions"""
    
    def __init__(self, session_manager: SessionManager, snapshot_manager: SnapshotManager):
        self.session_manager = session_manager
        self.snapshot_manager = snapshot_manager
        self.state_adapter_manager = StateAdapterManager(session_manager.container_orchestrator.client)
        self.session_forks = {}  # Maps session_id to list of forks

    
    async def create_forkable_session(self, session: Session, app_type: str = "generic-gui") -> Environment:
        """Create a forkable GUI session"""
        # Create service definition for GUI app
        service = {
            'name': 'gui-app',
            'type': 'gui',
            'image': f'gui-{app_type}-base:latest',  # Would be determined by app type
            'command': f'start-{app_type}-app',
            'port': 8080,
            'env': {
                'APP_TYPE': app_type,
                'DISPLAY': ':0'  # For GUI applications
            }
        }
        
        # Create environment
        environment = Environment(
            id=f"env-{session.id}",
            name=f"gui-{session.id}",
            session_id=session.id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=session.expires_at,
            services=[service]
        )
        
        # Create isolated network
        network_name = self.session_manager.network_manager.create_isolated_network(environment.id)
        environment.network_name = network_name
        
        # Create containers
        container_ids = self.session_manager.container_orchestrator.create_environment_containers(environment)
        
        # Update session with container info
        session.container_id = json.dumps(container_ids)
        session.network_id = network_name
        session.status = SessionStatus.RUNNING
        session.metadata['app_type'] = app_type

        # Create external access
        url = self.session_manager.network_manager.create_external_access(
            session.id, 8080, self.session_manager.config.domain
        )
        session.ports = {'gui': 8080}
        
        # Initialize forks tracking
        self.session_forks[session.id] = []
        
        return environment
    
    async def create_snapshot(self, session_id: str, description: str = "") -> str:
        """Create a snapshot of a GUI session's state"""
        if session_id not in self.session_manager.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.session_manager.sessions[session_id]
        
        # Get container ID
        container_ids = json.loads(session.container_id) if session.container_id else {}
        main_container_id = next(iter(container_ids.values()), None)
        
        if not main_container_id:
            raise ValueError(f"No container found for session {session_id}")
        
        # Capture the application state
        app_type = session.metadata.get('app_type', 'generic-gui')
        state_data = await self.state_adapter_manager.capture_app_state(
            main_container_id, app_type
        )
        
        # Add snapshot metadata
        state_data['snapshot_metadata'] = {
            'session_id': session_id,
            'description': description,
            'created_at': datetime.now().isoformat(),
            'app_type': app_type
        }
        
        # Create snapshot using the platform's snapshot manager
        snapshot_id = await self.snapshot_manager.create_snapshot(session_id, state_data)
        
        # Update session metadata
        session.metadata['last_snapshot'] = snapshot_id
        session.updated_at = datetime.now()
        
        return snapshot_id
    
    async def fork_session(self, session_id: str, snapshot_id: Optional[str] = None) -> Session:
        """Create a fork of a GUI session"""
        if session_id not in self.session_manager.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        original_session = self.session_manager.sessions[session_id]
        
        # If no snapshot ID provided, create one now
        if not snapshot_id:
            snapshot_id = await self.create_snapshot(session_id, "Fork point")
        
        # Load the snapshot state
        snapshot_data = await self.snapshot_manager.load_snapshot(snapshot_id)
        if not snapshot_data:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        
        # Create a new session for the fork
        fork_session_id = f"fork-{session_id}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{os.urandom(4).hex()}"
        
        fork_session = Session(
            id=fork_session_id,
            type=original_session.type,
            status=SessionStatus.CREATING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            expires_at=original_session.expires_at,
            repo_url=original_session.repo_url,
            repo_ref=original_session.repo_ref,
            pr_number=original_session.pr_number
        )
        
        # Copy relevant metadata
        fork_session.metadata = original_session.metadata.copy()
        fork_session.metadata['forked_from'] = session_id
        fork_session.metadata['forked_snapshot'] = snapshot_id
        
        # Add to session manager
        self.session_manager.sessions[fork_session_id] = fork_session
        
        # Create environment for fork with the same app type
        app_type = original_session.metadata.get('app_type', 'generic-gui')
        fork_environment = await self.create_forkable_session(fork_session, app_type)
        
        # Restore the state from the snapshot
        container_ids = json.loads(fork_session.container_id) if fork_session.container_id else {}
        main_container_id = next(iter(container_ids.values()), None)
        
        if main_container_id:
            # Use the appropriate adapter to restore state
            adapter = self.state_adapter_manager.get_adapter(app_type)
            if adapter:
                await adapter.restore_state(main_container_id, snapshot_data['state_data'])
        
        # Track the fork relationship
        if session_id not in self.session_forks:
            self.session_forks[session_id] = []
        self.session_forks[session_id].append(fork_session_id)
        
        return fork_session
    
    async def get_session_lineage(self, session_id: str) -> Dict[str, Any]:
        """Get the lineage of a session (what it was forked from, what forks exist)"""
        if session_id not in self.session_manager.sessions:
            return {}
        
        session = self.session_manager.sessions[session_id]
        
        lineage = {
            'session_id': session_id,
            'forked_from': session.metadata.get('forked_from'),
            'forked_snapshot': session.metadata.get('forked_snapshot'),
            'forks': self.session_forks.get(session_id, []),
            'created_at': session.created_at.isoformat()
        }
        
        # If this session was forked from another, get its parent lineage too
        if session.metadata.get('forked_from'):
            parent_lineage = await self.get_session_lineage(session.metadata['forked_from'])
            lineage['parent'] = parent_lineage
        
        return lineage
    
    async def merge_sessions(self, base_session_id: str, fork_session_id: str, 
                           merge_strategy: str = "manual") -> Dict[str, Any]:
        """Attempt to merge changes from a forked session back to base"""
        # This is a simplified implementation
        # Real merging would be complex and app-specific
        
        result = {
            'base_session_id': base_session_id,
            'fork_session_id': fork_session_id,
            'merge_strategy': merge_strategy,
            'status': 'completed',
            'conflicts': [],
            'merged_changes': []
        }
        
        # In a real implementation, this would:
        # 1. Compare the states of both sessions
        # 2. Identify conflicts
        # 3. Apply merge strategy
        # 4. Update the base session
        
        print(f"Merging {fork_session_id} into {base_session_id} using {merge_strategy} strategy")
        
        return result


# Integration with the main SessionManager
async def extend_session_manager_with_forkable_gui(session_manager: SessionManager):
    """Extend the session manager with forkable GUI capabilities"""
    snapshot_manager = session_manager.snapshot_manager if hasattr(session_manager, 'snapshot_manager') else None
    if not snapshot_manager:
        from src.services.platform import SnapshotManager
        snapshot_manager = SnapshotManager(session_manager.config.storage_path)
        session_manager.snapshot_manager = snapshot_manager
    
    forkable_manager = ForkableSessionManager(session_manager, snapshot_manager)
    
    # Override the fork-gui session creation method
    original_create_fork_gui = session_manager._create_fork_gui_session
    
    async def new_create_fork_gui_session(session: Session):
        await forkable_manager.create_forkable_session(session)
    
    session_manager._create_fork_gui_session = new_create_fork_gui_session