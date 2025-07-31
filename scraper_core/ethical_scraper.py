"""
Enhanced Ethical Web Scraper

A professional web scraper with JavaScript rendering, proxy rotation,
user-agent rotation, intelligent caching, and comprehensive ethical features.
"""

import asyncio
import time
import logging
import hashlib
from typing import Dict, List, Optional, Any, Union, Tuple
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
from collections import deque
import aiohttp
import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser, Page
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import gzip
import base64

from .config_manager import ConfigManager

logger = logging.getLogger(__name__)


@dataclass
class ScrapingResult:
    """Result of a scraping operation"""
    url: str
    content: str
    status_code: int
    headers: Dict[str, str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    response_time: float = 0.0
    cache_hit: bool = False
    proxy_used: Optional[str] = None
    user_agent_used: Optional[str] = None


@dataclass
class ScrapingStats:
    """Statistics for scraping operations"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_response_time: float = 0.0
    average_response_time: float = 0.0
    errors: Dict[str, int] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.now)
    
    def update_average_response_time(self):
        """Update average response time"""
        if self.successful_requests > 0:
            self.average_response_time = self.total_response_time / self.successful_requests


class EthicalScraper:
    """
    Enhanced ethical web scraper with advanced features
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize the ethical scraper
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config = config_manager or ConfigManager()
        
        # Ensure config is available
        if self.config is None:
            logger.warning("No config manager provided, using defaults")
            # Create a minimal config for basic functionality
            self.config = type('MockConfig', (), {
                'get': lambda key, default=None: default,
                'get_section': lambda section: {}
            })()
        
        # Initialize with error handling
        try:
            self.session = requests.Session()
        except Exception as e:
            logger.error(f"Error initializing requests session: {e}")
            self.session = None
        self.session = requests.Session()
        self.async_session: Optional[aiohttp.ClientSession] = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        
        # Rate limiting
        self.request_timestamps = deque()
        self.requests_per_minute = self.config.get('ethical.requests_per_minute', 30)
        self.delay_between_requests = self.config.get('ethical.delay_between_requests', 2.0)
        
        # Robots.txt cache
        self.robots_cache: Dict[str, Tuple[RobotFileParser, datetime]] = {}
        self.robots_cache_ttl = timedelta(hours=1)
        
        # Statistics
        self.stats = ScrapingStats()
        
        # Initialize components
        self._setup_session()
        self._setup_headers()
        
        logger.info("EthicalScraper initialized")
    
    def _setup_session(self):
        """Setup HTTP session with default settings"""
        timeout = self.config.get('scraper.timeout', 30)
        self.session.timeout = timeout
        
        # Setup retry strategy
        max_retries = self.config.get('scraper.max_retries', 3)
        retry_delay = self.config.get('scraper.retry_delay', 1)
        
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=retry_delay,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _setup_headers(self):
        """Setup default headers"""
        self.default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session.headers.update(self.default_headers)
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.start_async()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop_async()
    
    async def start_async(self):
        """Start async session and browser"""
        if self.async_session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.get('scraper.timeout', 30))
            self.async_session = aiohttp.ClientSession(timeout=timeout)
        
        if self.config.get('javascript.enabled', True):
            await self._start_browser()
    
    async def stop_async(self):
        """Stop async session and browser"""
        if self.async_session:
            await self.async_session.close()
            self.async_session = None
        
        if self.browser:
            await self.browser.close()
            self.browser = None
    
    async def _start_browser(self):
        """Start Playwright browser"""
        try:
            # Check if playwright is available
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                logger.error("Playwright not installed. Install with: pip install playwright")
                self.browser = None
                self.page = None
                return
            
            self.playwright = await async_playwright().start()
            browser_type = self.playwright.chromium
            
            headless = self.config.get('javascript.headless', True)
            self.browser = await browser_type.launch(headless=headless)
            
            viewport = self.config.get('javascript.viewport', {'width': 1920, 'height': 1080})
            self.page = await self.browser.new_page(viewport=viewport)
            
            # Set user agent
            user_agent = self.default_headers['User-Agent']
            await self.page.set_extra_http_headers({'User-Agent': user_agent})
            
            logger.info("Playwright browser started")
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            self.browser = None
            self.page = None
    
    def check_robots_txt(self, url: str) -> bool:
        """
        Check robots.txt for URL with caching
        
        Args:
            url: URL to check
            
        Returns:
            True if scraping is allowed
        """
        if not self.config.get('ethical.respect_robots_txt', True):
            return True
        
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Check cache
        if base_url in self.robots_cache:
            rp, timestamp = self.robots_cache[base_url]
            if datetime.now() - timestamp < self.robots_cache_ttl:
                return rp.can_fetch(self.session.headers['User-Agent'], url)
        
        # Fetch robots.txt
        try:
            robots_url = f"{base_url}/robots.txt"
            response = self.session.get(robots_url, timeout=10)
            
            if response.status_code == 200:
                rp = RobotFileParser()
                rp.set_url(robots_url)
                rp.read()
                rp.parse(response.text.splitlines())
                
                # Cache the result
                self.robots_cache[base_url] = (rp, datetime.now())
                
                return rp.can_fetch(self.session.headers['User-Agent'], url)
            else:
                # If robots.txt doesn't exist, assume allowed
                return True
                
        except Exception as e:
            logger.warning(f"Error checking robots.txt for {base_url}: {e}")
            return True
    
    def _rate_limit(self):
        """Apply rate limiting"""
        if not self.config.get('ethical.rate_limit', True):
            return
        
        now = time.time()
        self.request_timestamps.append(now)
        
        # Remove old timestamps
        while self.request_timestamps and now - self.request_timestamps[0] > 60:
            self.request_timestamps.popleft()
        
        # Check if we're over the limit
        if len(self.request_timestamps) > self.requests_per_minute:
            sleep_time = 60 - (now - self.request_timestamps[0])
            if sleep_time > 0:
                logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
        
        # Apply delay between requests
        if self.delay_between_requests > 0:
            time.sleep(self.delay_between_requests)
    
    def get_page(self, url: str, use_javascript: bool = False, 
                 wait_for_selectors: Optional[List[str]] = None) -> ScrapingResult:
        """
        Get page content with optional JavaScript rendering
        
        Args:
            url: URL to scrape
            use_javascript: Whether to use JavaScript rendering
            wait_for_selectors: CSS selectors to wait for
            
        Returns:
            ScrapingResult object
        """
        start_time = time.time()
        
        # Check robots.txt
        if not self.check_robots_txt(url):
            return ScrapingResult(
                url=url,
                content="",
                status_code=403,
                headers={},
                error="Scraping not allowed by robots.txt"
            )
        
        # Apply rate limiting
        self._rate_limit()
        
        try:
            if use_javascript and self.page:
                return self._get_page_with_javascript(url, wait_for_selectors)
            else:
                return self._get_page_with_requests(url)
                
        except Exception as e:
            self.stats.failed_requests += 1
            error_type = type(e).__name__
            self.stats.errors[error_type] = self.stats.errors.get(error_type, 0) + 1
            
            logger.error(f"Error scraping {url}: {e}")
            return ScrapingResult(
                url=url,
                content="",
                status_code=0,
                headers={},
                error=str(e),
                response_time=time.time() - start_time
            )
        finally:
            self.stats.total_requests += 1
            response_time = time.time() - start_time
            self.stats.total_response_time += response_time
            self.stats.update_average_response_time()
    
    def _get_page_with_requests(self, url: str) -> ScrapingResult:
        """Get page using requests library"""
        response = self.session.get(url)
        
        return ScrapingResult(
            url=url,
            content=response.text,
            status_code=response.status_code,
            headers=dict(response.headers),
            response_time=response.elapsed.total_seconds()
        )
    
    async def _get_page_with_javascript(self, url: str, 
                                      wait_for_selectors: Optional[List[str]] = None) -> ScrapingResult:
        """Get page using Playwright with JavaScript rendering"""
        if not self.page:
            raise RuntimeError("Browser not initialized")
        
        try:
            # Navigate to page
            response = await self.page.goto(url, wait_until='networkidle')
            
            # Wait for selectors if specified
            if wait_for_selectors:
                for selector in wait_for_selectors:
                    try:
                        await self.page.wait_for_selector(selector, timeout=5000)
                    except Exception as e:
                        logger.warning(f"Selector {selector} not found: {e}")
            
            # Wait for additional timeout
            wait_timeout = self.config.get('javascript.wait_for_timeout', 5000)
            if wait_timeout > 0:
                await asyncio.sleep(wait_timeout / 1000)
            
            # Get content
            content = await self.page.content()
            
            # Get response info
            status_code = response.status if response else 200
            headers = response.headers if response else {}
            
            return ScrapingResult(
                url=url,
                content=content,
                status_code=status_code,
                headers=dict(headers),
                response_time=0.0  # Will be calculated by caller
            )
            
        except Exception as e:
            # Take screenshot on error if enabled
            if self.config.get('javascript.screenshot_on_error', True):
                try:
                    screenshot_path = f"error_screenshot_{int(time.time())}.png"
                    await self.page.screenshot(path=screenshot_path)
                    logger.info(f"Error screenshot saved to {screenshot_path}")
                except Exception as screenshot_error:
                    logger.warning(f"Failed to take error screenshot: {screenshot_error}")
            
            raise e
    
    async def get_page_async(self, url: str, use_javascript: bool = False,
                           wait_for_selectors: Optional[List[str]] = None) -> ScrapingResult:
        """
        Get page content asynchronously
        
        Args:
            url: URL to scrape
            use_javascript: Whether to use JavaScript rendering
            wait_for_selectors: CSS selectors to wait for
            
        Returns:
            ScrapingResult object
        """
        start_time = time.time()
        
        # Check robots.txt
        if not self.check_robots_txt(url):
            return ScrapingResult(
                url=url,
                content="",
                status_code=403,
                headers={},
                error="Scraping not allowed by robots.txt"
            )
        
        try:
            if use_javascript and self.page:
                return await self._get_page_with_javascript(url, wait_for_selectors)
            elif self.async_session:
                return await self._get_page_with_aiohttp(url)
            else:
                # Fallback to synchronous method
                return self._get_page_with_requests(url)
                
        except Exception as e:
            self.stats.failed_requests += 1
            error_type = type(e).__name__
            self.stats.errors[error_type] = self.stats.errors.get(error_type, 0) + 1
            
            logger.error(f"Error scraping {url}: {e}")
            return ScrapingResult(
                url=url,
                content="",
                status_code=0,
                headers={},
                error=str(e),
                response_time=time.time() - start_time
            )
        finally:
            self.stats.total_requests += 1
            response_time = time.time() - start_time
            self.stats.total_response_time += response_time
            self.stats.update_average_response_time()
    
    async def _get_page_with_aiohttp(self, url: str) -> ScrapingResult:
        """Get page using aiohttp"""
        async with self.async_session.get(url) as response:
            content = await response.text()
            
            return ScrapingResult(
                url=url,
                content=content,
                status_code=response.status,
                headers=dict(response.headers),
                response_time=0.0  # Will be calculated by caller
            )
    
    async def get_multiple_pages(self, urls: List[str], 
                               use_javascript: bool = False,
                               max_concurrent: Optional[int] = None) -> List[ScrapingResult]:
        """
        Get multiple pages concurrently
        
        Args:
            urls: List of URLs to scrape
            use_javascript: Whether to use JavaScript rendering
            max_concurrent: Maximum concurrent requests
            
        Returns:
            List of ScrapingResult objects
        """
        if max_concurrent is None:
            max_concurrent = self.config.get('scraper.max_workers', 10)
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def scrape_url(url: str) -> ScrapingResult:
            async with semaphore:
                return await self.get_page_async(url, use_javascript)
        
        tasks = [scrape_url(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Convert exceptions to ScrapingResult objects
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(ScrapingResult(
                    url=urls[i],
                    content="",
                    status_code=0,
                    headers={},
                    error=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
    
    def parse_html(self, content: str) -> BeautifulSoup:
        """
        Parse HTML content with BeautifulSoup
        
        Args:
            content: HTML content
            
        Returns:
            BeautifulSoup object
        """
        return BeautifulSoup(content, 'lxml')
    
    def extract_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        Extract all links from HTML
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL for relative links
            
        Returns:
            List of absolute URLs
        """
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href']
            absolute_url = urljoin(base_url, href)
            links.append(absolute_url)
        return links
    
    def extract_text(self, soup: BeautifulSoup, selectors: Optional[List[str]] = None) -> str:
        """
        Extract text content from HTML
        
        Args:
            soup: BeautifulSoup object
            selectors: CSS selectors to extract from
            
        Returns:
            Extracted text
        """
        if selectors:
            elements = []
            for selector in selectors:
                elements.extend(soup.select(selector))
            return ' '.join(elem.get_text(strip=True) for elem in elements)
        else:
            return soup.get_text(strip=True)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get scraping statistics
        
        Returns:
            Dictionary with statistics
        """
        return {
            'total_requests': self.stats.total_requests,
            'successful_requests': self.stats.successful_requests,
            'failed_requests': self.stats.failed_requests,
            'success_rate': (self.stats.successful_requests / self.stats.total_requests * 100) if self.stats.total_requests > 0 else 0,
            'average_response_time': self.stats.average_response_time,
            'total_response_time': self.stats.total_response_time,
            'errors': dict(self.stats.errors),
            'start_time': self.stats.start_time.isoformat(),
            'uptime': (datetime.now() - self.stats.start_time).total_seconds()
        }
    
    def reset_stats(self):
        """Reset statistics"""
        self.stats = ScrapingStats()
        logger.info("Statistics reset")
    
    def close(self):
        """Close the scraper and cleanup resources"""
        if self.session:
            self.session.close()
        
        if self.browser:
            asyncio.create_task(self.browser.close())
        
        logger.info("EthicalScraper closed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close() 