# Scrapelillo - Web Scraping Framework
# Integración con navegador web

__version__ = "1.0.0"
__author__ = "Scrapelillo Team"

# Importar componentes principales para facilitar el acceso
try:
    from .scraper_core.ethical_scraper import EthicalScraper
    from .scraper_core.html_analyzer import EnhancedHTMLAnalyzer
    from .scraper_core.structured_data_extractor import StructuredDataExtractor
    from .scraper_core.advanced_selectors import AdvancedSelectors
    from .scraper_core.crawler import IntelligentCrawler
    from .scraper_core.config_manager import ConfigManager
    from .scraper_core.metrics import MetricsCollector
    from .scraper_core.plugin_manager import PluginManager
    from .scraper_core.etl_pipeline import ETLPipeline
    from .scraper_core.simple_scheduler import SimpleTaskScheduler
    from .scraper_core.url_discovery import URLDiscoveryEngine
    from .scraper_core.cache_manager import CacheManager
    from .scraper_core.proxy_manager import ProxyManager
    from .scraper_core.user_agent_manager import UserAgentManager
except ImportError as e:
    print(f"Advertencia: No se pudieron importar todos los módulos de Scrapelillo: {e}")

__all__ = [
    'EthicalScraper',
    'EnhancedHTMLAnalyzer', 
    'StructuredDataExtractor',
    'AdvancedSelectors',
    'IntelligentCrawler',
    'ConfigManager',
    'MetricsCollector',
    'PluginManager',
    'ETLPipeline',
    'SimpleTaskScheduler',
    'URLDiscoveryEngine',
    'CacheManager',
    'ProxyManager',
    'UserAgentManager'
] 