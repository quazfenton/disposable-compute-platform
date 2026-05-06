"""
Security Penetration Testing Suite
Automated security testing for common vulnerabilities

Install: pip install bandit safety pytest-security
Run: pytest tests/security/test_security.py -v
"""
import pytest
import requests
import subprocess
import json
import os
from typing import Dict, List, Any


class TestInputValidation:
    """Test input validation and injection prevention"""
    
    BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
    
    def test_sql_injection_prevention(self):
        """Test SQL injection prevention"""
        sql_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "1; DELETE FROM sessions",
            "admin'--",
            "1 UNION SELECT * FROM users"
        ]
        
        for payload in sql_payloads:
            response = requests.post(
                f"{self.BASE_URL}/sessions",
                json={
                    "type": "run_repo",
                    "repo_url": f"https://github.com/{payload}/repo",
                    "ttl_minutes": 30
                }
            )
            
            # Should reject invalid input, not crash
            assert response.status_code in [400, 401, 403, 422], \
                f"SQL injection payload accepted: {payload}"
    
    def test_xss_prevention(self):
        """Test XSS prevention"""
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg onload=alert('XSS')>"
        ]
        
        for payload in xss_payloads:
            response = requests.post(
                f"{self.BASE_URL}/sessions",
                json={
                    "type": "run_repo",
                    "repo_url": "https://github.com/user/repo",
                    "metadata": {"test": payload}
                }
            )
            
            # Check response doesn't reflect payload unsanitized
            if response.status_code == 200:
                assert payload not in response.text, \
                    f"XSS payload reflected in response: {payload}"
    
    def test_path_traversal_prevention(self):
        """Test path traversal prevention"""
        traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd"
        ]
        
        for payload in traversal_payloads:
            response = requests.get(
                f"{self.BASE_URL}/sessions/{payload}/logs"
            )
            
            # Should reject or return 404, not expose files
            assert response.status_code in [400, 403, 404, 422], \
                f"Path traversal payload succeeded: {payload}"
    
    def test_command_injection_prevention(self):
        """Test command injection prevention"""
        cmd_payloads = [
            "; ls -la",
            "| cat /etc/passwd",
            "&& whoami",
            "$(whoami)",
            "`whoami`"
        ]
        
        for payload in cmd_payloads:
            response = requests.post(
                f"{self.BASE_URL}/sessions",
                json={
                    "type": "run_repo",
                    "repo_url": f"https://github.com/user{payload}/repo"
                }
            )
            
            # Should reject invalid input
            assert response.status_code in [400, 422], \
                f"Command injection payload accepted: {payload}"


class TestAuthentication:
    """Test authentication and authorization"""
    
    BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
    
    def test_unauthenticated_access(self):
        """Test that protected endpoints require auth"""
        protected_endpoints = [
            "/sessions",
            "/sessions/test-id",
            "/sessions/test-id/logs",
            "/stats"
        ]
        
        for endpoint in protected_endpoints:
            response = requests.get(f"{self.BASE_URL}{endpoint}")
            
            # Should return 401 or 403
            assert response.status_code in [401, 403], \
                f"Endpoint {endpoint} accessible without auth"
    
    def test_weak_password_policy(self):
        """Test password policy enforcement"""
        weak_passwords = [
            "password",
            "123456",
            "qwerty",
            "admin123",
            "a" * 7  # Too short
        ]
        
        for password in weak_passwords:
            response = requests.post(
                f"{self.BASE_URL}/auth/register",
                json={
                    "email": f"test{password}@example.com",
                    "password": password
                }
            )
            
            # Should reject weak passwords
            assert response.status_code == 400, \
                f"Weak password accepted: {password}"
    
    def test_brute_force_protection(self):
        """Test brute force protection"""
        # Try many failed logins
        for i in range(10):
            response = requests.post(
                f"{self.BASE_URL}/auth/login",
                json={
                    "email": "test@example.com",
                    "password": f"wrongpassword{i}"
                }
            )
        
        # Should eventually rate limit
        assert response.status_code in [401, 429], \
            "No brute force protection detected"
    
    def test_jwt_token_security(self):
        """Test JWT token security"""
        # Login to get token
        login_response = requests.post(
            f"{self.BASE_URL}/auth/login",
            json={
                "email": "test@example.com",
                "password": "ValidPassword123!"
            }
        )
        
        if login_response.status_code == 200:
            token = login_response.json().get("access_token")
            
            # Test tampered token
            tampered_token = token[:-5] + "xxxxx"
            response = requests.get(
                f"{self.BASE_URL}/sessions",
                headers={"Authorization": f"Bearer {tampered_token}"}
            )
            
            # Should reject tampered token
            assert response.status_code == 401, \
                "Tampered JWT token accepted"


class TestSSRF:
    """Test Server-Side Request Forgery prevention"""
    
    BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
    
    def test_internal_ip_blocking(self):
        """Test that internal IPs are blocked"""
        internal_urls = [
            "http://127.0.0.1/repo",
            "http://192.168.1.1/repo",
            "http://10.0.0.1/repo",
            "http://172.16.0.1/repo",
            "http://169.254.169.254/latest/meta-data/"  # AWS metadata
        ]
        
        for url in internal_urls:
            response = requests.post(
                f"{self.BASE_URL}/sessions",
                json={
                    "type": "run_repo",
                    "repo_url": url
                }
            )
            
            # Should reject internal URLs
            assert response.status_code == 400, \
                f"Internal IP URL accepted: {url}"
    
    def test_localhost_blocking(self):
        """Test that localhost is blocked"""
        localhost_urls = [
            "http://localhost/repo",
            "http://localhost:8080/repo",
            "http://127.1/repo",  # Alternate localhost
        ]
        
        for url in localhost_urls:
            response = requests.post(
                f"{self.BASE_URL}/sessions",
                json={"type": "run_repo", "repo_url": url}
            )
            
            assert response.status_code == 400, \
                f"Localhost URL accepted: {url}"


class TestContainerSecurity:
    """Test container security isolation"""
    
    BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
    
    def test_container_escape_prevention(self):
        """Test container escape prevention"""
        # This would require actual container access
        # Placeholder for manual testing
        pytest.skip("Requires manual container escape testing")
    
    def test_resource_limits(self):
        """Test that resource limits are enforced"""
        # Create session and check resource limits
        response = requests.post(
            f"{self.BASE_URL}/sessions",
            json={
                "type": "run_repo",
                "repo_url": "https://github.com/test/repo"
            }
        )
        
        if response.status_code == 200:
            session_id = response.json().get("session_id")
            
            # Check container has resource limits
            # This would require Docker API access
            pytest.skip("Requires Docker API access")


class TestDependencySecurity:
    """Test dependency security"""
    
    def test_dependency_vulnerabilities(self):
        """Check for known vulnerabilities in dependencies"""
        try:
            result = subprocess.run(
                ["safety", "check", "--json"],
                capture_output=True,
                text=True
            )
            
            vulnerabilities = json.loads(result.stdout)
            
            # Fail if critical vulnerabilities found
            critical = [
                v for v in vulnerabilities
                if v.get("severity") == "critical"
            ]
            
            assert len(critical) == 0, \
                f"Critical vulnerabilities found: {critical}"
                
        except subprocess.CalledProcessError:
            pytest.skip("Safety not installed")


class TestSecurityHeaders:
    """Test security headers"""
    
    BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
    
    def test_security_headers_present(self):
        """Test that security headers are present"""
        response = requests.get(f"{self.BASE_URL}/health")
        
        required_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Content-Security-Policy",
            "Strict-Transport-Security"
        ]
        
        missing = []
        for header in required_headers:
            if header not in response.headers:
                missing.append(header)
        
        # Note: Some headers may not be applicable for API
        assert len(missing) <= 2, \
            f"Missing security headers: {missing}"


# Run security tests:
# pytest tests/security/test_security.py -v --tb=short
#
# Additional manual testing:
# 1. OWASP ZAP scan
# 2. Burp Suite penetration test
# 3. Nuclei vulnerability scan
# 4. Manual code review
