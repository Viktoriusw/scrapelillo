#!/usr/bin/env python3
"""
A robust web crawler to discover all URLs, endpoints in JavaScript, and brute-force hidden routes on a given website.

Usage:
    python web_crawler.py https://example.com --user-agent "YourBot/1.0" --fuzz-list paths.txt

Dependencies:
    - requests
    - beautifulsoup4

Features:
    - Validates and normalizes the base URL scheme.
    - Handles HTTPS/HTTP fallback and DNS resolution with 'www' prefix.
    - Respects robots.txt with allow-all fallback.
    - Custom User-Agent header support.
    - Configurable request delay and optional max URL limit.
    - Extracts and scans JS files for API endpoints via regex.
    - Brute-force directory/file discovery using a wordlist.
    - Graceful handling of errors and interruption (Ctrl+C).
"""
import argparse
import logging
logger = logging.getLogger(__name__)
import time
import socket
import sys
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from urllib import robotparser

DEFAULT_UA = 'Mozilla/5.0 (compatible; WebCrawler/1.0; +https://github.com/yourusername)'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

class WebCrawler:
    def __init__(self, base_url, delay=1.0, max_urls=None, user_agent=None):
        # Normalize scheme
        parsed = urlparse(base_url)
        if parsed.scheme not in ('http','https'):
            logging.warning(f"Missing scheme, defaulting to http://")
            base_url = 'http://' + base_url.lstrip('/')
            parsed = urlparse(base_url)
        self.scheme = parsed.scheme
        self.domain = parsed.netloc
        # DNS resolution, retry with www prefix
        try:
            socket.gethostbyname(self.domain)
        except socket.gaierror:
            if not self.domain.startswith('www.'):
                alt = 'www.' + self.domain
                try:
                    socket.gethostbyname(alt)
                    logging.info(f"Retrying domain with www: {alt}")
                    self.domain = alt
                except socket.gaierror:
                    logging.error(f"Could not resolve {self.domain} or {alt}. Exiting.")
                    sys.exit(1)
            else:
                logging.error(f"Could not resolve {self.domain}. Exiting.")
                sys.exit(1)
        self.base_url = f"{self.scheme}://{self.domain}".rstrip('/')

        # Queues and storage
        self.visited = set()
        self.to_visit = [self.base_url]
        self.visited_js = set()
        self.discovered_endpoints = set()

        self.delay = delay
        self.max_urls = max_urls

        # Headers
        ua = user_agent or DEFAULT_UA
        self.headers = {'User-Agent': ua}

        # Robots.txt
        self.robots = robotparser.RobotFileParser()
        robots_url = urljoin(self.base_url, '/robots.txt')
        self.robots.set_url(robots_url)
        try:
            self.robots.read()
        except Exception as e:
            logging.warning(f"robots.txt read error at {robots_url}: {e}")
            self.robots = None

    def allowed(self, url):
        if not self.robots:
            return True
        try:
            return self.robots.can_fetch('*', url)
        except Exception:
            return True

    def crawl(self):
        try:
            while self.to_visit:
                current = self.to_visit.pop(0)
                if current in self.visited:
                    continue

                if self.max_urls and len(self.visited) >= self.max_urls:
                    logging.info("Reached max URL limit.")
                    break

                if not self.allowed(current):
                    logging.info(f"Blocked by robots.txt: {current}")
                    self.visited.add(current)
                    continue

                logging.info(f"Crawling: {current}")
                try:
                    resp = requests.get(current, headers=self.headers, timeout=10)
                    resp.raise_for_status()
                except requests.exceptions.RequestException as e:
                    msg = str(e)
                    # HTTPS->HTTP fallback
                    if isinstance(e, requests.exceptions.ConnectionError) and 'getaddrinfo failed' in msg and current.startswith('https://'):
                        fallback = 'http://' + current[len('https://'):]
                        logging.info(f"Retry HTTP: {fallback}")
                        self.to_visit.insert(0, fallback)
                        continue
                    # Skip 403
                    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None and e.response.status_code == 403:
                        logging.warning(f"403 Forbidden: {current}")
                        self.visited.add(current)
                        continue
                    logging.warning(f"Fetch error for {current}: {e}")
                    self.visited.add(current)
                    time.sleep(self.delay)
                    continue

                self.visited.add(current)
                html = resp.text
                self.extract_links(html, current)
                self.scan_js(html, current)
                time.sleep(self.delay)
        except KeyboardInterrupt:
            logging.info("Interrupted by user.")
        return self.visited

    def extract_links(self, html, base):
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup.find_all('a', href=True):
            href = urljoin(base, tag['href'])
            p = urlparse(href)
            if p.scheme in ('http','https') and p.netloc == self.domain:
                norm = p._replace(fragment='').geturl().rstrip('/')
                if norm not in self.visited and norm not in self.to_visit:
                    self.to_visit.append(norm)

    def scan_js(self, html, base):
        soup = BeautifulSoup(html, 'html.parser')
        scripts = [urljoin(base, tag['src']) for tag in soup.find_all('script', src=True)]
        for js_url in scripts:
            p = urlparse(js_url)
            if p.scheme in ('http','https') and p.netloc == self.domain and js_url not in self.visited_js:
                self.visited_js.add(js_url)
                self.fetch_and_scan_js(js_url)

    def fetch_and_scan_js(self, js_url):
        logging.info(f"Fetching JS: {js_url}")
        try:
            r = requests.get(js_url, headers=self.headers, timeout=10)
            r.raise_for_status()
        except Exception as e:
            logging.warning(f"JS fetch error for {js_url}: {e}")
            return
        matches = set(re.findall(r'/api/v\d+/[A-Za-z0-9_\-/]+', r.text))
        for m in matches:
            full = urljoin(self.base_url, m)
            if full not in self.discovered_endpoints:
                self.discovered_endpoints.add(full)
                logging.info(f"Found endpoint: {full}")

    def fuzz(self, wordlist):
        if not os.path.isfile(wordlist):
            logging.error(f"Wordlist not found: {wordlist}")
            return
        logging.info(f"Starting fuzzing with {wordlist}")
        with open(wordlist) as f:
            for line in f:
                path = line.strip()
                if not path or path.startswith('#'):
                    continue
                url = f"{self.base_url}/{path.lstrip('/')}"
                try:
                    resp = requests.head(url, headers=self.headers, allow_redirects=True, timeout=5)
                    code = resp.status_code
                except Exception:
                    continue
                if code < 400:
                    logging.info(f"Fuzz found: {url} ({code})")
                    self.discovered_endpoints.add(url)
        logging.info("Fuzzing complete.")


def main():
    parser = argparse.ArgumentParser(description='Discover URLs, JS endpoints, and fuzz routes')
    parser.add_argument('url', help='Base URL to crawl')
    parser.add_argument('--delay', type=float, default=1.0, help='Seconds between requests')
    parser.add_argument('--max', type=int, default=None, help='Max URLs to crawl')
    parser.add_argument('--user-agent', type=str, default=None, help='Custom User-Agent')
    parser.add_argument('--fuzz-list', type=str, default=None, help='File with paths to fuzz')
    args = parser.parse_args()

    crawler = WebCrawler(args.url, delay=args.delay, max_urls=args.max, user_agent=args.user_agent)
    crawled = crawler.crawl()

    if args.fuzz_list:
        crawler.fuzz(args.fuzz_list)

    logger.info("\nDiscovered URLs:")
    for u in sorted(crawled):
        logger.info(u)
    if crawler.discovered_endpoints:
        logger.info("\nDiscovered Endpoints and Fuzz Results:")
        for e in sorted(crawler.discovered_endpoints):
            logger.info(e)

if __name__ == '__main__':
    main()
