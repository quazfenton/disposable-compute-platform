"""
Advanced Load Testing Suite with Enhanced Scenarios
Includes: Soak testing, Spike testing, Stress testing, and Performance regression
"""
import random
import string
import time
import json
from datetime import datetime, timedelta
from locust import HttpUser, task, between, events, constant_pacing
from locust.runners import MasterRunner, WorkerRunner
from locust import stats
import logging
import os

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

class TestConfig:
    """Centralized test configuration"""
    
    # API Endpoints
    ENDPOINTS = {
        'health': '/health',
        'sessions': '/sessions',
        'stats': '/stats',
        'auth_login': '/auth/login'
    }
    
    # Test data
    VALID_REPOS = [
        "https://github.com/vercel/next.js",
        "https://github.com/fastapi/fastapi",
        "https://github.com/docker/compose",
        "https://github.com/microsoft/vscode",
        "https://github.com/facebook/react",
        "https://github.com/tensorflow/tensorflow",
        "https://github.com/kubernetes/kubernetes",
    ]
    
    # Performance thresholds (milliseconds)
    THRESHOLDS = {
        'health': {'p95': 100, 'p99': 200},
        'sessions': {'p95': 10000, 'p99': 30000},
        'stats': {'p95': 500, 'p99': 1000},
    }
    
    # User behavior weights
    WEIGHTS = {
        'health': 30,
        'create_session': 40,
        'get_session': 20,
        'get_logs': 10,
    }


# ============================================================================
# BASE USER CLASSES
# ============================================================================

class BaseUser(HttpUser):
    """Base user class with common functionality"""
    
    abstract = True
    
    def __init__(self, parent):
        super().__init__(parent)
        self._session_cache = []
        self._auth_token = None
    
    def cache_session(self, session_id: str):
        """Cache session ID for reuse"""
        self._session_cache.append(session_id)
        if len(self._session_cache) > 20:
            self._session_cache.pop(0)
    
    def get_cached_session(self) -> str:
        """Get cached session ID"""
        if self._session_cache:
            return random.choice(self._session_cache)
        return None
    
    def clear_cache(self):
        """Clear session cache"""
        self._session_cache = []


# ============================================================================
# LOAD TEST SCENARIOS
# ============================================================================

class NormalLoadUser(BaseUser):
    """
    Normal load user - simulates typical user behavior
    Use case: Baseline performance testing
    """
    
    wait_time = between(2, 5)
    priority = 1
    
    @task(TestConfig.WEIGHTS['health'])
    def health_check(self):
        """Health check endpoint"""
        self.client.get(
            TestConfig.ENDPOINTS['health'],
            name="GET /health"
        )
    
    @task(TestConfig.WEIGHTS['create_session'])
    def create_session(self):
        """Create new session"""
        repo_url = random.choice(TestConfig.VALID_REPOS)
        
        with self.client.post(
            TestConfig.ENDPOINTS['sessions'],
            json={
                "type": "run_repo",
                "repo_url": repo_url,
                "ttl_minutes": random.choice([30, 60, 120])
            },
            name="POST /sessions",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                session_id = response.json().get("session_id")
                self.cache_session(session_id)
                response.success()
            else:
                response.failure(f"Failed to create session: {response.status_code}")
    
    @task(TestConfig.WEIGHTS['get_session'])
    def get_session(self):
        """Get session details"""
        session_id = self.get_cached_session()
        
        if session_id:
            self.client.get(
                f"{TestConfig.ENDPOINTS['sessions']}/{session_id}",
                name="GET /sessions/[id]"
            )
    
    @task(TestConfig.WEIGHTS['get_logs'])
    def get_logs(self):
        """Get session logs"""
        session_id = self.get_cached_session()
        
        if session_id:
            self.client.get(
                f"{TestConfig.ENDPOINTS['sessions']}/{session_id}/logs?lines=50",
                name="GET /sessions/[id]/logs"
            )


class PowerUser(BaseUser):
    """
    Power user - heavy API usage, multiple concurrent operations
    Use case: Stress testing, power user simulation
    """
    
    wait_time = between(0.5, 2)
    priority = 2
    
    @task(5)
    def rapid_session_creation(self):
        """Create multiple sessions rapidly"""
        for _ in range(3):
            repo_url = random.choice(TestConfig.VALID_REPOS)
            
            self.client.post(
                TestConfig.ENDPOINTS['sessions'],
                json={
                    "type": "run_repo",
                    "repo_url": repo_url,
                    "ttl_minutes": 30
                },
                name="POST /sessions (rapid)"
            )
            time.sleep(0.1)
    
    @task(3)
    def batch_operations(self):
        """Perform batch operations"""
        # Create session
        create_resp = self.client.post(
            TestConfig.ENDPOINTS['sessions'],
            json={
                "type": "run_repo",
                "repo_url": random.choice(TestConfig.VALID_REPOS),
                "ttl_minutes": 60
            },
            name="POST /sessions (batch)"
        )
        
        if create_resp.status_code == 200:
            session_id = create_resp.json().get("session_id")
            self.cache_session(session_id)
            
            # Immediately get session
            self.client.get(
                f"{TestConfig.ENDPOINTS['sessions']}/{session_id}",
                name="GET /sessions/[id] (batch)"
            )
            
            # Get logs
            self.client.get(
                f"{TestConfig.ENDPOINTS['sessions']}/{session_id}/logs",
                name="GET /sessions/[id]/logs (batch)"
            )
    
    @task(2)
    def stats_heavy(self):
    """Hit stats endpoint repeatedly"""
        for _ in range(5):
            self.client.get(
                TestConfig.ENDPOINTS['stats'],
                name="GET /stats (heavy)"
            )
            time.sleep(0.05)


class APIExplorerUser(BaseUser):
    """
    API Explorer - tests all endpoints systematically
    Use case: Full API coverage testing
    """
    
    wait_time = between(1, 3)
    priority = 3
    
    @task(1)
    def explore_all_endpoints(self):
        """Test all available endpoints"""
        endpoints_to_test = [
            ("GET", "/health", None),
            ("GET", "/stats", None),
            ("GET", "/", None),
        ]
        
        for method, endpoint, data in endpoints_to_test:
            if method == "GET":
                self.client.get(endpoint, name=f"EXPLORE: {method} {endpoint}")
            elif method == "POST":
                self.client.post(endpoint, json=data, name=f"EXPLORE: {method} {endpoint}")


# ============================================================================
# SPECIALIZED TEST SCENARIOS
# ============================================================================

class SpikeTestUser(BaseUser):
    """
    Spike test user - sudden traffic surge simulation
    Use case: Test auto-scaling, capacity limits
    """
    
    wait_time = constant_pacing(0.1)  # Fixed pace
    priority = 4
    
    @task
    def spike_request(self):
        """Single rapid request"""
        self.client.get(
            TestConfig.ENDPOINTS['health'],
            name="SPIKE: GET /health"
        )


class SoakTestUser(BaseUser):
    """
    Soak test user - extended duration testing
    Use case: Memory leak detection, resource exhaustion
    """
    
    wait_time = between(5, 10)
    priority = 5
    
    @task(10)
    def sustained_load(self):
        """Sustained moderate load"""
        self.client.get(
            TestConfig.ENDPOINTS['health'],
            name="SOAK: GET /health"
        )
    
    @task(5)
    def periodic_session(self):
        """Periodic session creation"""
        self.client.post(
            TestConfig.ENDPOINTS['sessions'],
            json={
                "type": "run_repo",
                "repo_url": random.choice(TestConfig.VALID_REPOS),
                "ttl_minutes": 30
            },
            name="SOAK: POST /sessions"
        )


class ErrorConditionUser(BaseUser):
    """
    Error condition user - tests error handling
    Use case: Error response validation, rate limiting
    """
    
    wait_time = between(0.1, 0.5)
    priority = 6
    
    @task(5)
    def invalid_requests(self):
        """Send invalid requests"""
        invalid_payloads = [
            {"type": "invalid_type", "repo_url": "https://github.com/test/repo"},
            {"type": "run_repo", "repo_url": "not-a-valid-url"},
            {"type": "run_repo", "repo_url": "http://192.168.1.1/internal"},  # SSRF attempt
            {},  # Empty payload
        ]
        
        for payload in invalid_payloads:
            self.client.post(
                TestConfig.ENDPOINTS['sessions'],
                json=payload,
                name="ERROR: Invalid payload",
                expect_error=True
            )
    
    @task(3)
    def rate_limit_test(self):
        """Test rate limiting"""
        for _ in range(20):
            self.client.get(
                TestConfig.ENDPOINTS['health'],
                name="ERROR: Rate limit test"
            )


# ============================================================================
# AUTHENTICATION TEST SCENARIOS
# ============================================================================

class AuthUser(BaseUser):
    """
    Authentication test user
    Use case: Auth flow testing, token validation
    """
    
    wait_time = between(2, 5)
    priority = 7
    
    def on_start(self):
        """Login on start"""
        self.login()
    
    def login(self):
        """Perform login"""
        response = self.client.post(
            TestConfig.ENDPOINTS['auth_login'],
            json={
                "email": f"test{random.randint(1, 1000)}@example.com",
                "password": "TestPassword123!"
            },
            name="POST /auth/login"
        )
        
        if response.status_code == 200:
            self._auth_token = response.json().get("access_token")
    
    @task(5)
    def authenticated_request(self):
        """Make authenticated request"""
        if self._auth_token:
            self.client.get(
                TestConfig.ENDPOINTS['sessions'],
                headers={"Authorization": f"Bearer {self._auth_token}"},
                name="AUTH: GET /sessions"
            )
    
    @task(2)
    def token_refresh(self):
        """Refresh auth token"""
        self.login()


# ============================================================================
# EVENT HANDLERS & METRICS
# ============================================================================

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """Custom request logging and metrics"""
    if exception:
        logger.error(f"Request failed: {name} - {exception}")
    
    # Log slow requests
    if response_time > 5000:
        logger.warning(f"Slow request: {name} took {response_time:.2f}ms")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Setup before test starts"""
    logger.info("=" * 60)
    logger.info("LOAD TEST STARTING")
    logger.info("=" * 60)
    logger.info(f"Target host: {environment.host}")
    logger.info(f"Available users: {[c.__name__ for c in environment.user_classes]}")
    
    # Reset stats
    stats.clear_all()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Cleanup and reporting after test ends"""
    logger.info("=" * 60)
    logger.info("LOAD TEST COMPLETE")
    logger.info("=" * 60)
    
    # Print summary
    stats.print_stats()
    
    # Check thresholds
    for endpoint, thresholds in TestConfig.THRESHOLDS.items():
        for stat in environment.stats.entries:
            if endpoint in stat.name:
                p95 = stat.get_response_time_percentile(0.95)
                p99 = stat.get_response_time_percentile(0.99)
                
                if p95 > thresholds['p95']:
                    logger.warning(f"⚠️  {endpoint} P95 ({p95:.2f}ms) exceeds threshold ({thresholds['p95']}ms)")
                
                if p99 > thresholds['p99']:
                    logger.warning(f"⚠️  {endpoint} P99 ({p99:.2f}ms) exceeds threshold ({thresholds['p99']}ms)")


@events.quorum.add_listener
def on_quorum_reached(environment, **kwargs):
    """Called when worker quorum is reached"""
    logger.info("Worker quorum reached, starting test")


# ============================================================================
# LOAD PROFILES
# ============================================================================

class LoadProfiles:
    """Pre-defined load profiles for different test scenarios"""
    
    SMOKE = {
        "user_classes": [NormalLoadUser],
        "users": 10,
        "spawn_rate": 2,
        "run_time": "5m",
        "description": "Smoke test - verify system works"
    }
    
    BASELINE = {
        "user_classes": [NormalLoadUser],
        "users": 50,
        "spawn_rate": 5,
        "run_time": "30m",
        "description": "Baseline - normal operating conditions"
    }
    
    LOAD = {
        "user_classes": [NormalLoadUser, PowerUser],
        "users": 100,
        "spawn_rate": 10,
        "run_time": "1h",
        "description": "Load test - expected peak traffic"
    }
    
    STRESS = {
        "user_classes": [NormalLoadUser, PowerUser, APIExplorerUser],
        "users": 300,
        "spawn_rate": 30,
        "run_time": "30m",
        "description": "Stress test - beyond expected capacity"
    }
    
    SPIKE = {
        "user_classes": [SpikeTestUser],
        "users": 500,
        "spawn_rate": 100,
        "run_time": "10m",
        "description": "Spike test - sudden traffic surge"
    }
    
    SOAK = {
        "user_classes": [SoakTestUser],
        "users": 25,
        "spawn_rate": 5,
        "run_time": "4h",
        "description": "Soak test - extended duration"
    }
    
    ERROR = {
        "user_classes": [ErrorConditionUser],
        "users": 20,
        "spawn_rate": 5,
        "run_time": "15m",
        "description": "Error handling test"
    }
    
    MIXED = {
        "user_classes": [NormalLoadUser, PowerUser, AuthUser, ErrorConditionUser],
        "users": 150,
        "spawn_rate": 15,
        "run_time": "2h",
        "description": "Mixed workload - realistic traffic pattern"
    }


# ============================================================================
# RUN COMMANDS
# ============================================================================

"""
Run commands for different test scenarios:

# Smoke test
locust -f tests/load/test_load_advanced.py --headless -u 10 -r 2 -t 5m \
  --host=http://localhost:8000

# Baseline test
locust -f tests/load/test_load_advanced.py --headless -u 50 -r 5 -t 30m \
  --host=http://localhost:8000

# Load test
locust -f tests/load/test_load_advanced.py --headless -u 100 -r 10 -t 1h \
  --host=http://localhost:8000

# Stress test
locust -f tests/load/test_load_advanced.py --headless -u 300 -r 30 -t 30m \
  --host=http://localhost:8000

# Spike test
locust -f tests/load/test_load_advanced.py --headless -u 500 -r 100 -t 10m \
  --host=http://localhost:8000

# Soak test
locust -f tests/load/test_load_advanced.py --headless -u 25 -r 5 -t 4h \
  --host=http://localhost:8000

# Mixed workload
locust -f tests/load/test_load_advanced.py --headless -u 150 -r 15 -t 2h \
  --host=http://localhost:8000

# Distributed (master/worker)
locust -f tests/load/test_load_advanced.py --master
locust -f tests/load/test_load_advanced.py --worker --master-host=localhost

# With custom threshold checking
locust -f tests/load/test_load_advanced.py --headless -u 100 -r 10 -t 30m \
  --host=http://localhost:8000 --csv=results/
"""
