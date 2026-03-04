"""
DevContainer specification parser for disposable compute platform
Converts .devcontainer/devcontainer.json to platform service definitions
"""
import json
import os
import tempfile
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from pathlib import Path
from git import Repo as GitRepo

logger = logging.getLogger(__name__)


@dataclass
class DevContainerFeature:
    """Represents a devcontainer feature"""
    id: str
    version: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DevContainerConfig:
    """Parsed devcontainer.json configuration"""
    # Core properties
    image: Optional[str] = None
    dockerfile: Optional[str] = None
    build_context: Optional[str] = None
    
    # Features
    features: Dict[str, DevContainerFeature] = field(default_factory=dict)
    
    # Commands
    post_create_command: Optional[Union[str, List[str]]] = None
    post_start_command: Optional[Union[str, List[str]]] = None
    
    # Ports
    forward_ports: List[int] = field(default_factory=list)
    other_ports: List[str] = field(default_factory=list)
    
    # Environment
    remote_env: Dict[str, str] = field(default_factory=dict)
    
    # VS Code extensions
    extensions: List[str] = field(default_factory=list)
    
    # VS Code settings
    settings: Dict[str, Any] = field(default_factory=dict)
    
    # Container user
    remote_user: Optional[str] = None
    container_user: Optional[str] = None
    
    # Mounts
    mounts: List[str] = field(default_factory=list)
    
    # Run arguments
    run_args: List[str] = field(default_factory=list)
    
    # Host requirements
    host_requirements: Dict[str, Any] = field(default_factory=dict)
    
    # Customizations
    customizations: Dict[str, Any] = field(default_factory=dict)
    
    # Name and description
    name: Optional[str] = None
    description: Optional[str] = None
    
    # Override command
    override_command: Optional[Union[str, List[str]]] = None
    
    # Init and privileged
    init: bool = False
    privileged: bool = False
    
    # Capabilities
    cap_add: List[str] = field(default_factory=list)
    
    # Security options
    security_opt: List[str] = field(default_factory=list)
    
    # Workspace folder
    workspace_folder: Optional[str] = None
    
    # Update content cache
    update_content_cache: bool = False
    
    # Additional properties
    additional_properties: Dict[str, Any] = field(default_factory=dict)


class DevContainerParser:
    """Parse .devcontainer/devcontainer.json files"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_file(self, path: str) -> DevContainerConfig:
        """Parse a devcontainer.json file"""
        config_path = Path(path)
        
        if not config_path.exists():
            raise FileNotFoundError(f"DevContainer config not found: {path}")
        
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        return self._parse_dict(data)
    
    def parse_dict(self, data: Dict[str, Any]) -> DevContainerConfig:
        """Parse a devcontainer.json dictionary"""
        return self._parse_dict(data)
    
    def _parse_dict(self, data: Dict[str, Any]) -> DevContainerConfig:
        """Internal parse method"""
        config = DevContainerConfig()
        
        # Core properties
        config.image = data.get("image")
        config.dockerfile = data.get("build", {}).get("dockerfile") if isinstance(data.get("build"), dict) else data.get("build")
        config.build_context = data.get("build", {}).get("context", ".") if isinstance(data.get("build"), dict) else "."
        
        # Features (can be array or object)
        features_data = data.get("features", {})
        if isinstance(features_data, dict):
            for feature_id, feature_value in features_data.items():
                if isinstance(feature_value, str):
                    config.features[feature_id] = DevContainerFeature(id=feature_id, version=feature_value)
                elif isinstance(feature_value, dict):
                    config.features[feature_id] = DevContainerFeature(
                        id=feature_id,
                        version=feature_value.get("version"),
                        options=feature_value.get("options", {})
                    )
        
        # Commands
        config.post_create_command = data.get("postCreateCommand")
        config.post_start_command = data.get("postStartCommand")
        
        # Ports
        forward_ports = data.get("forwardPorts", [])
        config.forward_ports = [
            int(port) if isinstance(port, str) and port.isdigit() else port
            for port in forward_ports
            if isinstance(port, (int, str))
        ]
        
        other_ports = data.get("otherPorts", [])
        config.other_ports = [str(port) for port in other_ports]
        
        # Environment
        config.remote_env = data.get("remoteEnv", {})
        
        # Extensions and settings
        config.extensions = data.get("extensions", [])
        config.settings = data.get("settings", {})
        
        # User
        config.remote_user = data.get("remoteUser")
        config.container_user = data.get("containerUser")
        
        # Mounts
        config.mounts = data.get("mounts", [])
        
        # Run arguments
        config.run_args = data.get("runArgs", [])
        
        # Host requirements
        config.host_requirements = data.get("hostRequirements", {})
        
        # Customizations
        config.customizations = data.get("customizations", {})
        
        # Name and description
        config.name = data.get("name")
        config.description = data.get("description")
        
        # Override command
        config.override_command = data.get("overrideCommand")
        
        # Init and privileged
        config.init = data.get("init", False)
        config.privileged = data.get("privileged", False)
        
        # Capabilities
        config.cap_add = data.get("capAdd", [])
        
        # Security options
        config.security_opt = data.get("securityOpt", [])
        
        # Workspace folder
        config.workspace_folder = data.get("workspaceFolder")
        
        # Update content cache
        config.update_content_cache = data.get("updateContentCache", False)
        
        # Store additional properties
        known_keys = {
            "image", "build", "features", "postCreateCommand", "postStartCommand",
            "forwardPorts", "otherPorts", "remoteEnv", "extensions", "settings",
            "remoteUser", "containerUser", "mounts", "runArgs", "hostRequirements",
            "customizations", "name", "description", "overrideCommand", "init",
            "privileged", "capAdd", "securityOpt", "workspaceFolder", "updateContentCache"
        }
        
        config.additional_properties = {
            k: v for k, v in data.items() if k not in known_keys
        }
        
        return config
    
    async def parse_from_repo(
        self, 
        repo_url: str, 
        repo_ref: Optional[str] = None,
        config_path: str = ".devcontainer/devcontainer.json"
    ) -> Optional[DevContainerConfig]:
        """Parse devcontainer.json from a Git repository"""
        if not repo_url:
            return None
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                # Clone the repository
                self.logger.info(f"Cloning repository: {repo_url}")
                git_repo = GitRepo.clone_from(repo_url, tmp_dir)
                
                # Checkout specific ref if provided
                if repo_ref:
                    self.logger.info(f"Checking out ref: {repo_ref}")
                    git_repo.git.checkout(repo_ref)
                
                # Look for devcontainer.json
                config_file = Path(tmp_dir) / config_path
                
                if not config_file.exists():
                    # Try alternative paths
                    alternative_paths = [
                        ".devcontainer.json",
                        "devcontainer.json",
                        ".devcontainer/devcontainer.json"
                    ]
                    
                    for alt_path in alternative_paths:
                        alt_file = Path(tmp_dir) / alt_path
                        if alt_file.exists():
                            config_file = alt_file
                            break
                
                if not config_file.exists():
                    self.logger.info(f"No devcontainer.json found in repository")
                    return None
                
                # Parse the config
                return self.parse_file(str(config_file))
                
            except Exception as e:
                self.logger.error(f"Error parsing devcontainer from repo: {e}")
                return None
    
    def to_service_definition(self, config: DevContainerConfig) -> Dict[str, Any]:
        """Convert DevContainer config to platform service definition"""
        
        # Determine image
        image = config.image
        if not image and config.dockerfile:
            # Will need to build
            image = None
        
        # Build command
        command = None
        if config.post_start_command:
            command = config.post_start_command
        elif config.post_create_command:
            command = config.post_create_command
        
        # Convert command to string if it's a list
        if isinstance(command, list):
            command = " && ".join(command)
        
        # Build service definition
        service = {
            'name': config.name or 'dev-container',
            'type': 'development',
            'image': image,
            'command': command,
            'ports': config.forward_ports + [int(p.split(':')[0]) for p in config.other_ports if ':' in p],
            'env': config.remote_env,
            'extensions': config.extensions,
            'features': {k: v.__dict__ for k, v in config.features.items()},
            'settings': config.settings,
            'metadata': {
                'devcontainer': True,
                'description': config.description,
                'source': 'devcontainer.json'
            }
        }
        
        # Add build context if Dockerfile specified
        if config.dockerfile:
            service['build'] = {
                'context': config.build_context or '.',
                'dockerfile': config.dockerfile
            }
        
        # Add user
        if config.remote_user:
            service['user'] = config.remote_user
        
        # Add mounts
        if config.mounts:
            service['volumes'] = config.mounts
        
        # Add run arguments
        if config.run_args:
            service['run_args'] = config.run_args
        
        # Add capabilities
        if config.cap_add:
            service['cap_add'] = config.cap_add
        
        # Add security options
        if config.security_opt:
            service['security_opt'] = config.security_opt
        
        # Add init and privileged flags
        if config.init:
            service['init'] = True
        if config.privileged:
            service['privileged'] = True
        
        # Add host requirements
        if config.host_requirements:
            service['host_requirements'] = config.host_requirements
        
        return service
    
    def to_docker_compose(self, config: DevContainerConfig, service_name: str = "app") -> Dict[str, Any]:
        """Convert DevContainer config to docker-compose format"""
        
        compose = {
            'version': '3.8',
            'services': {
                service_name: {}
            }
        }
        
        service = compose['services'][service_name]
        
        # Image or build
        if config.image:
            service['image'] = config.image
        elif config.dockerfile:
            service['build'] = {
                'context': config.build_context or '.',
                'dockerfile': config.dockerfile
            }
        
        # Command
        if config.post_start_command:
            cmd = config.post_start_command
            if isinstance(cmd, list):
                cmd = ' && '.join(cmd)
            service['command'] = cmd
        
        # Ports
        if config.forward_ports:
            service['ports'] = [f"{port}:{port}" for port in config.forward_ports]
        
        # Environment
        if config.remote_env:
            service['environment'] = config.remote_env
        
        # Volumes
        if config.mounts:
            service['volumes'] = config.mounts
        
        # User
        if config.remote_user:
            service['user'] = config.remote_user
        
        # Privileged
        if config.privileged:
            service['privileged'] = True
        
        # Capabilities
        if config.cap_add:
            service['cap_add'] = config.cap_add
        
        # Security options
        if config.security_opt:
            service['security_opt'] = config.security_opt
        
        # Init
        if config.init:
            service['init'] = True
        
        return compose


class DevContainerManager:
    """Manages DevContainer-based sessions"""
    
    def __init__(self, session_manager: Any = None):
        self.session_manager = session_manager
        self.parser = DevContainerParser()
        self.logger = logging.getLogger(__name__)
    
    async def create_session_from_devcontainer(
        self,
        repo_url: str,
        repo_ref: Optional[str] = None,
        user_id: Optional[str] = None,
        ttl_minutes: Optional[int] = None
    ) -> Any:
        """Create a session from a DevContainer configuration"""
        
        # Parse devcontainer.json
        config = await self.parser.parse_from_repo(repo_url, repo_ref)
        
        if not config:
            raise ValueError("No devcontainer.json found in repository")
        
        # Convert to service definition
        service_def = self.parser.to_service_definition(config)
        
        # Create session using session manager
        if self.session_manager:
            from src.models.session import SessionType
            
            session = await self.session_manager.create_session(
                session_type=SessionType.RUN_REPO,
                repo_url=repo_url,
                repo_ref=repo_ref,
                ttl_minutes=ttl_minutes,
                user_id=user_id,
                services=[service_def]  # Pass custom service definition
            )
            
            # Store devcontainer metadata
            session.metadata['devcontainer'] = True
            session.metadata['devcontainer_config'] = {
                'name': config.name,
                'description': config.description,
                'extensions': config.extensions,
                'features': list(config.features.keys())
            }
            
            return session
        else:
            raise ValueError("Session manager not configured")


# Integration with SessionManager
async def extend_session_manager_with_devcontainer(session_manager: Any):
    """Extend session manager with DevContainer capabilities"""
    
    devcontainer_manager = DevContainerManager(session_manager)
    
    # Add method to create sessions from DevContainer
    async def create_devcontainer_session(
        repo_url: str,
        repo_ref: Optional[str] = None,
        user_id: Optional[str] = None,
        ttl_minutes: Optional[int] = None
    ):
        return await devcontainer_manager.create_session_from_devcontainer(
            repo_url=repo_url,
            repo_ref=repo_ref,
            user_id=user_id,
            ttl_minutes=ttl_minutes
        )
    
    session_manager.create_devcontainer_session = create_devcontainer_session
    
    logger.info("DevContainer support added to SessionManager")
