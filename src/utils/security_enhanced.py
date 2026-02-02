"""
Enhanced security features for disposable compute platform
"""
import asyncio
import hashlib
import hmac
import secrets
import jwt
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
import subprocess
import os
import pwd
import grp
from pathlib import Path


@dataclass
class SecurityPolicy:
    """Security policy for a pod or session"""
    id: str
    name: str
    description: str
    rules: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    enabled: bool = True


@dataclass
class SecurityScanResult:
    """Result of a security scan"""
    scan_id: str
    target: str  # image, container, file, etc.
    scan_type: str  # vulnerability, malware, config
    timestamp: datetime
    status: str  # completed, failed, in-progress
    vulnerabilities: List[Dict[str, Any]]
    severity_summary: Dict[str, int]  # count by severity
    recommendations: List[str]


class VulnerabilityScanner:
    """Scans for vulnerabilities in containers and images"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.scanners = {}  # Available scanners
        self._discover_scanners()
    
    def _discover_scanners(self):
        """Discover available security scanners"""
        # Check for Trivy
        if self._command_exists("trivy"):
            self.scanners["trivy"] = {
                "path": "trivy",
                "version": self._get_scanner_version("trivy")
            }
        
        # Check for Clair
        if self._command_exists("clair"):
            self.scanners["clair"] = {
                "path": "clair",
                "version": self._get_scanner_version("clair")
            }
        
        # Check for Grype
        if self._command_exists("grype"):
            self.scanners["grype"] = {
                "path": "grype",
                "version": self._get_scanner_version("grype")
            }
        
        self.logger.info(f"Discovered security scanners: {list(self.scanners.keys())}")
    
    def _command_exists(self, cmd: str) -> bool:
        """Check if a command exists in the system"""
        try:
            subprocess.run(["which", cmd], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False
    
    def _get_scanner_version(self, cmd: str) -> str:
        """Get the version of a scanner"""
        try:
            result = subprocess.run([cmd, "--version"], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return "unknown"
    
    async def scan_image(self, image_name: str) -> SecurityScanResult:
        """Scan a container image for vulnerabilities"""
        scan_id = f"scan-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}"
        
        result = SecurityScanResult(
            scan_id=scan_id,
            target=image_name,
            scan_type="vulnerability",
            timestamp=datetime.now(),
            status="in-progress",
            vulnerabilities=[],
            severity_summary={},
            recommendations=[]
        )
        
        try:
            # Use Trivy if available, otherwise simulate
            if "trivy" in self.scanners:
                result = await self._scan_with_trivy(image_name, scan_id)
            else:
                # Simulate scan results for demo purposes
                result.status = "completed"
                result.vulnerabilities = [
                    {
                        "id": "CVE-2023-1234",
                        "title": "Sample Vulnerability",
                        "severity": "MEDIUM",
                        "package": "openssl",
                        "version": "1.1.1",
                        "description": "Sample vulnerability for demonstration"
                    }
                ]
                result.severity_summary = {"MEDIUM": 1}
                result.recommendations = ["Update to latest version"]
            
            result.status = "completed"
            
        except Exception as e:
            result.status = "failed"
            result.vulnerabilities = []
            result.severity_summary = {}
            result.recommendations = [f"Scan failed: {str(e)}"]
            self.logger.error(f"Security scan failed for {image_name}: {e}")
        
        return result
    
    async def _scan_with_trivy(self, image_name: str, scan_id: str) -> SecurityScanResult:
        """Perform scan using Trivy"""
        # This would be the actual implementation using Trivy
        # For now, we'll simulate the scan
        await asyncio.sleep(1)  # Simulate scan time
        
        # Return simulated results
        return SecurityScanResult(
            scan_id=scan_id,
            target=image_name,
            scan_type="vulnerability",
            timestamp=datetime.now(),
            status="completed",
            vulnerabilities=[
                {
                    "id": "CVE-2023-1234",
                    "title": "Sample Vulnerability",
                    "severity": "MEDIUM",
                    "package": "openssl",
                    "version": "1.1.1",
                    "description": "Sample vulnerability for demonstration"
                }
            ],
            severity_summary={"MEDIUM": 1},
            recommendations=["Update to latest version"]
        )


class RuntimeSecurityMonitor:
    """Monitors running containers for security issues"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.active_monitors = {}
    
    async def start_monitoring_container(self, container_id: str):
        """Start monitoring a container for runtime security issues"""
        if container_id in self.active_monitors:
            self.logger.warning(f"Security monitoring already active for container {container_id}")
            return
        
        # In a real implementation, this would start a runtime security agent
        # For now, we'll just simulate by creating a monitoring task
        task = asyncio.create_task(self._monitor_container(container_id))
        self.active_monitors[container_id] = task
        self.logger.info(f"Started security monitoring for container {container_id}")
    
    async def stop_monitoring_container(self, container_id: str):
        """Stop monitoring a container"""
        if container_id in self.active_monitors:
            task = self.active_monitors[container_id]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.active_monitors[container_id]
            self.logger.info(f"Stopped security monitoring for container {container_id}")
    
    async def _monitor_container(self, container_id: str):
        """Monitor a single container for security issues"""
        while True:
            try:
                # In a real implementation, this would check for:
                # - Unexpected process execution
                # - File system changes
                # - Network connections
                # - Privilege escalation attempts
                # - etc.
                
                # For simulation, we'll just sleep and occasionally "detect" issues
                await asyncio.sleep(30)  # Check every 30 seconds
                
                # Simulate occasional security event detection
                if secrets.randbelow(10) == 0:  # 10% chance of detecting an event
                    self.logger.warning(f"Security event detected in container {container_id}")
                
            except asyncio.CancelledError:
                self.logger.info(f"Security monitoring cancelled for container {container_id}")
                break
            except Exception as e:
                self.logger.error(f"Error monitoring container {container_id}: {e}")
                await asyncio.sleep(30)  # Wait before retrying


class NetworkPolicyEnforcer:
    """Enforces network policies for pods"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.policies = {}
    
    def apply_policy_to_pod(self, pod_id: str, policy: Dict[str, Any]) -> bool:
        """Apply network policy to a pod"""
        try:
            # In a real implementation, this would configure iptables, CNI, or similar
            # For now, we'll just store the policy
            self.policies[pod_id] = policy
            self.logger.info(f"Applied network policy to pod {pod_id}")
            
            # Example: configure iptables rules
            # self._configure_iptables_rules(pod_id, policy)
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to apply network policy to pod {pod_id}: {e}")
            return False
    
    def remove_policy_from_pod(self, pod_id: str) -> bool:
        """Remove network policy from a pod"""
        try:
            if pod_id in self.policies:
                # In a real implementation, this would remove iptables rules, etc.
                del self.policies[pod_id]
                self.logger.info(f"Removed network policy from pod {pod_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove network policy from pod {pod_id}: {e}")
            return False
    
    def _configure_iptables_rules(self, pod_id: str, policy: Dict[str, Any]):
        """Configure iptables rules for a pod (simplified example)"""
        # This is a simplified example - in practice, this would be more complex
        # and would need to identify the pod's network namespace
        
        # Example: block all outbound traffic except to allowed domains
        allowed_domains = policy.get("egress", {}).get("allowed_domains", [])
        
        for domain in allowed_domains:
            # Resolve domain to IP and add rule
            try:
                # This would require proper DNS resolution and iptables commands
                # cmd = ["iptables", "-A", "FORWARD", "-d", ip, "-j", "ACCEPT"]
                # subprocess.run(cmd, check=True)
                pass
            except Exception as e:
                self.logger.error(f"Failed to configure iptables for domain {domain}: {e}")


class CredentialManager:
    """Manages secure credential storage and access"""
    
    def __init__(self, storage_path: str = "/var/lib/dcp-credentials"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(__name__)
    
    def store_credential(self, key: str, value: str, ttl_minutes: int = 60) -> str:
        """Store a credential securely"""
        try:
            # Sanitize the key to prevent path traversal
            sanitized_key = Path(key).name  # Only use the filename part, discard any path components
            cred_file = self.storage_path / f"{sanitized_key}.cred"

            # Write the credential with restrictive permissions from the start to avoid race condition
            fd = os.open(cred_file, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(value)
            except:
                os.close(fd)
                raise

            # Schedule cleanup
            asyncio.create_task(self._schedule_cleanup(str(cred_file), ttl_minutes))

            self.logger.info(f"Stored credential for key: {key}")
            return str(cred_file)
        except Exception as e:
            self.logger.error(f"Failed to store credential for key {key}: {e}")
            raise
    
    def retrieve_credential(self, key: str) -> Optional[str]:
        """Retrieve a credential"""
        try:
            # Sanitize the key to prevent path traversal
            sanitized_key = Path(key).name  # Only use the filename part, discard any path components
            cred_file = self.storage_path / f"{sanitized_key}.cred"

            if not cred_file.exists():
                return None

            with open(cred_file, 'r') as f:
                return f.read().strip()
        except Exception as e:
            self.logger.error(f"Failed to retrieve credential for key {key}: {e}")
            return None
    
    def delete_credential(self, key: str) -> bool:
        """Delete a credential"""
        try:
            # Sanitize the key to prevent path traversal
            sanitized_key = Path(key).name  # Only use the filename part, discard any path components
            cred_file = self.storage_path / f"{sanitized_key}.cred"

            if cred_file.exists():
                cred_file.unlink()
                self.logger.info(f"Deleted credential for key: {key}")

            return True
        except Exception as e:
            self.logger.error(f"Failed to delete credential for key {key}: {e}")
            return False
    
    async def _schedule_cleanup(self, file_path: str, ttl_minutes: int):
        """Schedule cleanup of credential file after TTL"""
        await asyncio.sleep(ttl_minutes * 60)
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.info(f"Cleaned up credential file: {file_path}")
        except Exception as e:
            self.logger.error(f"Failed to cleanup credential file {file_path}: {e}")


class AuditLogger:
    """Logs security-relevant events for audit purposes"""
    
    def __init__(self, log_file: str = "/var/log/dcp-audit.log"):
        self.log_file = log_file
        self.logger = logging.getLogger(__name__)
        
        # Set up audit-specific logger
        self.audit_logger = logging.getLogger("dcp.audit")
        self.audit_logger.setLevel(logging.INFO)
        
        # Create file handler for audit logs
        handler = logging.FileHandler(self.log_file)
        formatter = logging.Formatter(
            '%(asctime)s - AUDIT - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        self.audit_logger.addHandler(handler)
    
    def log_event(self, event_type: str, user_id: str, resource: str, action: str, 
                  result: str, details: Optional[Dict] = None):
        """Log a security event"""
        details_str = f" - Details: {details}" if details else ""
        message = f"EVENT={event_type} USER={user_id} RESOURCE={resource} ACTION={action} RESULT={result}{details_str}"
        
        self.audit_logger.info(message)
        self.logger.debug(f"Audit event logged: {event_type}")
    
    def log_pod_creation(self, user_id: str, pod_id: str, pod_spec: Dict):
        """Log pod creation event"""
        self.log_event(
            event_type="POD_CREATION",
            user_id=user_id,
            resource=pod_id,
            action="CREATE",
            result="SUCCESS",
            details={"pod_type": pod_spec.get("pod_type"), "image": pod_spec.get("image")}
        )
    
    def log_session_access(self, user_id: str, session_id: str, ip_address: str):
        """Log session access event"""
        self.log_event(
            event_type="SESSION_ACCESS",
            user_id=user_id,
            resource=session_id,
            action="ACCESS",
            result="SUCCESS",
            details={"ip_address": ip_address}
        )
    
    def log_security_violation(self, user_id: str, resource: str, violation_type: str, details: Dict):
        """Log security violation"""
        self.log_event(
            event_type="SECURITY_VIOLATION",
            user_id=user_id,
            resource=resource,
            action="VIOLATION",
            result="DETECTED",
            details={"violation_type": violation_type, **details}
        )


class SecurityManager:
    """Main security manager that coordinates all security features"""
    
    def __init__(self):
        self.vulnerability_scanner = VulnerabilityScanner()
        self.runtime_monitor = RuntimeSecurityMonitor()
        self.network_enforcer = NetworkPolicyEnforcer()
        self.credential_manager = CredentialManager()
        self.audit_logger = AuditLogger()
        self.logger = logging.getLogger(__name__)
        
        # Default security policies
        self.default_policies = {
            "container": {
                "no_new_privileges": True,
                "read_only_root": True,
                "drop_all_capabilities": True,
                "allowed_syscalls": [
                    "read", "write", "open", "close", "stat", "fstat", "lstat",
                    "poll", "lseek", "mmap", "mprotect", "munmap", "brk",
                    "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "ioctl",
                    "pread64", "pwrite64", "readv", "writev", "access", "pipe",
                    "select", "sched_yield", "mremap", "msync", "mincore",
                    "madvise", "shmget", "shmat", "shmctl", "dup", "dup2",
                    "pause", "nanosleep", "getitimer", "alarm", "setitimer",
                    "getpid", "sendfile", "socket", "connect", "accept",
                    "sendto", "recvfrom", "sendmsg", "recvmsg", "shutdown",
                    "bind", "listen", "getsockname", "getpeername",
                    "socketpair", "setsockopt", "getsockopt", "clone",
                    "fork", "vfork", "execve", "exit", "wait4", "kill",
                    "uname", "semget", "semop", "semctl", "shmdt", "msgget",
                    "msgsnd", "msgrcv", "msgctl", "fcntl", "flock", "fsync",
                    "fdatasync", "truncate", "ftruncate", "getdents",
                    "getcwd", "chdir", "rename", "mkdir", "rmdir", "creat",
                    "link", "unlink", "symlink", "readlink", "chmod",
                    "fchmod", "chown", "fchown", "lchown", "umask",
                    "gettimeofday", "getrlimit", "getuid", "geteuid",
                    "getgid", "getegid", "setpgid", "getppid", "getpgrp",
                    "setsid", "setreuid", "setregid", "getgroups",
                    "setgroups", "setresuid", "getresuid", "setresgid",
                    "getresgid", "getpgid", "setfsuid", "setfsgid",
                    "times", "setrlimit", "getrusage", "gettimeofday",
                    "settimeofday", "getpid", "getppid", "getuid",
                    "geteuid", "getgid", "getegid", "getpgid", "setpgid",
                    "setsid", "setreuid", "setregid", "getgroups",
                    "setgroups", "setresuid", "getresuid", "setresgid",
                    "getresgid", "getpgid", "setfsuid", "setfsgid",
                    "getsid", "capget", "capset", "personality",
                    "arch_prctl", "set_thread_area", "get_thread_area",
                    "unmap", "mprotect"
                ],
                "blocked_syscalls": [
                    "open_by_handle_at", "init_module", "finit_module",
                    "delete_module", "iopl", "ioperm", "swapon",
                    "swapoff", "syslog", "reboot", "settimeofday",
                    "stime", "adjtimex", "clock_settime", "clock_adjtime",
                    "lookup_dcookie", "fanotify_init", "fanotify_mark",
                    "quotactl", "mount", "umount2", "pivot_root",
                    "chroot", "acct", "setdomainname", "sethostname",
                    "vhangup", "modify_ldt", "writev", "pciconfig_read",
                    "pciconfig_write", "bpf", "kexec_load", "execveat",
                    "userfaultfd", "perf_event_open", "membarrier",
                    "mlock", "mlockall", "munlock", "munlockall",
                    "name_to_handle_at", "unshare", "setns", "mount",
                    "umount2", "pivot_root", "chroot", "init_module",
                    "finit_module", "delete_module", "iopl", "ioperm",
                    "swapon", "swapoff", "syslog", "reboot", "settimeofday",
                    "stime", "adjtimex", "clock_settime", "clock_adjtime",
                    "lookup_dcookie", "fanotify_init", "fanotify_mark",
                    "quotactl", "mount", "umount2", "pivot_root",
                    "chroot", "acct", "setdomainname", "sethostname",
                    "vhangup", "modify_ldt", "writev", "pciconfig_read",
                    "pciconfig_write", "bpf", "kexec_load", "execveat",
                    "userfaultfd", "perf_event_open", "membarrier",
                    "mlock", "mlockall", "munlock", "munlockall",
                    "name_to_handle_at", "unshare", "setns"
                ]
            }
        }
    
    async def scan_pod_image(self, image_name: str) -> SecurityScanResult:
        """Scan a pod's image for vulnerabilities"""
        return await self.vulnerability_scanner.scan_image(image_name)
    
    async def start_runtime_monitoring(self, container_id: str):
        """Start runtime security monitoring for a container"""
        await self.runtime_monitor.start_monitoring_container(container_id)
    
    async def stop_runtime_monitoring(self, container_id: str):
        """Stop runtime security monitoring for a container"""
        await self.runtime_monitor.stop_monitoring_container(container_id)
    
    def apply_network_policy(self, pod_id: str, policy: Optional[Dict] = None) -> bool:
        """Apply network policy to a pod"""
        # Use provided policy or default
        policy_to_apply = policy or self.default_policies.get("container", {})
        return self.network_enforcer.apply_policy_to_pod(pod_id, policy_to_apply)
    
    def remove_network_policy(self, pod_id: str) -> bool:
        """Remove network policy from a pod"""
        return self.network_enforcer.remove_policy_from_pod(pod_id)
    
    def store_pod_credentials(self, pod_id: str, credentials: Dict[str, str], 
                            ttl_minutes: int = 60) -> Dict[str, str]:
        """Store credentials for a pod"""
        stored_keys = {}
        
        for key, value in credentials.items():
            full_key = f"{pod_id}-{key}"
            self.credential_manager.store_credential(full_key, value, ttl_minutes)
            stored_keys[key] = full_key  # Return the full key for retrieval
        
        return stored_keys
    
    def retrieve_pod_credentials(self, pod_id: str, credential_keys: List[str]) -> Dict[str, str]:
        """Retrieve credentials for a pod"""
        credentials = {}
        
        for key in credential_keys:
            full_key = f"{pod_id}-{key}"
            value = self.credential_manager.retrieve_credential(full_key)
            if value:
                credentials[key] = value
        
        return credentials
    
    def log_pod_creation(self, user_id: str, pod_id: str, pod_spec: Dict):
        """Log pod creation for audit purposes"""
        self.audit_logger.log_pod_creation(user_id, pod_id, pod_spec)
    
    def log_session_access(self, user_id: str, session_id: str, ip_address: str):
        """Log session access for audit purposes"""
        self.audit_logger.log_session_access(user_id, session_id, ip_address)
    
    def log_security_violation(self, user_id: str, resource: str, violation_type: str, details: Dict):
        """Log security violation for audit purposes"""
        self.audit_logger.log_security_violation(user_id, resource, violation_type, details)
    
    def get_default_security_policy(self, resource_type: str) -> Optional[Dict]:
        """Get the default security policy for a resource type"""
        return self.default_policies.get(resource_type)