"""
Performance Profiling Suite
CPU, memory, and I/O profiling for performance optimization

Install: pip install py-spy memory_profiler line_profiler
Run: python tests/performance/test_profiling.py
"""
import asyncio
import time
import tracemalloc
import cProfile
import pstats
import io
from contextlib import contextmanager
from typing import Dict, Any, Callable
import logging
import os

logger = logging.getLogger(__name__)


class PerformanceProfiler:
    """Performance profiling utilities"""
    
    def __init__(self, output_dir: str = "profiling_results"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
    
    @contextmanager
    def profile_cpu(self, name: str = "profile"):
        """Profile CPU usage"""
        profiler = cProfile.Profile()
        profiler.enable()
        
        start_time = time.time()
        
        try:
            yield profiler
        finally:
            profiler.disable()
            elapsed = time.time() - start_time
            
            # Save stats
            stats_file = os.path.join(self.output_dir, f"{name}_cpu.prof")
            profiler.dump_stats(stats_file)
            
            # Print summary
            stats = pstats.Stats(profiler)
            stats.sort_stats('cumulative')
            
            print(f"\n=== CPU Profile: {name} ===")
            print(f"Duration: {elapsed:.2f}s")
            print(f"Top 10 functions by cumulative time:")
            stats.print_stats(10)
            
            logger.info(f"CPU profile saved to {stats_file}")
    
    @contextmanager
    def profile_memory(self, name: str = "profile"):
        """Profile memory usage"""
        tracemalloc.start()
        
        start_time = time.time()
        
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            
            print(f"\n=== Memory Profile: {name} ===")
            print(f"Duration: {elapsed:.2f}s")
            print(f"Current memory: {current / 1024 / 1024:.2f} MB")
            print(f"Peak memory: {peak / 1024 / 1024:.2f} MB")
            
            # Save top allocations
            snapshot = tracemalloc.take_snapshot()
            stats_file = os.path.join(self.output_dir, f"{name}_memory.txt")
            
            with open(stats_file, 'w') as f:
                for stat in snapshot.statistics('lineno')[:20]:
                    f.write(f"{stat}\n")
            
            logger.info(f"Memory profile saved to {stats_file}")
    
    @contextmanager
    def profile_async(self, name: str = "profile"):
        """Profile async operations"""
        import aiofiles
        
        start_time = time.time()
        start_mem = tracemalloc.get_traced_memory()[0] if tracemalloc.is_tracing() else 0
        
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            
            end_mem = tracemalloc.get_traced_memory()[0] if tracemalloc.is_tracing() else 0
            mem_delta = end_mem - start_mem
            
            print(f"\n=== Async Profile: {name} ===")
            print(f"Duration: {elapsed:.2f}s")
            print(f"Memory delta: {mem_delta / 1024:.2f} KB")


class SessionPerformanceTest:
    """Performance tests for session operations"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.profiler = PerformanceProfiler()
    
    async def test_session_creation_performance(self, iterations: int = 100):
        """Test session creation performance"""
        import aiohttp
        
        latencies = []
        errors = 0
        
        async with aiohttp.ClientSession() as session:
            for i in range(iterations):
                start = time.time()
                
                try:
                    async with session.post(
                        f"{self.base_url}/sessions",
                        json={
                            "type": "run_repo",
                            "repo_url": "https://github.com/test/repo",
                            "ttl_minutes": 30
                        }
                    ) as response:
                        if response.status != 200:
                            errors += 1
                except Exception as e:
                    errors += 1
                
                latency = time.time() - start
                latencies.append(latency)
        
        # Calculate statistics
        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        
        print(f"\n=== Session Creation Performance ===")
        print(f"Iterations: {iterations}")
        print(f"Errors: {errors} ({errors/iterations*100:.1f}%)")
        print(f"P50 latency: {p50*1000:.2f}ms")
        print(f"P95 latency: {p95*1000:.2f}ms")
        print(f"P99 latency: {p99*1000:.2f}ms")
        print(f"Min latency: {min(latencies)*1000:.2f}ms")
        print(f"Max latency: {max(latencies)*1000:.2f}ms")
        
        return {
            "p50": p50,
            "p95": p95,
            "p99": p99,
            "errors": errors,
            "iterations": iterations
        }
    
    async def test_concurrent_sessions(self, max_concurrent: int = 50):
        """Test concurrent session handling"""
        import aiohttp
        
        async def create_session(session, i):
            try:
                async with session.post(
                    f"{self.base_url}/sessions",
                    json={
                        "type": "run_repo",
                        "repo_url": f"https://github.com/test/repo-{i}",
                        "ttl_minutes": 30
                    }
                ) as response:
                    return response.status == 200
            except:
                return False
        
        async with aiohttp.ClientSession() as session:
            # Test increasing concurrency
            for concurrent in [10, 25, 50, 100]:
                tasks = [create_session(session, i) for i in range(concurrent)]
                
                start = time.time()
                results = await asyncio.gather(*tasks)
                elapsed = time.time() - start
                
                success = sum(results)
                success_rate = success / concurrent * 100
                
                print(f"\nConcurrent: {concurrent}")
                print(f"  Success: {success}/{concurrent} ({success_rate:.1f}%)")
                print(f"  Duration: {elapsed:.2f}s")
                print(f"  Throughput: {concurrent/elapsed:.2f} req/s")


class MemoryLeakTest:
    """Test for memory leaks"""
    
    def test_session_lifecycle_memory(self):
        """Test memory usage across session lifecycle"""
        from src.services.platform import SessionManager, PlatformConfig
        
        config = PlatformConfig(
            domain="test.preview.dev",
            default_ttl=30,
            storage_path="/tmp/test-storage"
        )
        
        session_manager = SessionManager(config)
        
        # Track memory over multiple sessions
        memory_samples = []
        
        for i in range(100):
            # Create session
            # Note: This is simplified - actual test would create real sessions
            memory_samples.append(0)  # Placeholder
        
        # Analyze memory trend
        if len(memory_samples) > 10:
            early_avg = sum(memory_samples[:10]) / 10
            late_avg = sum(memory_samples[-10:]) / 10
            
            growth = (late_avg - early_avg) / early_avg * 100 if early_avg > 0 else 0
            
            print(f"\n=== Memory Leak Test ===")
            print(f"Early avg: {early_avg:.2f} KB")
            print(f"Late avg: {late_avg:.2f} KB")
            print(f"Growth: {growth:.2f}%")
            
            if growth > 50:
                print("WARNING: Potential memory leak detected!")


class IOProfiling:
    """I/O performance profiling"""
    
    def test_database_query_performance(self):
        """Test database query performance"""
        # Placeholder for database profiling
        print("\n=== Database Query Performance ===")
        print("Requires actual database connection")
    
    def test_redis_cache_performance(self):
        """Test Redis cache performance"""
        # Placeholder for Redis profiling
        print("\n=== Redis Cache Performance ===")
        print("Requires actual Redis connection")


def run_all_profiles():
    """Run all performance profiles"""
    print("=" * 60)
    print("PERFORMANCE PROFILING SUITE")
    print("=" * 60)
    
    # CPU Profiling
    profiler = PerformanceProfiler()
    
    with profiler.profile_cpu("session_test"):
        # Simulate workload
        time.sleep(0.1)
    
    # Memory Profiling
    with profiler.profile_memory("session_test"):
        # Simulate workload
        data = [i for i in range(10000)]
    
    print("\n" + "=" * 60)
    print("Profiling complete. Check profiling_results/ for details.")
    print("=" * 60)


if __name__ == "__main__":
    run_all_profiles()
