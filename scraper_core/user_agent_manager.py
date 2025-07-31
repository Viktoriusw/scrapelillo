import requests
"""
User Agent Manager for Professional Web Scraper

Manages user agent rotation with multiple strategies and fake-useragent integration.
"""

import random
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import threading

try:
    from fake_useragent import UserAgent
    FAKE_USERAGENT_AVAILABLE = True
except ImportError:
    FAKE_USERAGENT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class UserAgentStats:
    """User agent usage statistics"""
    total_requests: int = 0
    usage_count: Dict[str, int] = field(default_factory=dict)
    last_rotation: Optional[datetime] = None
    rotation_count: int = 0


class UserAgentManager:
    """
    Manages user agent rotation with multiple strategies
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize user agent manager
        
        Args:
            config_manager: Configuration manager instance
        """
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        
        ua_config = self.config.get_section('user_agent')
        self.enabled = ua_config.get('rotation_enabled', True)
        
        if not self.enabled:
            self.user_agents = []
            self.stats = UserAgentStats()
            logger.info("User agent manager disabled")
            return
        
        # Configuration
        self.strategy = ua_config.get('strategy', 'random')
        self.custom_agents = ua_config.get('custom_agents', [])
        
        # User agent storage
        self.user_agents: List[str] = []
        self.current_index = 0
        self.stats = UserAgentStats()
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Load user agents
        self._load_user_agents()
        
        logger.info(f"User agent manager initialized with {len(self.user_agents)} agents")
    
    def _load_user_agents(self):
        """Load user agents from multiple sources"""
        # Default modern user agents
        default_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
        ]
        
        self.user_agents.extend(default_agents)
        
        # Add custom agents from config
        if self.custom_agents:
            self.user_agents.extend(self.custom_agents)
        
        # Try to load from fake-useragent if available
        if FAKE_USERAGENT_AVAILABLE:
            try:
                ua = UserAgent()
                # Get a few random user agents
                for _ in range(5):
                    try:
                        random_ua = ua.random
                        if random_ua and random_ua not in self.user_agents:
                            self.user_agents.append(random_ua)
                    except Exception:
                        continue
                logger.info("Loaded additional user agents from fake-useragent")
            except Exception as e:
                logger.warning(f"Failed to load user agents from fake-useragent: {e}")
        
        # Remove duplicates
        self.user_agents = list(dict.fromkeys(self.user_agents))
        
        # Initialize stats
        for agent in self.user_agents:
            self.stats.usage_count[agent] = 0
    
    def get_user_agent(self) -> str:
        """
        Get next user agent based on rotation strategy
        
        Returns:
            User agent string
        """
        if not self.enabled or not self.user_agents:
            return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        with self._lock:
            if self.strategy == 'round_robin':
                user_agent = self._get_round_robin()
            elif self.strategy == 'random':
                user_agent = self._get_random()
            elif self.strategy == 'weighted':
                user_agent = self._get_weighted()
            else:
                user_agent = self._get_round_robin()
            
            # Update statistics
            self.stats.total_requests += 1
            self.stats.usage_count[user_agent] += 1
            self.stats.rotation_count += 1
            self.stats.last_rotation = datetime.now()
            
            return user_agent
    
    def _get_round_robin(self) -> str:
        """Get user agent using round-robin strategy"""
        user_agent = self.user_agents[self.current_index % len(self.user_agents)]
        self.current_index = (self.current_index + 1) % len(self.user_agents)
        return user_agent
    
    def _get_random(self) -> str:
        """Get user agent using random strategy"""
        return random.choice(self.user_agents)
    
    def _get_weighted(self) -> str:
        """Get user agent using weighted strategy based on usage"""
        if not self.user_agents:
            return self._get_random()
        
        # Calculate weights (less used = higher weight)
        weights = []
        for agent in self.user_agents:
            usage = self.stats.usage_count.get(agent, 0)
            weight = 1.0 / (usage + 1)  # Avoid division by zero
            weights.append(weight)
        
        # Normalize weights
        total_weight = sum(weights)
        if total_weight > 0:
            weights = [w / total_weight for w in weights]
        else:
            weights = [1.0 / len(self.user_agents)] * len(self.user_agents)
        
        # Choose based on weights
        return random.choices(self.user_agents, weights=weights)[0]
    
    def add_user_agent(self, user_agent: str) -> bool:
        """
        Add a new user agent
        
        Args:
            user_agent: User agent string to add
            
        Returns:
            True if added successfully
        """
        if not self.enabled:
            return False
        
        with self._lock:
            if user_agent not in self.user_agents:
                self.user_agents.append(user_agent)
                self.stats.usage_count[user_agent] = 0
                logger.info(f"Added user agent: {user_agent[:50]}...")
                return True
        
        return False
    
    def remove_user_agent(self, user_agent: str) -> bool:
        """
        Remove a user agent
        
        Args:
            user_agent: User agent string to remove
            
        Returns:
            True if removed successfully
        """
        if not self.enabled:
            return False
        
        with self._lock:
            if user_agent in self.user_agents:
                self.user_agents.remove(user_agent)
                if user_agent in self.stats.usage_count:
                    del self.stats.usage_count[user_agent]
                logger.info(f"Removed user agent: {user_agent[:50]}...")
                return True
        
        return False
    
    def get_user_agent_stats(self) -> Dict[str, Any]:
        """
        Get user agent statistics
        
        Returns:
            Dictionary with user agent statistics
        """
        if not self.enabled:
            return {'enabled': False}
        
        with self._lock:
            # Calculate usage percentages
            total_requests = self.stats.total_requests
            usage_percentages = {}
            for agent, count in self.stats.usage_count.items():
                if total_requests > 0:
                    usage_percentages[agent] = (count / total_requests) * 100
                else:
                    usage_percentages[agent] = 0
            
            stats = {
                'enabled': True,
                'total_agents': len(self.user_agents),
                'total_requests': self.stats.total_requests,
                'rotation_strategy': self.strategy,
                'rotation_count': self.stats.rotation_count,
                'last_rotation': self.stats.last_rotation.isoformat() if self.stats.last_rotation else None,
                'usage_count': dict(self.stats.usage_count),
                'usage_percentages': usage_percentages,
                'agents': self.user_agents
            }
        
        return stats
    
    def reset_stats(self):
        """Reset user agent statistics"""
        if not self.enabled:
            return
        
        with self._lock:
            self.stats = UserAgentStats()
            for agent in self.user_agents:
                self.stats.usage_count[agent] = 0
        
        logger.info("User agent statistics reset")
    
    def get_all_user_agents(self) -> List[str]:
        """
        Get list of all user agents
        
        Returns:
            List of user agent strings
        """
        return self.user_agents.copy() 