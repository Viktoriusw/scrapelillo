"""
Cache Manager for Professional Web Scraper

Provides intelligent caching with multiple backends, compression,
TTL management, cleanup, and content change detection.
"""

import sqlite3
import json
import hashlib
import gzip
import base64
import logging
import time
from typing import Dict, Any, Optional, Union, List
from datetime import datetime, timedelta
from pathlib import Path
import pickle
import threading
from dataclasses import dataclass, field
import asyncio

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata"""
    url: str
    content: str
    headers: Dict[str, str]
    content_hash: str
    timestamp: datetime
    ttl: int
    compressed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseCacheBackend:
    """Base class for cache backends"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.compression = config.get('compression', True)
        self.ttl = config.get('ttl', 3600)
        self.hash_algorithm = config.get('hash_algorithm', 'sha256')
    
    def _compress_content(self, content: str) -> str:
        """Compress content using gzip"""
        if not self.compression:
            return content
        
        compressed = gzip.compress(content.encode('utf-8'))
        return base64.b64encode(compressed).decode('utf-8')
    
    def _decompress_content(self, compressed_content: str) -> str:
        """Decompress content using gzip"""
        if not self.compression:
            return compressed_content
        
        try:
            compressed = base64.b64decode(compressed_content.encode('utf-8'))
            return gzip.decompress(compressed).decode('utf-8')
        except Exception as e:
            logger.warning(f"Failed to decompress content: {e}")
            return compressed_content
    
    def _calculate_hash(self, content: str) -> str:
        """Calculate content hash"""
        hash_func = getattr(hashlib, self.hash_algorithm)
        return hash_func(content.encode('utf-8')).hexdigest()
    
    def get(self, url: str) -> Optional[CacheEntry]:
        """Get cached content for URL"""
        raise NotImplementedError
    
    def set(self, url: str, content: str, headers: Dict[str, str], 
            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set cached content for URL"""
        raise NotImplementedError
    
    def delete(self, url: str) -> bool:
        """Delete cached content for URL"""
        raise NotImplementedError
    
    def clear(self) -> bool:
        """Clear all cached content"""
        raise NotImplementedError
    
    def cleanup(self) -> int:
        """Clean up expired entries, return number of cleaned entries"""
        raise NotImplementedError
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        raise NotImplementedError


class SQLiteCacheBackend(BaseCacheBackend):
    """SQLite-based cache backend"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.db_path = config.get('database_path', 'cache.db')
        self._lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database"""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS cache (
                        url TEXT PRIMARY KEY,
                        content TEXT NOT NULL,
                        headers TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        ttl INTEGER NOT NULL,
                        compressed BOOLEAN NOT NULL DEFAULT 0,
                        metadata TEXT
                    )
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_timestamp 
                    ON cache(timestamp)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_content_hash 
                    ON cache(content_hash)
                ''')
                
                conn.commit()
                conn.close()
                logger.info(f"SQLite cache database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize SQLite cache database: {e}")
            raise
    
    def get(self, url: str) -> Optional[CacheEntry]:
        """Get cached content for URL"""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT content, headers, content_hash, timestamp, ttl, compressed, metadata
                    FROM cache WHERE url = ? AND (timestamp + ttl) > ?
                ''', (url, time.time()))
                
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    content, headers_json, content_hash, timestamp, ttl, compressed, metadata_json = row
                    
                    # Decompress if needed
                    if compressed:
                        content = self._decompress_content(content)
                    
                    # Parse JSON fields
                    try:
                        headers = json.loads(headers_json) if headers_json else {}
                        metadata = json.loads(metadata_json) if metadata_json else {}
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse JSON for {url}: {e}")
                        headers = {}
                        metadata = {}
                    
                    return CacheEntry(
                        url=url,
                        content=content,
                        headers=headers,
                        content_hash=content_hash,
                        timestamp=datetime.fromtimestamp(timestamp),
                        ttl=ttl,
                        compressed=compressed,
                        metadata=metadata
                    )
                
                return None
        except Exception as e:
            logger.error(f"Failed to get cache for {url}: {e}")
            return None
    
    def set(self, url: str, content: str, headers: Dict[str, str], 
            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set cached content for URL"""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Compress if enabled
                compressed_content = content
                compressed = False
                if self.compression:
                    compressed_content = self._compress_content(content)
                    compressed = True
                
                # Calculate hash
                content_hash = self._calculate_hash(content)
                
                # Prepare data
                headers_json = json.dumps(headers)
                metadata_json = json.dumps(metadata) if metadata else None
                timestamp = time.time()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO cache 
                    (url, content, headers, content_hash, timestamp, ttl, compressed, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (url, compressed_content, headers_json, content_hash, timestamp, 
                     self.ttl, compressed, metadata_json))
                
                conn.commit()
                conn.close()
                
                logger.debug(f"Cached content for {url}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to cache content for {url}: {e}")
            return False
    
    def delete(self, url: str) -> bool:
        """Delete cached content for URL"""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM cache WHERE url = ?', (url,))
                deleted = cursor.rowcount > 0
                
                conn.commit()
                conn.close()
                
                return deleted
                
        except Exception as e:
            logger.error(f"Failed to delete cache for {url}: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear all cached content"""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM cache')
                deleted_count = cursor.rowcount
                
                conn.commit()
                conn.close()
                
                logger.info(f"Cleared {deleted_count} cache entries")
                return True
                
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
    
    def cleanup(self) -> int:
        """Clean up expired entries"""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('DELETE FROM cache WHERE (timestamp + ttl) <= ?', (time.time(),))
                deleted_count = cursor.rowcount
                
                conn.commit()
                conn.close()
                
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} expired cache entries")
                
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup cache: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                # Total entries
                cursor.execute('SELECT COUNT(*) FROM cache')
                total_entries = cursor.fetchone()[0]
                
                # Expired entries
                cursor.execute('SELECT COUNT(*) FROM cache WHERE (timestamp + ttl) <= ?', (time.time(),))
                expired_entries = cursor.fetchone()[0]
                
                # Compressed entries
                cursor.execute('SELECT COUNT(*) FROM cache WHERE compressed = 1')
                compressed_entries = cursor.fetchone()[0]
                
                # Database size
                cursor.execute('SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()')
                db_size = cursor.fetchone()[0]
                
                conn.close()
                
                return {
                    'total_entries': total_entries,
                    'expired_entries': expired_entries,
                    'compressed_entries': compressed_entries,
                    'database_size_bytes': db_size,
                    'backend': 'sqlite',
                    'database_path': self.db_path
                }
                
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {'error': str(e)}


class RedisCacheBackend(BaseCacheBackend):
    """Redis-based cache backend"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        if not REDIS_AVAILABLE:
            raise ImportError("Redis is not available. Install with: pip install redis")
        
        try:
            self.redis_client = redis.Redis(
                host=config.get('host', 'localhost'),
                port=config.get('port', 6379),
                db=config.get('db', 0),
                password=config.get('password'),
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            
            # Test connection
            self.redis_client.ping()
            logger.info("Redis cache backend initialized")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error initializing Redis: {e}")
            raise
    
    def get(self, url: str) -> Optional[CacheEntry]:
        """Get cached content for URL"""
        try:
            # Get main data
            data = self.redis_client.get(f"cache:{url}")
            if not data:
                return None
            
            # Get metadata
            metadata_key = f"cache_meta:{url}"
            metadata_data = self.redis_client.get(metadata_key)
            
            if metadata_data:
                metadata = json.loads(metadata_data)
            else:
                metadata = {}
            
            # Parse data
            cache_data = json.loads(data)
            
            # Decompress if needed
            content = cache_data['content']
            if cache_data.get('compressed', False):
                content = self._decompress_content(content)
            
            return CacheEntry(
                url=url,
                content=content,
                headers=cache_data['headers'],
                content_hash=cache_data['content_hash'],
                timestamp=datetime.fromtimestamp(cache_data['timestamp']),
                ttl=cache_data['ttl'],
                compressed=cache_data.get('compressed', False),
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Failed to get cache for {url}: {e}")
            return None
    
    def set(self, url: str, content: str, headers: Dict[str, str], 
            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set cached content for URL"""
        try:
            # Compress if enabled
            compressed_content = content
            compressed = False
            if self.compression:
                compressed_content = self._compress_content(content)
                compressed = True
            
            # Calculate hash
            content_hash = self._calculate_hash(content)
            
            # Prepare cache data
            cache_data = {
                'content': compressed_content,
                'headers': headers,
                'content_hash': content_hash,
                'timestamp': time.time(),
                'ttl': self.ttl,
                'compressed': compressed
            }
            
            # Store main data
            self.redis_client.setex(
                f"cache:{url}",
                self.ttl,
                json.dumps(cache_data)
            )
            
            # Store metadata separately
            if metadata:
                self.redis_client.setex(
                    f"cache_meta:{url}",
                    self.ttl,
                    json.dumps(metadata)
                )
            
            logger.debug(f"Cached content for {url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cache content for {url}: {e}")
            return False
    
    def delete(self, url: str) -> bool:
        """Delete cached content for URL"""
        try:
            # Delete main data and metadata
            self.redis_client.delete(f"cache:{url}", f"cache_meta:{url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete cache for {url}: {e}")
            return False
    
    def clear(self) -> bool:
        """Clear all cached content"""
        try:
            # Delete all cache keys
            keys = self.redis_client.keys("cache:*")
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache entries")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
    
    def cleanup(self) -> int:
        """Clean up expired entries (Redis handles TTL automatically)"""
        return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        try:
            info = self.redis_client.info()
            
            # Count cache keys
            cache_keys = self.redis_client.keys("cache:*")
            total_entries = len(cache_keys)
            
            return {
                'total_entries': total_entries,
                'redis_info': {
                    'used_memory': info.get('used_memory', 0),
                    'connected_clients': info.get('connected_clients', 0),
                    'total_commands_processed': info.get('total_commands_processed', 0)
                },
                'backend': 'redis'
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {'error': str(e)}


class MemoryCacheBackend(BaseCacheBackend):
    """In-memory cache backend"""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.cache: Dict[str, CacheEntry] = {}
        self._lock = threading.Lock()
        self.max_size = config.get('max_size', 1000)
    
    def get(self, url: str) -> Optional[CacheEntry]:
        """Get cached content for URL"""
        with self._lock:
            if url not in self.cache:
                return None
            
            entry = self.cache[url]
            
            # Check if expired
            if datetime.now() > entry.timestamp + timedelta(seconds=entry.ttl):
                del self.cache[url]
                return None
            
            return entry
    
    def set(self, url: str, content: str, headers: Dict[str, str], 
            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Set cached content for URL"""
        try:
            with self._lock:
                # Check cache size limit
                if len(self.cache) >= self.max_size:
                    # Remove oldest entry
                    oldest_url = min(self.cache.keys(), 
                                   key=lambda k: self.cache[k].timestamp)
                    del self.cache[oldest_url]
                
                # Compress if enabled
                compressed_content = content
                compressed = False
                if self.compression:
                    compressed_content = self._compress_content(content)
                    compressed = True
                
                # Calculate hash
                content_hash = self._calculate_hash(content)
                
                # Create entry
                entry = CacheEntry(
                    url=url,
                    content=compressed_content,
                    headers=headers,
                    content_hash=content_hash,
                    timestamp=datetime.now(),
                    ttl=self.ttl,
                    compressed=compressed,
                    metadata=metadata or {}
                )
                
                self.cache[url] = entry
                logger.debug(f"Cached content for {url}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to cache content for {url}: {e}")
            return False
    
    def delete(self, url: str) -> bool:
        """Delete cached content for URL"""
        with self._lock:
            if url in self.cache:
                del self.cache[url]
                return True
            return False
    
    def clear(self) -> bool:
        """Clear all cached content"""
        with self._lock:
            deleted_count = len(self.cache)
            self.cache.clear()
            logger.info(f"Cleared {deleted_count} cache entries")
            return True
    
    def cleanup(self) -> int:
        """Clean up expired entries"""
        with self._lock:
            expired_urls = []
            now = datetime.now()
            
            for url, entry in self.cache.items():
                if now > entry.timestamp + timedelta(seconds=entry.ttl):
                    expired_urls.append(url)
            
            for url in expired_urls:
                del self.cache[url]
            
            if expired_urls:
                logger.info(f"Cleaned up {len(expired_urls)} expired cache entries")
            
            return len(expired_urls)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            now = datetime.now()
            expired_count = sum(
                1 for entry in self.cache.values()
                if now > entry.timestamp + timedelta(seconds=entry.ttl)
            )
            
            compressed_count = sum(
                1 for entry in self.cache.values()
                if entry.compressed
            )
            
            return {
                'total_entries': len(self.cache),
                'expired_entries': expired_count,
                'compressed_entries': compressed_count,
                'max_size': self.max_size,
                'backend': 'memory'
            }


class CacheManager:
    """
    Main cache manager that coordinates different backends
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize cache manager
        
        Args:
            config_manager: Configuration manager instance
        """
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        
        cache_config = self.config.get_section('cache')
        self.enabled = cache_config.get('enabled', True)
        
        if not self.enabled:
            self.backend = None
            logger.info("Cache disabled")
            return
        
        # Initialize backend
        backend_type = cache_config.get('backend', 'sqlite')
        
        if backend_type == 'sqlite':
            self.backend = SQLiteCacheBackend(cache_config)
        elif backend_type == 'redis':
            if not REDIS_AVAILABLE:
                logger.warning("Redis not available, falling back to SQLite")
                self.backend = SQLiteCacheBackend(cache_config)
            else:
                self.backend = RedisCacheBackend(cache_config)
        elif backend_type == 'memory':
            self.backend = MemoryCacheBackend(cache_config)
        else:
            logger.warning(f"Unknown cache backend: {backend_type}, using SQLite")
            self.backend = SQLiteCacheBackend(cache_config)
        
        # Setup cleanup
        self.cleanup_interval = cache_config.get('cleanup_interval', 86400)
        self.last_cleanup = time.time()
        
        logger.info(f"Cache manager initialized with {backend_type} backend")
    
    def get_cached_content(self, url: str) -> Optional[CacheEntry]:
        """
        Get cached content for URL
        
        Args:
            url: URL to get cached content for
            
        Returns:
            CacheEntry if found and valid, None otherwise
        """
        if not self.enabled or not self.backend:
            return None
        
        # Check if cleanup is needed
        self._maybe_cleanup()
        
        return self.backend.get(url)
    
    def cache_content(self, url: str, content: str, headers: Dict[str, str], 
                     metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Cache content for URL
        
        Args:
            url: URL to cache content for
            content: Content to cache
            headers: Response headers
            metadata: Additional metadata
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.backend:
            return False
        
        return self.backend.set(url, content, headers, metadata)
    
    def delete_cached_content(self, url: str) -> bool:
        """
        Delete cached content for URL
        
        Args:
            url: URL to delete cached content for
            
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.backend:
            return False
        
        return self.backend.delete(url)
    
    def clear_cache(self) -> bool:
        """
        Clear all cached content
        
        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.backend:
            return False
        
        return self.backend.clear()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics
        
        Returns:
            Dictionary with cache statistics
        """
        if not self.enabled or not self.backend:
            return {'enabled': False}
        
        stats = self.backend.get_stats()
        stats['enabled'] = True
        stats['cleanup_interval'] = self.cleanup_interval
        stats['last_cleanup'] = self.last_cleanup
        
        return stats
    
    def _maybe_cleanup(self):
        """Run cleanup if enough time has passed"""
        if time.time() - self.last_cleanup > self.cleanup_interval:
            self.cleanup()
    
    def cleanup(self) -> int:
        """
        Clean up expired cache entries
        
        Returns:
            Number of cleaned entries
        """
        if not self.enabled or not self.backend:
            return 0
        
        cleaned = self.backend.cleanup()
        self.last_cleanup = time.time()
        return cleaned
    
    def check_content_changed(self, url: str, new_content: str) -> bool:
        """
        Check if content has changed since last cache
        
        Args:
            url: URL to check
            new_content: New content to compare
            
        Returns:
            True if content has changed, False otherwise
        """
        if not self.enabled or not self.backend:
            return True
        
        cached_entry = self.get_cached_content(url)
        if not cached_entry:
            return True
        
        # Calculate hash of new content
        hash_func = getattr(hashlib, self.backend.hash_algorithm)
        new_hash = hash_func(new_content.encode('utf-8')).hexdigest()
        
        return new_hash != cached_entry.content_hash 