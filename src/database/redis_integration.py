"""
Redis integration for distributed session state and caching
"""
import asyncio
import logging
import pickle
import json
from typing import Dict, List, Optional, Any
from datetime import timedelta

try:
    import redis.asyncio as aioredis
    AIOREDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    AIOREDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class RedisConfig:
    """Redis configuration"""
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        retry_on_timeout: bool = True,
        max_connections: int = 50,
        key_prefix: str = "dcp:"
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        self.max_connections = max_connections
        self.key_prefix = key_prefix


class RedisSessionStore:
    """Redis-backed session store for distributed state"""
    
    def __init__(self, config: RedisConfig):
        self.config = config
        self.redis: Optional[aioredis.Redis] = None
        self._connected = False
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._pubsub_channels: Dict[str, List] = {}
        
        logger.info("RedisSessionStore initialized")
    
    async def connect(self):
        """Connect to Redis"""
        if not AIOREDIS_AVAILABLE:
            logger.warning("aioredis not available, Redis disabled")
            return False
        
        try:
            self.redis = aioredis.from_url(
                f"redis://{self.config.host}:{self.config.port}/{self.config.db}",
                password=self.config.password,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                retry_on_timeout=self.config.retry_on_timeout,
                max_connections=self.config.max_connections,
                decode_responses=False  # We handle decoding
            )
            
            # Test connection
            await self.redis.ping()
            
            self._connected = True
            logger.info(f"Connected to Redis at {self.config.host}:{self.config.port}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self._pubsub:
            await self._pubsub.close()
        
        if self.redis:
            await self.redis.close()
        
        self._connected = False
        logger.info("Disconnected from Redis")
    
    def _key(self, key: str) -> str:
        """Add prefix to key"""
        return f"{self.config.key_prefix}{key}"
    
    async def set_session(self, session_id: str, session_data: Dict[str, Any], ttl_seconds: int = 3600):
        """Store session in Redis"""
        if not self._connected:
            return False
        
        try:
            key = self._key(f"session:{session_id}")
            # Use pickle for complex objects
            data = pickle.dumps(session_data)
            await self.redis.setex(key, timedelta(seconds=ttl_seconds), data)
            
            logger.debug(f"Stored session {session_id} in Redis (TTL: {ttl_seconds}s)")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store session {session_id}: {e}")
            return False
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve session from Redis"""
        if not self._connected:
            return None
        
        try:
            key = self._key(f"session:{session_id}")
            data = await self.redis.get(key)
            
            if not data:
                return None
            
            return pickle.loads(data)
            
        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session from Redis"""
        if not self._connected:
            return False
        
        try:
            key = self._key(f"session:{session_id}")
            await self.redis.delete(key)
            
            logger.debug(f"Deleted session {session_id} from Redis")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            return False
    
    async def session_exists(self, session_id: str) -> bool:
        """Check if session exists in Redis"""
        if not self._connected:
            return False
        
        try:
            key = self._key(f"session:{session_id}")
            return await self.redis.exists(key) > 0
            
        except Exception as e:
            logger.error(f"Failed to check session {session_id}: {e}")
            return False
    
    async def set_cache(self, key: str, value: Any, ttl_seconds: int = 300):
        """Store arbitrary data in cache"""
        if not self._connected:
            return False
        
        try:
            redis_key = self._key(f"cache:{key}")
            data = pickle.dumps(value)
            await self.redis.setex(redis_key, timedelta(seconds=ttl_seconds), data)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache {key}: {e}")
            return False
    
    async def get_cache(self, key: str) -> Optional[Any]:
        """Retrieve data from cache"""
        if not self._connected:
            return None
        
        try:
            redis_key = self._key(f"cache:{key}")
            data = await self.redis.get(redis_key)
            
            if not data:
                return None
            
            return pickle.loads(data)
            
        except Exception as e:
            logger.error(f"Failed to retrieve cache {key}: {e}")
            return None
    
    async def increment_counter(self, key: str, amount: int = 1) -> int:
        """Increment a counter"""
        if not self._connected:
            return 0
        
        try:
            redis_key = self._key(f"counter:{key}")
            return await self.redis.incr(redis_key, amount)
            
        except Exception as e:
            logger.error(f"Failed to increment counter {key}: {e}")
            return 0
    
    async def get_counter(self, key: str) -> int:
        """Get counter value"""
        if not self._connected:
            return 0
        
        try:
            redis_key = self._key(f"counter:{key}")
            value = await self.redis.get(redis_key)
            return int(value) if value else 0
            
        except Exception as e:
            logger.error(f"Failed to get counter {key}: {e}")
            return 0
    
    async def publish_event(self, channel: str, event: Dict[str, Any]) -> int:
        """Publish event to channel"""
        if not self._connected:
            return 0
        
        try:
            redis_channel = self._key(f"channel:{channel}")
            message = json.dumps(event)
            return await self.redis.publish(redis_channel, message)
            
        except Exception as e:
            logger.error(f"Failed to publish event to {channel}: {e}")
            return 0
    
    async def subscribe_to_channel(self, channel: str, callback):
        """Subscribe to channel with callback"""
        if not self._connected:
            return
        
        try:
            redis_channel = self._key(f"channel:{channel}")
            
            if self._pubsub is None:
                self._pubsub = self.redis.pubsub()
            
            await self._pubsub.subscribe(redis_channel)
            
            # Store callback
            if channel not in self._pubsub_channels:
                self._pubsub_channels[channel] = []
            self._pubsub_channels[channel].append(callback)
            
            # Start listening if not already
            if not hasattr(self, '_listen_task') or self._listen_task.done():
                self._listen_task = asyncio.create_task(self._listen_to_channels())
            
            logger.info(f"Subscribed to channel {channel}")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to channel {channel}: {e}")
    
    async def _listen_to_channels(self):
        """Listen to subscribed channels with auto-reconnect"""
        while self._connected:
            try:
                if not self._pubsub:
                    self._pubsub = self.redis.pubsub()
                    # Re-subscribe to all existing channels
                    for channel in self._pubsub_channels:
                        redis_channel = self._key(f"channel:{channel}")
                        await self._pubsub.subscribe(redis_channel)
                        logger.info(f"Re-subscribed to channel {channel}")

                async for message in self._pubsub.listen():
                    if message['type'] == 'message':
                        # Extract channel name from prefixed key
                        channel_key = message['channel'].decode() if isinstance(message['channel'], bytes) else message['channel']
                        channel = channel_key.replace(self._key('channel:'), '')
                        
                        # Call callbacks
                        if channel in self._pubsub_channels:
                            try:
                                raw_data = message['data']
                                if asyncio.iscoroutine(raw_data):
                                    raw_data = await raw_data
                                data = json.loads(raw_data)
                                for callback in self._pubsub_channels[channel]:
                                    await callback(data)
                            except Exception as e:
                                logger.error(f"Error in channel callback: {e}")
            
            except (asyncio.CancelledError, GeneratorExit):
                logger.info("PubSub listener stopping")
                break
            except Exception as e:
                logger.error(f"Error listening to channels: {e}, reconnecting in 5s...")
                self._pubsub = None # Force recreation
                await asyncio.sleep(5)
    
    async def get_keys(self, pattern: str) -> List[str]:
        """Get keys matching pattern"""
        if not self._connected:
            return []
        
        try:
            redis_pattern = self._key(pattern)
            keys = await self.redis.keys(redis_pattern)
            return [k.decode().replace(self._key(''), '') for k in keys]
            
        except Exception as e:
            logger.error(f"Failed to get keys: {e}")
            return []
    
    async def flush_db(self):
        """Flush all data (use with caution!)"""
        if not self._connected:
            return
        
        try:
            # Only flush keys with our prefix
            keys = await self.get_keys("*")
            
            if keys:
                redis_keys = [self._key(k) for k in keys]
                await self.redis.delete(*redis_keys)
            
            logger.info(f"Flushed {len(keys)} keys from Redis")
            
        except Exception as e:
            logger.error(f"Failed to flush database: {e}")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis statistics"""
        if not self._connected:
            return {}
        
        try:
            info = await self.redis.info()
            
            # Count our keys
            our_keys = len(await self.get_keys("*"))
            
            return {
                'connected': self._connected,
                'our_keys': our_keys,
                'used_memory': info.get('used_memory_human', 'unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'ops_per_second': info.get('instantaneous_ops_per_sec', 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}


class DistributedLock:
    """Distributed lock using Redis"""
    
    def __init__(self, redis_store: RedisSessionStore, lock_name: str, timeout_seconds: int = 30):
        self.redis = redis_store
        self.lock_name = lock_name
        self.timeout_seconds = timeout_seconds
        self.lock_key = f"lock:{lock_name}"
        self.lock_value = None
    
    async def acquire(self) -> bool:
        """Acquire lock"""
        if not self.redis._connected:
            return True  # No Redis, allow
        
        try:
            import uuid
            self.lock_value = str(uuid.uuid4())
            
            # Try to set key with NX (only if not exists)
            result = await self.redis.redis.set(
                self.redis._key(self.lock_key),
                self.lock_value,
                ex=self.timeout_seconds,
                nx=True
            )
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Failed to acquire lock {self.lock_name}: {e}")
            return False
    
    async def release(self) -> bool:
        """Release lock"""
        if not self.redis._connected:
            return True
        
        try:
            # Only release if we still own the lock
            current_value = await self.redis.redis.get(self.redis._key(self.lock_key))
            
            if current_value and current_value.decode() == self.lock_value:
                await self.redis.redis.delete(self.redis._key(self.lock_key))
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to release lock {self.lock_name}: {e}")
            return False
    
    async def __aenter__(self):
        """Async context manager entry"""
        acquired = await self.acquire()
        if not acquired:
            raise Exception(f"Failed to acquire lock {self.lock_name}")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.release()


# Global Redis instance
_redis_store: Optional[RedisSessionStore] = None


def get_redis_store() -> Optional[RedisSessionStore]:
    """Get global Redis store"""
    return _redis_store


def init_redis_store(config: RedisConfig = None) -> RedisSessionStore:
    """Initialize global Redis store"""
    global _redis_store
    
    if config is None:
        import os
        config = RedisConfig(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD")
        )
    
    _redis_store = RedisSessionStore(config)
    return _redis_store


async def connect_redis() -> bool:
    """Connect global Redis store"""
    if _redis_store:
        return await _redis_store.connect()
    return False


async def disconnect_redis():
    """Disconnect global Redis store"""
    if _redis_store:
        await _redis_store.disconnect()
