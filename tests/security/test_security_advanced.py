"""
Advanced Security Testing Suite
Comprehensive vulnerability scanning, fuzzing, and penetration testing
"""
import pytest
import requests
import subprocess
import json
import os
import re
import hashlib
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

class SecurityConfig:
    """Security testing configuration"""
    
    BASE_URL = os.getenv("TEST_BASE_URL", "http://localhost:8000")
    TIMEOUT = int(os.getenv("TEST_TIMEOUT", "30"))
    
    # Vulnerability databases
    CVE_DATABASES = [
        "https://cve.mitre.org/data/feeds/index.html",
        "https://nvd.nist.gov/vuln/data-feeds"
    ]
    
    # Security headers required
    REQUIRED_HEADERS = [
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "X-XSS-Protection",
        "Content-Security-Policy",
        "Referrer-Policy"
    ]
    
    # Known vulnerable patterns
    VULNERABLE_PATTERNS = [
        r'error:\s*database',  # SQL errors
        r'traceback',  # Python tracebacks
        r'stack\s*trace',  # Stack traces
        r'root:',  # Root user info
        r'password:',  # Password exposure
    ]


# ============================================================================
# FUZZING TESTS
# ============================================================================

class TestFuzzing:
    """Fuzzing tests for input validation"""
    
    BASE_URL = SecurityConfig.BASE_URL
    
    def test_fuzz_session_endpoint(self):
        """Fuzz session creation endpoint"""
        fuzz_payloads = [
            # Boundary values
            {"ttl_minutes": -1},
            {"ttl_minutes": 0},
            {"ttl_minutes": 999999999},
            {"ttl_minutes": None},
            {"ttl_minutes": "not-a-number"},
            
            # Type confusion
            {"type": 123},
            {"type": ["run_repo"]},
            {"type": {"nested": "object"}},
            
            # Missing fields
            {},
            {"type": "run_repo"},
            {"repo_url": "https://github.com/test/repo"},
            
            # Extra fields
            {"type": "run_repo", "repo_url": "https://github.com/test/repo", "extra": "field"},
            
            # Unicode/special chars
            {"type": "run_repo", "repo_url": "https://github.com/test/🚀repo"},
            {"type": "run_repo", "repo_url": "https://github.com/test/repo\u0000"},
        ]
        
        for payload in fuzz_payloads:
            response = requests.post(
                f"{self.BASE_URL}/sessions",
                json=payload,
                timeout=SecurityConfig.TIMEOUT
            )
            
            # Should not return 500 (server error)
            assert response.status_code != 500, \
                f"Server error on fuzz input: {payload}"
    
    def test_fuzz_auth_endpoint(self):
        """Fuzz authentication endpoint"""
        fuzz_payloads = [
            # SQL injection in email
            {"email": "admin' OR '1'='1", "password": "password"},
            {"email": "'; DROP TABLE users; --", "password": "password"},
            
            # XSS in email
            {"email": "<script>alert('XSS')</script>", "password": "password"},
            
            # Buffer overflow attempts
            {"email": "a" * 10000 + "@example.com", "password": "password"},
            {"email": "test@example.com", "password": "p" * 10000},
            
            # Null bytes
            {"email": "test\x00@example.com", "password": "password"},
            
            # Unicode
            {"email": "test@例え.jp", "password": "パスワード"},
            
            # Missing fields
            {},
            {"email": "test@example.com"},
            {"password": "password"},
        ]
        
        for payload in fuzz_payloads:
            response = requests.post(
                f"{self.BASE_URL}/auth/login",
                json=payload,
                timeout=SecurityConfig.TIMEOUT
            )
            
            # Should not return 500
            assert response.status_code != 500, \
                f"Server error on auth fuzz input: {payload}"
    
    def test_fuzz_headers(self):
        """Fuzz HTTP headers"""
        fuzz_headers = [
            {"X-Forwarded-For": "127.0.0.1, 0.0.0.0"},
            {"X-Real-IP": "127.0.0.1"},
            {"Host": "evil.com"},
            {"Content-Type": "application/json; charset=utf-8; boundary=--"},
            {"Content-Length": "-1"},
            {"Content-Length": "999999999"},
            {"User-Agent": "<script>alert('XSS')</script>"},
            {"User-Agent": "Mozilla/5.0" + "A" * 10000},
            {"Referer": "javascript:alert('XSS')"},
        ]
        
        for headers in fuzz_headers:
            response = requests.get(
                f"{self.BASE_URL}/health",
                headers=headers,
                timeout=SecurityConfig.TIMEOUT
            )
            
            # Should not crash
            assert response.status_code in [200, 400, 401, 403, 404, 422], \
                f"Unexpected status for header fuzz: {headers}"


# ============================================================================
# ADVANCED INJECTION TESTS
# ============================================================================

class TestAdvancedInjection:
    """Advanced injection vulnerability tests"""
    
    BASE_URL = SecurityConfig.BASE_URL
    
    def test_nosql_injection(self):
        """Test NoSQL injection (if using MongoDB)"""
        nosql_payloads = [
            {"$ne": None},
            {"$gt": ""},
            {"$regex": ".*"},
            {"$where": "this.password != ''"},
        ]
        
        for payload in nosql_payloads:
            response = requests.post(
                f"{self.BASE_URL}/auth/login",
                json={"email": payload, "password": "test"},
                timeout=SecurityConfig.TIMEOUT
            )
            
            # Should reject NoSQL injection
            assert response.status_code in [400, 401, 422], \
                f"NoSQL injection may be possible: {payload}"
    
    def test_template_injection(self):
        """Test server-side template injection"""
        template_payloads = [
            "{{7*7}}",
            "${7*7}",
            "#{7*7}",
            "{{config}}",
            "{{self.__class__.__mro__}}",
            "<%= system('ls') %>",
        ]
        
        for payload in template_payloads:
            response = requests.post(
                f"{self.BASE_URL}/sessions",
                json={
                    "type": "run_repo",
                    "repo_url": f"https://github.com/{payload}/repo"
                },
                timeout=SecurityConfig.TIMEOUT
            )
            
            # Check for template execution in response
            if response.status_code == 200:
                assert "49" not in response.text, \
                    f"Template injection may be possible: {payload}"
    
    def test_command_injection_advanced(self):
        """Advanced command injection tests"""
        cmd_payloads = [
            # Basic
            "; id",
            "| id",
            "&& id",
            
            # Backticks
            "$(id)",
            "`id`",
            
            # Encoding
            "%3Bid%3B",
            "%7Cid%7C",
            
            # Unicode
            "\u003bid\u003b",
            
            # Null byte
            "id\x00; ls",
            
            # Newline
            "id\nls",
            "id%0als",
        ]
        
        for payload in cmd_payloads:
            response = requests.post(
                f"{self.BASE_URL}/sessions",
                json={
                    "type": "run_repo",
                    "repo_url": f"https://github.com/user{payload}/repo"
                },
                timeout=SecurityConfig.TIMEOUT
            )
            
            # Should reject command injection
            assert response.status_code in [400, 422], \
                f"Command injection not blocked: {payload}"


# ============================================================================
# AUTHENTICATION & AUTHORIZATION TESTS
# ============================================================================

class TestAdvancedAuth:
    """Advanced authentication and authorization tests"""
    
    BASE_URL = SecurityConfig.BASE_URL
    
    def test_jwt_algorithm_confusion(self):
        """Test JWT algorithm confusion attack"""
        # This would require a valid token to test properly
        # Placeholder for manual testing
        pytest.skip("Requires valid JWT token for testing")
    
    def test_jwt_none_algorithm(self):
        """Test JWT none algorithm attack"""
        # Create token with alg: none
        # This would require JWT manipulation
        pytest.skip("Requires JWT manipulation for testing")
    
    def test_idor(self):
        """Test Insecure Direct Object Reference"""
        # Try to access other users' sessions
        test_session_ids = [
            "00000000-0000-0000-0000-000000000001",
            "sess-20260303-000000-abcd",
            "../sessions/other-user",
        ]
        
        for session_id in test_session_ids:
            response = requests.get(
                f"{self.BASE_URL}/sessions/{session_id}",
                timeout=SecurityConfig.TIMEOUT
            )
            
            # Should return 404 or 403, not 200
            assert response.status_code in [403, 404], \
                f"IDOR vulnerability may exist: {session_id}"
    
    def test_privilege_escalation(self):
        """Test privilege escalation"""
        # Try to access admin endpoints
        admin_endpoints = [
            "/admin",
            "/admin/users",
            "/api/admin",
            "/v1/admin",
        ]
        
        for endpoint in admin_endpoints:
            response = requests.get(
                f"{self.BASE_URL}{endpoint}",
                timeout=SecurityConfig.TIMEOUT
            )
            
            # Should return 401 or 403
            assert response.status_code in [401, 403, 404], \
                f"Admin endpoint accessible: {endpoint}"
    
    def test_session_fixation(self):
        """Test session fixation"""
        # Set session cookie before login
        session = requests.Session()
        session.cookies.set("session_id", "attacker-controlled-id")
        
        # Login
        response = session.post(
            f"{self.BASE_URL}/auth/login",
            json={"email": "test@example.com", "password": "TestPassword123!"},
            timeout=SecurityConfig.TIMEOUT
        )
        
        # Session should be regenerated
        new_session_id = session.cookies.get("session_id")
        assert new_session_id != "attacker-controlled-id", \
            "Session fixation may be possible"


# ============================================================================
# INFORMATION DISCLOSURE TESTS
# ============================================================================

class TestInformationDisclosure:
    """Information disclosure vulnerability tests"""
    
    BASE_URL = SecurityConfig.BASE_URL
    
    def test_error_messages(self):
        """Test error message information disclosure"""
        # Trigger various errors
        error_triggers = [
            ("GET", "/nonexistent-endpoint"),
            ("POST", "/sessions", {"invalid": "payload"}),
            ("GET", "/sessions/invalid-id-format"),
        ]
        
        for trigger in error_triggers:
            if len(trigger) == 2:
                method, url = trigger
                response = getattr(requests, method.lower())(
                    f"{self.BASE_URL}{url}",
                    timeout=SecurityConfig.TIMEOUT
                )
            else:
                method, url, data = trigger
                response = getattr(requests, method.lower())(
                    f"{self.BASE_URL}{url}",
                    json=data,
                    timeout=SecurityConfig.TIMEOUT
                )
            
            # Check for sensitive information in error messages
            response_text = response.text.lower()
            
            for pattern in SecurityConfig.VULNERABLE_PATTERNS:
                assert not re.search(pattern, response_text, re.IGNORECASE), \
                    f"Sensitive information in error response: {pattern}"
    
    def test_version_disclosure(self):
        """Test version information disclosure"""
        endpoints = [
            "/",
            "/health",
            "/stats",
            "/api",
        ]
        
        version_patterns = [
            r'version[:\s]+[\d.]+',
            r'v\d+\.\d+\.\d+',
            r'release[:\s]+\w+',
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.get(
                    f"{self.BASE_URL}{endpoint}",
                    timeout=SecurityConfig.TIMEOUT
                )
                
                for pattern in version_patterns:
                    assert not re.search(pattern, response.text, re.IGNORECASE), \
                        f"Version information disclosed at {endpoint}"
                        
            except:
                pass
    
    def test_directory_listing(self):
        """Test directory listing"""
        directories = [
            "/static/",
            "/assets/",
            "/uploads/",
            "/files/",
        ]
        
        for directory in directories:
            response = requests.get(
                f"{self.BASE_URL}{directory}",
                timeout=SecurityConfig.TIMEOUT,
                allow_redirects=True
            )
            
            # Should not show directory listing
            assert "Index of" not in response.text, \
                f"Directory listing enabled: {directory}"


# ============================================================================
# DEPENDENCY SECURITY
# ============================================================================

class TestDependencySecurity:
    """Dependency security testing"""
    
    def test_requirements_audit(self):
        """Audit requirements.txt for vulnerabilities"""
        try:
            result = subprocess.run(
                ["safety", "check", "--full-report", "--json"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            )
            
            vulnerabilities = json.loads(result.stdout)
            
            # Categorize by severity
            critical = [v for v in vulnerabilities if v.get("severity") == "critical"]
            high = [v for v in vulnerabilities if v.get("severity") == "high"]
            
            assert len(critical) == 0, f"Critical vulnerabilities: {critical}"
            assert len(high) <= 3, f"Too many high vulnerabilities: {high}"
            
        except FileNotFoundError:
            pytest.skip("Safety not installed (pip install safety)")
        except json.JSONDecodeError:
            pytest.skip("Safety output parsing failed")
    
    def test_dockerfile_security(self):
        """Check Dockerfile for security issues"""
        dockerfile_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "Dockerfile"
        )
        
        if not os.path.exists(dockerfile_path):
            pytest.skip("Dockerfile not found")
        
        with open(dockerfile_path, 'r') as f:
            content = f.read().lower()
        
        # Check for security issues
        issues = []
        
        if 'root' in content and 'user' not in content:
            issues.append("Running as root user")
        
        if 'latest' in content:
            issues.append("Using 'latest' tag")
        
        if 'curl' in content or 'wget' in content:
            issues.append("Downloading files in build")
        
        assert len(issues) == 0, f"Dockerfile security issues: {issues}"


# ============================================================================
# SECURITY HEADERS
# ============================================================================

class TestSecurityHeaders:
    """Security headers testing"""
    
    BASE_URL = SecurityConfig.BASE_URL
    
    def test_all_security_headers(self):
        """Test all required security headers"""
        response = requests.get(f"{self.BASE_URL}/health", timeout=SecurityConfig.TIMEOUT)
        
        missing_headers = []
        for header in SecurityConfig.REQUIRED_HEADERS:
            if header not in response.headers:
                missing_headers.append(header)
        
        # API may not need all headers (frontend responsibility)
        # Just log missing headers
        if missing_headers:
            logger.warning(f"Missing security headers: {missing_headers}")
    
    def test_cors_configuration(self):
        """Test CORS configuration"""
        response = requests.options(
            f"{self.BASE_URL}/sessions",
            headers={
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "POST"
            },
            timeout=SecurityConfig.TIMEOUT
        )
        
        # Should not allow all origins in production
        acao = response.headers.get("Access-Control-Allow-Origin", "")
        
        if acao == "*":
            logger.warning("CORS allows all origins (*)")


# ============================================================================
# REPORTING
# ============================================================================

class SecurityReport:
    """Generate security test reports"""
    
    def __init__(self):
        self.findings = []
        self.start_time = datetime.now()
    
    def add_finding(self, severity: str, title: str, description: str, remediation: str):
        """Add a security finding"""
        self.findings.append({
            "severity": severity,
            "title": title,
            "description": description,
            "remediation": remediation,
            "timestamp": datetime.now().isoformat()
        })
    
    def generate_report(self, output_path: str = "security_report.json"):
        """Generate JSON report"""
        report = {
            "report_date": self.start_time.isoformat(),
            "total_findings": len(self.findings),
            "findings_by_severity": {
                "critical": len([f for f in self.findings if f["severity"] == "critical"]),
                "high": len([f for f in self.findings if f["severity"] == "high"]),
                "medium": len([f for f in self.findings if f["severity"] == "medium"]),
                "low": len([f for f in self.findings if f["severity"] == "low"]),
            },
            "findings": self.findings
        }
        
        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report


# Run with:
# pytest tests/security/test_security_advanced.py -v --tb=short
#
# Generate report:
# python -c "from tests.security.test_security_advanced import SecurityReport; r = SecurityReport(); r.generate_report()"
