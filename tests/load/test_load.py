"""
Load Testing Suite for Disposable Compute Platform
Uses Locust for load testing, stress testing, and performance benchmarking

Install: pip install locust
Run: locust -f tests/load/test_load.py --host=http://localhost:8000
"""
import random
import string
import time
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner
import logging

logger = logging.getLogger(__name__)


class SessionLoadTest(HttpUser):
    """Load test for session lifecycle operations"""
    
    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks
    
    # Test data
    valid_repos = [
        "https://github.com/vercel/next.js",
        "https://github.com/fastapi/fastapi",
        "https://github.com/docker/compose",
        "https://github.com/microsoft/vscode",
        "https://github.com/facebook/react"
    ]
    
    def on_start(self):
        """Called when a simulated user starts"""
        # Could authenticate here if needed
        pass
    
    @task(3)
    def get_health(self):
        """Test health endpoint (most common)"""
        self.client.get("/health", name="GET /health")
    
    @task(5)
    def get_session(self):
        """Test getting session details"""
        # Use a known session ID or skip
        session_id = self.get_cached_session_id()
        if session_id:
            self.client.get(
                f"/sessions/{session_id}",
                name="GET /sessions/[id]"
            )
        else:
            # Skip if no session cached
            pass
    
    @task(10)
    def create_session(self):
        """Test session creation (most important)"""
        repo_url = random.choice(self.valid_repos)
        
        response = self.client.post(
            "/sessions",
            json={
                "type": "run_repo",
                "repo_url": repo_url,
                "ttl_minutes": 30
            },
            name="POST /sessions"
        )
        
        if response.status_code == 200:
            # Cache session ID for later use
            session_id = response.json().get("session_id")
            self.cache_session_id(session_id)
    
    @task(2)
    def get_logs(self):
        """Test log retrieval"""
        session_id = self.get_cached_session_id()
        if session_id:
            self.client.get(
                f"/sessions/{session_id}/logs?lines=50",
                name="GET /sessions/[id]/logs"
            )
    
    @task(1)
    def destroy_session(self):
        """Test session destruction"""
        session_id = self.get_cached_session_id()
        if session_id:
            self.client.delete(
                f"/sessions/{session_id}",
                name="DELETE /sessions/[id]"
            )
            self.clear_cached_session_id()
    
    # Helper methods
    def cache_session_id(self, session_id: str):
        """Cache session ID for reuse"""
        if not hasattr(self, '_session_cache'):
            self._session_cache = []
        self._session_cache.append(session_id)
        # Limit cache size
        if len(self._session_cache) > 10:
            self._session_cache.pop(0)
    
    def get_cached_session_id(self) -> str:
        """Get a cached session ID"""
        if hasattr(self, '_session_cache') and self._session_cache:
            return random.choice(self._session_cache)
        return None
    
    def clear_cached_session_id(self):
        """Clear cached session ID"""
        if hasattr(self, '_session_cache') and self._session_cache:
            self._session_cache.pop()


class AuthLoadTest(HttpUser):
    """Load test for authentication endpoints"""
    
    wait_time = between(2, 5)
    
    @task(10)
    def login(self):
        """Test login endpoint"""
        # Use test credentials
        self.client.post(
            "/auth/login",
            json={
                "email": f"test{random.randint(1, 100)}@example.com",
                "password": "TestPassword123!"
            },
            name="POST /auth/login"
        )
    
    @task(5)
    def access_protected(self):
        """Test accessing protected endpoint with token"""
        # Would need valid token from login
        pass


class APIStressTest(HttpUser):
    """Stress test - push system to breaking point"""
    
    wait_time = between(0.1, 0.5)  # Minimal wait
    
    @task
    def rapid_requests(self):
        """Send rapid requests to test rate limiting"""
        self.client.get("/health", name="GET /health (stress)")


class EnduranceTest(HttpUser):
    """Endurance test - run for extended period"""
    
    wait_time = between(5, 10)
    test_duration = 3600  # 1 hour
    
    @task(5)
    def mixed_operations(self):
        """Mixed workload over extended period"""
        operations = [
            ("GET /health", lambda: self.client.get("/health")),
            ("GET /stats", lambda: self.client.get("/stats")),
        ]
        
        name, operation = random.choice(operations)
        with self.client.get("/health", name="Endurance: GET /health"):
            pass


# Event handlers for custom metrics
@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """Track custom metrics on each request"""
    if exception:
        logger.error(f"Request failed: {name} - {exception}")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts"""
    logger.info("Load test starting...")
    
    # Set custom environment variables
    environment.host = environment.host or "http://localhost:8000"


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops"""
    logger.info("Load test completed")
    
    # Print summary
    stats = environment.stats
    logger.info(f"Total requests: {stats.total.num_requests}")
    logger.info(f"Failures: {stats.total.num_failures}")
    logger.info(f"Avg response time: {stats.total.avg_response_time:.2f}ms")


# Load test configurations
class LoadTestConfig:
    """Configuration for different load test scenarios"""
    
    # Smoke test - verify system works
    SMOKE = {
        "users": 10,
        "spawn_rate": 2,
        "run_time": "5m"
    }
    
    # Load test - normal operating conditions
    LOAD = {
        "users": 100,
        "spawn_rate": 10,
        "run_time": "30m"
    }
    
    # Stress test - push to breaking point
    STRESS = {
        "users": 500,
        "spawn_rate": 50,
        "run_time": "15m"
    }
    
    # Spike test - sudden traffic surge
    SPIKE = {
        "users": 1000,
        "spawn_rate": 100,
        "run_time": "5m"
    }
    
    # Endurance test - extended runtime
    ENDURANCE = {
        "users": 50,
        "spawn_rate": 5,
        "run_time": "4h"
    }


# Performance thresholds
class PerformanceThresholds:
    """Acceptable performance thresholds"""
    
    HEALTH_ENDPOINT = {
        "p50": 50,  # ms
        "p95": 100,
        "p99": 200,
        "failure_rate": 0.1  # %
    }
    
    SESSION_CREATE = {
        "p50": 3000,  # ms (includes container startup)
        "p95": 10000,
        "p99": 30000,
        "failure_rate": 1.0
    }
    
    SESSION_GET = {
        "p50": 100,
        "p95": 500,
        "p99": 1000,
        "failure_rate": 0.5
    }


# Run with: locust -f tests/load/test_load.py --headless -u 100 -r 10 -t 5m --host=http://localhost:8000
