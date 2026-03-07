import uuid
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
import psutil
import os
import pathlib
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


async def run_command(cmd: List[str], timeout: int = 30) -> Optional[str]:
    """Run a shell command asynchronously and return output"""
    try:
        # Use asyncio.create_subprocess_exec for non-blocking execution
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            
            if proc.returncode == 0:
                return stdout.decode().strip()
            else:
                logging.error(f"Command failed: {' '.join(cmd)}, error: {stderr.decode()}")
                return None
        except asyncio.TimeoutError:
            proc.kill()
            logging.error(f"Command timed out: {' '.join(cmd)}")
            return None
            
    except Exception as e:
        logging.error(f"Command execution error: {e}")
        return None


async def get_gpu_info() -> Dict[str, Any]:
    """Get information about available GPUs asynchronously"""
    try:
        # Check if nvidia-smi is available
        which_result = await run_command(['which', 'nvidia-smi'])
        if not which_result:
            return {"gpus": [], "driver_version": "No GPU"}

        # Try to get NVIDIA GPU info
        output = await run_command(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used", "--format=csv,noheader,nounits"]
        )
        
        if output:
            gpus = []
            for line in output.strip().split('\n'):
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
            return {"gpus": [], "driver_version": "No GPU"}
    except Exception as e:
        logging.error(f"Error getting GPU info: {e}")
        return {"gpus": [], "driver_version": "Error"}



def cleanup_temporary_files(pod_id: str):
    """Clean up temporary files associated with a pod"""
    # Sanitize the pod_id to prevent path traversal
    safe_pod_id = pathlib.Path(pod_id).name
    if not safe_pod_id:
        logging.error(f"Invalid pod_id provided for cleanup: {pod_id!r}")
        return

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