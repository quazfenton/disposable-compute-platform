"""
Security and isolation mechanisms for disposable compute platform
"""
import asyncio
import os
import tempfile
import subprocess
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import secrets
import hashlib
import pwd
import grp


class SecurityPolicy:
    """Defines security policies for disposable environments"""
    
    def __init__(self):
        self.default_policies = {
            'cpu_quota': '1000m',  # 1 CPU
            'memory_limit': '1G',  # 1GB RAM
            'disk_quota': '5G',    # 5GB disk space
            'network_rate_limit': '100mbps',
            'max_processes': 32,
            'read_only_root': True,
            'no_new_privileges': True,
            'allowed_syscalls': [
                'read', 'write', 'open', 'close', 'stat', 'fstat',
                'lstat', 'poll', 'lseek', 'mmap', 'mprotect', 'munmap',
                'brk', 'rt_sigaction', 'rt_sigprocmask', 'rt_sigreturn',
                'ioctl', 'pread64', 'pwrite64', 'readv', 'writev',
                'access', 'pipe', 'select', 'sched_yield', 'mremap',
                'msync', 'mincore', 'madvise', 'shmget', 'shmat',
                'shmctl', 'dup', 'dup2', 'pause', 'nanosleep',
                'getitimer', 'alarm', 'setitimer', 'getpid', 'sendfile',
                'socket', 'connect', 'accept', 'sendto', 'recvfrom',
                'sendmsg', 'recvmsg', 'shutdown', 'bind', 'listen',
                'getsockname', 'getpeername', 'socketpair', 'setsockopt',
                'getsockopt', 'clone', 'fork', 'vfork', 'execve',
                'exit', 'wait4', 'kill', 'uname', 'semget', 'semop',
                'semctl', 'shmdt', 'msgget', 'msgsnd', 'msgrcv',
                'msgctl', 'fcntl', 'flock', 'fsync', 'fdatasync',
                'truncate', 'ftruncate', 'getdents', 'getcwd',
                'chdir', 'rename', 'mkdir', 'rmdir', 'creat',
                'link', 'unlink', 'symlink', 'readlink', 'chmod',
                'fchmod', 'chown', 'fchown', 'lchown', 'umask',
                'gettimeofday', 'getrlimit', 'getuid', 'geteuid',
                'getgid', 'getegid', 'setpgid', 'getppid', 'getpgrp',
                'setsid', 'setreuid', 'setregid', 'getgroups',
                'setgroups', 'setresuid', 'getresuid', 'setresgid',
                'getresgid', 'getpgid', 'setfsuid', 'setfsgid',
                'times', 'setrlimit', 'getrusage', 'gettimeofday',
                'settimeofday', 'getpid', 'getppid', 'getuid',
                'geteuid', 'getgid', 'getegid', 'getpgid', 'setpgid',
                'setsid', 'setreuid', 'setregid', 'getgroups',
                'setgroups', 'setresuid', 'getresuid', 'setresgid',
                'getresgid', 'getpgid', 'setfsuid', 'setfsgid',
                'getsid', 'capget', 'capset', 'personality',
                'arch_prctl', 'set_thread_area', 'get_thread_area',
                'unmap', 'mprotect'
            ],
            'blocked_syscalls': [
                'open_by_handle_at', 'init_module', 'finit_module',
                'delete_module', 'iopl', 'ioperm', 'swapon',
                'swapoff', 'syslog', 'reboot', 'settimeofday',
                'stime', 'adjtimex', 'clock_settime', 'clock_adjtime',
                'lookup_dcookie', 'fanotify_init', 'fanotify_mark',
                'quotactl', 'mount', 'umount2', 'pivot_root',
                'chroot', 'acct', 'setdomainname', 'sethostname',
                'vhangup', 'modify_ldt', 'writev', 'pciconfig_read',
                'pciconfig_write', 'bpf', 'kexec_load', 'execveat',
                'userfaultfd', 'perf_event_open', 'membarrier',
                'mlock', 'mlockall', 'munlock', 'munlockall',
                'name_to_handle_at', 'unshare', 'setns', 'mount',
                'umount2', 'pivot_root', 'chroot', 'init_module',
                'finit_module', 'delete_module', 'iopl', 'ioperm',
                'swapon', 'swapoff', 'syslog', 'reboot', 'settimeofday',
                'stime', 'adjtimex', 'clock_settime', 'clock_adjtime',
                'lookup_dcookie', 'fanotify_init', 'fanotify_mark',
                'quotactl', 'mount', 'umount2', 'pivot_root',
                'chroot', 'acct', 'setdomainname', 'sethostname',
                'vhangup', 'modify_ldt', 'writev', 'pciconfig_read',
                'pciconfig_write', 'bpf', 'kexec_load', 'execveat',
                'userfaultfd', 'perf_event_open', 'membarrier',
                'mlock', 'mlockall', 'munlock', 'munlockall',
                'name_to_handle_at', 'unshare', 'setns'
            ]
        }
    
    def get_policy_for_session_type(self, session_type: str) -> Dict:
        """Get security policy for a specific session type"""
        policy = self.default_policies.copy()
        
        if session_type == 'preview':
            # Preview environments might need slightly more resources
            policy.update({
                'cpu_quota': '2000m',
                'memory_limit': '2G',
                'disk_quota': '10G'
            })
        elif session_type == 'run_repo':
            # Run-repo sessions have standard limits
            pass  # Use defaults
        elif session_type == 'fork_gui':
            # GUI sessions might need more memory for graphics
            policy.update({
                'memory_limit': '2G',
                'disk_quota': '8G'
            })
        
        return policy


class ResourceIsolator:
    """Manages resource isolation for disposable environments"""
    
    def __init__(self):
        self.security_policy = SecurityPolicy()
    
    def create_cgroup_for_session(self, session_id: str, session_type: str) -> str:
        """Create a cgroup for a session to enforce resource limits"""
        # Create a unique cgroup path for this session
        cgroup_path = f"/sys/fs/cgroup/disposable/{session_id}"
        
        # In a real implementation, this would create the actual cgroup
        # For now, we'll just return the path
        return cgroup_path
    
    def apply_resource_limits(self, container_id: str, session_type: str):
        """Apply resource limits to a container"""
        policy = self.security_policy.get_policy_for_session_type(session_type)
        
        # In a real implementation, this would configure the container
        # with the specified resource limits
        print(f"Applying resource limits to container {container_id}: {policy}")
        
        # Example Docker run options that would be used:
        docker_options = {
            'mem_limit': policy['memory_limit'],
            'memswap_limit': policy['memory_limit'],  # No swap
            'cpu_quota': policy['cpu_quota'],
            'blkio_weight': 500,  # Block I/O weight
            'pids_limit': policy['max_processes']
        }
        
        return docker_options
    
    def setup_network_isolation(self, network_name: str) -> str:
        """Set up network isolation for an environment"""
        # In a real implementation, this would configure network policies
        # For now, return a simulated network policy
        policy = {
            'network_name': network_name,
            'ingress_rate_limit': '100mbps',
            'egress_rate_limit': '100mbps',
            'allowed_external_hosts': ['registry-1.docker.io', 'index.docker.io'],
            'dns_servers': ['8.8.8.8', '1.1.1.1']
        }
        
        return policy


class SecurityScanner:
    """Scans containers and environments for security issues"""
    
    def __init__(self):
        self.vulnerability_db = {}  # Would connect to a real vulnerability database
    
    async def scan_container_image(self, image_name: str) -> Dict[str, any]:
        """Scan a container image for vulnerabilities"""
        # In a real implementation, this would use tools like Trivy, Clair, or Anchore
        # For simulation, return a mock scan result
        return {
            'image': image_name,
            'scan_time': datetime.now().isoformat(),
            'vulnerabilities': [],
            'security_rating': 'A',
            'recommendations': []
        }
    
    async def scan_running_container(self, container_id: str) -> Dict[str, any]:
        """Scan a running container for security issues"""
        # In a real implementation, this would run security checks inside the container
        return {
            'container_id': container_id,
            'scan_time': datetime.now().isoformat(),
            'processes': [],
            'open_ports': [],
            'security_issues': [],
            'status': 'secure'
        }


class AccessController:
    """Controls access to disposable environments"""
    
    def __init__(self):
        self.session_tokens = {}  # Maps session_id to access tokens
        self.token_expiration = {}  # Maps token to expiration time
    
    def generate_access_token(self, session_id: str, ttl_minutes: int = 60) -> str:
        """Generate a secure access token for a session"""
        token = secrets.token_urlsafe(32)
        expiration = datetime.now().timestamp() + (ttl_minutes * 60)
        
        self.session_tokens[session_id] = token
        self.token_expiration[token] = expiration
        
        return token
    
    def validate_access_token(self, session_id: str, token: str) -> bool:
        """Validate an access token for a session"""
        if session_id not in self.session_tokens:
            return False
        
        stored_token = self.session_tokens[session_id]
        if token != stored_token:
            return False
        
        # Check expiration
        if token in self.token_expiration:
            if datetime.now().timestamp() > self.token_expiration[token]:
                # Token expired, clean it up
                del self.session_tokens[session_id]
                del self.token_expiration[token]
                return False
        
        return True
    
    def revoke_access_token(self, session_id: str):
        """Revoke the access token for a session"""
        if session_id in self.session_tokens:
            token = self.session_tokens[session_id]
            if token in self.token_expiration:
                del self.token_expiration[token]
            del self.session_tokens[session_id]


class NetworkSecurity:
    """Manages network security for disposable environments"""
    
    def __init__(self):
        self.firewall_rules = {}
        self.rate_limits = {}
    
    def setup_firewall_rules(self, network_name: str, session_type: str) -> List[str]:
        """Set up firewall rules for an environment"""
        rules = []
        
        # Allow internal network communication
        rules.append(f"ALLOW {network_name} -> {network_name}")
        
        # Limit external access based on session type
        if session_type == 'preview':
            # Preview environments may need more external access for dependencies
            rules.extend([
                "ALLOW OUT -> registry-1.docker.io",
                "ALLOW OUT -> index.docker.io", 
                "ALLOW OUT -> npmjs.org",
                "ALLOW OUT -> pypi.org",
                "RATE_LIMIT OUT 100mbps"
            ])
        else:
            # Other environments have more restricted access
            rules.extend([
                "ALLOW OUT -> registry-1.docker.io",
                "ALLOW OUT -> index.docker.io",
                "RATE_LIMIT OUT 50mbps"
            ])
        
        # Block all other external traffic by default
        rules.append("DENY OUT -> *")
        
        self.firewall_rules[network_name] = rules
        return rules
    
    def setup_rate_limiting(self, network_name: str, rate_limit: str = "100mbps"):
        """Set up network rate limiting"""
        self.rate_limits[network_name] = rate_limit
        # In a real implementation, this would configure traffic shaping
        print(f"Set up rate limiting for {network_name}: {rate_limit}")


class SecurityManager:
    """Main security manager that coordinates all security components"""
    
    def __init__(self):
        self.resource_isolator = ResourceIsolator()
        self.security_scanner = SecurityScanner()
        self.access_controller = AccessController()
        self.network_security = NetworkSecurity()
        self.security_policy = SecurityPolicy()
    
    async def secure_session_environment(self, session_id: str, session_type: str, 
                                       network_name: str) -> Dict[str, any]:
        """Apply all security measures to a session environment"""
        security_report = {
            'session_id': session_id,
            'timestamp': datetime.now().isoformat(),
            'applied_security': [],
            'security_issues': [],
            'status': 'secured'
        }
        
        # 1. Apply resource isolation
        resource_limits = self.resource_isolator.apply_resource_limits(
            f"container-{session_id}", session_type
        )
        security_report['applied_security'].append({
            'type': 'resource_isolation',
            'config': resource_limits
        })
        
        # 2. Set up network security
        firewall_rules = self.network_security.setup_firewall_rules(
            network_name, session_type
        )
        security_report['applied_security'].append({
            'type': 'network_security',
            'rules': firewall_rules
        })
        
        # 3. Generate access token
        access_token = self.access_controller.generate_access_token(
            session_id, ttl_minutes=60
        )
        security_report['applied_security'].append({
            'type': 'access_control',
            'token': access_token[:8] + '...'  # Only show first 8 chars
        })
        
        # 4. Apply security policy
        policy = self.security_policy.get_policy_for_session_type(session_type)
        security_report['applied_security'].append({
            'type': 'security_policy',
            'policy': policy
        })
        
        return security_report
    
    async def scan_session(self, session_id: str, container_id: str) -> Dict[str, any]:
        """Perform security scan on a session"""
        scan_results = {
            'session_id': session_id,
            'container_id': container_id,
            'timestamp': datetime.now().isoformat(),
            'image_scan': await self.security_scanner.scan_container_image(f"image-{session_id}"),
            'container_scan': await self.security_scanner.scan_running_container(container_id),
            'overall_status': 'secure'
        }
        
        # Check if any scans found issues
        if (scan_results['image_scan']['security_rating'] != 'A' or 
            scan_results['container_scan']['status'] != 'secure'):
            scan_results['overall_status'] = 'issues_found'
        
        return scan_results
    
    def validate_session_access(self, session_id: str, token: str) -> bool:
        """Validate access to a session"""
        return self.access_controller.validate_access_token(session_id, token)
    
    def cleanup_session_security(self, session_id: str):
        """Clean up security resources for a destroyed session"""
        # Revoke access token
        self.access_controller.revoke_access_token(session_id)
        
        # In a real implementation, this would also:
        # - Remove cgroups
        # - Remove firewall rules
        # - Clean up any other security resources
        print(f"Cleaned up security resources for session {session_id}")


# Integration with the main platform
async def integrate_security_manager(session_manager):
    """Integrate security manager with the session manager"""
    # Use the enhanced security manager
    from .security_enhanced import SecurityManager as EnhancedSecurityManager
    security_manager = EnhancedSecurityManager()

    # Store security manager in session manager
    session_manager.security_manager = security_manager

    # Override session creation to include security setup
    original_create_session = session_manager.create_session

    async def new_create_session(session_type, repo_url, repo_ref=None, pr_number=None, ttl_minutes=None):
        session = await original_create_session(
            session_type, repo_url, repo_ref, pr_number, ttl_minutes
        )

        # Apply security measures after session creation
        if hasattr(session_manager, 'network_manager') and session.network_id:
            # Log the pod creation for audit purposes
            security_manager.log_pod_creation("system", session.id, {
                "type": session_type.value,
                "repo_url": repo_url,
                "repo_ref": repo_ref
            })

        return session

    session_manager.create_session = new_create_session

    # Override session destruction to include security cleanup
    original_destroy_session = session_manager.destroy_session

    async def new_destroy_session(session_id):
        # Clean up security resources first
        # In the enhanced manager, we don't have a direct cleanup method
        # but we can log the destruction
        security_manager.audit_logger.log_event(
            event_type="POD_DESTRUCTION",
            user_id="system",
            resource=session_id,
            action="DESTROY",
            result="SUCCESS",
            details={}
        )

        # Then destroy the session normally
        await original_destroy_session(session_id)

    session_manager.destroy_session = new_destroy_session

    return security_manager