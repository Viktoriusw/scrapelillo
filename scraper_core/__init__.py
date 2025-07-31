"""
Professional Web Scraper Core Package

A comprehensive web scraping framework with advanced features including:
- JavaScript rendering with Playwright
- Proxy and user-agent rotation
- Intelligent caching with change detection
- Asynchronous architecture
- Structured data extraction
- ETL pipelines
- Scheduling and notifications
- Metrics dashboard
- Plugin extensibility
"""

__version__ = "2.0.0"
__author__ = "Professional Web Scraper Team"
__email__ = "support@scraper.com"

from .config_manager import ConfigManager
from .ethical_scraper import EthicalScraper
from .cache_manager import CacheManager
from .proxy_manager import ProxyManager
from .user_agent_manager import UserAgentManager
from .metrics import MetricsCollector
from .structured_data_extractor import StructuredDataExtractor
from .crawler import IntelligentCrawler
from .etl_pipeline import ETLPipeline
from .simple_scheduler import SimpleTaskScheduler
from .plugin_manager import PluginManager
from .html_analyzer import EnhancedHTMLAnalyzer
from .advanced_selectors import AdvancedSelectors

__all__ = [
    "ConfigManager",
    "EthicalScraper", 
    "CacheManager",
    "ProxyManager",
    "UserAgentManager",
    "MetricsCollector",
    "StructuredDataExtractor",
    "IntelligentCrawler",
    "ETLPipeline",
    "SimpleTaskScheduler",
    "PluginManager",
    "EnhancedHTMLAnalyzer",
    "AdvancedSelectors",
] 