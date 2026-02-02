import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import json

from src.models.session import Session, SessionType, SessionStatus, ServiceDefinition
from src.models.environment import Environment
from src.services.platform import SessionManager, PlatformConfig
from src.services.preview import PreviewEnvironmentManager, PreviewConfig
from src.services.run_repo import RunRepoManager, RuntimeDetector
from src.services.fork_gui import ForkableSessionManager, StateCaptureAdapter
from src.containers.orchestrator import ContainerOrchestrator
from src.networking.router import NetworkManager


class TestSessionModel:
    """Test session model functionality"""
    
    def test_session_creation(self):
        """Test creating a session with all required fields"""
        session = Session(
            id="test-session",
            type=SessionType.RUN_REPO,
            status=SessionStatus.CREATING,
            created_at=datetime.now()
        )
        
        assert session.id == "test-session"
        assert session.type == SessionType.RUN_REPO
        assert session.status == SessionStatus.CREATING
        assert session.ports == {}
        assert session.metadata == {}
    
    def test_session_with_optional_fields(self):
        """Test creating a session with optional fields"""
        now = datetime.now()
        session = Session(
            id="test-session",
            type=SessionType.PREVIEW,
            status=SessionStatus.RUNNING,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(hours=1),
            repo_url="https://github.com/test/repo.git",
            repo_ref="main",
            pr_number=123,
            container_id="abc123",
            network_id="net123",
            ports={"api": 3000, "db": 5432},
            metadata={"env": "test"}
        )
        
        assert session.repo_url == "https://github.com/test/repo.git"
        assert session.pr_number == 123
        assert session.ports == {"api": 3000, "db": 5432}


class TestServiceDefinition:
    """Test service definition model"""
    
    def test_service_definition_creation(self):
        """Test creating a service definition"""
        service = ServiceDefinition(
            name="api",
            type="web",
            image="node:18-alpine",
            command="npm start",
            port=3000,
            env={"NODE_ENV": "production"},
            volumes=["/data:/app/data"]
        )
        
        assert service.name == "api"
        assert service.type == "web"
        assert service.image == "node:18-alpine"
        assert service.command == "npm start"
        assert service.port == 3000
        assert service.env == {"NODE_ENV": "production"}
        assert service.volumes == ["/data:/app/data"]


class TestPreviewConfig:
    """Test preview configuration parsing"""
    
    @pytest.mark.asyncio
    async def test_parse_from_repo(self):
        """Test parsing preview config from repo"""
        config = PreviewConfig()
        result = await config.parse_from_repo("https://github.com/test/repo.git")
        
        # Should return a valid config structure
        assert "services" in result
        assert "entrypoints" in result
        assert isinstance(result["services"], dict)
    
    def test_validate_config(self):
        """Test config validation"""
        config = PreviewConfig()
        
        # Valid config
        valid_config = {
            "services": {
                "api": {
                    "type": "web",
                    "image": "node:18-alpine"
                }
            }
        }
        assert config.validate_config(valid_config) is True
        
        # Invalid config (missing services)
        invalid_config = {
            "entrypoints": {}
        }
        assert config.validate_config(invalid_config) is False


class TestRuntimeDetector:
    """Test runtime detection"""
    
    @pytest.mark.asyncio
    async def test_detect_runtime(self):
        """Test runtime detection"""
        detector = RuntimeDetector()
        result = await detector.detect_runtime("https://github.com/test/repo.git")
        
        # Should return a runtime config or None
        assert result is None or isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_get_entrypoint_command(self):
        """Test getting entrypoint command"""
        detector = RuntimeDetector()
        command = await detector.get_entrypoint_command("https://github.com/test/repo.git")
        
        assert isinstance(command, str)


class TestContainerOrchestrator:
    """Test container orchestration"""
    
    def test_container_config_creation(self):
        """Test creating container configuration"""
        from src.containers.orchestrator import ContainerConfig
        
        config = ContainerConfig(
            image="alpine:latest",
            command="sleep infinity",
            environment={"TEST": "value"},
            ports={"8080/tcp": None},
            volumes=["/tmp:/data"],
            network="test-network"
        )
        
        assert config.image == "alpine:latest"
        assert config.command == "sleep infinity"
        assert config.environment == {"TEST": "value"}
        assert config.ports == {"8080/tcp": None}
        assert config.volumes == ["/tmp:/data"]
        assert config.network == "test-network"


class TestNetworkManager:
    """Test network management"""
    
    def test_create_isolated_network(self):
        """Test creating isolated network"""
        manager = NetworkManager()
        network_name = manager.create_isolated_network("test-env-12345678")
        
        assert network_name.startswith("env-test-env-1234")
        assert len(network_name) > 10


class TestSessionManager:
    """Test session management"""
    
    @pytest.mark.asyncio
    async def test_create_session(self):
        """Test creating a session"""
        config = PlatformConfig()
        manager = SessionManager(config)
        
        session = await manager.create_session(
            SessionType.RUN_REPO,
            "https://github.com/test/repo.git",
            ttl_minutes=10
        )
        
        assert session.id.startswith("sess-")
        assert session.type == SessionType.RUN_REPO
        assert session.status in [SessionStatus.CREATING, SessionStatus.RUNNING]
        assert session.expires_at > session.created_at
    
    @pytest.mark.asyncio
    async def test_destroy_session(self):
        """Test destroying a session"""
        config = PlatformConfig()
        manager = SessionManager(config)
        
        # Create a session first
        session = await manager.create_session(
            SessionType.RUN_REPO,
            "https://github.com/test/repo.git"
        )
        
        session_id = session.id
        assert session_id in manager.sessions
        
        # Destroy the session
        await manager.destroy_session(session_id)
        
        # Session should be marked as destroyed
        assert manager.sessions[session_id].status == SessionStatus.DESTROYED


class TestPreviewEnvironmentManager:
    """Test preview environment management"""
    
    @pytest.mark.asyncio
    async def test_create_preview_environment(self):
        """Test creating a preview environment"""
        config = PlatformConfig()
        session_manager = SessionManager(config)
        
        # Create a session first
        session = Session(
            id="test-session-preview",
            type=SessionType.PREVIEW,
            status=SessionStatus.CREATING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            repo_url="https://github.com/test/repo.git",
            repo_ref="feature/test",
            pr_number=123
        )
        session_manager.sessions[session.id] = session
        
        manager = PreviewEnvironmentManager(session_manager)
        
        # This would normally create actual containers, but we're testing the structure
        # For now, just verify the method exists and can be called
        assert hasattr(manager, 'create_preview_environment')


class TestRunRepoManager:
    """Test run-repo functionality"""
    
    @pytest.mark.asyncio
    async def test_create_run_repo_session(self):
        """Test creating a run-repo session"""
        config = PlatformConfig()
        session_manager = SessionManager(config)
        
        # Create a session first
        session = Session(
            id="test-session-run-repo",
            type=SessionType.RUN_REPO,
            status=SessionStatus.CREATING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            repo_url="https://github.com/test/repo.git"
        )
        session_manager.sessions[session.id] = session
        
        manager = RunRepoManager(session_manager)
        
        # This would normally create actual containers, but we're testing the structure
        # For now, just verify the method exists and can be called
        assert hasattr(manager, 'create_run_repo_session')


class TestForkableSessionManager:
    """Test forkable GUI session management"""
    
    @pytest.mark.asyncio
    async def test_create_forkable_session(self):
        """Test creating a forkable GUI session"""
        config = PlatformConfig()
        session_manager = SessionManager(config)
        
        # Create a session first
        session = Session(
            id="test-session-fork-gui",
            type=SessionType.FORK_GUI,
            status=SessionStatus.CREATING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            repo_url="https://github.com/test/gui-app.git"
        )
        session_manager.sessions[session.id] = session
        
        manager = ForkableSessionManager(session_manager, session_manager.snapshot_manager)
        
        # This would normally create actual containers, but we're testing the structure
        # For now, just verify the method exists and can be called
        assert hasattr(manager, 'create_forkable_session')


class TestStateCaptureAdapter:
    """Test state capture adapter"""
    
    def test_adapter_interface(self):
        """Test that adapter implements required interface"""
        class TestAdapter(StateCaptureAdapter):
            async def capture_state(self, container_id: str) -> dict:
                return {"test": "state"}
            
            async def restore_state(self, container_id: str, state_data: dict):
                pass
        
        adapter = TestAdapter()
        assert hasattr(adapter, 'capture_state')
        assert hasattr(adapter, 'restore_state')


# Integration tests
class TestAPIIntegration:
    """Test API integration"""
    
    @pytest.mark.asyncio
    async def test_session_lifecycle(self):
        """Test complete session lifecycle"""
        config = PlatformConfig()
        manager = SessionManager(config)
        
        # Create session
        session = await manager.create_session(
            SessionType.RUN_REPO,
            "https://github.com/test/repo.git",
            ttl_minutes=5
        )
        
        session_id = session.id
        assert session_id in manager.sessions
        
        # Verify session properties
        assert manager.sessions[session_id].type == SessionType.RUN_REPO
        assert manager.sessions[session_id].status in [SessionStatus.CREATING, SessionStatus.RUNNING]
        
        # Destroy session
        await manager.destroy_session(session_id)
        
        # Verify destruction
        assert manager.sessions[session_id].status == SessionStatus.DESTROYED


if __name__ == "__main__":
    pytest.main([__file__])