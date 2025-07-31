import requests
"""
Metrics Collector for Professional Web Scraper

Collects detailed scraping metrics for requests, cache, errors, performance,
with alerts, export, and persistence capabilities.
"""

import time
import json
import logging
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
import threading
import sqlite3
from collections import defaultdict, deque
import statistics

logger = logging.getLogger(__name__)


@dataclass
class RequestMetrics:
    """Metrics for individual requests"""
    url: str
    method: str
    status_code: int
    response_time: float
    content_length: int
    timestamp: datetime
    cache_hit: bool = False
    error: Optional[str] = None
    proxy_used: Optional[str] = None
    user_agent_used: Optional[str] = None


@dataclass
class CacheMetrics:
    """Cache performance metrics"""
    hits: int = 0
    misses: int = 0
    total_requests: int = 0
    hit_rate: float = 0.0
    avg_response_time: float = 0.0
    total_size_bytes: int = 0


@dataclass
class ErrorMetrics:
    """Error tracking metrics"""
    total_errors: int = 0
    error_types: Dict[str, int] = field(default_factory=dict)
    error_urls: Dict[str, int] = field(default_factory=dict)
    last_error: Optional[datetime] = None


@dataclass
class PerformanceMetrics:
    """Performance tracking metrics"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    avg_response_time: float = 0.0
    min_response_time: float = float('inf')
    max_response_time: float = 0.0
    response_times: List[float] = field(default_factory=list)
    requests_per_minute: float = 0.0
    start_time: datetime = field(default_factory=datetime.now)


@dataclass
class AlertThresholds:
    """Alert threshold configuration"""
    error_rate_threshold: float = 0.1  # 10%
    response_time_threshold: float = 5.0  # 5 seconds
    cache_hit_rate_threshold: float = 0.8  # 80%
    requests_per_minute_threshold: int = 100


class MetricsCollector:
    """
    Collects and manages comprehensive scraping metrics
    """
    
    def __init__(self, config_manager=None, db_path: str = "metrics.db"):
        """
        Initialize metrics collector
        
        Args:
            config_manager: Configuration manager instance
            db_path: Path to SQLite database for metrics storage
        """
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        
        metrics_config = self.config.get_section('metrics')
        self.enabled = metrics_config.get('enabled', True)
        
        if not self.enabled:
            logger.info("Metrics collector disabled")
            return
        
        # Configuration
        self.collection_interval = metrics_config.get('collection_interval', 60)
        self.retention_days = metrics_config.get('retention_days', 30)
        self.db_path = db_path
        
        # Alert thresholds
        alerts_config = metrics_config.get('alerts', {})
        self.alert_thresholds = AlertThresholds(
            error_rate_threshold=alerts_config.get('error_rate_threshold', 0.1),
            response_time_threshold=alerts_config.get('response_time_threshold', 5000) / 1000,  # Convert to seconds
            cache_hit_rate_threshold=alerts_config.get('cache_hit_rate_threshold', 0.8)
        )
        
        # Metrics storage
        self.requests: List[RequestMetrics] = []
        self.cache_metrics = CacheMetrics()
        self.error_metrics = ErrorMetrics()
        self.performance_metrics = PerformanceMetrics()
        
        # Rolling window for recent metrics
        self.recent_requests = deque(maxlen=1000)
        self.recent_errors = deque(maxlen=100)
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Initialize database
        self._init_database()
        
        # Start background cleanup
        self._start_cleanup_thread()
        
        logger.info("Metrics collector initialized")
    
    def _init_database(self):
        """Initialize SQLite database for metrics storage"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS request_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    response_time REAL NOT NULL,
                    content_length INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    cache_hit BOOLEAN NOT NULL DEFAULT 0,
                    error TEXT,
                    proxy_used TEXT,
                    user_agent_used TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hits INTEGER NOT NULL,
                    misses INTEGER NOT NULL,
                    total_requests INTEGER NOT NULL,
                    hit_rate REAL NOT NULL,
                    avg_response_time REAL NOT NULL,
                    total_size_bytes INTEGER NOT NULL,
                    timestamp TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS error_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT NOT NULL,
                    error_count INTEGER NOT NULL,
                    url TEXT,
                    timestamp TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    total_requests INTEGER NOT NULL,
                    successful_requests INTEGER NOT NULL,
                    failed_requests INTEGER NOT NULL,
                    avg_response_time REAL NOT NULL,
                    min_response_time REAL NOT NULL,
                    max_response_time REAL NOT NULL,
                    requests_per_minute REAL NOT NULL,
                    timestamp TEXT NOT NULL
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_request_timestamp ON request_metrics(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_request_url ON request_metrics(url)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_error_timestamp ON error_metrics(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON performance_metrics(timestamp)')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize metrics database: {e}")
    
    def record_request(self, url: str, method: str = "GET", status_code: int = 200,
                      response_time: float = 0.0, content_length: int = 0,
                      cache_hit: bool = False, error: Optional[str] = None,
                      proxy_used: Optional[str] = None, user_agent_used: Optional[str] = None):
        """
        Record a request metric
        
        Args:
            url: Request URL
            method: HTTP method
            status_code: Response status code
            response_time: Response time in seconds
            content_length: Content length in bytes
            cache_hit: Whether it was a cache hit
            error: Error message if any
            proxy_used: Proxy used for request
            user_agent_used: User agent used for request
        """
        if not self.enabled:
            return
        
        timestamp = datetime.now()
        
        with self._lock:
            # Create request metric
            request_metric = RequestMetrics(
                url=url,
                method=method,
                status_code=status_code,
                response_time=response_time,
                content_length=content_length,
                timestamp=timestamp,
                cache_hit=cache_hit,
                error=error,
                proxy_used=proxy_used,
                user_agent_used=user_agent_used
            )
            
            # Add to storage
            self.requests.append(request_metric)
            self.recent_requests.append(request_metric)
            
            # Update cache metrics
            if cache_hit:
                self.cache_metrics.hits += 1
            else:
                self.cache_metrics.misses += 1
            
            self.cache_metrics.total_requests += 1
            self.cache_metrics.hit_rate = self.cache_metrics.hits / max(self.cache_metrics.total_requests, 1)
            
            # Update error metrics
            if error:
                self.error_metrics.total_errors += 1
                self.error_metrics.error_types[error] = self.error_metrics.error_types.get(error, 0) + 1
                self.error_metrics.error_urls[url] = self.error_metrics.error_urls.get(url, 0) + 1
                self.error_metrics.last_error = timestamp
                self.recent_errors.append((error, url, timestamp))
            
            # Update performance metrics
            self.performance_metrics.total_requests += 1
            if status_code < 400 and not error:
                self.performance_metrics.successful_requests += 1
            else:
                self.performance_metrics.failed_requests += 1
            
            self.performance_metrics.response_times.append(response_time)
            self.performance_metrics.avg_response_time = statistics.mean(self.performance_metrics.response_times)
            self.performance_metrics.min_response_time = min(self.performance_metrics.min_response_time, response_time)
            self.performance_metrics.max_response_time = max(self.performance_metrics.max_response_time, response_time)
            
            # Calculate requests per minute
            elapsed = (timestamp - self.performance_metrics.start_time).total_seconds() / 60
            if elapsed > 0:
                self.performance_metrics.requests_per_minute = self.performance_metrics.total_requests / elapsed
            
            # Store in database
            self._store_request_metric(request_metric)
            
            # Check alerts
            self._check_alerts()
    
    def _store_request_metric(self, metric: RequestMetrics):
        """Store request metric in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO request_metrics 
                (url, method, status_code, response_time, content_length, timestamp, 
                 cache_hit, error, proxy_used, user_agent_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metric.url, metric.method, metric.status_code, metric.response_time,
                metric.content_length, metric.timestamp.isoformat(), metric.cache_hit,
                metric.error, metric.proxy_used, metric.user_agent_used
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to store request metric: {e}")
    
    def _check_alerts(self):
        """Check for alert conditions"""
        try:
            # Error rate alert
            if self.performance_metrics.total_requests > 0:
                error_rate = self.error_metrics.total_errors / self.performance_metrics.total_requests
                if error_rate > self.alert_thresholds.error_rate_threshold:
                    self._trigger_alert("HIGH_ERROR_RATE", f"Error rate {error_rate:.2%} exceeds threshold {self.alert_thresholds.error_rate_threshold:.2%}")
            
            # Response time alert
            if self.performance_metrics.avg_response_time > self.alert_thresholds.response_time_threshold:
                self._trigger_alert("HIGH_RESPONSE_TIME", f"Average response time {self.performance_metrics.avg_response_time:.2f}s exceeds threshold {self.alert_thresholds.response_time_threshold:.2f}s")
            
            # Cache hit rate alert
            if self.cache_metrics.total_requests > 0:
                cache_hit_rate = self.cache_metrics.hit_rate
                if cache_hit_rate < self.alert_thresholds.cache_hit_rate_threshold:
                    self._trigger_alert("LOW_CACHE_HIT_RATE", f"Cache hit rate {cache_hit_rate:.2%} below threshold {self.alert_thresholds.cache_hit_rate_threshold:.2%}")
            
            # Requests per minute alert
            if self.performance_metrics.requests_per_minute > self.alert_thresholds.requests_per_minute_threshold:
                self._trigger_alert("HIGH_REQUEST_RATE", f"Request rate {self.performance_metrics.requests_per_minute:.1f}/min exceeds threshold {self.alert_thresholds.requests_per_minute_threshold}/min")
                
        except Exception as e:
            logger.error(f"Error checking alerts: {e}")
    
    def _trigger_alert(self, alert_type: str, message: str):
        """Trigger an alert"""
        logger.warning(f"ALERT [{alert_type}]: {message}")
        # TODO: Implement alert notifications (email, webhook, etc.)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive metrics summary
        
        Returns:
            Dictionary with all metrics
        """
        if not self.enabled:
            return {'enabled': False}
        
        with self._lock:
            # Calculate additional metrics
            success_rate = (self.performance_metrics.successful_requests / 
                          max(self.performance_metrics.total_requests, 1))
            
            # Get recent activity (last hour)
            now = datetime.now()
            one_hour_ago = now - timedelta(hours=1)
            recent_requests = [r for r in self.recent_requests if r.timestamp > one_hour_ago]
            recent_errors = [e for e in self.recent_errors if e[2] > one_hour_ago]
            
            # Top URLs by requests
            url_counts = defaultdict(int)
            for req in self.requests:
                url_counts[req.url] += 1
            top_urls = sorted(url_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            
            # Top error types
            top_errors = sorted(self.error_metrics.error_types.items(), 
                              key=lambda x: x[1], reverse=True)[:5]
            
            summary = {
                'enabled': True,
                'performance': {
                    'total_requests': self.performance_metrics.total_requests,
                    'successful_requests': self.performance_metrics.successful_requests,
                    'failed_requests': self.performance_metrics.failed_requests,
                    'success_rate': success_rate,
                    'avg_response_time': self.performance_metrics.avg_response_time,
                    'min_response_time': self.performance_metrics.min_response_time,
                    'max_response_time': self.performance_metrics.max_response_time,
                    'requests_per_minute': self.performance_metrics.requests_per_minute,
                    'start_time': self.performance_metrics.start_time.isoformat(),
                    'uptime_hours': (now - self.performance_metrics.start_time).total_seconds() / 3600
                },
                'cache': {
                    'hits': self.cache_metrics.hits,
                    'misses': self.cache_metrics.misses,
                    'total_requests': self.cache_metrics.total_requests,
                    'hit_rate': self.cache_metrics.hit_rate,
                    'avg_response_time': self.cache_metrics.avg_response_time,
                    'total_size_bytes': self.cache_metrics.total_size_bytes
                },
                'errors': {
                    'total_errors': self.error_metrics.total_errors,
                    'error_types': dict(self.error_metrics.error_types),
                    'error_urls': dict(self.error_metrics.error_urls),
                    'last_error': self.error_metrics.last_error.isoformat() if self.error_metrics.last_error else None,
                    'top_errors': top_errors
                },
                'recent_activity': {
                    'requests_last_hour': len(recent_requests),
                    'errors_last_hour': len(recent_errors),
                    'avg_response_time_last_hour': statistics.mean([r.response_time for r in recent_requests]) if recent_requests else 0
                },
                'top_urls': top_urls,
                'alerts': {
                    'error_rate_threshold': self.alert_thresholds.error_rate_threshold,
                    'response_time_threshold': self.alert_thresholds.response_time_threshold,
                    'cache_hit_rate_threshold': self.alert_thresholds.cache_hit_rate_threshold,
                    'requests_per_minute_threshold': self.alert_thresholds.requests_per_minute_threshold
                }
            }
        
        return summary
    
    def export_metrics(self, file_path: str, format: str = "json") -> bool:
        """
        Export metrics to file
        
        Args:
            file_path: Path to export file
            format: Export format (json, csv)
            
        Returns:
            True if exported successfully
        """
        if not self.enabled:
            return False
        
        try:
            if format.lower() == "json":
                return self._export_json(file_path)
            elif format.lower() == "csv":
                return self._export_csv(file_path)
            else:
                logger.error(f"Unsupported export format: {format}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return False
    
    def _export_json(self, file_path: str) -> bool:
        """Export metrics as JSON"""
        try:
            summary = self.get_metrics_summary()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, default=str)
            
            logger.info(f"Metrics exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export JSON metrics: {e}")
            return False
    
    def _export_csv(self, file_path: str) -> bool:
        """Export metrics as CSV"""
        try:
            import csv
            
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow(['Metric', 'Value'])
                
                # Write metrics
                summary = self.get_metrics_summary()
                
                # Performance metrics
                writer.writerow(['Total Requests', summary['performance']['total_requests']])
                writer.writerow(['Successful Requests', summary['performance']['successful_requests']])
                writer.writerow(['Failed Requests', summary['performance']['failed_requests']])
                writer.writerow(['Success Rate', f"{summary['performance']['success_rate']:.2%}"])
                writer.writerow(['Average Response Time', f"{summary['performance']['avg_response_time']:.2f}s"])
                writer.writerow(['Requests per Minute', f"{summary['performance']['requests_per_minute']:.1f}"])
                
                # Cache metrics
                writer.writerow(['Cache Hits', summary['cache']['hits']])
                writer.writerow(['Cache Misses', summary['cache']['misses']])
                writer.writerow(['Cache Hit Rate', f"{summary['cache']['hit_rate']:.2%}"])
                
                # Error metrics
                writer.writerow(['Total Errors', summary['errors']['total_errors']])
                
            logger.info(f"Metrics exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export CSV metrics: {e}")
            return False
    
    def reset_metrics(self):
        """Reset all metrics"""
        if not self.enabled:
            return
        
        with self._lock:
            self.requests.clear()
            self.recent_requests.clear()
            self.recent_errors.clear()
            self.cache_metrics = CacheMetrics()
            self.error_metrics = ErrorMetrics()
            self.performance_metrics = PerformanceMetrics()
        
        logger.info("Metrics reset")
    
    def _start_cleanup_thread(self):
        """Start background thread for cleaning old metrics"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(self.collection_interval)
                    self._cleanup_old_metrics()
                except Exception as e:
                    logger.error(f"Error in metrics cleanup: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.info("Metrics cleanup thread started")
    
    def _cleanup_old_metrics(self):
        """Clean up old metrics from database"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Delete old request metrics
            cursor.execute('DELETE FROM request_metrics WHERE timestamp < ?', 
                         (cutoff_date.isoformat(),))
            
            # Delete old error metrics
            cursor.execute('DELETE FROM error_metrics WHERE timestamp < ?', 
                         (cutoff_date.isoformat(),))
            
            # Delete old performance metrics
            cursor.execute('DELETE FROM performance_metrics WHERE timestamp < ?', 
                         (cutoff_date.isoformat(),))
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Cleaned up metrics older than {self.retention_days} days")
            
        except Exception as e:
            logger.error(f"Error cleaning up old metrics: {e}")
    
    def get_metrics_for_period(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """
        Get metrics for a specific time period
        
        Args:
            start_date: Start of period
            end_date: End of period
            
        Returns:
            Dictionary with metrics for the period
        """
        if not self.enabled:
            return {'enabled': False}
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get request metrics for period
            cursor.execute('''
                SELECT * FROM request_metrics 
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp
            ''', (start_date.isoformat(), end_date.isoformat()))
            
            requests = cursor.fetchall()
            
            # Calculate period metrics
            total_requests = len(requests)
            successful_requests = len([r for r in requests if r[3] < 400])
            failed_requests = total_requests - successful_requests
            response_times = [r[4] for r in requests]
            avg_response_time = statistics.mean(response_times) if response_times else 0
            
            conn.close()
            
            return {
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'total_requests': total_requests,
                    'successful_requests': successful_requests,
                    'failed_requests': failed_requests,
                    'success_rate': successful_requests / max(total_requests, 1),
                    'avg_response_time': avg_response_time,
                    'min_response_time': min(response_times) if response_times else 0,
                    'max_response_time': max(response_times) if response_times else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting metrics for period: {e}")
            return {'error': str(e)} 