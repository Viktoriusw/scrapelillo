import requests
from playwright.async_api import async_playwright
"""
Configuration Manager for Professional Web Scraper

Handles loading and managing configuration from YAML files with environment
variable overrides, validation, and hot-reloading capabilities.
"""

import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class ScraperConfig:
    """Configuration data class for scraper settings"""
    name: str = "ProfessionalWebScraper"
    version: str = "2.0.0"
    debug: bool = False
    log_level: str = "INFO"
    max_workers: int = 10
    timeout: int = 30
    max_retries: int = 3
    retry_delay: int = 1
    exponential_backoff: bool = True


@dataclass
class EthicalConfig:
    """Configuration for ethical scraping settings"""
    respect_robots_txt: bool = True
    rate_limit: bool = True
    requests_per_minute: int = 30
    delay_between_requests: float = 2.0
    user_agent_rotation: bool = True
    proxy_rotation: bool = True
    cache_enabled: bool = True
    cache_ttl: int = 3600


@dataclass
class JavaScriptConfig:
    """Configuration for JavaScript rendering"""
    enabled: bool = True
    engine: str = "playwright"
    headless: bool = True
    wait_for_selectors: list = field(default_factory=list)
    wait_for_timeout: int = 5000
    screenshot_on_error: bool = True
    viewport: Dict[str, int] = field(default_factory=lambda: {"width": 1920, "height": 1080})


@dataclass
class ProxyConfig:
    """Configuration for proxy settings"""
    enabled: bool = True
    rotation_strategy: str = "round_robin"
    timeout: int = 10
    max_failures: int = 3
    sources: list = field(default_factory=list)
    authentication: Dict[str, str] = field(default_factory=dict)


@dataclass
class UserAgentConfig:
    """Configuration for user agent settings"""
    rotation_enabled: bool = True
    strategy: str = "random"
    custom_agents: list = field(default_factory=list)


@dataclass
class CacheConfig:
    """Configuration for caching settings"""
    enabled: bool = True
    backend: str = "sqlite"
    ttl: int = 3600
    compression: bool = True
    cleanup_interval: int = 86400
    max_size: str = "1GB"
    change_detection: bool = True
    hash_algorithm: str = "sha256"


@dataclass
class DatabaseConfig:
    """Configuration for database settings"""
    type: str = "sqlite"
    url: str = "sqlite:///scraper_data.db"
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20


@dataclass
class StructuredDataConfig:
    """Configuration for structured data extraction"""
    enabled: bool = True
    formats: list = field(default_factory=lambda: ["json-ld", "microdata", "rdfa", "microformats"])
    clean_data: bool = True
    validate_schema: bool = True
    filter_by_type: list = field(default_factory=list)
    export_format: str = "json"


@dataclass
class CrawlerConfig:
    """Configuration for crawler settings"""
    enabled: bool = True
    max_depth: int = 3
    max_pages: int = 100
    follow_links: bool = True
    respect_nofollow: bool = True
    allowed_domains: list = field(default_factory=list)
    excluded_patterns: list = field(default_factory=list)
    pagination: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ETLConfig:
    """Configuration for ETL pipeline settings"""
    enabled: bool = True
    batch_size: int = 100
    transform_rules: list = field(default_factory=list)
    validation_rules: list = field(default_factory=list)
    output_formats: list = field(default_factory=lambda: ["json", "csv", "excel", "parquet"])
    data_quality: Dict[str, bool] = field(default_factory=dict)


@dataclass
class SchedulerConfig:
    """Configuration for scheduling settings"""
    enabled: bool = True
    timezone: str = "UTC"
    jobs: list = field(default_factory=list)
    notifications: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricsConfig:
    """Configuration for metrics and monitoring"""
    enabled: bool = True
    collection_interval: int = 60
    retention_days: int = 30
    alerts: Dict[str, Any] = field(default_factory=dict)
    dashboard: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExportConfig:
    """Configuration for export settings"""
    default_format: str = "json"
    compression: bool = True
    include_metadata: bool = True
    timestamp_format: str = "%Y-%m-%d_%H-%M-%S"
    output_directory: str = "exports"


@dataclass
class PluginConfig:
    """Configuration for plugin settings"""
    enabled: bool = True
    directory: str = "plugins"
    auto_load: bool = True
    required_plugins: list = field(default_factory=list)


@dataclass
class TestingConfig:
    """Configuration for testing settings"""
    mock_responses: bool = True
    test_urls: list = field(default_factory=list)
    coverage_threshold: int = 80
    parallel_tests: bool = True


@dataclass
class GUIConfig:
    """Configuration for GUI settings"""
    theme: str = "light"
    window_size: str = "1200x800"
    auto_save: bool = True
    show_advanced_options: bool = False


class ConfigManager:
    """
    Manages configuration loading, validation, and environment overrides
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration manager
        
        Args:
            config_path: Path to the configuration file
        """
        self.config_path = config_path or "config/config.yaml"
        self.config_data: Dict[str, Any] = {}
        self.last_modified: Optional[datetime] = None
        self._load_config()
    
    def _load_config(self) -> None:
        """Load configuration from YAML file"""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                logger.warning(f"Config file {self.config_path} not found, using defaults")
                self._set_defaults()
                return
            
            # Check if file has been modified
            current_mtime = datetime.fromtimestamp(config_file.stat().st_mtime)
            if self.last_modified and current_mtime <= self.last_modified:
                return
            
            with open(config_file, 'r', encoding='utf-8') as f:
                self.config_data = yaml.safe_load(f) or {}
            
            self.last_modified = current_mtime
            self._apply_environment_overrides()
            self._validate_config()
            
            logger.info(f"Configuration loaded from {self.config_path}")
            
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            self._set_defaults()
    
    def _set_defaults(self) -> None:
        """Set default configuration values"""
        self.config_data = {
            "scraper": {
                "name": "ProfessionalWebScraper",
                "version": "2.0.0",
                "debug": False,
                "log_level": "INFO",
                "max_workers": 10,
                "timeout": 30,
                "max_retries": 3,
                "retry_delay": 1,
                "exponential_backoff": True
            },
            "ethical": {
                "respect_robots_txt": True,
                "rate_limit": True,
                "requests_per_minute": 30,
                "delay_between_requests": 2.0,
                "user_agent_rotation": True,
                "proxy_rotation": True,
                "cache_enabled": True,
                "cache_ttl": 3600
            },
            "javascript": {
                "enabled": True,
                "engine": "playwright",
                "headless": True,
                "wait_for_selectors": [],
                "wait_for_timeout": 5000,
                "screenshot_on_error": True,
                "viewport": {"width": 1920, "height": 1080}
            },
            "proxy": {
                "enabled": True,
                "rotation_strategy": "round_robin",
                "timeout": 10,
                "max_failures": 3,
                "sources": [],
                "authentication": {}
            },
            "user_agent": {
                "rotation_enabled": True,
                "strategy": "random",
                "custom_agents": []
            },
            "cache": {
                "enabled": True,
                "backend": "sqlite",
                "ttl": 3600,
                "compression": True,
                "cleanup_interval": 86400,
                "max_size": "1GB",
                "change_detection": True,
                "hash_algorithm": "sha256"
            },
            "database": {
                "type": "sqlite",
                "url": "sqlite:///scraper_data.db",
                "echo": False,
                "pool_size": 10,
                "max_overflow": 20
            },
            "structured_data": {
                "enabled": True,
                "formats": ["json-ld", "microdata", "rdfa", "microformats"],
                "clean_data": True,
                "validate_schema": True,
                "filter_by_type": [],
                "export_format": "json"
            },
            "crawler": {
                "enabled": True,
                "max_depth": 3,
                "max_pages": 100,
                "follow_links": True,
                "respect_nofollow": True,
                "allowed_domains": [],
                "excluded_patterns": ["*.pdf", "*.jpg", "*.png", "mailto:*", "tel:*"],
                "pagination": {
                    "enabled": True,
                    "selectors": [".pagination .next", ".pagination a[rel='next']", "a:contains('Next')"],
                    "max_pages": 10
                }
            },
            "etl": {
                "enabled": True,
                "batch_size": 100,
                "transform_rules": [],
                "validation_rules": [],
                "output_formats": ["json", "csv", "excel", "parquet"],
                "data_quality": {
                    "check_duplicates": True,
                    "validate_required_fields": True,
                    "clean_html": True
                }
            },
            "scheduler": {
                "enabled": True,
                "timezone": "UTC",
                "jobs": [],
                "notifications": {
                    "email": {"enabled": False},
                    "webhook": {"enabled": False}
                }
            },
            "metrics": {
                "enabled": True,
                "collection_interval": 60,
                "retention_days": 30,
                "alerts": {
                    "error_rate_threshold": 0.1,
                    "response_time_threshold": 5000,
                    "cache_hit_rate_threshold": 0.8
                },
                "dashboard": {
                    "enabled": True,
                    "port": 8080,
                    "host": "localhost"
                }
            },
            "export": {
                "default_format": "json",
                "compression": True,
                "include_metadata": True,
                "timestamp_format": "%Y-%m-%d_%H-%M-%S",
                "output_directory": "exports"
            },
            "plugins": {
                "enabled": True,
                "directory": "plugins",
                "auto_load": True,
                "required_plugins": []
            },
            "testing": {
                "mock_responses": True,
                "test_urls": [],
                "coverage_threshold": 80,
                "parallel_tests": True
            },
            "gui": {
                "theme": "light",
                "window_size": "1200x800",
                "auto_save": True,
                "show_advanced_options": False
            },
            "html_analyzer": {
                "enabled": True,
                "enable_semantic_analysis": True,
                "enable_accessibility_checking": True,
                "enable_content_detection": True,
                "min_content_length": 100,
                "max_content_blocks": 10
            }
        }
    
    def _apply_environment_overrides(self) -> None:
        """Apply environment variable overrides to configuration"""
        env_mappings = {
            "SCRAPER_DEBUG": ("scraper", "debug", bool),
            "SCRAPER_LOG_LEVEL": ("scraper", "log_level", str),
            "SCRAPER_MAX_WORKERS": ("scraper", "max_workers", int),
            "SCRAPER_TIMEOUT": ("scraper", "timeout", int),
            "SCRAPER_MAX_RETRIES": ("scraper", "max_retries", int),
            "ETHICAL_RESPECT_ROBOTS": ("ethical", "respect_robots_txt", bool),
            "ETHICAL_RATE_LIMIT": ("ethical", "rate_limit", bool),
            "ETHICAL_REQUESTS_PER_MINUTE": ("ethical", "requests_per_minute", int),
            "ETHICAL_DELAY": ("ethical", "delay_between_requests", float),
            "JAVASCRIPT_ENABLED": ("javascript", "enabled", bool),
            "JAVASCRIPT_ENGINE": ("javascript", "engine", str),
            "JAVASCRIPT_HEADLESS": ("javascript", "headless", bool),
            "PROXY_ENABLED": ("proxy", "enabled", bool),
            "PROXY_STRATEGY": ("proxy", "rotation_strategy", str),
            "CACHE_ENABLED": ("cache", "enabled", bool),
            "CACHE_BACKEND": ("cache", "backend", str),
            "CACHE_TTL": ("cache", "ttl", int),
            "DATABASE_URL": ("database", "url", str),
            "DATABASE_TYPE": ("database", "type", str),
            "METRICS_ENABLED": ("metrics", "enabled", bool),
            "SCHEDULER_ENABLED": ("scheduler", "enabled", bool),
            "PLUGINS_ENABLED": ("plugins", "enabled", bool),
        }
        
        for env_var, (section, key, type_func) in env_mappings.items():
            if env_var in os.environ:
                try:
                    value = os.environ[env_var]
                    if type_func == bool:
                        value = value.lower() in ('true', '1', 'yes', 'on')
                    else:
                        value = type_func(value)
                    
                    if section not in self.config_data:
                        self.config_data[section] = {}
                    self.config_data[section][key] = value
                    logger.debug(f"Override {section}.{key} = {value} from {env_var}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid value for {env_var}: {e}")
    
    def _validate_config(self) -> None:
        """Validate configuration values"""
        validators = {
            "scraper.log_level": lambda x: x in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            "scraper.max_workers": lambda x: isinstance(x, int) and 1 <= x <= 100,
            "scraper.timeout": lambda x: isinstance(x, int) and x > 0,
            "scraper.max_retries": lambda x: isinstance(x, int) and x >= 0,
            "ethical.requests_per_minute": lambda x: isinstance(x, int) and x > 0,
            "ethical.delay_between_requests": lambda x: isinstance(x, (int, float)) and x >= 0,
            "javascript.engine": lambda x: x in ["playwright", "selenium"],
            "proxy.rotation_strategy": lambda x: x in ["round_robin", "random", "weighted"],
            "cache.backend": lambda x: x in ["sqlite", "redis", "memory"],
            "cache.hash_algorithm": lambda x: x in ["md5", "sha1", "sha256", "sha512"],
            "database.type": lambda x: x in ["sqlite", "postgresql", "mysql"],
            "user_agent.strategy": lambda x: x in ["random", "round_robin", "weighted"],
            "metrics.collection_interval": lambda x: isinstance(x, int) and x > 0,
            "crawler.max_depth": lambda x: isinstance(x, int) and 0 <= x <= 10,
            "crawler.max_pages": lambda x: isinstance(x, int) and x > 0,
        }
        
        for path, validator in validators.items():
            try:
                value = self.get_nested(path)
                if value is not None and not validator(value):
                    logger.warning(f"Invalid configuration value for {path}: {value}")
            except Exception as e:
                logger.warning(f"Error validating {path}: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key
        
        Args:
            key: Configuration key (e.g., 'scraper.timeout')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        self._load_config()  # Reload if file changed
        return self.get_nested(key, default)
    
    def get_nested(self, key: str, default: Any = None) -> Any:
        """
        Get nested configuration value using dot notation
        
        Args:
            key: Nested key (e.g., 'scraper.timeout')
            default: Default value if key not found
            
        Returns:
            Configuration value
        """
        keys = key.split('.')
        value = self.config_data
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value
        
        Args:
            key: Configuration key
            value: Value to set
        """
        keys = key.split('.')
        config = self.config_data
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        logger.debug(f"Set configuration {key} = {value}")
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get entire configuration section
        
        Args:
            section: Section name
            
        Returns:
            Section configuration as dictionary
        """
        self._load_config()
        return self.config_data.get(section, {})
    
    def reload(self) -> None:
        """Force reload configuration from file"""
        self.last_modified = None
        self._load_config()
    
    def save(self, path: Optional[str] = None) -> None:
        """
        Save current configuration to file
        
        Args:
            path: Optional path to save to (defaults to original path)
        """
        save_path = path or self.config_path
        
        try:
            # Ensure directory exists
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(save_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config_data, f, default_flow_style=False, indent=2)
            
            logger.info(f"Configuration saved to {save_path}")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
    
    def export_json(self, path: str) -> None:
        """
        Export configuration as JSON
        
        Args:
            path: Path to save JSON file
        """
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=2, default=str)
            logger.info(f"Configuration exported to {path}")
        except Exception as e:
            logger.error(f"Error exporting configuration: {e}")
    
    def get_all(self) -> Dict[str, Any]:
        """
        Get all configuration data
        
        Returns:
            Complete configuration dictionary
        """
        self._load_config()
        return self.config_data.copy()
    
    def __str__(self) -> str:
        """String representation of configuration"""
        return f"ConfigManager(config_path='{self.config_path}')"
    
    def __repr__(self) -> str:
        """Detailed string representation"""
        return f"ConfigManager(config_path='{self.config_path}', sections={list(self.config_data.keys())})" 