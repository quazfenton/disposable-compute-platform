"""
Integration tests for Disposable Compute Platform
Tests authentication, database, Redis, and API endpoints
"""
import pytest
import asyncio
import os
from datetime import datetime
from typing import Dict, Any

# Test fixtures
@pytest.fixture
def test_config():
    """Test configuration"""
    return {
        'auth_secret_key': 'test-secret-key-for-testing-only',
        'db_host': 'localhost',
        'db_port': 5432,
        'db_name': 'disposable_compute_test',
        'db_user': 'postgres',
        'db_password': 'test-password',
        'redis_host': 'localhost',
        'redis_port': 6379,
        'domain': 'test.preview.dev',
        'default_ttl': 30,
        'max_ttl': 60
    }


@pytest.fixture
def test_user():
    """Test user data"""
    return {
        'email': f'test-{datetime.now().timestamp()}@example.com',
        'password': 'TestPassword123!',
        'tier': 'free'
    }


class TestAuthentication:
    """Test authentication system"""
    
    def test_jwt_token_creation(self, test_config):
        """Test JWT token creation"""
        from src.api.auth import AuthManager
        
        auth = AuthManager(secret_key=test_config['auth_secret_key'])
        
        token = auth.create_access_token(
            user_id='test-user-123',
            email='test@example.com',
            tier='free'
        )
        
        assert token is not None
        assert len(token) > 100
        
        # Verify token
        payload = auth.verify_token(token)
        assert payload.user_id == 'test-user-123'
        assert payload.email == 'test@example.com'
        assert payload.tier == 'free'
    
    def test_password_hashing(self, test_config):
        """Test password hashing"""
        from src.api.auth import AuthManager
        
        auth = AuthManager(secret_key=test_config['auth_secret_key'])
        
        password = 'TestPassword123!'
        hashed = auth.hash_password(password)
        
        assert hashed != password
        assert auth.verify_password(password, hashed)
        assert not auth.verify_password('WrongPassword', hashed)
    
    def test_rate_limiting(self, test_config):
        """Test login rate limiting"""
        from src.api.auth import AuthManager
        
        auth = AuthManager(secret_key=test_config['auth_secret_key'])
        
        # Simulate multiple failed attempts
        for i in range(5):
            auth._record_failed_attempt('test-user')
        
        # Should be rate limited
        assert not auth._check_rate_limit('test-user')


class TestInputValidation:
    """Test input validation"""
    
    def test_repo_url_validation(self):
        """Test repository URL validation"""
        from src.utils.input_validation import validate_repo_url
        
        # Valid URLs
        valid_urls = [
            'https://github.com/user/repo',
            'https://github.com/user/repo.git',
            'https://gitlab.com/user/repo',
            'https://bitbucket.org/user/repo'
        ]
        
        for url in valid_urls:
            is_valid, _ = validate_repo_url(url)
            assert is_valid, f"{url} should be valid"
        
        # Invalid URLs
        invalid_urls = [
            'http://internal-server/repo',
            'https://192.168.1.1/repo',
            'https://10.0.0.1/repo',
            'ftp://github.com/user/repo',
            'not-a-url'
        ]
        
        for url in invalid_urls:
            is_valid, _ = validate_repo_url(url)
            assert not is_valid, f"{url} should be invalid"
    
    def test_ttl_validation(self):
        """Test TTL validation"""
        from src.utils.input_validation import validate_ttl
        
        # Valid TTLs
        assert validate_ttl(30)[0] == 30
        assert validate_ttl(60)[0] == 60
        
        # Clamped TTLs
        assert validate_ttl(1)[0] == 5  # Min
        assert validate_ttl(2000)[0] == 1440  # Max
        assert validate_ttl(None)[0] == 30  # Default
    
    def test_metadata_sanitization(self):
        """Test metadata sanitization"""
        from src.utils.input_validation import validate_metadata
        
        # Valid metadata
        meta = {'key1': 'value1', 'key2': 'value2'}
        sanitized = validate_metadata(meta)
        assert sanitized == meta
        
        # Invalid keys
        invalid_meta = {'../etc/passwd': 'value', 'key': 'value'}
        sanitized = validate_metadata(invalid_meta)
        assert '../etc/passwd' not in sanitized


class TestDatabase:
    """Test database integration"""
    
    @pytest.mark.asyncio
    async def test_database_connection(self, test_config):
        """Test database connection"""
        from src.database.db import Database, DatabaseConfig
        
        config = DatabaseConfig(
            host=test_config['db_host'],
            port=test_config['db_port'],
            database=test_config['db_name'],
            user=test_config['db_user'],
            password=test_config['db_password']
        )
        
        db = Database(config)
        await db.connect()
        
        assert db._connected
        
        await db.disconnect()
        assert not db._connected
    
    @pytest.mark.asyncio
    async def test_session_persistence(self, test_config):
        """Test session persistence"""
        from src.database.db import Database, DatabaseConfig
        from src.database.models import SessionType, SessionStatus
        
        config = DatabaseConfig(
            host=test_config['db_host'],
            database=test_config['db_name'],
            user=test_config['db_user'],
            password=test_config['db_password']
        )
        
        db = Database(config)
        await db.connect()
        
        # Create session
        session = await db.create_session(
            session_type=SessionType.RUN_REPO,
            user_id='test-user',
            ttl_minutes=30
        )
        
        assert session is not None
        
        # Retrieve session
        retrieved = await db.get_session(session.id)
        assert retrieved is not None
        assert retrieved.id == session.id
        
        # Update status
        await db.update_session_status(session.id, SessionStatus.RUNNING)
        
        # Delete session
        deleted = await db.delete_session(session.id)
        assert deleted
        
        await db.disconnect()


class TestRedis:
    """Test Redis integration"""
    
    @pytest.mark.asyncio
    async def test_redis_connection(self, test_config):
        """Test Redis connection"""
        from src.database.redis_integration import RedisSessionStore, RedisConfig
        
        config = RedisConfig(
            host=test_config['redis_host'],
            port=test_config['redis_port']
        )
        
        store = RedisSessionStore(config)
        connected = await store.connect()
        
        # Test may run without Redis, skip if not available
        if not connected:
            pytest.skip("Redis not available")
        
        assert store._connected
        
        await store.disconnect()
        assert not store._connected
    
    @pytest.mark.asyncio
    async def test_session_caching(self, test_config):
        """Test session caching"""
        from src.database.redis_integration import RedisSessionStore, RedisConfig
        
        config = RedisConfig(
            host=test_config['redis_host'],
            port=test_config['redis_port']
        )
        
        store = RedisSessionStore(config)
        await store.connect()
        
        if not store._connected:
            pytest.skip("Redis not available")
        
        # Store session
        session_data = {'id': 'test-123', 'status': 'running'}
        stored = await store.set_session('test-123', session_data, ttl_seconds=60)
        assert stored
        
        # Retrieve session
        retrieved = await store.get_session('test-123')
        assert retrieved is not None
        assert retrieved['id'] == 'test-123'
        
        # Delete session
        deleted = await store.delete_session('test-123')
        assert deleted
        
        await store.disconnect()


class TestHealthChecks:
    """Test health check service"""
    
    @pytest.mark.asyncio
    async def test_health_check_initialization(self):
        """Test health checker initialization"""
        from src.services.health import HealthChecker
        
        checker = HealthChecker()
        
        assert len(checker.checkers) > 0
    
    @pytest.mark.asyncio
    async def test_health_check_execution(self):
        """Test health check execution"""
        from src.services.health import HealthChecker
        
        checker = HealthChecker()
        report = await checker.check_all()
        
        assert report is not None
        assert report.status is not None
        assert len(report.checks) > 0


class TestErrorHandling:
    """Test error handling"""
    
    def test_custom_exceptions(self):
        """Test custom exception classes"""
        from src.api.middleware.error_handler import (
            NotFoundError, ValidationError, AuthenticationError
        )
        
        # NotFoundError
        try:
            raise NotFoundError("Session", "test-123")
        except NotFoundError as e:
            assert e.status_code == 404
            assert "test-123" in e.message
        
        # ValidationError
        try:
            raise ValidationError("Invalid email", field="email")
        except ValidationError as e:
            assert e.status_code == 400
            assert e.details['field'] == 'email'
        
        # AuthenticationError
        try:
            raise AuthenticationError()
        except AuthenticationError as e:
            assert e.status_code == 401


class TestCredentialEncryption:
    """Test credential encryption"""
    
    def test_encryption_decryption(self):
        """Test encryption and decryption"""
        from src.utils.credential_encryption import CredentialEncryption
        
        encryption = CredentialEncryption()
        
        # Test dictionary encryption
        data = {'username': 'test', 'password': 'secret123'}
        encrypted = encryption.encrypt(data)
        
        assert encrypted != data
        decrypted = encryption.decrypt(encrypted)
        assert decrypted == data
    
    def test_string_encryption(self):
        """Test string encryption"""
        from src.utils.credential_encryption import CredentialEncryption
        
        encryption = CredentialEncryption()
        
        value = "TestSecretValue"
        encrypted = encryption.encrypt_string(value)
        
        assert encrypted != value
        decrypted = encryption.decrypt_string(encrypted)
        assert decrypted == value


class TestDevContainerParser:
    """Test DevContainer parsing"""
    
    def test_devcontainer_parsing(self):
        """Test DevContainer JSON parsing"""
        from src.parsers.devcontainer import DevContainerParser
        
        parser = DevContainerParser()
        
        # Test config
        config_data = {
            "image": "node:18-alpine",
            "forwardPorts": [3000],
            "extensions": ["dbaeumer.vscode-eslint"],
            "settings": {"terminal.integrated.shell.linux": "/bin/sh"}
        }
        
        config = parser.parse_dict(config_data)
        
        assert config.image == "node:18-alpine"
        assert 3000 in config.forward_ports
        assert "dbaeumer.vscode-eslint" in config.extensions


class TestContainerSecurity:
    """Test container security features"""
    
    def test_security_profiles(self):
        """Test security profiles"""
        from src.containers.orchestrator_enhanced import EnhancedContainerOrchestrator
        
        orchestrator = EnhancedContainerOrchestrator()
        
        # Get default profile
        profile = orchestrator._get_security_profile("default")
        
        assert "no-new-privileges:true" in profile['security_opt']
        assert "ALL" in profile['cap_drop']
        assert profile['read_only'] is True
        assert profile['user'] == "1000:1000"


# Run tests
if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
