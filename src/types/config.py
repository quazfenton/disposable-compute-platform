from pydantic_settings import BaseSettings
from typing import Optional, List
import os


class Settings(BaseSettings):
    # API Settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_debug: bool = False
    
    # Database Settings
    database_url: str = "postgresql+asyncpg://user:password@localhost/disposable_compute"
    
    # Redis Settings
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # QEMU Settings
    qemu_binary_path: str = "/usr/bin/qemu-system-x86_64"
    qemu_default_memory: int = 4096  # MB
    qemu_default_cpu_cores: int = 2
    qemu_gpu_passthrough: bool = True
    
    # Docker Settings
    docker_api_version: str = "1.40"
    docker_timeout: int = 120
    
    # Storage Settings
    storage_base_path: str = "/var/lib/disposable-compute"
    snapshot_storage_path: str = "/var/lib/disposable-compute/snapshots"
    container_storage_path: str = "/var/lib/disposable-compute/containers"
    
    # Network Settings
    network_interface: str = "eth0"
    streaming_port_range_start: int = 8000
    streaming_port_range_end: int = 9000
    
    # GPU Settings
    gpu_vram_threshold: float = 0.9  # 90% threshold for VRAM
    gpu_monitoring_interval: int = 5  # seconds
    
    # Pod Settings
    pod_startup_timeout: int = 300  # seconds
    pod_idle_timeout: int = 3600  # seconds (1 hour)
    pod_max_runtime: int = 86400  # seconds (24 hours)

    # Scheduler Settings
    scheduler_check_interval: int = 10  # seconds
    scheduler_max_attempts: int = 5

    # Security Settings
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    debug: str = os.getenv("DEBUG", "true").lower()

    # Logging Settings
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    class Config:
        env_file = ".env"

settings = Settings()
