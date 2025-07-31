import requests
"""
Intelligent Web Crawler for Professional Web Scraper

Implements intelligent crawling with pagination detection, link discovery,
crawling strategies, and content prioritization.
"""

import logging
import time
import re
from typing import Dict, List, Set, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, parse_qs
from collections import deque, defaultdict
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class CrawlRule:
    """Defines a crawling rule"""
    pattern: str
    follow: bool = True
    extract_data: bool = True
    priority: int = 1
    max_depth: int = 3
    rate_limit: float = 1.0  # seconds between requests


@dataclass
class PageInfo:
    """Information about a crawled page"""
    url: str
    title: str
    content_type: str
    content_length: int
    last_modified: Optional[str] = None
    etag: Optional[str] = None
    links: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    forms: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    crawl_depth: int = 0
    parent_url: Optional[str] = None
    crawl_time: datetime = field(default_factory=datetime.now)


@dataclass
class CrawlResult:
    """Result of a crawling operation"""
    pages: List[PageInfo] = field(default_factory=list)
    total_pages: int = 0
    total_links: int = 0
    total_images: int = 0
    crawl_time: float = 0.0
    errors: List[str] = field(default_factory=list)
    pagination_info: Dict[str, Any] = field(default_factory=dict)


class IntelligentCrawler:
    """
    Intelligent web crawler with pagination detection and link discovery
    """
    
    def __init__(self, config_manager=None, ethical_scraper=None):
        """
        Initialize intelligent crawler
        
        Args:
            config_manager: Configuration manager instance
            ethical_scraper: Ethical scraper instance for making requests
        """
        from .config_manager import ConfigManager
        from .ethical_scraper import EthicalScraper
        
        self.config = config_manager or ConfigManager()
        self.ethical_scraper = ethical_scraper or EthicalScraper()
        
        crawler_config = self.config.get_section('crawler')
        self.enabled = crawler_config.get('enabled', True)
        
        if not self.enabled:
            logger.info("Intelligent crawler disabled")
            return
        
        # Configuration
        self.max_pages = crawler_config.get('max_pages', 100)
        self.max_depth = crawler_config.get('max_depth', 3)
        self.max_concurrent_requests = crawler_config.get('max_concurrent_requests', 5)
        self.request_delay = crawler_config.get('request_delay', 1.0)
        self.follow_redirects = crawler_config.get('follow_redirects', True)
        self.respect_robots_txt = crawler_config.get('respect_robots_txt', True)
        
        # Crawling rules
        self.crawl_rules = self._load_crawl_rules(crawler_config.get('rules', []))
        
        # Pagination detection
        self.pagination_patterns = crawler_config.get('pagination_patterns', [
            r'page=(\d+)',
            r'p=(\d+)',
            r'pagina=(\d+)',
            r'pag=(\d+)',
            r'/page/(\d+)',
            r'/p/(\d+)',
            r'página=(\d+)',
            r'pagina=(\d+)'
        ])
        
        # Link discovery patterns
        self.link_patterns = crawler_config.get('link_patterns', [
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>',
            r'href=["\']([^"\']+)["\']',
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]*>'
        ])
        
        # Content type filters
        self.allowed_content_types = crawler_config.get('allowed_content_types', [
            'text/html',
            'application/xhtml+xml'
        ])
        
        # File extensions to skip
        self.skip_extensions = crawler_config.get('skip_extensions', [
            '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
            '.zip', '.rar', '.tar', '.gz', '.mp3', '.mp4', '.avi',
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg'
        ])
        
        # Crawling state
        self.visited_urls: Set[str] = set()
        self.url_queue: deque = deque()
        self.pages: List[PageInfo] = []
        self.errors: List[str] = []
        self.pagination_info: Dict[str, Any] = {}
        self.base_domain: Optional[str] = None
        
        # Thread safety
        self._lock = threading.Lock()
        self._stop_crawling = False
        
        logger.info("Intelligent crawler initialized")
    
    def _load_crawl_rules(self, rules_config: List[Dict[str, Any]]) -> List[CrawlRule]:
        """Load crawling rules from configuration"""
        rules = []
        
        for rule_config in rules_config:
            rule = CrawlRule(
                pattern=rule_config.get('pattern', ''),
                follow=rule_config.get('follow', True),
                extract_data=rule_config.get('extract_data', True),
                priority=rule_config.get('priority', 1),
                max_depth=rule_config.get('max_depth', 3),
                rate_limit=rule_config.get('rate_limit', 1.0)
            )
            rules.append(rule)
        
        return rules
    
    def crawl(self, start_urls: List[str], strategy: str = "breadth_first") -> CrawlResult:
        """
        Start crawling from given URLs
        
        Args:
            start_urls: List of starting URLs
            strategy: Crawling strategy ('breadth_first', 'depth_first', 'priority')
            
        Returns:
            CrawlResult with crawled pages and statistics
        """
        if not self.enabled:
            return CrawlResult()
        
        import time
        start_time = time.time()
        
        # Reset state
        self.visited_urls.clear()
        self.url_queue.clear()
        self.pages.clear()
        self.errors.clear()
        self.pagination_info.clear()
        self._stop_crawling = False
        
        # Set base domain from first URL
        if start_urls:
            parsed_url = urlparse(start_urls[0])
            self.base_domain = parsed_url.netloc
        
        # Add starting URLs to queue
        for url in start_urls:
            self.url_queue.append((url, 0, None))  # (url, depth, parent_url)
        
        logger.info(f"Starting crawl with {len(start_urls)} starting URLs using {strategy} strategy")
        
        try:
            if strategy == "breadth_first":
                self._crawl_breadth_first()
            elif strategy == "depth_first":
                self._crawl_depth_first()
            elif strategy == "priority":
                self._crawl_priority()
            else:
                logger.warning(f"Unknown strategy '{strategy}', using breadth_first")
                self._crawl_breadth_first()
                
        except Exception as e:
            error_msg = f"Error during crawling: {e}"
            logger.error(error_msg)
            self.errors.append(error_msg)
        
        # Calculate result
        result = CrawlResult(
            pages=self.pages.copy(),
            total_pages=len(self.pages),
            total_links=sum(len(page.links) for page in self.pages),
            total_images=sum(len(page.images) for page in self.pages),
            crawl_time=time.time() - start_time,
            errors=self.errors.copy(),
            pagination_info=self.pagination_info.copy()
        )
        
        logger.info(f"Crawl completed: {result.total_pages} pages, {result.total_links} links, {result.crawl_time:.2f}s")
        
        return result
    
    def _crawl_breadth_first(self):
        """Crawl using breadth-first strategy"""
        with ThreadPoolExecutor(max_workers=self.max_concurrent_requests) as executor:
            futures = []
            
            while self.url_queue and len(self.pages) < self.max_pages and not self._stop_crawling:
                # Get next URL
                url, depth, parent_url = self.url_queue.popleft()
                
                # Check if already visited
                if url in self.visited_urls:
                    continue
                
                # Check depth limit
                if depth > self.max_depth:
                    continue
                
                # Mark as visited
                self.visited_urls.add(url)
                
                # Submit for processing
                future = executor.submit(self._process_page, url, depth, parent_url)
                futures.append(future)
                
                # Rate limiting
                time.sleep(self.request_delay)
            
            # Wait for all futures to complete
            for future in as_completed(futures):
                try:
                    page_info = future.result()
                    if page_info:
                        self.pages.append(page_info)
                except Exception as e:
                    logger.error(f"Error processing page: {e}")
                    self.errors.append(str(e))
    
    def _crawl_depth_first(self):
        """Crawl using depth-first strategy"""
        while self.url_queue and len(self.pages) < self.max_pages and not self._stop_crawling:
            # Get next URL (LIFO for depth-first)
            url, depth, parent_url = self.url_queue.pop()
            
            # Check if already visited
            if url in self.visited_urls:
                continue
            
            # Check depth limit
            if depth > self.max_depth:
                continue
            
            # Mark as visited
            self.visited_urls.add(url)
            
            # Process page
            try:
                page_info = self._process_page(url, depth, parent_url)
                if page_info:
                    self.pages.append(page_info)
            except Exception as e:
                logger.error(f"Error processing page {url}: {e}")
                self.errors.append(str(e))
            
            # Rate limiting
            time.sleep(self.request_delay)
    
    def _crawl_priority(self):
        """Crawl using priority-based strategy"""
        # Sort queue by priority
        priority_queue = []
        
        while self.url_queue and len(priority_queue) < self.max_pages and not self._stop_crawling:
            url, depth, parent_url = self.url_queue.popleft()
            
            # Calculate priority
            priority = self._calculate_url_priority(url, depth)
            priority_queue.append((priority, url, depth, parent_url))
        
        # Sort by priority (highest first)
        priority_queue.sort(key=lambda x: x[0], reverse=True)
        
        # Process in priority order
        with ThreadPoolExecutor(max_workers=self.max_concurrent_requests) as executor:
            futures = []
            
            for priority, url, depth, parent_url in priority_queue:
                if url in self.visited_urls:
                    continue
                
                if depth > self.max_depth:
                    continue
                
                self.visited_urls.add(url)
                
                future = executor.submit(self._process_page, url, depth, parent_url)
                futures.append(future)
                
                time.sleep(self.request_delay)
            
            for future in as_completed(futures):
                try:
                    page_info = future.result()
                    if page_info:
                        self.pages.append(page_info)
                except Exception as e:
                    logger.error(f"Error processing page: {e}")
                    self.errors.append(str(e))
    
    def _calculate_url_priority(self, url: str, depth: int) -> float:
        """Calculate priority for a URL"""
        priority = 1.0
        
        # Depth penalty
        priority -= depth * 0.1
        
        # URL pattern matching
        for rule in self.crawl_rules:
            if re.search(rule.pattern, url):
                priority += rule.priority
        
        # Content type preference
        if any(ext in url.lower() for ext in ['.html', '.htm', '.php', '.asp', '.aspx']):
            priority += 0.5
        
        # Avoid query parameters (usually less important)
        if '?' in url:
            priority -= 0.2
        
        return max(0.0, priority)
    
    def _process_page(self, url: str, depth: int, parent_url: Optional[str]) -> Optional[PageInfo]:
        """Process a single page"""
        try:
            # Check robots.txt
            if self.respect_robots_txt and not self.ethical_scraper.check_robots_txt(url):
                logger.info(f"Skipping {url} (robots.txt)")
                return None
            
            # Get page content
            result = self.ethical_scraper.get_page(url)
            
            # Extract HTML content from result
            if hasattr(result, 'content'):
                html_content = result.content
            elif hasattr(result, 'html'):
                html_content = result.html
            else:
                html_content = str(result)
            
            # Parse HTML
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract page information
            page_info = self._extract_page_info(soup, url, depth, parent_url)
            
            # Discover links
            if depth < self.max_depth:
                new_links = self._discover_links(soup, url)
                for link in new_links:
                    if link not in self.visited_urls:
                        self.url_queue.append((link, depth + 1, url))
            
            # Detect pagination
            pagination_links = self._detect_pagination(soup, url)
            if pagination_links:
                self.pagination_info[url] = pagination_links
            
            return page_info
            
        except Exception as e:
            logger.error(f"Error processing {url}: {e}")
            self.errors.append(f"{url}: {e}")
            return None
    
    def _extract_page_info(self, soup: BeautifulSoup, url: str, depth: int, parent_url: Optional[str]) -> PageInfo:
        """Extract information from a page"""
        # Extract title
        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else ''
        
        # Extract content type
        content_type = 'text/html'
        meta_content_type = soup.find('meta', attrs={'http-equiv': 'Content-Type'})
        if meta_content_type:
            content_type = meta_content_type.get('content', 'text/html')
        
        # Extract content length
        content_length = len(str(soup))
        
        # Extract last modified
        last_modified = None
        meta_modified = soup.find('meta', attrs={'http-equiv': 'Last-Modified'})
        if meta_modified:
            last_modified = meta_modified.get('content')
        
        # Extract ETag
        etag = None
        meta_etag = soup.find('meta', attrs={'http-equiv': 'ETag'})
        if meta_etag:
            etag = meta_etag.get('content')
        
        # Extract links
        links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if href:
                absolute_url = urljoin(url, href)
                links.append(absolute_url)
        
        # Extract images
        images = []
        for img in soup.find_all('img', src=True):
            src = img.get('src')
            if src:
                absolute_url = urljoin(url, src)
                images.append(absolute_url)
        
        # Extract forms
        forms = []
        for form in soup.find_all('form'):
            form_info = {
                'action': form.get('action', ''),
                'method': form.get('method', 'get'),
                'inputs': []
            }
            
            for input_tag in form.find_all('input'):
                input_info = {
                    'name': input_tag.get('name', ''),
                    'type': input_tag.get('type', 'text'),
                    'value': input_tag.get('value', '')
                }
                form_info['inputs'].append(input_info)
            
            forms.append(form_info)
        
        # Extract metadata
        metadata = {}
        for meta in soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            if name and content:
                metadata[name] = content
        
        return PageInfo(
            url=url,
            title=title,
            content_type=content_type,
            content_length=content_length,
            last_modified=last_modified,
            etag=etag,
            links=links,
            images=images,
            forms=forms,
            metadata=metadata,
            crawl_depth=depth,
            parent_url=parent_url
        )
    
    def _discover_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Discover links from page content"""
        links = set()
        
        # Extract links from anchor tags
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if href:
                absolute_url = urljoin(base_url, href)
                if self._should_follow_link(absolute_url):
                    links.add(absolute_url)
        
        # Extract links from link tags
        for link in soup.find_all('link', href=True):
            href = link.get('href')
            if href:
                absolute_url = urljoin(base_url, href)
                if self._should_follow_link(absolute_url):
                    links.add(absolute_url)
        
        return list(links)
    
    def _should_follow_link(self, url: str) -> bool:
        """Check if a link should be followed"""
        # Skip already visited URLs
        if url in self.visited_urls:
            return False
        
        # Skip file extensions
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()
        if any(path.endswith(ext) for ext in self.skip_extensions):
            return False
        
        # Skip external domains (optional) - only if base_domain is set
        if self.base_domain and parsed_url.netloc != self.base_domain:
            return False
        
        # Check crawl rules
        for rule in self.crawl_rules:
            if re.search(rule.pattern, url):
                return rule.follow
        
        return True
    
    def _detect_pagination(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Detect pagination on the page"""
        pagination_info = {
            'current_page': 1,
            'total_pages': None,
            'next_page': None,
            'prev_page': None,
            'pagination_links': []
        }
        
        # Look for pagination patterns in URL
        for pattern in self.pagination_patterns:
            match = re.search(pattern, url)
            if match:
                try:
                    page_num = int(match.group(1))
                    pagination_info['current_page'] = page_num
                    break
                except ValueError:
                    continue
        
        # Look for pagination elements
        pagination_selectors = [
            '.pagination',
            '.pager',
            '.page-numbers',
            '[class*="pagination"]',
            '[class*="pager"]',
            '[class*="page"]'
        ]
        
        for selector in pagination_selectors:
            pagination_elem = soup.select_one(selector)
            if pagination_elem:
                pagination_info['pagination_links'] = self._extract_pagination_links(pagination_elem, url)
                break
        
        # Look for next/prev links
        next_link = soup.find('a', string=re.compile(r'next|siguiente|próximo', re.I))
        if next_link and next_link.get('href'):
            pagination_info['next_page'] = urljoin(url, next_link.get('href'))
        
        prev_link = soup.find('a', string=re.compile(r'prev|anterior|atrás', re.I))
        if prev_link and prev_link.get('href'):
            pagination_info['prev_page'] = urljoin(url, prev_link.get('href'))
        
        return pagination_info
    
    def _extract_pagination_links(self, pagination_elem, base_url: str) -> List[Dict[str, Any]]:
        """Extract pagination links from pagination element"""
        links = []
        
        for link in pagination_elem.find_all('a', href=True):
            href = link.get('href')
            text = link.get_text(strip=True)
            
            if href and text:
                try:
                    page_num = int(text)
                    links.append({
                        'page': page_num,
                        'url': urljoin(base_url, href),
                        'text': text
                    })
                except ValueError:
                    # Not a numeric page
                    continue
        
        return links
    
    def stop_crawling(self):
        """Stop the crawling process"""
        self._stop_crawling = True
        logger.info("Crawling stopped by user request")
    
    def get_crawl_statistics(self) -> Dict[str, Any]:
        """Get crawling statistics"""
        if not self.pages:
            return {}
        
        # Calculate statistics
        total_links = sum(len(page.links) for page in self.pages)
        total_images = sum(len(page.images) for page in self.pages)
        total_forms = sum(len(page.forms) for page in self.pages)
        
        # Content length statistics
        content_lengths = [page.content_length for page in self.pages]
        avg_content_length = sum(content_lengths) / len(content_lengths)
        
        # Depth statistics
        depths = [page.crawl_depth for page in self.pages]
        max_depth = max(depths)
        avg_depth = sum(depths) / len(depths)
        
        # Domain statistics
        domains = defaultdict(int)
        for page in self.pages:
            domain = urlparse(page.url).netloc
            domains[domain] += 1
        
        return {
            'total_pages': len(self.pages),
            'total_links': total_links,
            'total_images': total_images,
            'total_forms': total_forms,
            'avg_content_length': avg_content_length,
            'max_depth': max_depth,
            'avg_depth': avg_depth,
            'domains': dict(domains),
            'errors': len(self.errors),
            'pagination_pages': len(self.pagination_info)
        }
    
    def export_crawl_results(self, file_path: str, format: str = "json") -> bool:
        """
        Export crawl results to file
        
        Args:
            file_path: Path to export file
            format: Export format (json, csv)
            
        Returns:
            True if exported successfully
        """
        try:
            if format.lower() == "json":
                return self._export_crawl_results_json(file_path)
            elif format.lower() == "csv":
                return self._export_crawl_results_csv(file_path)
            else:
                logger.error(f"Unsupported export format: {format}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to export crawl results: {e}")
            return False
    
    def _export_crawl_results_json(self, file_path: str) -> bool:
        """Export crawl results as JSON"""
        try:
            import json
            
            export_data = {
                'crawl_time': datetime.now().isoformat(),
                'statistics': self.get_crawl_statistics(),
                'pages': [
                    {
                        'url': page.url,
                        'title': page.title,
                        'content_type': page.content_type,
                        'content_length': page.content_length,
                        'links': page.links,
                        'images': page.images,
                        'crawl_depth': page.crawl_depth,
                        'parent_url': page.parent_url,
                        'crawl_time': page.crawl_time.isoformat()
                    }
                    for page in self.pages
                ],
                'errors': self.errors,
                'pagination_info': self.pagination_info
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            logger.info(f"Crawl results exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export JSON crawl results: {e}")
            return False
    
    def _export_crawl_results_csv(self, file_path: str) -> bool:
        """Export crawl results as CSV"""
        try:
            import csv
            
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow(['URL', 'Title', 'Content Type', 'Content Length', 'Links Count', 'Images Count', 'Depth', 'Parent URL', 'Crawl Time'])
                
                # Write data
                for page in self.pages:
                    writer.writerow([
                        page.url,
                        page.title,
                        page.content_type,
                        page.content_length,
                        len(page.links),
                        len(page.images),
                        page.crawl_depth,
                        page.parent_url or '',
                        page.crawl_time.isoformat()
                    ])
            
            logger.info(f"Crawl results exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export CSV crawl results: {e}")
            return False 