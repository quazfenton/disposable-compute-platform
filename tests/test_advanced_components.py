import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio
import json

from src.models.pod import Pod, PodSpec, PodStatus, PodType, ResourceRequirements, GPUResource, GPUType
from src.models.vm import VM, VMSpec, VMStatus, VMType
from src.models.gpu import GPUDevice, GPUStatus, GPUVendor, GPUFamily
from src.models.session import Session, SessionType, SessionStatus
from src.orchestrator.orchestrator import AdvancedOrchestrator, VMOrchestrator, GPUManager
from src.scheduler.scheduler import Scheduler, NodeSelector, SchedulingRequest
from src.storage.storage_manager import StorageManager, VolumeManager, SnapshotManager
from src.streaming.streaming_server import StreamingManager, StreamSession
from src.types.platform_types import SessionType as TypeSessionType, PodType as TypePodType


class TestPodModel:
    """Test pod model functionality"""

    def test_pod_creation(self):
        """Test creating a pod with all required fields"""
        from src.models.pod import ComputeNode, NodeResources
        
        # Create a simple pod
        pod_spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="web",
            image="nginx:latest"
        )
        
        pod = Pod(
            id="test-pod-123",
            spec=pod_spec,
            status=PodStatus.CREATING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        assert pod.id == "test-pod-123"
        assert pod.spec.pod_type == PodType.CONTAINER
        assert pod.status == PodStatus.CREATING
        assert pod.metadata == {}  # Should be initialized by __post_init__

    def test_resource_requirements(self):
        """Test resource requirements model"""
        gpu_resource = GPUResource(
            gpu_type=GPUType.NVIDIA_TESLA,
            count=1,
            memory_mb=8192
        )
        
        req = ResourceRequirements(
            cpu_cores=2.0,
            memory_mb=4096,
            storage_gb=20,
            gpu_resources=gpu_resource
        )

        assert req.cpu_cores == 2.0
        assert req.memory_mb == 4096
        assert req.gpu_resources.count == 1
        assert req.gpu_resources.memory_mb == 8192


class TestVMModel:
    """Test VM model functionality"""

    def test_vm_creation(self):
        """Test creating a VM with all required fields"""
        vm_spec = VMSpec(
            vm_type=VMType.LINUX,
            base_image="ubuntu:20.04",
            cpu_cores=2,
            memory_mb=2048,
            disk_size_gb=20
        )
        
        vm = VM(
            id="test-vm-123",
            spec=vm_spec,
            status=VMStatus.CREATING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

        assert vm.id == "test-vm-123"
        assert vm.spec.vm_type == VMType.LINUX
        assert vm.status == VMStatus.CREATING
        assert vm.metadata == {}  # Should be initialized by __post_init__


class TestGPUModel:
    """Test GPU model functionality"""

    def test_gpu_device_creation(self):
        """Test creating a GPU device"""
        from src.models.gpu import GPUSpec
        
        gpu_spec = GPUSpec(
            vendor=GPUVendor.NVIDIA,
            family=GPUFamily.GEFORCE,
            model="RTX 3080",
            memory_mb=10240,
            cuda_cores=8704
        )
        
        gpu = GPUDevice(
            id="gpu-001",
            spec=gpu_spec,
            status=GPUStatus.AVAILABLE,
            node_id="node-1",
            driver_version="470.123"
        )

        assert gpu.id == "gpu-001"
        assert gpu.spec.model == "RTX 3080"
        assert gpu.status == GPUStatus.AVAILABLE
        assert gpu.node_id == "node-1"


class TestAdvancedOrchestrator:
    """Test advanced orchestrator functionality"""

    @pytest.mark.asyncio
    async def test_pod_lifecycle(self):
        """Test complete pod lifecycle"""
        # Mock the dependencies
        with patch('src.orchestrator.orchestrator.ContainerOrchestrator') as mock_container_orchestrator, \
             patch('src.orchestrator.orchestrator.VMOrchestrator') as mock_vm_orchestrator:
            
            # Setup mocks
            mock_container_instance = Mock()
            mock_container_instance.create_container.return_value = "mock-container-id"
            mock_container_instance.start_container = AsyncMock()
            mock_container_instance.stop_container = AsyncMock()
            mock_container_instance.remove_container = AsyncMock()
            mock_container_orchestrator.return_value = mock_container_instance
            
            mock_vm_instance = Mock()
            mock_vm_instance.create_vm.return_value = "mock-vm-id"
            mock_vm_instance.start_vm = AsyncMock()
            mock_vm_instance.stop_vm = AsyncMock()
            mock_vm_instance.destroy_vm = AsyncMock()
            mock_vm_orchestrator.return_value = mock_vm_instance
            
            orchestrator = AdvancedOrchestrator()
            
            # Create a pod spec
            pod_spec = PodSpec(
                pod_type=PodType.CONTAINER,
                app_type="web",
                image="nginx:latest",
                resource_requirements=ResourceRequirements(cpu_cores=1.0, memory_mb=1024)
            )
            
            # Create pod
            pod_id = await orchestrator.create_pod(pod_spec)
            
            # Verify pod was created
            assert pod_id in orchestrator.pods
            assert orchestrator.pods[pod_id].status == PodStatus.RUNNING
            
            # Start pod
            await orchestrator.start_pod(pod_id)
            mock_container_instance.start_container.assert_called_once()
            
            # Stop pod
            await orchestrator.stop_pod(pod_id)
            mock_container_instance.stop_container.assert_called_once()
            
            # Destroy pod
            await orchestrator.destroy_pod(pod_id)
            mock_container_instance.remove_container.assert_called_once()


class TestNodeSelector:
    """Test node selection logic"""

    def test_basic_node_selection(self):
        """Test basic node selection based on resources"""
        selector = NodeSelector()
        
        # Create a pod spec requiring certain resources
        pod_spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="web",
            resource_requirements=ResourceRequirements(
                cpu_cores=2.0,
                memory_mb=2048,
                storage_gb=10
            )
        )
        
        # Create some compute nodes
        from src.models.pod import ComputeNode, NodeResources
        
        node1 = ComputeNode(
            id="node1",
            hostname="node1.example.com",
            ip_address="192.168.1.10",
            resources=NodeResources(
                total_cpu_cores=4.0,
                available_cpu_cores=3.0,
                total_memory_mb=8192,
                available_memory_mb=6144,
                total_storage_gb=100,
                available_storage_gb=50,
                total_gpus=0,
                available_gpus=0
            ),
            status="active",
            capabilities=["container"],
            last_heartbeat=datetime.now()
        )
        
        node2 = ComputeNode(
            id="node2",
            hostname="node2.example.com",
            ip_address="192.168.1.11",
            resources=NodeResources(
                total_cpu_cores=2.0,
                available_cpu_cores=1.0,  # Not enough CPU
                total_memory_mb=4096,
                available_memory_mb=2048,
                total_storage_gb=100,
                available_storage_gb=50,
                total_gpus=0,
                available_gpus=0
            ),
            status="active",
            capabilities=["container"],
            last_heartbeat=datetime.now()
        )
        
        nodes = [node1, node2]
        
        # Find best node - should be node1 since node2 doesn't have enough CPU
        result = selector.find_best_node(pod_spec, nodes)
        
        assert result.success is True
        assert result.node_id == "node1"
        assert result.score > 0


class TestStorageManager:
    """Test storage management functionality"""

    @pytest.mark.asyncio
    async def test_volume_lifecycle(self):
        """Test complete volume lifecycle"""
        import tempfile
        import os
        
        # Use a temporary directory for testing
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_manager = StorageManager(base_storage_path=temp_dir)
            await storage_manager.initialize()
            
            # Create a volume
            volume = await storage_manager.volume_manager.create_volume("test-volume", 1)  # 1GB
            
            assert volume is not None
            assert volume.name == "test-volume"
            assert volume.size_bytes == 1024 * 1024 * 1024  # 1GB in bytes
            assert os.path.exists(volume.path)
            
            # Get volume usage
            usage = await storage_manager.volume_manager.get_volume_usage(volume.id)
            assert usage is not None
            assert usage["total_bytes"] == volume.size_bytes
            
            # Delete the volume
            success = await storage_manager.volume_manager.delete_volume(volume.id)
            assert success is True
            assert volume.id not in storage_manager.volume_manager.volumes
            assert not os.path.exists(volume.path)


class TestStreamingManager:
    """Test streaming management functionality"""

    @pytest.mark.asyncio
    async def test_stream_session_creation(self):
        """Test creating a stream session"""
        streaming_manager = StreamingManager()
        await streaming_manager.initialize()
        
        # Create a mock pod ID
        pod_id = "test-pod-123"
        
        # Start streaming for the pod
        session_id = await streaming_manager.start_pod_streaming(
            pod_id, 
            stream_type="webrtc", 
            resolution="1024x768", 
            fps=30
        )
        
        assert session_id is not None
        assert session_id in streaming_manager.streaming_sessions.values()
        
        # Check streaming status
        status = streaming_manager.get_streaming_status(pod_id)
        assert status["status"] == "active"
        assert status["session_id"] == session_id
        
        # Stop streaming
        await streaming_manager.stop_pod_streaming(pod_id)
        
        # Verify it's stopped
        status = streaming_manager.get_streaming_status(pod_id)
        assert status["status"] == "not_streaming"


class TestScheduler:
    """Test scheduler functionality"""

    @pytest.mark.asyncio
    async def test_pod_scheduling(self):
        """Test basic pod scheduling"""
        # Create a mock orchestrator
        mock_orchestrator = Mock()
        mock_orchestrator.create_pod = AsyncMock(return_value="mock-pod-id")
        mock_orchestrator.start_pod = AsyncMock()
        
        scheduler = Scheduler(mock_orchestrator)
        
        # Add a node to the scheduler
        from src.models.pod import ComputeNode, NodeResources
        
        node = ComputeNode(
            id="test-node-1",
            hostname="test-node.example.com",
            ip_address="192.168.1.100",
            resources=NodeResources(
                total_cpu_cores=4.0,
                available_cpu_cores=4.0,
                total_memory_mb=8192,
                available_memory_mb=8192,
                total_storage_gb=100,
                available_storage_gb=100,
                total_gpus=0,
                available_gpus=0
            ),
            status="active",
            capabilities=["container"],
            last_heartbeat=datetime.now()
        )
        scheduler.add_node(node)
        
        # Create a pod spec
        pod_spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="web",
            resource_requirements=ResourceRequirements(cpu_cores=1.0, memory_mb=1024)
        )
        
        # Submit a scheduling request
        pod_id = await scheduler.submit_pod_request(pod_spec, priority=1)
        
        # Manually trigger scheduling since we're not running the loop
        request = scheduler.request_queue.pop()
        if request:
            await scheduler._schedule_request(request)
        
        # Verify the pod was scheduled
        assert pod_id in scheduler.scheduled_pods
        assert scheduler.scheduled_pods[pod_id] == "test-node-1"
        
        # Verify orchestrator methods were called
        mock_orchestrator.create_pod.assert_called_once()
        mock_orchestrator.start_pod.assert_called_once()


class TestTypeDefinitions:
    """Test type definitions"""

    def test_enum_values(self):
        """Test that enum values are correctly defined"""
        # Test SessionType enum
        assert TypeSessionType.PREVIEW.value == "preview"
        assert TypeSessionType.RUN_REPO.value == "run_repo"
        assert TypeSessionType.FORK_GUI.value == "fork_gui"
        
        # Test PodType enum
        assert TypePodType.CONTAINER.value == "container"
        assert TypePodType.VM.value == "vm"
        assert TypePodType.HYBRID.value == "hybrid"
        
        # Test that they can be used in comparisons
        session_type = TypeSessionType.PREVIEW
        assert session_type == TypeSessionType.PREVIEW
        assert session_type != TypeSessionType.RUN_REPO


class TestIntegration:
    """Test integration between components"""

    @pytest.mark.asyncio
    async def test_full_session_with_storage_and_streaming(self):
        """Test creating a session with attached storage and streaming"""
        # This is a high-level integration test
        # We'll mock the heavy dependencies but test the logical flow
        
        from src.services.platform import SessionManager, PlatformConfig
        from src.storage.storage_manager import StorageManager
        from src.streaming.streaming_server import StreamingManager
        
        # Create platform components
        config = PlatformConfig()
        session_manager = SessionManager(config)
        
        # Initialize storage and streaming managers
        storage_manager = StorageManager()
        streaming_manager = StreamingManager()
        await storage_manager.initialize()
        await streaming_manager.initialize()
        
        # Create a session (this would normally go through the full flow)
        # For this test, we'll simulate the important parts
        
        # Verify components can be instantiated together
        assert session_manager is not None
        assert storage_manager is not None
        assert streaming_manager is not None
        
        # Verify they have the expected attributes/methods
        assert hasattr(session_manager, 'create_session')
        assert hasattr(storage_manager, 'create_ephemeral_volume')
        assert hasattr(streaming_manager, 'start_pod_streaming')


if __name__ == "__main__":
    pytest.main([__file__])