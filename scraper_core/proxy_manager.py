"""
Proxy Manager for Professional Web Scraper

Manages proxy loading, rotation, validation, failover, and usage statistics.
Supports multiple sources and rotation strategies.
"""

import os
import time
import random
import logging
import asyncio
import aiohttp
import requests
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import threading
from urllib.parse import urlparse
import json

logger = logging.getLogger(__name__)


@dataclass
class Proxy:
    """Proxy configuration"""
    url: str
    protocol: str
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    country: Optional[str] = None
    speed: Optional[float] = None
    uptime: Optional[float] = None
    last_used: Optional[datetime] = None
    failure_count: int = 0
    last_failure: Optional[datetime] = None
    is_active: bool = True
    
    def __post_init__(self):
        """Parse URL and extract components"""
        if not hasattr(self, 'parsed_url'):
            parsed = urlparse(self.url)
            self.protocol = parsed.scheme
            self.host = parsed.hostname
            self.port = parsed.port or (8080 if self.protocol == 'http' else 1080)
            
            if parsed.username:
                self.username = parsed.username
            if parsed.password:
                self.password = parsed.password
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'url': self.url,
            'protocol': self.protocol,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'country': self.country,
            'speed': self.speed,
            'uptime': self.uptime,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'failure_count': self.failure_count,
            'last_failure': self.last_failure.isoformat() if self.last_failure else None,
            'is_active': self.is_active
        }
    
    def mark_used(self):
        """Mark proxy as used"""
        self.last_used = datetime.now()
    
    def mark_failure(self):
        """Mark proxy as failed"""
        self.failure_count += 1
        self.last_failure = datetime.now()
        
        # Deactivate if too many failures
        max_failures = 3
        if self.failure_count >= max_failures:
            self.is_active = False
            logger.warning(f"Proxy {self.url} deactivated due to {self.failure_count} failures")
    
    def reset_failures(self):
        """Reset failure count"""
        self.failure_count = 0
        self.last_failure = None
        self.is_active = True


@dataclass
class ProxyStats:
    """Proxy usage statistics"""
    total_proxies: int = 0
    active_proxies: int = 0
    failed_proxies: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_rotation: Optional[datetime] = None
    rotation_count: int = 0


class ProxyManager:
    """
    Manages proxy loading, rotation, validation, and failover
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize proxy manager
        
        Args:
            config_manager: Configuration manager instance
        """
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        
        proxy_config = self.config.get_section('proxy')
        self.enabled = proxy_config.get('enabled', True)
        
        if not self.enabled:
            self.proxies = []
            self.stats = ProxyStats()
            logger.info("Proxy manager disabled")
            return
        
        # Configuration
        self.rotation_strategy = proxy_config.get('rotation_strategy', 'round_robin')
        self.timeout = proxy_config.get('timeout', 10)
        self.max_failures = proxy_config.get('max_failures', 3)
        self.validation_url = proxy_config.get('validation_url', 'http://httpbin.org/ip')
        
        # Proxy storage
        self.proxies: List[Proxy] = []
        self.current_index = 0
        self.stats = ProxyStats()
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Load proxies
        self._load_proxies()
        
        logger.info(f"Proxy manager initialized with {len(self.proxies)} proxies")
    
    def _load_proxies(self):
        """Load proxies from configured sources"""
        proxy_config = self.config.get_section('proxy')
        sources = proxy_config.get('sources', [])
        
        for source in sources:
            if isinstance(source, dict):
                if 'file' in source:
                    self._load_from_file(source['file'])
                elif 'env' in source:
                    self._load_from_env(source['env'])
            elif isinstance(source, str):
                # Assume it's a file path
                self._load_from_file(source)
        
        # Load from environment variables if not already loaded
        if not self.proxies:
            self._load_from_env('PROXY_LIST')
        
        # Update stats
        self.stats.total_proxies = len(self.proxies)
        self.stats.active_proxies = len([p for p in self.proxies if p.is_active])
    
    def _load_from_file(self, file_path: str):
        """Load proxies from file"""
        try:
            path = Path(file_path)
            if not path.exists():
                logger.warning(f"Proxy file not found: {file_path}")
                return
            
            with open(path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    
                    try:
                        proxy = self._parse_proxy_line(line)
                        if proxy:
                            self.proxies.append(proxy)
                    except Exception as e:
                        logger.warning(f"Invalid proxy line {line_num} in {file_path}: {e}")
            
            logger.info(f"Loaded {len([p for p in self.proxies if p.url.startswith('file://')])} proxies from {file_path}")
            
        except Exception as e:
            logger.error(f"Error loading proxies from {file_path}: {e}")
    
    def _load_from_env(self, env_var: str):
        """Load proxies from environment variable"""
        proxy_list = os.getenv(env_var)
        if not proxy_list:
            return
        
        # Split by common delimiters
        for delimiter in [',', ';', '\n']:
            if delimiter in proxy_list:
                proxy_urls = proxy_list.split(delimiter)
                break
        else:
            proxy_urls = [proxy_list]
        
        for proxy_url in proxy_urls:
            proxy_url = proxy_url.strip()
            if proxy_url:
                try:
                    proxy = self._parse_proxy_line(proxy_url)
                    if proxy:
                        self.proxies.append(proxy)
                except Exception as e:
                    logger.warning(f"Invalid proxy from env {env_var}: {e}")
        
        logger.info(f"Loaded {len([p for p in self.proxies if p.url.startswith('env://')])} proxies from environment")
    
    def _parse_proxy_line(self, line: str) -> Optional[Proxy]:
        """Parse a proxy line into Proxy object"""
        line = line.strip()
        
        # Handle different formats
        if '://' in line:
            # Full URL format: http://user:pass@host:port
            return Proxy(url=line)
        elif '@' in line:
            # Format: user:pass@host:port
            auth_part, host_part = line.split('@', 1)
            if ':' in auth_part and ':' in host_part:
                username, password = auth_part.split(':', 1)
                host, port = host_part.rsplit(':', 1)
                url = f"http://{username}:{password}@{host}:{port}"
                return Proxy(url=url)
        elif ':' in line:
            # Format: host:port
            host, port = line.rsplit(':', 1)
            url = f"http://{host}:{port}"
            return Proxy(url=url)
        
        return None
    
    def get_proxy(self) -> Optional[Proxy]:
        """
        Get next proxy based on rotation strategy
        
        Returns:
            Proxy object or None if no proxies available
        """
        if not self.enabled or not self.proxies:
            return None
        
        with self._lock:
            active_proxies = [p for p in self.proxies if p.is_active]
            if not active_proxies:
                logger.warning("No active proxies available")
                return None
            
            if self.rotation_strategy == 'round_robin':
                proxy = self._get_round_robin(active_proxies)
            elif self.rotation_strategy == 'random':
                proxy = self._get_random(active_proxies)
            elif self.rotation_strategy == 'weighted':
                proxy = self._get_weighted(active_proxies)
            else:
                proxy = self._get_round_robin(active_proxies)
            
            if proxy:
                proxy.mark_used()
                self.stats.rotation_count += 1
                self.stats.last_rotation = datetime.now()
            
            return proxy
    
    def _get_round_robin(self, active_proxies: List[Proxy]) -> Proxy:
        """Get proxy using round-robin strategy"""
        proxy = active_proxies[self.current_index % len(active_proxies)]
        self.current_index = (self.current_index + 1) % len(active_proxies)
        return proxy
    
    def _get_random(self, active_proxies: List[Proxy]) -> Proxy:
        """Get proxy using random strategy"""
        return random.choice(active_proxies)
    
    def _get_weighted(self, active_proxies: List[Proxy]) -> Proxy:
        """Get proxy using weighted strategy based on speed and uptime"""
        if not active_proxies:
            return None
        
        # Calculate weights based on speed and uptime
        weights = []
        for proxy in active_proxies:
            weight = 1.0
            
            # Factor in speed (higher speed = higher weight)
            if proxy.speed:
                weight *= (proxy.speed / 1000)  # Normalize speed
            
            # Factor in uptime (higher uptime = higher weight)
            if proxy.uptime:
                weight *= (proxy.uptime / 100)  # Normalize uptime
            
            # Factor in failure count (fewer failures = higher weight)
            weight *= max(0.1, 1.0 - (proxy.failure_count * 0.3))
            
            weights.append(weight)
        
        # Normalize weights
        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w / total_weight for w in weights]
        else:
            weights = [1.0 / len(active_proxies)] * len(active_proxies)
        
        # Choose based on weights
        return random.choices(active_proxies, weights=weights)[0]
    
    def mark_proxy_failure(self, proxy: Proxy):
        """Mark a proxy as failed"""
        if not self.enabled:
            return
        
        with self._lock:
            proxy.mark_failure()
            self.stats.failed_requests += 1
            
            # Update stats
            self.stats.active_proxies = len([p for p in self.proxies if p.is_active])
            self.stats.failed_proxies = len([p for p in self.proxies if not p.is_active])
    
    def mark_proxy_success(self, proxy: Proxy):
        """Mark a proxy as successful"""
        if not self.enabled:
            return
        
        with self._lock:
            proxy.reset_failures()
            self.stats.successful_requests += 1
    
    async def validate_proxy(self, proxy: Proxy) -> bool:
        """
        Validate proxy by making a test request
        
        Args:
            proxy: Proxy to validate
            
        Returns:
            True if proxy is working, False otherwise
        """
        if not self.enabled:
            return True
        
        try:
            proxy_dict = {
                'http': proxy.url,
                'https': proxy.url
            }
            
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.validation_url, proxy=proxy.url) as response:
                    if response.status == 200:
                        logger.debug(f"Proxy {proxy.url} validation successful")
                        return True
                    else:
                        logger.warning(f"Proxy {proxy.url} validation failed: status {response.status}")
                        return False
                        
        except Exception as e:
            logger.warning(f"Proxy {proxy.url} validation failed: {e}")
            return False
    
    async def validate_all_proxies(self) -> Dict[str, bool]:
        """
        Validate all proxies
        
        Returns:
            Dictionary mapping proxy URLs to validation results
        """
        if not self.enabled or not self.proxies:
            return {}
        
        results = {}
        tasks = []
        
        # Create validation tasks
        for proxy in self.proxies:
            task = asyncio.create_task(self._validate_proxy_with_result(proxy))
            tasks.append(task)
        
        # Wait for all validations to complete
        validation_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for i, result in enumerate(validation_results):
            proxy = self.proxies[i]
            if isinstance(result, Exception):
                results[proxy.url] = False
                self.mark_proxy_failure(proxy)
            else:
                results[proxy.url] = result
                if result:
                    self.mark_proxy_success(proxy)
                else:
                    self.mark_proxy_failure(proxy)
        
        logger.info(f"Validated {len(self.proxies)} proxies: {sum(results.values())} working")
        return results
    
    async def _validate_proxy_with_result(self, proxy: Proxy) -> bool:
        """Validate proxy and return result"""
        try:
            return await self.validate_proxy(proxy)
        except Exception as e:
            logger.error(f"Error validating proxy {proxy.url}: {e}")
            return False
    
    def add_proxy(self, proxy_url: str, **kwargs) -> bool:
        """
        Add a new proxy
        
        Args:
            proxy_url: Proxy URL
            **kwargs: Additional proxy attributes
            
        Returns:
            True if added successfully
        """
        if not self.enabled:
            return False
        
        try:
            proxy = Proxy(url=proxy_url, **kwargs)
            with self._lock:
                self.proxies.append(proxy)
                self.stats.total_proxies += 1
                self.stats.active_proxies += 1
            
            logger.info(f"Added proxy: {proxy_url}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add proxy {proxy_url}: {e}")
            return False
    
    def remove_proxy(self, proxy_url: str) -> bool:
        """
        Remove a proxy
        
        Args:
            proxy_url: Proxy URL to remove
            
        Returns:
            True if removed successfully
        """
        if not self.enabled:
            return False
        
        with self._lock:
            for i, proxy in enumerate(self.proxies):
                if proxy.url == proxy_url:
                    removed_proxy = self.proxies.pop(i)
                    self.stats.total_proxies -= 1
                    if removed_proxy.is_active:
                        self.stats.active_proxies -= 1
                    else:
                        self.stats.failed_proxies -= 1
                    
                    logger.info(f"Removed proxy: {proxy_url}")
                    return True
        
        return False
    
    def get_proxy_stats(self) -> Dict[str, Any]:
        """
        Get proxy statistics
        
        Returns:
            Dictionary with proxy statistics
        """
        if not self.enabled:
            return {'enabled': False}
        
        with self._lock:
            stats = {
                'enabled': True,
                'total_proxies': self.stats.total_proxies,
                'active_proxies': self.stats.active_proxies,
                'failed_proxies': self.stats.failed_proxies,
                'total_requests': self.stats.total_requests,
                'successful_requests': self.stats.successful_requests,
                'failed_requests': self.stats.failed_requests,
                'success_rate': (self.stats.successful_requests / max(self.stats.total_requests, 1)) * 100,
                'rotation_strategy': self.rotation_strategy,
                'rotation_count': self.stats.rotation_count,
                'last_rotation': self.stats.last_rotation.isoformat() if self.stats.last_rotation else None,
                'proxies': [proxy.to_dict() for proxy in self.proxies]
            }
        
        return stats
    
    def reset_stats(self):
        """Reset proxy statistics"""
        if not self.enabled:
            return
        
        with self._lock:
            self.stats = ProxyStats()
            self.stats.total_proxies = len(self.proxies)
            self.stats.active_proxies = len([p for p in self.proxies if p.is_active])
            self.stats.failed_proxies = len([p for p in self.proxies if not p.is_active])
        
        logger.info("Proxy statistics reset")
    
    def export_proxies(self, file_path: str) -> bool:
        """
        Export proxies to file
        
        Args:
            file_path: Path to export file
            
        Returns:
            True if exported successfully
        """
        if not self.enabled:
            return False
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                for proxy in self.proxies:
                    f.write(f"{proxy.url}\n")
            
            logger.info(f"Exported {len(self.proxies)} proxies to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export proxies to {file_path}: {e}")
            return False
    
    def import_proxies(self, file_path: str) -> bool:
        """
        Import proxies from file
        
        Args:
            file_path: Path to import file
            
        Returns:
            True if imported successfully
        """
        if not self.enabled:
            return False
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.add_proxy(line)
            
            logger.info(f"Imported proxies from {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import proxies from {file_path}: {e}")
            return False 