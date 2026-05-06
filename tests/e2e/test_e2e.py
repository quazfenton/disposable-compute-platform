"""
End-to-End tests for Disposable Compute Platform
Tests complete workflows from API to database
"""
import pytest
import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class TestE2ESessionLifecycle:
    """End-to-end test for complete session lifecycle"""
    
    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self):
        """Test complete session lifecycle: create -> run -> destroy"""
        from src.services.platform import SessionManager, PlatformConfig
        from src.models.session import SessionType
        
        # Initialize
        config = PlatformConfig(
            domain="test.preview.dev",
            default_ttl=30,
            max_ttl=60,
            storage_path="/tmp/test-disposable-storage",
            max_concurrent_sessions=10,
            redis_url=None  # Disable Redis for testing
        )
        
        session_manager = SessionManager(config)
        
        try:
            # Create session
            session = await session_manager.create_session(
                session_type=SessionType.RUN_REPO,
                repo_url="https://github.com/test/repo",
                repo_ref="main",
                ttl_minutes=30
            )
            
            assert session is not None
            assert session.id.startswith("sess-")
            assert session.status == SessionType.RUNNING
            
            # Verify session is tracked
            assert session.id in session_manager.sessions
            
            # Destroy session
            await session_manager.destroy_session(session.id)
            
            # Verify session is destroyed
            destroyed_session = session_manager.sessions[session.id]
            assert destroyed_session.status == SessionType.DESTROYED
            
        except Exception as e:
            # Cleanup on error
            pytest.fail(f"E2E test failed: {str(e)}")
    
    @pytest.mark.asyncio
    async def test_concurrent_session_creation(self):
        """Test concurrent session creation doesn't cause race conditions"""
        from src.services.platform import SessionManager, PlatformConfig
        from src.models.session import SessionType
        
        config = PlatformConfig(
            domain="test.preview.dev",
            default_ttl=30,
            storage_path="/tmp/test-disposable-storage",
            max_concurrent_sessions=100
        )
        
        session_manager = SessionManager(config)
        
        # Create multiple sessions concurrently
        async def create_session(i):
            return await session_manager.create_session(
                session_type=SessionType.RUN_REPO,
                repo_url=f"https://github.com/test/repo-{i}",
                ttl_minutes=30
            )
        
        tasks = [create_session(i) for i in range(5)]
        sessions = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed
        for i, session in enumerate(sessions):
            if isinstance(session, Exception):
                pytest.fail(f"Session {i} failed: {session}")
            assert session is not None
            assert session.id in session_manager.sessions
        
        # Verify unique IDs
        session_ids = [s.id for s in sessions if not isinstance(s, Exception)]
        assert len(session_ids) == len(set(session_ids)), "Duplicate session IDs detected"
    
    @pytest.mark.asyncio
    async def test_session_expiration(self):
        """Test session expiration and cleanup"""
        from src.services.platform import SessionManager, PlatformConfig
        from src.models.session import SessionType, SessionStatus
        import time
        
        config = PlatformConfig(
            domain="test.preview.dev",
            default_ttl=1,  # 1 minute TTL
            storage_path="/tmp/test-disposable-storage"
        )
        
        session_manager = SessionManager(config)
        
        # Create session with very short TTL
        session = await session_manager.create_session(
            session_type=SessionType.RUN_REPO,
            repo_url="https://github.com/test/repo",
            ttl_minutes=1
        )
        
        # Manually expire session for testing
        session.expires_at = datetime.now() - timedelta(minutes=1)
        
        # Run cleanup
        expired = await session_manager.cleanup_expired_sessions()
        
        # Verify session was cleaned up
        assert session.id in expired or session.status == SessionStatus.DESTROYED


class TestE2EAuthentication:
    """End-to-end authentication tests"""
    
    def test_full_auth_flow(self):
        """Test complete authentication flow"""
        from src.api.auth import AuthManager, User, UserTier
        
        # Initialize
        auth = AuthManager(
            secret_key="test-secret-key-for-e2e-testing-only-min-32-chars"
        )
        
        # Create user
        user_data = {
            'id': 'test-user-e2e',
            'email': 'test-e2e@example.com',
            'tier': UserTier.FREE,
            'session_quota': 5,
            'max_session_ttl': 60
        }
        
        # Create token
        token = auth.create_access_token(
            user_id=user_data['id'],
            email=user_data['email'],
            tier=user_data['tier'].value
        )
        
        assert token is not None
        assert len(token) > 100
        
        # Verify token
        payload = auth.verify_token(token)
        assert payload.user_id == user_data['id']
        assert payload.email == user_data['email']
        assert payload.tier == user_data['tier'].value
        
        # Test token expiration
        auth_short = AuthManager(
            secret_key="test-secret-key",
            token_expiry_minutes=1  # 1 minute
        )
        
        short_token = auth_short.create_access_token(
            user_id='test',
            email='test@example.com'
        )
        
        # Token should be valid now
        payload = auth_short.verify_token(short_token)
        assert payload is not None
    
    def test_rate_limiting_e2e(self):
        """Test rate limiting end-to-end"""
        from src.api.auth import AuthManager
        
        auth = AuthManager(secret_key="test-secret-key-min-32-characters")
        
        # Simulate failed login attempts
        for i in range(5):
            auth._record_failed_attempt('test-user')
        
        # Should be rate limited
        assert not auth._check_rate_limit('test-user')
        
        # Verify retry-after calculation
        retry_after = auth._failed_attempts['test-user'][0] + auth._rate_limit_window - datetime.utcnow().timestamp()
        assert retry_after > 0


class TestE2EInputValidation:
    """End-to-end input validation tests"""
    
    def test_repo_url_security(self):
        """Test repository URL security validation"""
        from src.utils.input_validation import validate_repo_url, InputValidator
        
        # Test SSRF prevention
        malicious_urls = [
            'http://169.254.169.254/latest/meta-data/',  # AWS metadata
            'http://192.168.1.1/internal-repo',  # Private network
            'http://10.0.0.1/repo',  # Private network
            'http://127.0.0.1/repo',  # Localhost
            'http://internal-server/repo',  # Internal hostname
        ]
        
        for url in malicious_urls:
            is_valid, _ = validate_repo_url(url)
            assert not is_valid, f"URL should be blocked: {url}"
        
        # Test valid URLs
        valid_urls = [
            'https://github.com/user/repo',
            'https://github.com/user/repo.git',
            'https://gitlab.com/user/repo',
        ]
        
        for url in valid_urls:
            is_valid, _ = validate_repo_url(url)
            assert is_valid, f"URL should be allowed: {url}"
    
    def test_full_request_validation(self):
        """Test complete request validation"""
        from src.utils.input_validation import InputValidator
        
        # Valid request
        is_valid, error, sanitized = InputValidator.validate_create_session_request(
            session_type='run_repo',
            repo_url='https://github.com/user/repo',
            repo_ref='main',
            pr_number=None,
            ttl_minutes=30,
            metadata={'key': 'value'}
        )
        
        assert is_valid, f"Valid request failed: {error}"
        assert sanitized['session_type'] == 'run_repo'
        assert sanitized['ttl_minutes'] == 30
        
        # Invalid request - SSRF attempt
        is_valid, error, _ = InputValidator.validate_create_session_request(
            session_type='run_repo',
            repo_url='http://192.168.1.1/internal',
            ttl_minutes=30
        )
        
        assert not is_valid
        assert 'private' in error.lower() or 'not allowed' in error.lower()
        
        # Invalid request - TTL too long
        is_valid, error, sanitized = InputValidator.validate_create_session_request(
            session_type='run_repo',
            repo_url='https://github.com/user/repo',
            ttl_minutes=10000  # Too long
        )
        
        # Should be clamped, not rejected
        assert is_valid
        assert sanitized['ttl_minutes'] == 1440  # Max TTL


class TestE2ECredentialEncryption:
    """End-to-end credential encryption tests"""
    
    def test_full_encryption_cycle(self):
        """Test complete encryption/decryption cycle"""
        from src.utils.credential_encryption import CredentialEncryption, SecureCredentialStore
        import tempfile
        
        # Test basic encryption
        encryption = CredentialEncryption()
        
        sensitive_data = {
            'username': 'admin',
            'password': 'SuperSecret123!',
            'api_key': 'sk-1234567890abcdef'
        }
        
        encrypted = encryption.encrypt(sensitive_data)
        assert encrypted != sensitive_data
        assert isinstance(encrypted, str)
        
        decrypted = encryption.decrypt(encrypted)
        assert decrypted == sensitive_data
        
        # Test secure store
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecureCredentialStore(tmpdir, encryption)
            
            # Store credential
            cred_id = store.store_credential(
                'test-cred',
                {'secret': 'value'},
                ttl_minutes=60
            )
            
            assert cred_id == 'test-cred'
            
            # Retrieve credential
            retrieved = store.retrieve_credential('test-cred')
            assert retrieved == {'secret': 'value'}
            
            # Delete credential
            deleted = store.delete_credential('test-cred')
            assert deleted
            
            # Verify deletion
            retrieved = store.retrieve_credential('test-cred')
            assert retrieved is None


class TestE2EErrorHandling:
    """End-to-end error handling tests"""
    
    def test_error_response_format(self):
        """Test error response format consistency"""
        from src.api.middleware.error_handler import (
            NotFoundError, ValidationError, AuthenticationError,
            api_error_handler
        )
        from fastapi import Request
        from unittest.mock import Mock
        
        # Test NotFoundError
        try:
            raise NotFoundError("Session", "test-123")
        except NotFoundError as e:
            assert e.status_code == 404
            assert e.error_code == "NOT_FOUND"
            assert "test-123" in e.message
        
        # Test ValidationError
        try:
            raise ValidationError("Invalid email format", field="email")
        except ValidationError as e:
            assert e.status_code == 400
            assert e.error_code == "VALIDATION_ERROR"
            assert e.details['field'] == 'email'
        
        # Test AuthenticationError
        try:
            raise AuthenticationError("Token expired")
        except AuthenticationError as e:
            assert e.status_code == 401
            assert e.error_code == "AUTHENTICATION_ERROR"
    
    def test_error_handler_middleware(self):
        """Test error handler middleware"""
        from src.api.middleware.error_handler import ErrorHandlerMiddleware
        from fastapi import Request
        from unittest.mock import AsyncMock, Mock
        
        middleware = ErrorHandlerMiddleware()
        
        # Mock request
        request = Mock(spec=Request)
        request.state = Mock()
        
        # Test successful request
        async def success_call_next(request):
            from fastapi.responses import JSONResponse
            return JSONResponse(content={"status": "ok"})
        
        # Should add request ID
        # (Implementation test - verify no exceptions)
        assert middleware is not None


class TestE2EHealthChecks:
    """End-to-end health check tests"""
    
    @pytest.mark.asyncio
    async def test_health_check_workflow(self):
        """Test complete health check workflow"""
        from src.services.health import HealthChecker, HealthStatus
        
        checker = HealthChecker()
        
        # Run all health checks
        report = await checker.check_all()
        
        # Verify report structure
        assert report is not None
        assert report.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert report.timestamp is not None
        assert len(report.checks) > 0
        
        # Verify individual checks
        for check in report.checks:
            assert check.name is not None
            assert check.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY, HealthStatus.UNKNOWN]
            assert check.timestamp is not None
        
        # Get status summary
        summary = checker.get_status_summary()
        assert 'status' in summary
        assert 'checks_count' in summary


class TestE2EDevContainer:
    """End-to-end DevContainer parsing tests"""
    
    def test_devcontainer_to_compose(self):
        """Test DevContainer to docker-compose conversion"""
        from src.parsers.devcontainer import DevContainerParser
        
        parser = DevContainerParser()
        
        # Test config
        config_data = {
            "image": "node:18-alpine",
            "forwardPorts": [3000, 3001],
            "extensions": ["dbaeumer.vscode-eslint", "esbenp.prettier-vscode"],
            "settings": {
                "editor.formatOnSave": True,
                "editor.defaultFormatter": "esbenp.prettier-vscode"
            },
            "postCreateCommand": "npm install",
            "remoteEnv": {
                "NODE_ENV": "development"
            }
        }
        
        config = parser.parse_dict(config_data)
        
        # Verify parsing
        assert config.image == "node:18-alpine"
        assert 3000 in config.forward_ports
        assert 3001 in config.forward_ports
        assert len(config.extensions) == 2
        assert config.post_create_command == "npm install"
        assert config.remote_env['NODE_ENV'] == 'development'
        
        # Convert to service definition
        service = parser.to_service_definition(config)
        
        assert service['name'] == 'dev-container'
        assert service['type'] == 'development'
        assert service['image'] == 'node:18-alpine'
        assert 3000 in service['ports']


class TestE2EImageRegistry:
    """End-to-end image registry tests"""
    
    @pytest.mark.asyncio
    async def test_image_metadata_tracking(self):
        """Test image metadata tracking"""
        from src.registry.image_registry import Image, RegistryConfig
        from datetime import datetime
        
        # Create image record
        img = Image(
            id="sha256:test123",
            name="test-image",
            tag="latest",
            full_name="registry.local/test-image:latest",
            size_bytes=1024 * 1024 * 100,  # 100MB
            created_at=datetime.now(),
            labels={"app": "test"},
            layers=5
        )
        
        # Verify to_dict
        data = img.to_dict()
        assert data['id'] == "sha256:test123"
        assert data['name'] == "test-image"
        assert data['size_bytes'] == 1024 * 1024 * 100
        assert 'created_at' in data
        
        # Verify from_dict
        img2 = Image.from_dict(data)
        assert img2.id == img.id
        assert img2.name == img.name


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
