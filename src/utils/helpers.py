import uuid
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import psutil
import os
import pathlib
import subprocess
from .config import settings


def generate_pod_id() -> str:
    """Generate a unique pod ID"""
    return f"pod-{uuid.uuid4().hex[:8]}"


def generate_snapshot_id() -> str:
    """Generate a unique snapshot ID"""
    return f"snapshot-{uuid.uuid4().hex[:8]}"


def generate_node_id() -> str:
    """Generate a unique node ID"""
    return f"node-{uuid.uuid4().hex[:8]}"


def get_current_timestamp() -> datetime:
    """Get current timestamp in UTC"""
    return datetime.utcnow()


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human readable format"""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        return f"{minutes}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m {seconds % 60}s"


def calculate_distance(loc1: str, loc2: str) -> float:
    """
    Calculate distance between two locations (simplified)
    In a real implementation, this would use actual geographic coordinates
    """
    # This is a simplified implementation
    # In a real system, you would use geographic coordinates
    if loc1 == loc2:
        return 0.0
    else:
        # Return a mock distance based on string similarity
        return 100.0


def get_system_resources() -> Dict[str, Any]:
    """Get current system resource usage"""
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "memory_available_gb": psutil.virtual_memory().available / (1024**3),
        "disk_usage_percent": psutil.disk_usage('/').percent,
        "disk_available_gb": psutil.disk_usage('/').free / (1024**3),
        "load_average": psutil.getloadavg(),
        "temperature": get_cpu_temperature(),
    }


def get_cpu_temperature() -> float:
    """Get CPU temperature (simplified)"""
    # This is a simplified implementation
    # In a real system, you would read from hardware sensors
    try:
        # Try to read from common temperature sensor locations
        if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
            with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                temp = int(f.read().strip()) / 1000.0
                return temp
        else:
            # Return a mock temperature
            return 45.0
    except:
        return 45.0


def run_command(cmd: List[str], timeout: int = 30) -> Optional[str]:
    """Run a shell command and return output"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logging.error(f"Command failed: {' '.join(cmd)}, error: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        logging.error(f"Command timed out: {' '.join(cmd)}")
        return None
    except Exception as e:
        logging.error(f"Command execution error: {e}")
        return None


def validate_gpu_availability(gpu_type: str, required_vram: int) -> bool:
    """Validate if GPU with required VRAM is available"""
    # This is a simplified implementation
    # In a real system, you would query actual GPU resources
    if gpu_type and required_vram > 0:
        # Mock validation - assume GPU is available
        return True
    return True


def is_os_compatible(node_os: str, app_type: str) -> bool:
    """Check if node OS is compatible with requested app type"""
    if app_type == "windows":
        # Windows apps can run on Linux with QEMU
        return True
    elif app_type == "linux":
        # Linux apps can run on Linux with containers or VMs
        return node_os.lower().startswith("linux")
    elif app_type == "macos":
        # macOS apps require macOS or specialized setup
        return node_os.lower().startswith("darwin") or node_os.lower().startswith("mac")
    return True


def is_gpu_compatible(gpu_type: Optional[str], app_name: str) -> bool:
    """Check if GPU type is compatible with app"""
    if not gpu_type:
        return True
    
    # For GPU-intensive apps like UE5/TouchDesigner, any modern GPU should work
    if app_name.lower() in ["ue5", "unreal engine 5", "touchdesigner"]:
        return True
    
    return True


def create_directory_if_not_exists(path: str) -> bool:
    """Create directory if it doesn't exist"""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except Exception as e:
        logging.error(f"Failed to create directory {path}: {e}")
        return False


def format_bytes_to_gb(bytes_value: float) -> float:
    """Convert bytes to gigabytes"""
    return bytes_value / (1024**3)


def get_gpu_info() -> Dict[str, Any]:
    """Get information about available GPUs"""
    # This is a simplified implementation
    # In a real system, you would query nvidia-smi or similar
    try:
        # Try to get NVIDIA GPU info
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            gpus = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = [part.strip() for part in line.split(',')]
                    if len(parts) >= 3:
                        gpus.append({
                            "name": parts[0],
                            "memory_total_mb": int(parts[1]),
                            "memory_used_mb": int(parts[2])
                        })
            return {"gpus": gpus, "driver_version": "NVIDIA Driver"}
        else:
            # No NVIDIA GPU found, return empty info
            return {"gpus": [], "driver_version": "No GPU"}
    except FileNotFoundError:
        # nvidia-smi not found
        return {"gpus": [], "driver_version": "No GPU"}
    except Exception as e:
        logging.error(f"Error getting GPU info: {e}")
        return {"gpus": [], "driver_version": "Error"}


def cleanup_temporary_files(pod_id: str):
    """Clean up temporary files associated with a pod"""
    # Sanitize the pod_id to prevent path traversal
    safe_pod_id = pathlib.Path(pod_id).name

    temp_dirs = [
        f"{settings.storage_base_path}/temp/{safe_pod_id}",
        f"/tmp/disposable_compute_{safe_pod_id}"
    ]

    for temp_dir in temp_dirs:
        try:
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)
        except Exception as e:
            logging.error(f"Error cleaning up temp files for {pod_id}: {e}")


async def async_retry(func, max_attempts: int = 3, delay: float = 1.0, *args, **kwargs):
    """Retry a function asynchronously with exponential backoff"""
    for attempt in range(max_attempts):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if attempt == max_attempts - 1:
                raise e
            await asyncio.sleep(delay * (2 ** attempt))  # Exponential backoff
    return None