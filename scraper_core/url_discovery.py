import json
#!/usr/bin/env python3
"""
Módulo de descubrimiento de URLs para Scrapelillo
Basado en el script forcedor.py pero adaptado para integración con la GUI
"""

import logging
import time
import socket
import sys
import os
import re
import threading
from urllib.parse import urljoin, urlparse
from typing import Set, List, Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from urllib import robotparser

logger = logging.getLogger(__name__)

@dataclass
class DiscoveryResult:
    """Resultado del descubrimiento de URLs"""
    base_url: str
    discovered_urls: Set[str]
    discovered_endpoints: Set[str]
    js_files_scanned: Set[str]
    fuzz_results: Dict[str, int]
    start_time: datetime
    end_time: datetime
    total_requests: int
    errors: List[str]
    
    @property
    def duration(self) -> float:
        """Duración del descubrimiento en segundos"""
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def total_discovered(self) -> int:
        """Total de URLs descubiertas"""
        return len(self.discovered_urls) + len(self.discovered_endpoints)

class URLDiscoveryEngine:
    """Motor de descubrimiento de URLs con interfaz para GUI"""
    
    DEFAULT_UA = 'Mozilla/5.0 (compatible; Scrapelillo/1.0; +https://github.com/scrapelillo)'
    
    def __init__(self, 
                 base_url: str, 
                 delay: float = 1.0, 
                 max_urls: Optional[int] = None, 
                 user_agent: Optional[str] = None,
                 timeout: int = 10,
                 max_depth: int = 3):
        """
        Inicializa el motor de descubrimiento
        
        Args:
            base_url: URL base para descubrir
            delay: Delay entre requests en segundos
            max_urls: Máximo número de URLs a descubrir
            user_agent: User-Agent personalizado
            timeout: Timeout para requests
            max_depth: Profundidad máxima de crawling
        """
        self.base_url = self._normalize_url(base_url)
        self.delay = delay
        self.max_urls = max_urls
        self.timeout = timeout
        self.max_depth = max_depth
        
        # Headers
        ua = user_agent or self.DEFAULT_UA
        self.headers = {'User-Agent': ua}
        
        # Estado interno
        self.visited = set()
        self.to_visit = [(self.base_url, 0)]  # (url, depth)
        self.visited_js = set()
        self.discovered_endpoints = set()
        self.fuzz_results = {}
        self.errors = []
        self.total_requests = 0
        
        # Callbacks para GUI
        self.progress_callback: Optional[Callable] = None
        self.url_found_callback: Optional[Callable] = None
        self.endpoint_found_callback: Optional[Callable] = None
        self.error_callback: Optional[Callable] = None
        
        # Control de cancelación
        self._cancel_requested = False
        
        # Robots.txt
        self._setup_robots_txt()
    
    def _normalize_url(self, url: str) -> str:
        """Normaliza la URL base"""
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            logger.warning(f"Missing scheme, defaulting to http://")
            url = 'http://' + url.lstrip('/')
            parsed = urlparse(url)
        
        # DNS resolution, retry with www prefix
        domain = parsed.netloc
        try:
            socket.gethostbyname(domain)
        except socket.gaierror:
            if not domain.startswith('www.'):
                alt = 'www.' + domain
                try:
                    socket.gethostbyname(alt)
                    logger.info(f"Retrying domain with www: {alt}")
                    domain = alt
                except socket.gaierror:
                    raise ValueError(f"Could not resolve {domain} or {alt}")
            else:
                raise ValueError(f"Could not resolve {domain}")
        
        return f"{parsed.scheme}://{domain}".rstrip('/')
    
    def _setup_robots_txt(self):
        """Configura el parser de robots.txt"""
        self.robots = robotparser.RobotFileParser()
        robots_url = urljoin(self.base_url, '/robots.txt')
        self.robots.set_url(robots_url)
        try:
            self.robots.read()
        except Exception as e:
            logger.warning(f"robots.txt read error at {robots_url}: {e}")
            self.robots = None
    
    def allowed(self, url: str) -> bool:
        """Verifica si la URL está permitida por robots.txt"""
        if not self.robots:
            return True
        try:
            return self.robots.can_fetch('*', url)
        except Exception:
            return True
    
    def set_callbacks(self, 
                     progress_callback: Optional[Callable] = None,
                     url_found_callback: Optional[Callable] = None,
                     endpoint_found_callback: Optional[Callable] = None,
                     error_callback: Optional[Callable] = None):
        """Establece callbacks para actualizar la GUI"""
        self.progress_callback = progress_callback
        self.url_found_callback = url_found_callback
        self.endpoint_found_callback = endpoint_found_callback
        self.error_callback = error_callback
    
    def cancel(self):
        """Cancela el descubrimiento"""
        self._cancel_requested = True
    
    def discover(self) -> DiscoveryResult:
        """Ejecuta el descubrimiento de URLs"""
        start_time = datetime.now()
        
        try:
            while self.to_visit and not self._cancel_requested:
                current_url, depth = self.to_visit.pop(0)
                
                if current_url in self.visited:
                    continue
                
                if self.max_urls and len(self.visited) >= self.max_urls:
                    logger.info("Reached max URL limit.")
                    break
                
                if depth > self.max_depth:
                    continue
                
                if not self.allowed(current_url):
                    logger.info(f"Blocked by robots.txt: {current_url}")
                    self.visited.add(current_url)
                    continue
                
                # Callback de progreso
                if self.progress_callback:
                    self.progress_callback(f"Descubriendo: {current_url}", len(self.visited), len(self.discovered_endpoints))
                
                try:
                    resp = requests.get(current_url, headers=self.headers, timeout=self.timeout)
                    resp.raise_for_status()
                    self.total_requests += 1
                except requests.exceptions.RequestException as e:
                    msg = str(e)
                    # HTTPS->HTTP fallback
                    if isinstance(e, requests.exceptions.ConnectionError) and 'getaddrinfo failed' in msg and current_url.startswith('https://'):
                        fallback = 'http://' + current_url[len('https://'):]
                        logger.info(f"Retry HTTP: {fallback}")
                        self.to_visit.insert(0, (fallback, depth))
                        continue
                    # Skip 403
                    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None and e.response.status_code == 403:
                        logger.warning(f"403 Forbidden: {current_url}")
                        self.visited.add(current_url)
                        continue
                    
                    error_msg = f"Fetch error for {current_url}: {e}"
                    logger.warning(error_msg)
                    self.errors.append(error_msg)
                    if self.error_callback:
                        self.error_callback(current_url, str(e))
                    
                    self.visited.add(current_url)
                    time.sleep(self.delay)
                    continue
                
                self.visited.add(current_url)
                
                # Callback de URL encontrada
                if self.url_found_callback:
                    self.url_found_callback(current_url, depth)
                
                html = resp.text
                self._extract_links(html, current_url, depth)
                self._scan_js(html, current_url)
                time.sleep(self.delay)
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user.")
        
        end_time = datetime.now()
        
        return DiscoveryResult(
            base_url=self.base_url,
            discovered_urls=self.visited.copy(),
            discovered_endpoints=self.discovered_endpoints.copy(),
            js_files_scanned=self.visited_js.copy(),
            fuzz_results=self.fuzz_results.copy(),
            start_time=start_time,
            end_time=end_time,
            total_requests=self.total_requests,
            errors=self.errors.copy()
        )
    
    def _extract_links(self, html: str, base_url: str, current_depth: int):
        """Extrae enlaces de la página HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup.find_all('a', href=True):
            href = urljoin(base_url, tag['href'])
            p = urlparse(href)
            if p.scheme in ('http', 'https') and p.netloc == urlparse(self.base_url).netloc:
                norm = p._replace(fragment='').geturl().rstrip('/')
                if norm not in self.visited and norm not in [url for url, _ in self.to_visit]:
                    self.to_visit.append((norm, current_depth + 1))
    
    def _scan_js(self, html: str, base_url: str):
        """Escanea archivos JavaScript en busca de endpoints"""
        soup = BeautifulSoup(html, 'html.parser')
        scripts = [urljoin(base_url, tag['src']) for tag in soup.find_all('script', src=True)]
        
        for js_url in scripts:
            p = urlparse(js_url)
            if p.scheme in ('http', 'https') and p.netloc == urlparse(self.base_url).netloc and js_url not in self.visited_js:
                self.visited_js.add(js_url)
                self._fetch_and_scan_js(js_url)
    
    def _fetch_and_scan_js(self, js_url: str):
        """Obtiene y escanea un archivo JavaScript"""
        logger.info(f"Fetching JS: {js_url}")
        try:
            r = requests.get(js_url, headers=self.headers, timeout=self.timeout)
            r.raise_for_status()
            self.total_requests += 1
        except Exception as e:
            error_msg = f"JS fetch error for {js_url}: {e}"
            logger.warning(error_msg)
            self.errors.append(error_msg)
            return
        
        # Patrones para encontrar endpoints
        patterns = [
            r'/api/v\d+/[A-Za-z0-9_\-/]+',
            r'/api/[A-Za-z0-9_\-/]+',
            r'/v\d+/[A-Za-z0-9_\-/]+',
            r'/[a-z]+/[A-Za-z0-9_\-/]+\.(json|xml|html)',
            r'/[A-Za-z0-9_\-/]+\.(json|xml|html)'
        ]
        
        for pattern in patterns:
            matches = set(re.findall(pattern, r.text))
            for match in matches:
                if isinstance(match, tuple):
                    match = ''.join(match)
                full = urljoin(self.base_url, match)
                if full not in self.discovered_endpoints:
                    self.discovered_endpoints.add(full)
                    if self.endpoint_found_callback:
                        self.endpoint_found_callback(full)
                    logger.info(f"Found endpoint: {full}")
    
    def fuzz(self, wordlist_path: str) -> Dict[str, int]:
        """Ejecuta fuzzing de directorios/archivos"""
        if not os.path.isfile(wordlist_path):
            error_msg = f"Wordlist not found: {wordlist_path}"
            logger.error(error_msg)
            self.errors.append(error_msg)
            return {}
        
        logger.info(f"Starting fuzzing with {wordlist_path}")
        fuzz_results = {}
        
        with open(wordlist_path) as f:
            for line_num, line in enumerate(f, 1):
                if self._cancel_requested:
                    break
                
                path = line.strip()
                if not path or path.startswith('#'):
                    continue
                
                url = f"{self.base_url}/{path.lstrip('/')}"
                
                # Callback de progreso
                if self.progress_callback and line_num % 10 == 0:
                    self.progress_callback(f"Fuzzing: {path}", len(self.visited), len(self.discovered_endpoints))
                
                try:
                    resp = requests.head(url, headers=self.headers, allow_redirects=True, timeout=5)
                    code = resp.status_code
                    self.total_requests += 1
                except Exception as e:
                    continue
                
                if code < 400:
                    fuzz_results[url] = code
                    if self.endpoint_found_callback:
                        self.endpoint_found_callback(url)
                    logger.info(f"Fuzz found: {url} ({code})")
        
        self.fuzz_results = fuzz_results
        logger.info("Fuzzing complete.")
        return fuzz_results 