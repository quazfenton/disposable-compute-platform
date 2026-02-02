"""
Storage management for disposable compute platform
"""
import asyncio
import os
import shutil
import tempfile
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import hashlib
import json
import aiofiles


@dataclass
class StorageVolume:
    """Represents a storage volume"""
    id: str
    name: str
    size_bytes: int
    used_bytes: int
    storage_class: str  # ssd, hdd, nvme, etc.
    path: str
    created_at: datetime
    attached_to_pod: Optional[str] = None
    readonly: bool = False
    encrypted: bool = False


@dataclass
class Snapshot:
    """Represents a storage snapshot"""
    id: str
    volume_id: str
    created_at: datetime
    size_bytes: int
    parent_snapshot_id: Optional[str] = None
    description: str = ""


@dataclass
class Backup:
    """Represents a backup of storage data"""
    id: str
    volume_id: str
    snapshot_id: str
    created_at: datetime
    destination: str  # s3://bucket/path, /backup/location, etc.
    status: str  # pending, in-progress, completed, failed
    size_bytes: int = 0


class VolumeManager:
    """Manages storage volumes for pods"""
    
    def __init__(self, base_storage_path: str = "/var/lib/disposable-storage"):
        self.base_storage_path = base_storage_path
        self.volumes: Dict[str, StorageVolume] = {}
        self.snapshots: Dict[str, Snapshot] = {}
        self.backups: Dict[str, Backup] = {}
        self.logger = logging.getLogger(__name__)
        
        # Create base storage directory if it doesn't exist
        os.makedirs(base_storage_path, exist_ok=True)
    
    async def create_volume(self, name: str, size_gb: int, storage_class: str = "ssd") -> StorageVolume:
        """Create a new storage volume"""
        volume_id = f"vol-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.urandom(4).hex()}"
        
        # Convert GB to bytes
        size_bytes = size_gb * 1024 * 1024 * 1024
        
        # Create volume directory
        volume_path = os.path.join(self.base_storage_path, volume_id)
        os.makedirs(volume_path, exist_ok=True)
        
        volume = StorageVolume(
            id=volume_id,
            name=name,
            size_bytes=size_bytes,
            used_bytes=0,
            storage_class=storage_class,
            path=volume_path,
            created_at=datetime.now()
        )
        
        self.volumes[volume_id] = volume
        self.logger.info(f"Created volume {volume_id} with size {size_gb}GB at {volume_path}")
        
        return volume
    
    async def attach_volume_to_pod(self, volume_id: str, pod_id: str) -> bool:
        """Attach a volume to a pod"""
        if volume_id not in self.volumes:
            self.logger.error(f"Volume {volume_id} not found")
            return False
        
        volume = self.volumes[volume_id]
        
        if volume.attached_to_pod:
            self.logger.error(f"Volume {volume_id} already attached to pod {volume.attached_to_pod}")
            return False
        
        volume.attached_to_pod = pod_id
        self.logger.info(f"Attached volume {volume_id} to pod {pod_id}")
        
        return True
    
    async def detach_volume_from_pod(self, volume_id: str, pod_id: str) -> bool:
        """Detach a volume from a pod"""
        if volume_id not in self.volumes:
            self.logger.error(f"Volume {volume_id} not found")
            return False
        
        volume = self.volumes[volume_id]
        
        if volume.attached_to_pod != pod_id:
            self.logger.error(f"Volume {volume_id} not attached to pod {pod_id}")
            return False
        
        volume.attached_to_pod = None
        self.logger.info(f"Detached volume {volume_id} from pod {pod_id}")
        
        return True
    
    async def delete_volume(self, volume_id: str) -> bool:
        """Delete a storage volume"""
        if volume_id not in self.volumes:
            self.logger.error(f"Volume {volume_id} not found")
            return False
        
        volume = self.volumes[volume_id]
        
        if volume.attached_to_pod:
            self.logger.error(f"Cannot delete volume {volume_id} - still attached to pod {volume.attached_to_pod}")
            return False
        
        # Remove the volume directory
        try:
            shutil.rmtree(volume.path)
        except OSError as e:
            self.logger.error(f"Error deleting volume directory {volume.path}: {e}")
            return False
        
        # Remove from tracking
        del self.volumes[volume_id]
        self.logger.info(f"Deleted volume {volume_id}")
        
        return True
    
    async def resize_volume(self, volume_id: str, new_size_gb: int) -> bool:
        """Resize a storage volume (only increase size)"""
        if volume_id not in self.volumes:
            self.logger.error(f"Volume {volume_id} not found")
            return False
        
        volume = self.volumes[volume_id]
        new_size_bytes = new_size_gb * 1024 * 1024 * 1024
        
        if new_size_bytes < volume.size_bytes:
            self.logger.error(f"Cannot shrink volume {volume_id} from {volume.size_bytes} to {new_size_bytes}")
            return False
        
        # Update size
        volume.size_bytes = new_size_bytes
        self.logger.info(f"Resized volume {volume_id} to {new_size_gb}GB")
        
        return True
    
    async def get_volume_usage(self, volume_id: str) -> Optional[Dict[str, int]]:
        """Get usage statistics for a volume"""
        if volume_id not in self.volumes:
            return None
        
        volume = self.volumes[volume_id]
        
        # Calculate actual used space
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(volume.path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except OSError:
                    continue  # Skip files that can't be accessed
        
        volume.used_bytes = total_size
        
        return {
            "total_bytes": volume.size_bytes,
            "used_bytes": volume.used_bytes,
            "free_bytes": volume.size_bytes - volume.used_bytes
        }


class SnapshotManager:
    """Manages storage snapshots"""
    
    def __init__(self, volume_manager: VolumeManager):
        self.volume_manager = volume_manager
        self.logger = logging.getLogger(__name__)
    
    async def create_snapshot(self, volume_id: str, description: str = "") -> Optional[Snapshot]:
        """Create a snapshot of a volume"""
        if volume_id not in self.volume_manager.volumes:
            self.logger.error(f"Volume {volume_id} not found")
            return None
        
        volume = self.volume_manager.volumes[volume_id]
        
        if volume.attached_to_pod:
            self.logger.warning(f"Creating snapshot of volume {volume_id} while attached to pod {volume.attached_to_pod}")
        
        snapshot_id = f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.urandom(4).hex()}"
        
        # Get volume usage to determine snapshot size
        usage = await self.volume_manager.get_volume_usage(volume_id)
        size_bytes = usage["used_bytes"] if usage else 0
        
        snapshot = Snapshot(
            id=snapshot_id,
            volume_id=volume_id,
            created_at=datetime.now(),
            size_bytes=size_bytes,
            description=description
        )
        
        self.volume_manager.snapshots[snapshot_id] = snapshot
        self.logger.info(f"Created snapshot {snapshot_id} of volume {volume_id}")
        
        return snapshot
    
    async def restore_snapshot(self, snapshot_id: str, new_volume_name: str, size_gb: Optional[int] = None) -> Optional[StorageVolume]:
        """Restore a snapshot to a new volume"""
        if snapshot_id not in self.volume_manager.snapshots:
            self.logger.error(f"Snapshot {snapshot_id} not found")
            return None
        
        snapshot = self.volume_manager.snapshots[snapshot_id]
        
        # Use snapshot size if no size specified
        if size_gb is None:
            size_gb = snapshot.size_bytes // (1024 * 1024 * 1024) + 1  # Convert to GB and add 1GB buffer
        
        # Create new volume
        new_volume = await self.volume_manager.create_volume(new_volume_name, size_gb)
        
        # Copy snapshot data to new volume
        # In a real implementation, this would use more efficient methods like reflinks or copy-on-write
        snapshot_path = os.path.join(self.volume_manager.base_storage_path, snapshot.volume_id)
        new_volume_path = new_volume.path
        
        try:
            # Copy all files from snapshot volume to new volume
            if os.path.exists(snapshot_path):
                for item in os.listdir(snapshot_path):
                    s = os.path.join(snapshot_path, item)
                    d = os.path.join(new_volume_path, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d)
                    else:
                        shutil.copy2(s, d)
        except Exception as e:
            self.logger.error(f"Error restoring snapshot {snapshot_id}: {e}")
            # Clean up the partially created volume
            await self.volume_manager.delete_volume(new_volume.id)
            return None
        
        self.logger.info(f"Restored snapshot {snapshot_id} to new volume {new_volume.id}")
        
        return new_volume
    
    async def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot"""
        if snapshot_id not in self.volume_manager.snapshots:
            self.logger.error(f"Snapshot {snapshot_id} not found")
            return False
        
        del self.volume_manager.snapshots[snapshot_id]
        self.logger.info(f"Deleted snapshot {snapshot_id}")
        
        return True


class BackupManager:
    """Manages backups of storage volumes"""
    
    def __init__(self, volume_manager: VolumeManager, snapshot_manager: SnapshotManager):
        self.volume_manager = volume_manager
        self.snapshot_manager = snapshot_manager
        self.backup_locations = {}
        self.logger = logging.getLogger(__name__)
    
    async def configure_backup_location(self, name: str, location: str, credentials: Optional[Dict] = None):
        """Configure a backup location"""
        self.backup_locations[name] = {
            "location": location,
            "credentials": credentials,
            "configured_at": datetime.now()
        }
        self.logger.info(f"Configured backup location {name} at {location}")
    
    async def create_backup(self, volume_id: str, location_name: str, snapshot_description: str = "") -> Optional[Backup]:
        """Create a backup of a volume to a configured location"""
        if location_name not in self.backup_locations:
            self.logger.error(f"Backup location {location_name} not configured")
            return None
        
        # First create a snapshot
        snapshot = await self.snapshot_manager.create_snapshot(volume_id, snapshot_description)
        if not snapshot:
            return None
        
        backup_id = f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.urandom(4).hex()}"
        
        backup = Backup(
            id=backup_id,
            volume_id=volume_id,
            snapshot_id=snapshot.id,
            created_at=datetime.now(),
            destination=self.backup_locations[location_name]["location"],
            status="pending"
        )
        
        self.volume_manager.backups[backup_id] = backup
        
        # Perform the backup asynchronously
        asyncio.create_task(self._perform_backup(backup_id))
        
        self.logger.info(f"Started backup {backup_id} of volume {volume_id} to {location_name}")
        
        return backup
    
    async def _perform_backup(self, backup_id: str):
        """Actually perform the backup operation"""
        if backup_id not in self.volume_manager.backups:
            return
        
        backup = self.volume_manager.backups[backup_id]
        backup.status = "in-progress"
        
        try:
            # In a real implementation, this would upload to the backup destination
            # For now, we'll simulate the operation
            
            # Get the snapshot data
            snapshot = self.volume_manager.snapshots[backup.snapshot_id]
            volume = self.volume_manager.volumes[backup.volume_id]
            
            # Simulate backup process
            await asyncio.sleep(2)  # Simulate time for backup
            
            # Update backup status
            backup.status = "completed"
            backup.size_bytes = snapshot.size_bytes
            
            self.logger.info(f"Completed backup {backup_id}")
            
        except Exception as e:
            backup.status = "failed"
            self.logger.error(f"Backup {backup_id} failed: {e}")
    
    async def restore_backup(self, backup_id: str, new_volume_name: str) -> Optional[StorageVolume]:
        """Restore a backup to a new volume"""
        if backup_id not in self.volume_manager.backups:
            self.logger.error(f"Backup {backup_id} not found")
            return None
        
        backup = self.volume_manager.backups[backup_id]
        
        if backup.status != "completed":
            self.logger.error(f"Cannot restore backup {backup_id} - status is {backup.status}")
            return None
        
        # Restore from the associated snapshot
        return await self.snapshot_manager.restore_snapshot(backup.snapshot_id, new_volume_name)
    
    async def get_backup_status(self, backup_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a backup"""
        if backup_id not in self.volume_manager.backups:
            return None
        
        backup = self.volume_manager.backups[backup_id]
        return {
            "id": backup.id,
            "volume_id": backup.volume_id,
            "snapshot_id": backup.snapshot_id,
            "destination": backup.destination,
            "status": backup.status,
            "size_bytes": backup.size_bytes,
            "created_at": backup.created_at.isoformat()
        }


class StorageManager:
    """Main storage manager that coordinates all storage operations"""
    
    def __init__(self, base_storage_path: str = "/var/lib/disposable-storage"):
        self.volume_manager = VolumeManager(base_storage_path)
        self.snapshot_manager = SnapshotManager(self.volume_manager)
        self.backup_manager = BackupManager(self.volume_manager, self.snapshot_manager)
        self.logger = logging.getLogger(__name__)
    
    async def initialize(self):
        """Initialize the storage manager"""
        self.logger.info(f"Initialized storage manager with base path: {self.volume_manager.base_storage_path}")
    
    async def create_ephemeral_volume(self, pod_id: str, size_gb: int) -> Optional[StorageVolume]:
        """Create an ephemeral volume for a pod"""
        volume_name = f"ephemeral-{pod_id}"
        volume = await self.volume_manager.create_volume(volume_name, size_gb, "ssd")
        
        if volume:
            await self.volume_manager.attach_volume_to_pod(volume.id, pod_id)
        
        return volume
    
    async def create_persistent_volume(self, name: str, size_gb: int, storage_class: str = "ssd") -> Optional[StorageVolume]:
        """Create a persistent volume"""
        return await self.volume_manager.create_volume(name, size_gb, storage_class)
    
    async def cleanup_pod_volumes(self, pod_id: str):
        """Clean up all volumes associated with a pod"""
        # Find volumes attached to this pod
        volumes_to_detach = [
            vol_id for vol_id, volume in self.volume_manager.volumes.items()
            if volume.attached_to_pod == pod_id
        ]
        
        for volume_id in volumes_to_detach:
            await self.volume_manager.detach_volume_from_pod(volume_id, pod_id)
            
            # For ephemeral volumes, delete them
            if self.volume_manager.volumes[volume_id].name.startswith(f"ephemeral-{pod_id}"):
                await self.volume_manager.delete_volume(volume_id)
    
    async def get_storage_usage(self) -> Dict[str, Any]:
        """Get overall storage usage statistics"""
        total_volumes = len(self.volume_manager.volumes)
        total_snapshots = len(self.volume_manager.snapshots)
        total_backups = len(self.volume_manager.backups)
        
        total_size = sum(vol.size_bytes for vol in self.volume_manager.volumes.values())
        total_used = sum(vol.used_bytes for vol in self.volume_manager.volumes.values())
        
        return {
            "total_volumes": total_volumes,
            "total_snapshots": total_snapshots,
            "total_backups": total_backups,
            "total_size_bytes": total_size,
            "total_used_bytes": total_used,
            "total_free_bytes": total_size - total_used,
            "volumes": {
                vol_id: {
                    "name": volume.name,
                    "size_bytes": volume.size_bytes,
                    "used_bytes": volume.used_bytes,
                    "attached_to_pod": volume.attached_to_pod
                }
                for vol_id, volume in self.volume_manager.volumes.items()
            }
        }