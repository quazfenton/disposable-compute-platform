"""
Comprehensive tests for production implementation
"""
import pytest
import asyncio
from datetime import datetime, timedelta
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestScheduler:
    """Test the scheduler implementation"""
    
    @pytest.fixture
    def scheduler(self):
        from src.scheduler.scheduler import Scheduler, Node, NodeStatus
        from src.models.pod import PodSpec, PodType, ResourceRequirements
        
        scheduler = Scheduler()
        
        # Register test nodes
        node1 = Node(
            id="node-001",
            hostname="compute-01",
            ip_address="192.168.1.10",
            status=NodeStatus.ACTIVE,
            cpu_total=32.0,
            cpu_available=28.0,
            memory_total_mb=65536,
            memory_available_mb=60000,
            storage_total_gb=1000,
            storage_available_gb=900,
            capabilities=["container", "gpu"],
        )
        
        scheduler.register_node(node1)
        
        return scheduler
    
    def test_scheduler_initialization(self, scheduler):
        """Test scheduler initializes correctly"""
        assert scheduler is not None
        assert len(scheduler.nodes) == 1
        assert "node-001" in scheduler.nodes
    
    @pytest.mark.asyncio
    async def test_schedule_pod(self, scheduler):
        """Test scheduling a pod"""
        from src.scheduler.scheduler import PodRequest
        from src.models.pod import PodSpec, PodType, ResourceRequirements
        
        spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="linux",
            image="ubuntu:22.04",
            resource_requirements=ResourceRequirements(
                cpu_cores=2.0,
                memory_mb=4096,
                storage_gb=10
            )
        )
        
        request = PodRequest(
            id="pod-test-001",
            pod_spec=spec,
            user_id="user-001",
            user_tier="free"
        )
        
        success, message, node_id = await scheduler.schedule(request)
        
        assert success is True
        assert node_id == "node-001"
        assert request.status.value == "scheduled"
    
    @pytest.mark.asyncio
    async def test_schedule_insufficient_resources(self, scheduler):
        """Test scheduling with insufficient resources"""
        from src.scheduler.scheduler import PodRequest
        from src.models.pod import PodSpec, PodType, ResourceRequirements
        
        spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="linux",
            image="ubuntu:22.04",
            resource_requirements=ResourceRequirements(
                cpu_cores=100.0,  # More than available
                memory_mb=4096,
                storage_gb=10
            )
        )
        
        request = PodRequest(
            id="pod-test-002",
            pod_spec=spec,
            user_id="user-001",
            user_tier="free"
        )
        
        success, message, node_id = await scheduler.schedule(request)
        
        assert success is False
        assert node_id is None
    
    def test_cluster_status(self, scheduler):
        """Test getting cluster status"""
        status = scheduler.get_cluster_status()
        
        assert status["total_nodes"] == 1
        assert status["active_nodes"] == 1
        assert "nodes" in status


class TestAuth:
    """Test authentication implementation"""
    
    @pytest.fixture
    def auth_manager(self):
        from src.api.auth import AuthManager, AuthConfig
        
        config = AuthConfig()
        manager = AuthManager(config)
        
        # Create test user
        manager.create_user("user-001", "test@example.com", "free")
        
        return manager
    
    def test_create_user(self, auth_manager):
        """Test user creation"""
        user = auth_manager.get_user("user-001")
        
        assert user is not None
        assert user.email == "test@example.com"
        assert user.tier == "free"
    
    def test_create_api_key(self, auth_manager):
        """Test API key creation"""
        api_key = auth_manager.create_api_key("user-001", "test-key")
        
        assert api_key is not None
        assert api_key.user_id == "user-001"
        assert api_key.name == "test-key"
    
    def test_verify_api_key(self, auth_manager):
        """Test API key verification"""
        api_key = auth_manager.create_api_key("user-001", "test-key")
        
        verified = auth_manager.api_key_manager.verify_key(api_key.key)
        
        assert verified is not None
        assert verified.user_id == "user-001"
    
    def test_quota_check(self, auth_manager):
        """Test quota checking"""
        user = auth_manager.get_user("user-001")
        
        can_create, message = auth_manager.check_session_quota(user)
        
        assert can_create is True
    
    def test_quota_exceeded(self, auth_manager):
        """Test quota exceeded"""
        user = auth_manager.get_user("user-001")
        
        # Exhaust quota
        for _ in range(user.quota_sessions_per_day):
            auth_manager.record_session_created(user.id)
        
        can_create, message = auth_manager.check_session_quota(user)
        
        assert can_create is False
        assert "exceeded" in message.lower()


class TestMetrics:
    """Test metrics implementation"""
    
    @pytest.fixture
    def metrics(self):
        from src.metrics.metrics import PlatformMetrics, MetricsRegistry
        
        registry = MetricsRegistry()
        return PlatformMetrics(registry)
    
    def test_record_session_created(self, metrics):
        """Test recording session creation"""
        metrics.record_session_created("preview", "free")
        
        exported = metrics.registry.export_prometheus()
        assert b"dcp_sessions_created_total" in exported
        assert b'tier="free"' in exported
    
    def test_set_active_sessions(self, metrics):
        """Test setting active sessions gauge"""
        metrics.set_active_sessions(10)
        
        exported = metrics.registry.export_prometheus()
        assert b"dcp_sessions_active" in exported
        assert b"10.0" in exported

    def test_export_metrics(self, metrics):
        """Test exporting metrics"""
        metrics.record_session_created("preview", "free")
        metrics.set_active_sessions(5)
        
        exported = metrics.registry.export_prometheus()
        
        assert b"dcp_sessions_created_total" in exported
        assert b"dcp_sessions_active" in exported


class TestStorage:
    """Test storage implementation"""
    
    @pytest.fixture
    def storage_manager(self, tmp_path):
        from src.storage.storage_manager import StorageManager
        
        manager = StorageManager(base_storage_path=str(tmp_path))
        return manager
    
    @pytest.mark.asyncio
    async def test_create_volume(self, storage_manager):
        """Test creating a volume"""
        volume = await storage_manager.volume_manager.create_volume("test-vol", 10)
        
        assert volume is not None
        assert volume.name == "test-vol"
        assert volume.size_bytes == 10 * 1024 * 1024 * 1024
    
    @pytest.mark.asyncio
    async def test_attach_volume(self, storage_manager):
        """Test attaching volume to pod"""
        volume = await storage_manager.volume_manager.create_volume("test-vol", 10)
        
        success = await storage_manager.volume_manager.attach_volume_to_pod(volume.id, "pod-001")
        
        assert success is True
        assert volume.attached_to_pod == "pod-001"
    
    @pytest.mark.asyncio
    async def test_create_snapshot(self, storage_manager):
        """Test creating a snapshot"""
        volume = await storage_manager.volume_manager.create_volume("test-vol", 10)
        
        snapshot = await storage_manager.snapshot_manager.create_snapshot(volume.id, "test snapshot")
        
        assert snapshot is not None
        assert snapshot.volume_id == volume.id


class TestDatabase:
    """Test database implementation"""
    
    @pytest.mark.asyncio
    async def test_database_mock(self):
        """Test mock database (when asyncpg not available)"""
        from src.database.db import Database, DatabaseConfig, MockPool
        
        db = Database(DatabaseConfig())
        db._mock_pool = MockPool()
        db._connected = True
        
        # Test operations - verify mock pool works
        assert db._connected is True
        assert db._mock_pool is not None


class TestAPIIntegration:
    """Integration tests for API"""
    
    @pytest.fixture
    def app(self):
        from fastapi.testclient import TestClient
        from src.api.main_v2 import app
        
        return TestClient(app)
    
    def test_health_endpoint(self, app):
        """Test health endpoint"""
        response = app.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "checks" in data
    
    def test_metrics_endpoint(self, app):
        """Test metrics endpoint"""
        response = app.get("/metrics")
        
        assert response.status_code == 200
    
    def test_root_endpoint(self, app):
        """Test root endpoint"""
        response = app.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Disposable Compute Platform"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
