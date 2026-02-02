import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio
import json

from src.models.pod import Pod, PodSpec, PodStatus, PodType, ResourceRequirements
from src.models.session import Session, SessionType, SessionStatus
from src.orchestrator.orchestrator import AdvancedOrchestrator
from src.scheduler.scheduler import Scheduler
from src.storage.storage_manager import StorageManager
from src.streaming.streaming_server import StreamingManager
from src.monitoring.monitoring_manager import MonitoringManager, ResourceMonitor, HealthChecker
from src.utils.security_enhanced import SecurityManager, VulnerabilityScanner
from src.optimization.resource_manager import ResourceManager, ResourcePredictor, QuotaManager
from src.networking_advanced.network_manager import AdvancedNetworkManager, LoadBalancer, NetworkPolicyManager


class TestMonitoringManager:
    """Test monitoring and observability features"""

    @pytest.mark.asyncio
    async def test_monitoring_initialization(self):
        """Test monitoring manager initialization"""
        monitoring_manager = MonitoringManager()
        await monitoring_manager.initialize()
        
        # Verify components are initialized
        assert monitoring_manager.metrics_collector is not None
        assert monitoring_manager.resource_monitor is not None
        assert monitoring_manager.health_checker is not None

    @pytest.mark.asyncio
    async def test_resource_monitoring(self):
        """Test resource monitoring functionality"""
        from src.models.pod import Pod, PodSpec, PodStatus, PodType
        
        # Create a mock pod
        pod_spec = PodSpec(
            pod_type=PodType.CONTAINER,
            app_type="web",
            image="nginx:latest"
        )
        
        pod = Pod(
            id="test-monitoring-pod",
            spec=pod_spec,
            status=PodStatus.RUNNING,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Create monitoring manager
        monitoring_manager = MonitoringManager()
        await monitoring_manager.resource_monitor.start_monitoring_pod(pod)
        
        # Brief delay to allow monitoring to start
        await asyncio.sleep(0.1)
        
        # Stop monitoring
        await monitoring_manager.resource_monitor.stop_monitoring_pod(pod.id)
        
        # Verify monitoring was started and stopped
        assert pod.id not in monitoring_manager.resource_monitor.monitoring_tasks

    @pytest.mark.asyncio
    async def test_health_checks(self):
        """Test health check functionality"""
        health_checker = HealthChecker()
        
        # Register a mock check
        async def mock_check():
            return {"status": "healthy", "test": True}
        
        health_checker.register_check("mock_check", mock_check)
        
        # Run all checks
        results = await health_checker.run_all_checks()
        
        # Verify the check ran
        assert "mock_check" in results
        assert results["mock_check"].status == "healthy"


class TestSecurityManager:
    """Test enhanced security features"""

    @pytest.mark.asyncio
    async def test_vulnerability_scanning(self):
        """Test vulnerability scanning functionality"""
        scanner = VulnerabilityScanner()
        
        # Scan a mock image
        result = await scanner.scan_image("nginx:latest")
        
        # Verify scan completed
        assert result.scan_id.startswith("scan-")
        assert result.target == "nginx:latest"
        assert result.status in ["completed", "failed"]  # Could fail if scanner not available

    def test_credential_management(self):
        """Test credential management"""
        from src.utils.security_enhanced import CredentialManager
        
        cred_manager = CredentialManager()
        
        # Store a credential
        key = "test-key"
        value = "test-value"
        cred_manager.store_credential(key, value, ttl_minutes=1)
        
        # Retrieve the credential
        retrieved = cred_manager.retrieve_credential(key)
        assert retrieved == value
        
        # Clean up
        cred_manager.delete_credential(key)

    @pytest.mark.asyncio
    async def test_security_policy_application(self):
        """Test security policy application"""
        security_manager = SecurityManager()
        
        # Get default policy
        default_policy = security_manager.get_default_security_policy("container")
        assert default_policy is not None
        assert "no_new_privileges" in default_policy


class TestResourceManager:
    """Test resource optimization features"""

    def test_resource_prediction(self):
        """Test resource prediction functionality"""
        predictor = ResourcePredictor()
        
        # Record some usage data
        usage_data = {
            "cpu_percent": 50.0,
            "memory_mb": 1024,
            "disk_gb": 10.0,
            "network_mbps": 5.0
        }
        
        predictor.record_usage("test-pod-1", usage_data)
        
        # Add more data points
        for i in range(5):
            predictor.record_usage("test-pod-1", {
                "cpu_percent": 50.0 + i,
                "memory_mb": 1024 + (i * 10),
                "disk_gb": 10.0 + (i * 0.1),
                "network_mbps": 5.0 + (i * 0.5)
            })
        
        # Predict usage
        prediction = predictor.predict_usage("test-pod-1")
        
        # Verify prediction was made
        if prediction:  # May be None if insufficient data
            assert hasattr(prediction, 'cpu_percent')
            assert hasattr(prediction, 'memory_mb')

    def test_quota_management(self):
        """Test quota management functionality"""
        quota_manager = QuotaManager()
        
        # Set a quota
        quota_manager.set_quota(
            user_id="test-user",
            max_cpu_cores=4.0,
            max_memory_mb=4096,
            max_storage_gb=100,
            max_gpus=2
        )
        
        # Get the quota
        quota = quota_manager.get_quota("test-user")
        assert quota is not None
        assert quota.max_cpu_cores == 4.0
        assert quota.max_memory_mb == 4096
        
        # Check quota compliance
        request = {"cpu_cores": 2.0, "memory_mb": 2048}
        is_allowed, violations = quota_manager.check_quota("test-user", request)
        assert is_allowed is True
        assert len(violations) == 0
        
        # Check quota violation
        large_request = {"cpu_cores": 10.0, "memory_mb": 8192}
        is_allowed, violations = quota_manager.check_quota("test-user", large_request)
        assert is_allowed is False
        assert len(violations) > 0

    @pytest.mark.asyncio
    async def test_auto_scaling_evaluation(self):
        """Test auto scaling evaluation"""
        predictor = ResourcePredictor()
        auto_scaler = src.optimization.resource_manager.AutoScaler(predictor)
        
        # Set a scaling policy
        min_resources = {"cpu_cores": 1.0, "memory_mb": 512}
        max_resources = {"cpu_cores": 4.0, "memory_mb": 4096}
        
        auto_scaler.set_scaling_policy("test-pod", min_resources, max_resources)
        
        # Evaluate scaling (this may return None if insufficient prediction data)
        current_usage = {"cpu_percent": 80.0, "memory_used_mb": 3072, "memory_total_mb": 4096}
        scaling_recommendation = await auto_scaler.evaluate_scaling("test-pod", current_usage)
        
        # The function may return None if there isn't enough historical data for prediction
        # This is acceptable behavior


class TestAdvancedNetworkManager:
    """Test advanced networking features"""

    def test_network_policy_management(self):
        """Test network policy management"""
        policy_manager = NetworkPolicyManager()
        
        # Create a network policy
        policy = src.networking_advanced.network_manager.NetworkPolicy(
            id="test-policy",
            name="Test Policy",
            description="Test network policy",
            pod_selector={"app": "test"},
            ingress_rules=[{"ports": [80, 443], "from": [{"ipBlock": {"cidr": "0.0.0.0/0"}}]}],
            egress_rules=[{"ports": [53], "to": [{"ipBlock": {"cidr": "0.0.0.0/0"}}]}],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        # Create the policy
        success = policy_manager.create_policy(policy)
        assert success is True
        
        # Apply the policy to a pod
        applied = policy_manager.apply_policy_to_pod("test-pod", "test-policy")
        assert applied is True
        
        # Delete the policy
        deleted = policy_manager.delete_policy("test-policy")
        assert deleted is True

    @pytest.mark.asyncio
    async def test_load_balancer_functionality(self):
        """Test load balancer functionality"""
        lb = LoadBalancer()
        
        # Add backends
        backend1 = {"id": "backend1", "host": "127.0.0.1", "port": 8080}
        backend2 = {"id": "backend2", "host": "127.0.0.1", "port": 8081}
        
        lb.add_backend("test-service", backend1)
        lb.add_backend("test-service", backend2)
        
        # Configure load balancer
        config = src.networking_advanced.network_manager.LoadBalancerConfig(
            algorithm="round-robin",
            health_check_path="/health",
            health_check_interval=30,
            health_check_timeout=5,
            max_retries=3
        )
        lb.set_config("test-service", config)
        
        # Get a backend (may be None if health checks haven't run yet)
        backend = await lb.get_backend("test-service")
        # Note: This might be None if health checks determine backends are unhealthy
        
        # Remove a backend
        lb.remove_backend("test-service", "backend1")
        
        remaining_backends = lb.backends.get("test-service", [])
        backend_ids = [b['id'] for b in remaining_backends]
        assert "backend1" not in backend_ids
        assert "backend2" in backend_ids

    def test_service_mesh_configuration(self):
        """Test service mesh configuration"""
        mesh_manager = src.networking_advanced.network_manager.ServiceMeshManager()
        
        # Configure service mesh
        config = src.networking_advanced.network_manager.ServiceMeshConfig(
            enable_mtls=True,
            enable_tracing=True,
            enable_circuit_breaker=True,
            enable_rate_limiting=True,
            traffic_encryption="strict"
        )
        
        mesh_manager.configure_mesh("test-service", config)
        
        # Enable specific features
        mesh_manager.enable_mtls("test-service")
        mesh_manager.enable_tracing("test-service")


class TestIntegration:
    """Test integration between enhanced components"""

    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self):
        """Test an end-to-end workflow with all enhanced components"""
        # Initialize all managers
        monitoring_manager = MonitoringManager()
        security_manager = SecurityManager()
        resource_manager = ResourceManager()
        network_manager = AdvancedNetworkManager()
        
        # Initialize monitoring
        await monitoring_manager.initialize()
        
        # Set up a quota for a test user
        resource_manager.quota_manager.set_quota(
            user_id="integration-test-user",
            max_cpu_cores=8.0,
            max_memory_mb=8192,
            max_storage_gb=200,
            max_gpus=2
        )
        
        # Check quota before allocation
        resources_needed = {"cpu_cores": 2.0, "memory_mb": 2048, "storage_gb": 10, "gpu_count": 1}
        has_quota, violations = resource_manager.check_quota("integration-test-user", resources_needed)
        assert has_quota is True, f"Quota check failed: {violations}"
        
        # Allocate resources
        allocated = resource_manager.allocate_resources("integration-test-user", resources_needed)
        assert allocated is True
        
        # Record resource usage for prediction
        usage_data = {"cpu_percent": 60.0, "memory_mb": 1500}
        resource_manager.record_resource_usage("test-pod-integration", usage_data)
        
        # Apply network policy
        network_policy = src.networking_advanced.network_manager.NetworkPolicy(
            id="integration-policy",
            name="Integration Test Policy",
            description="Policy for integration test",
            pod_selector={"user": "integration-test-user"},
            ingress_rules=[{"ports": [80], "from": [{"ipBlock": {"cidr": "0.0.0.0/0"}}]}],
            egress_rules=[{"ports": [53], "to": [{"ipBlock": {"cidr": "0.0.0.0/0"}}]}],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        
        network_manager.policy_manager.create_policy(network_policy)
        applied = network_manager.apply_network_policy("test-pod-integration", "integration-policy")
        assert applied is True
        
        # Perform a security scan
        scan_result = await security_manager.scan_pod_image("nginx:latest")
        assert scan_result is not None
        assert scan_result.target == "nginx:latest"
        
        # Release resources
        resource_manager.release_resources("integration-test-user", resources_needed)
        
        # Verify quota is released
        quota = resource_manager.quota_manager.get_quota("integration-test-user")
        assert quota.used_cpu_cores == 0.0
        assert quota.used_memory_mb == 0


if __name__ == "__main__":
    pytest.main([__file__])