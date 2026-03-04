"""
Image Registry for disposable compute platform
Manages container images with registry integration, scanning, and caching
"""
import docker
import json
import logging
import hashlib
import asyncio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import aiofiles
import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class Image:
    """Represents a container image"""
    id: str
    name: str
    tag: str
    full_name: str
    size_bytes: int
    created_at: datetime
    labels: Dict[str, str]
    digest: Optional[str] = None
    architecture: Optional[str] = None
    os: Optional[str] = None
    layers: int = 0
    vulnerability_scan: Optional[Dict[str, Any]] = None
    last_pulled: Optional[datetime] = None
    pull_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'tag': self.tag,
            'full_name': self.full_name,
            'size_bytes': self.size_bytes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'labels': self.labels,
            'digest': self.digest,
            'architecture': self.architecture,
            'os': self.os,
            'layers': self.layers,
            'vulnerability_scan': self.vulnerability_scan,
            'last_pulled': self.last_pulled.isoformat() if self.last_pulled else None,
            'pull_count': self.pull_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Image":
        """Create from dictionary"""
        if data.get('created_at'):
            try:
                data['created_at'] = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
            except:
                data['created_at'] = datetime.now()
        
        if data.get('last_pulled'):
            try:
                data['last_pulled'] = datetime.fromisoformat(data['last_pulled'].replace('Z', '+00:00'))
            except:
                pass
        
        return cls(**data)


@dataclass
class RegistryConfig:
    """Registry configuration"""
    url: str
    username: Optional[str] = None
    password: Optional[str] = None
    verify_ssl: bool = True
    timeout: int = 300  # seconds
    max_retries: int = 3
    cache_enabled: bool = True
    cache_path: str = "/tmp/image-cache"
    scan_on_push: bool = True
    scan_on_pull: bool = False


class ImageRegistry:
    """Manages container images with registry integration"""
    
    def __init__(
        self, 
        config: RegistryConfig,
        docker_client: docker.DockerClient = None
    ):
        self.config = config
        self.client = docker_client or docker.from_env()
        self.images: Dict[str, Image] = {}
        self._lock = asyncio.Lock()
        
        # Create cache directory
        if config.cache_enabled:
            self.cache_path = Path(config.cache_path)
            self.cache_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"ImageRegistry initialized for {config.url}")
    
    async def initialize(self):
        """Initialize registry connection"""
        try:
            # Test registry connection
            await self._check_registry_health()
            logger.info("Registry connection successful")
        except Exception as e:
            logger.warning(f"Registry connection check failed: {e}")
    
    async def _check_registry_health(self) -> bool:
        """Check registry health"""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.config.url}/v2/"
                
                async with session.get(url, timeout=self.config.timeout) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Registry health check failed: {e}")
            return False
    
    async def push_image(self, image_name: str, tag: str = "latest") -> str:
        """Push image to registry"""
        full_name = f"{image_name}:{tag}"
        registry_name = f"{self.config.url}/{image_name}:{tag}"
        
        async with self._lock:
            try:
                # Get local image
                try:
                    local_image = self.client.images.get(image_name)
                except docker.errors.ImageNotFound:
                    raise Exception(f"Image {image_name} not found locally")
                
                # Tag for registry
                logger.info(f"Tagging {image_name} as {registry_name}")
                local_image.tag(registry_name)
                
                # Push to registry
                logger.info(f"Pushing {registry_name} to registry")
                push_result = await self._push_with_progress(registry_name)
                
                # Get image info
                image = self.client.images.get(registry_name)
                
                # Create image record
                img = Image(
                    id=image.id,
                    name=image_name,
                    tag=tag,
                    full_name=registry_name,
                    size_bytes=image.attrs.get('Size', 0),
                    created_at=datetime.fromtimestamp(image.attrs.get('Created', datetime.now().timestamp())),
                    labels=image.attrs.get('Labels', {}),
                    digest=image.attrs.get('RepoDigests', [None])[0],
                    architecture=image.attrs.get('Architecture'),
                    os=image.attrs.get('Os'),
                    layers=len(image.attrs.get('RootFS', {}).get('Layers', []))
                )
                
                # Scan if configured
                if self.config.scan_on_push:
                    logger.info(f"Scanning image {registry_name}")
                    scan_result = await self.scan_image(registry_name)
                    img.vulnerability_scan = scan_result
                
                self.images[registry_name] = img
                
                # Cache the image
                if self.config.cache_enabled:
                    await self._cache_image(registry_name)
                
                logger.info(f"Successfully pushed {registry_name}")
                return registry_name
                
            except Exception as e:
                logger.error(f"Failed to push image: {e}")
                raise
    
    async def _push_with_progress(self, image_name: str) -> Dict[str, Any]:
        """Push image with progress tracking"""
        try:
            result = self.client.images.push(image_name, stream=True, decode=True)
            
            for line in result:
                if 'error' in line:
                    raise Exception(f"Push failed: {line['error']}")
                if 'status' in line:
                    status = line.get('status', '')
                    progress = line.get('progress', '')
                    if progress:
                        logger.debug(f"Push progress: {status} {progress}")
                    else:
                        logger.debug(f"Push: {status}")
            
            return {'status': 'success'}
            
        except Exception as e:
            logger.error(f"Push error: {e}")
            raise
    
    async def pull_image(self, image_name: str, tag: str = "latest", force: bool = False) -> str:
        """Pull image from registry"""
        registry_name = f"{self.config.url}/{image_name}:{tag}"
        
        async with self._lock:
            try:
                # Check cache first
                if self.config.cache_enabled:
                    cached = await self._get_cached_image(registry_name)
                    if cached and not force:
                        logger.info(f"Using cached image {registry_name}")
                        return registry_name
                
                # Check if already exists locally
                try:
                    existing = self.client.images.get(registry_name)
                    if not force:
                        logger.info(f"Image {registry_name} already exists locally")
                        return registry_name
                except docker.errors.ImageNotFound:
                    pass
                
                # Pull from registry
                logger.info(f"Pulling {registry_name} from registry")
                await self._pull_with_progress(registry_name)
                
                # Get image info
                image = self.client.images.get(registry_name)
                
                # Create image record
                img = Image(
                    id=image.id,
                    name=image_name,
                    tag=tag,
                    full_name=registry_name,
                    size_bytes=image.attrs.get('Size', 0),
                    created_at=datetime.fromtimestamp(image.attrs.get('Created', datetime.now().timestamp())),
                    labels=image.attrs.get('Labels', {}),
                    digest=image.attrs.get('RepoDigests', [None])[0],
                    architecture=image.attrs.get('Architecture'),
                    os=image.attrs.get('Os'),
                    layers=len(image.attrs.get('RootFS', {}).get('Layers', []))
                )
                
                # Scan if configured
                if self.config.scan_on_pull:
                    logger.info(f"Scanning image {registry_name}")
                    scan_result = await self.scan_image(registry_name)
                    img.vulnerability_scan = scan_result
                
                # Update pull stats
                img.pull_count = 1
                img.last_pulled = datetime.now()
                
                self.images[registry_name] = img
                
                # Cache the image
                if self.config.cache_enabled:
                    await self._cache_image(registry_name)
                
                logger.info(f"Successfully pulled {registry_name}")
                return registry_name
                
            except Exception as e:
                logger.error(f"Failed to pull image: {e}")
                raise
    
    async def _pull_with_progress(self, image_name: str):
        """Pull image with progress tracking"""
        try:
            result = self.client.images.pull(image_name, stream=True, decode=True)
            
            for line in result:
                if 'error' in line:
                    raise Exception(f"Pull failed: {line['error']}")
                if 'status' in line:
                    status = line.get('status', '')
                    progress = line.get('progress', '')
                    if progress:
                        logger.debug(f"Pull progress: {status} {progress}")
                    else:
                        logger.debug(f"Pull: {status}")
            
        except Exception as e:
            logger.error(f"Pull error: {e}")
            raise
    
    async def scan_image(self, image_name: str) -> Dict[str, Any]:
        """Scan image for vulnerabilities"""
        try:
            # Try to use Trivy if available
            from src.utils.security_enhanced import VulnerabilityScanner
            
            scanner = VulnerabilityScanner()
            result = await scanner.scan_image(image_name)
            
            return {
                'scan_id': result.scan_id,
                'timestamp': result.timestamp.isoformat(),
                'vulnerabilities': result.vulnerabilities,
                'severity_summary': result.severity_summary,
                'recommendations': result.recommendations,
                'status': result.status
            }
            
        except ImportError:
            logger.warning("VulnerabilityScanner not available")
            return {
                'status': 'not_scanned',
                'reason': 'Scanner not available'
            }
        except Exception as e:
            logger.error(f"Image scan failed: {e}")
            return {
                'status': 'scan_failed',
                'error': str(e)
            }
    
    async def _cache_image(self, image_name: str):
        """Cache image metadata"""
        if not self.config.cache_enabled:
            return
        
        try:
            cache_file = self.cache_path / f"{self._sanitize_image_name(image_name)}.json"
            
            image = self.client.images.get(image_name)
            metadata = {
                'id': image.id,
                'tags': image.tags,
                'attrs': image.attrs,
                'cached_at': datetime.now().isoformat()
            }
            
            async with aiofiles.open(cache_file, 'w') as f:
                await f.write(json.dumps(metadata, indent=2))
            
            logger.debug(f"Cached metadata for {image_name}")
            
        except Exception as e:
            logger.warning(f"Failed to cache image {image_name}: {e}")
    
    async def _get_cached_image(self, image_name: str) -> bool:
        """Check if image is cached"""
        if not self.config.cache_enabled:
            return False
        
        try:
            cache_file = self.cache_path / f"{self._sanitize_image_name(image_name)}.json"
            
            if cache_file.exists():
                async with aiofiles.open(cache_file, 'r') as f:
                    metadata = json.loads(await f.read())
                
                # Check if image still exists locally
                try:
                    self.client.images.get(metadata['tags'][0] if metadata.get('tags') else image_name)
                    return True
                except docker.errors.ImageNotFound:
                    # Remove stale cache
                    cache_file.unlink()
            
            return False
            
        except Exception as e:
            logger.warning(f"Cache check failed for {image_name}: {e}")
            return False
    
    def _sanitize_image_name(self, name: str) -> str:
        """Sanitize image name for filesystem"""
        return name.replace('/', '_').replace(':', '_')
    
    async def delete_image(self, image_name: str, tag: str = "latest") -> bool:
        """Delete image from local storage"""
        registry_name = f"{self.config.url}/{image_name}:{tag}"
        
        async with self._lock:
            try:
                image = self.client.images.get(registry_name)
                self.client.images.remove(image.id, force=True)
                
                # Remove from tracking
                if registry_name in self.images:
                    del self.images[registry_name]
                
                # Remove cache
                if self.config.cache_enabled:
                    cache_file = self.cache_path / f"{self._sanitize_image_name(registry_name)}.json"
                    if cache_file.exists():
                        cache_file.unlink()
                
                logger.info(f"Deleted image {registry_name}")
                return True
                
            except docker.errors.ImageNotFound:
                logger.warning(f"Image {registry_name} not found")
                return False
            except Exception as e:
                logger.error(f"Failed to delete image {registry_name}: {e}")
                raise
    
    async def list_images(self) -> List[Image]:
        """List all tracked images"""
        return list(self.images.values())
    
    async def get_image(self, image_name: str, tag: str = "latest") -> Optional[Image]:
        """Get image by name"""
        registry_name = f"{self.config.url}/{image_name}:{tag}"
        return self.images.get(registry_name)
    
    async def cleanup_old_images(self, max_age_days: int = 7) -> int:
        """Clean up images older than max_age_days"""
        try:
            cleaned = 0
            cutoff = datetime.now().timestamp() - (max_age_days * 24 * 60 * 60)
            
            for registry_name, img in list(self.images.items()):
                image_timestamp = img.created_at.timestamp() if img.created_at else 0
                
                if image_timestamp < cutoff:
                    try:
                        await self.delete_image(img.name, img.tag)
                        cleaned += 1
                        logger.info(f"Cleaned up old image {registry_name}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup image {registry_name}: {e}")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
            return 0
    
    async def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics"""
        total_size = sum(img.size_bytes for img in self.images.values())
        total_pulls = sum(img.pull_count for img in self.images.values())
        
        severity_counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        for img in self.images.values():
            if img.vulnerability_scan and img.vulnerability_scan.get('severity_summary'):
                for severity, count in img.vulnerability_scan['severity_summary'].items():
                    severity_counts[severity] = severity_counts.get(severity, 0) + count
        
        return {
            'total_images': len(self.images),
            'total_size_bytes': total_size,
            'total_size_gb': total_size / (1024 ** 3),
            'total_pulls': total_pulls,
            'vulnerabilities': severity_counts,
            'cache_enabled': self.config.cache_enabled,
            'scan_on_push': self.config.scan_on_push,
            'scan_on_pull': self.config.scan_on_pull
        }


class ImageRegistryManager:
    """Manages multiple image registries"""
    
    def __init__(self):
        self.registries: Dict[str, ImageRegistry] = {}
        self.default_registry: Optional[str] = None
        self.logger = logging.getLogger(__name__)
    
    def add_registry(self, name: str, config: RegistryConfig, default: bool = False):
        """Add a registry"""
        registry = ImageRegistry(config)
        self.registries[name] = registry
        
        if default or self.default_registry is None:
            self.default_registry = name
        
        self.logger.info(f"Added registry {name} at {config.url}")
    
    def get_registry(self, name: str) -> Optional[ImageRegistry]:
        """Get registry by name"""
        return self.registries.get(name)
    
    def get_default_registry(self) -> Optional[ImageRegistry]:
        """Get default registry"""
        if self.default_registry:
            return self.registries.get(self.default_registry)
        return None
    
    async def initialize_all(self):
        """Initialize all registries"""
        for name, registry in self.registries.items():
            try:
                await registry.initialize()
                self.logger.info(f"Initialized registry {name}")
            except Exception as e:
                self.logger.error(f"Failed to initialize registry {name}: {e}")
