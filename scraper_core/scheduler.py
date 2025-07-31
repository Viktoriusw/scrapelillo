from sqlalchemy import create_engine
"""
Task Scheduler for Professional Web Scraper

Implements comprehensive task scheduling with notifications, job management,
monitoring, and persistence capabilities.
"""

import logging
import json
import time
from typing import Dict, List, Any, Optional, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import threading
from pathlib import Path
import sqlite3
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTask:
    """Represents a scheduled task"""
    id: str
    name: str
    function: str
    args: List[Any] = field(default_factory=list)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    trigger_type: str = "interval"  # interval, cron, date
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    description: str = ""
    notifications: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0


@dataclass
class TaskResult:
    """Result of a task execution"""
    task_id: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration: float
    result: Any = None
    error: Optional[str] = None
    logs: List[str] = field(default_factory=list)


@dataclass
class NotificationConfig:
    """Configuration for notifications"""
    email: Dict[str, Any] = field(default_factory=dict)
    webhook: Dict[str, Any] = field(default_factory=dict)
    slack: Dict[str, Any] = field(default_factory=dict)
    telegram: Dict[str, Any] = field(default_factory=dict)


class TaskScheduler:
    """
    Comprehensive task scheduler with notifications and monitoring
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize task scheduler
        
        Args:
            config_manager: Configuration manager instance
        """
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        
        scheduler_config = self.config.get_section('scheduler')
        self.enabled = scheduler_config.get('enabled', True)
        
        if not self.enabled:
            logger.info("Task scheduler disabled")
            return
        
        # Configuration
        self.max_workers = scheduler_config.get('max_workers', 10)
        self.job_defaults = scheduler_config.get('job_defaults', {
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 300
        })
        
        # Database configuration
        self.database_path = scheduler_config.get('database_path', 'scheduler.db')
        
        # Notification configuration
        self.notification_config = NotificationConfig(**scheduler_config.get('notifications', {}))
        
        # Initialize scheduler
        self.scheduler = self._initialize_scheduler()
        
        # Task registry
        self.registered_tasks: Dict[str, Callable] = {}
        
        # Task results storage
        self.task_results: List[TaskResult] = []
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Initialize database
        self._init_database()
        
        # Register default tasks
        self._register_default_tasks()
        
        logger.info("Task scheduler initialized")
    
    def _initialize_scheduler(self) -> BackgroundScheduler:
        """Initialize APScheduler with configuration"""
        jobstores = {
            'default': SQLAlchemyJobStore(url=f'sqlite:///{self.database_path}')
        }
        
        executors = {
            'default': ThreadPoolExecutor(max_workers=self.max_workers)
        }
        
        scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=self.job_defaults,
            timezone='UTC'
        )
        
        return scheduler
    
    def _init_database(self):
        """Initialize SQLite database for task results"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Create task results table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    duration REAL NOT NULL,
                    result TEXT,
                    error TEXT,
                    logs TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Create task configurations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_configs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    function TEXT NOT NULL,
                    args TEXT NOT NULL,
                    kwargs TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    trigger_config TEXT NOT NULL,
                    enabled BOOLEAN NOT NULL,
                    description TEXT,
                    notifications TEXT,
                    created_at TEXT NOT NULL,
                    last_run TEXT,
                    next_run TEXT,
                    run_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_results_task_id ON task_results(task_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_results_start_time ON task_results(start_time)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_configs_enabled ON task_configs(enabled)')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize scheduler database: {e}")
    
    def _register_default_tasks(self):
        """Register default system tasks"""
        # Data cleanup task
        self.register_task(
            'data_cleanup',
            self._cleanup_old_data_wrapper,
            trigger_type='cron',
            trigger_config={'hour': 2, 'minute': 0},  # Daily at 2 AM
            description="Clean up old data and logs",
            notifications={'on_failure': True}
        )
        
        # Health check task
        self.register_task(
            'health_check',
            self._health_check_wrapper,
            trigger_type='interval',
            trigger_config={'minutes': 30},  # Every 30 minutes
            description="System health check",
            notifications={'on_failure': True}
        )
        
        # Metrics collection task
        self.register_task(
            'collect_metrics',
            self._collect_metrics_wrapper,
            trigger_type='interval',
            trigger_config={'minutes': 15},  # Every 15 minutes
            description="Collect system metrics",
            notifications={'on_failure': False}
        )
    
    def start(self):
        """Start the scheduler"""
        if not self.enabled:
            return
        
        try:
            self.scheduler.start()
            logger.info("Task scheduler started")
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
    
    def stop(self):
        """Stop the scheduler"""
        if not self.enabled:
            return
        
        try:
            self.scheduler.shutdown()
            logger.info("Task scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    def register_task(self, task_id: str, function: Callable, trigger_type: str = "interval",
                     trigger_config: Dict[str, Any] = None, description: str = "",
                     notifications: Dict[str, Any] = None) -> bool:
        """
        Register a new task
        
        Args:
            task_id: Unique task identifier
            function: Function to execute
            trigger_type: Type of trigger (interval, cron, date)
            trigger_config: Trigger configuration
            description: Task description
            notifications: Notification configuration
            
        Returns:
            True if registered successfully
        """
        if not self.enabled:
            return False
        
        try:
            # Create a wrapper function that doesn't contain references to self
            def task_wrapper():
                try:
                    return function()
                except Exception as e:
                    logger.error(f"Error in task {task_id}: {e}")
                    return None
            
            # Store function reference
            self.registered_tasks[task_id] = task_wrapper
            
            # Create trigger
            trigger = self._create_trigger(trigger_type, trigger_config or {})
            
            # Add job to scheduler with the wrapper
            job = self.scheduler.add_job(
                func=self._execute_task,
                trigger=trigger,
                args=[task_id],
                id=task_id,
                name=task_id,
                replace_existing=True
            )
            
            # Store task configuration
            task = ScheduledTask(
                id=task_id,
                name=task_id,
                function=function.__name__,
                trigger_type=trigger_type,
                trigger_config=trigger_config or {},
                description=description,
                notifications=notifications or {},
                next_run=getattr(job, 'next_run_time', None)
            )
            
            self._store_task_config(task)
            
            logger.info(f"Task registered: {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error registering task {task_id}: {e}")
            return False
    
    def _create_trigger(self, trigger_type: str, config: Dict[str, Any]):
        """Create APScheduler trigger"""
        if trigger_type == "interval":
            return IntervalTrigger(**config)
        elif trigger_type == "cron":
            return CronTrigger(**config)
        elif trigger_type == "date":
            return DateTrigger(**config)
        else:
            raise ValueError(f"Unknown trigger type: {trigger_type}")
    
    def _execute_task(self, task_id: str):
        """Execute a scheduled task"""
        start_time = datetime.now()
        logs = []
        
        try:
            # Get task function
            if task_id not in self.registered_tasks:
                raise ValueError(f"Task {task_id} not found")
            
            function = self.registered_tasks[task_id]
            
            # Execute function
            logs.append(f"Starting task {task_id}")
            result = function()
            logs.append(f"Task {task_id} completed successfully")
            
            # Create success result
            end_time = datetime.now()
            task_result = TaskResult(
                task_id=task_id,
                success=True,
                start_time=start_time,
                end_time=end_time,
                duration=(end_time - start_time).total_seconds(),
                result=result,
                logs=logs
            )
            
            # Update task statistics (using a separate method to avoid serialization issues)
            self._update_task_stats_safe(task_id, True)
            
            # Send success notification if configured
            self._send_notification_safe(task_id, task_result)
            
        except Exception as e:
            # Create failure result
            end_time = datetime.now()
            error_msg = str(e)
            logs.append(f"Task {task_id} failed: {error_msg}")
            
            task_result = TaskResult(
                task_id=task_id,
                success=False,
                start_time=start_time,
                end_time=end_time,
                duration=(end_time - start_time).total_seconds(),
                error=error_msg,
                logs=logs
            )
            
            # Update task statistics
            self._update_task_stats_safe(task_id, False)
            
            # Send failure notification
            self._send_notification_safe(task_id, task_result)
            
            logger.error(f"Task {task_id} failed: {e}")
        
        # Store result
        self._store_task_result_safe(task_result)
    
    def _update_task_stats(self, task_id: str, success: bool):
        """Update task statistics"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            if success:
                cursor.execute('''
                    UPDATE task_configs 
                    SET run_count = run_count + 1, 
                        success_count = success_count + 1,
                        last_run = ?
                    WHERE id = ?
                ''', (datetime.now().isoformat(), task_id))
            else:
                cursor.execute('''
                    UPDATE task_configs 
                    SET run_count = run_count + 1, 
                        failure_count = failure_count + 1,
                        last_run = ?
                    WHERE id = ?
                ''', (datetime.now().isoformat(), task_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating task stats: {e}")

    def _update_task_stats_safe(self, task_id: str, success: bool):
        """Update task statistics (safe version for scheduler)"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            if success:
                cursor.execute('''
                    UPDATE task_configs 
                    SET run_count = run_count + 1, 
                        success_count = success_count + 1,
                        last_run = ?
                    WHERE id = ?
                ''', (datetime.now().isoformat(), task_id))
            else:
                cursor.execute('''
                    UPDATE task_configs 
                    SET run_count = run_count + 1, 
                        failure_count = failure_count + 1,
                        last_run = ?
                    WHERE id = ?
                ''', (datetime.now().isoformat(), task_id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating task stats for {task_id}: {e}")

    def _send_notification_safe(self, task_id: str, result: TaskResult):
        """Send notification (safe version for scheduler)"""
        try:
            # Get task configuration
            task_config = self._get_task_config(task_id)
            if not task_config:
                return
            
            notifications = task_config.get('notifications', {})
            if not notifications:
                return
            
            # Send notifications based on result
            if result.success and notifications.get('on_success'):
                self._send_email_notification_safe(task_id, result)
            elif not result.success and notifications.get('on_failure'):
                self._send_email_notification_safe(task_id, result)
                
        except Exception as e:
            logger.error(f"Error sending notification for {task_id}: {e}")

    def _send_email_notification_safe(self, task_id: str, result: TaskResult):
        """Send email notification (safe version)"""
        try:
            # This is a simplified version that doesn't use instance methods
            logger.info(f"Email notification would be sent for task {task_id}: {'Success' if result.success else 'Failure'}")
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")

    def _store_task_result_safe(self, result: TaskResult):
        """Store task result (safe version for scheduler)"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO task_results 
                (task_id, success, start_time, end_time, duration, result, error, logs, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result.task_id,
                result.success,
                result.start_time.isoformat(),
                result.end_time.isoformat(),
                result.duration,
                json.dumps(result.result) if result.result else None,
                result.error,
                json.dumps(result.logs),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing task result: {e}")
    
    def _send_notification(self, task_id: str, result: TaskResult):
        """Send notification for task result"""
        try:
            # Get task configuration
            task_config = self._get_task_config(task_id)
            if not task_config:
                return
            
            notifications = task_config.get('notifications', {})
            
            # Check if notification should be sent
            should_notify = False
            if result.success and notifications.get('on_success', False):
                should_notify = True
            elif not result.success and notifications.get('on_failure', True):
                should_notify = True
            
            if not should_notify:
                return
            
            # Send notifications
            if self.notification_config.email:
                self._send_email_notification(task_id, result)
            
            if self.notification_config.webhook:
                self._send_webhook_notification(task_id, result)
            
            if self.notification_config.slack:
                self._send_slack_notification(task_id, result)
            
            if self.notification_config.telegram:
                self._send_telegram_notification(task_id, result)
                
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
    
    def _send_email_notification(self, task_id: str, result: TaskResult):
        """Send email notification"""
        try:
            email_config = self.notification_config.email
            
            msg = MIMEMultipart()
            msg['From'] = email_config['from_email']
            msg['To'] = email_config['to_email']
            
            if result.success:
                msg['Subject'] = f"Task Success: {task_id}"
                body = f"""
                Task {task_id} completed successfully.
                
                Start Time: {result.start_time}
                End Time: {result.end_time}
                Duration: {result.duration:.2f} seconds
                
                Logs:
                {chr(10).join(result.logs)}
                """
            else:
                msg['Subject'] = f"Task Failure: {task_id}"
                body = f"""
                Task {task_id} failed.
                
                Start Time: {result.start_time}
                End Time: {result.end_time}
                Duration: {result.duration:.2f} seconds
                Error: {result.error}
                
                Logs:
                {chr(10).join(result.logs)}
                """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(email_config['smtp_server'], email_config['smtp_port'])
            if email_config.get('use_tls', True):
                server.starttls()
            
            if email_config.get('username') and email_config.get('password'):
                server.login(email_config['username'], email_config['password'])
            
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email notification sent for task {task_id}")
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
    
    def _send_webhook_notification(self, task_id: str, result: TaskResult):
        """Send webhook notification"""
        try:
            webhook_config = self.notification_config.webhook
            
            payload = {
                'task_id': task_id,
                'success': result.success,
                'start_time': result.start_time.isoformat(),
                'end_time': result.end_time.isoformat(),
                'duration': result.duration,
                'error': result.error,
                'logs': result.logs
            }
            
            response = requests.post(
                webhook_config['url'],
                json=payload,
                headers=webhook_config.get('headers', {}),
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook notification sent for task {task_id}")
            else:
                logger.warning(f"Webhook notification failed for task {task_id}: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")
    
    def _send_slack_notification(self, task_id: str, result: TaskResult):
        """Send Slack notification"""
        try:
            slack_config = self.notification_config.slack
            
            if result.success:
                color = "good"
                title = f"Task Success: {task_id}"
                text = f"Task completed in {result.duration:.2f} seconds"
            else:
                color = "danger"
                title = f"Task Failure: {task_id}"
                text = f"Error: {result.error}"
            
            payload = {
                "attachments": [{
                    "color": color,
                    "title": title,
                    "text": text,
                    "fields": [
                        {
                            "title": "Start Time",
                            "value": result.start_time.strftime("%Y-%m-%d %H:%M:%S"),
                            "short": True
                        },
                        {
                            "title": "Duration",
                            "value": f"{result.duration:.2f}s",
                            "short": True
                        }
                    ]
                }]
            }
            
            response = requests.post(
                slack_config['webhook_url'],
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Slack notification sent for task {task_id}")
            else:
                logger.warning(f"Slack notification failed for task {task_id}: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
    
    def _send_telegram_notification(self, task_id: str, result: TaskResult):
        """Send Telegram notification"""
        try:
            telegram_config = self.notification_config.telegram
            
            if result.success:
                text = f"✅ Task Success: {task_id}\nDuration: {result.duration:.2f}s"
            else:
                text = f"❌ Task Failure: {task_id}\nError: {result.error}"
            
            payload = {
                'chat_id': telegram_config['chat_id'],
                'text': text,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(
                f"https://api.telegram.org/bot{telegram_config['bot_token']}/sendMessage",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                logger.info(f"Telegram notification sent for task {task_id}")
            else:
                logger.warning(f"Telegram notification failed for task {task_id}: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Telegram notification: {e}")
    
    def _store_task_config(self, task: ScheduledTask):
        """Store task configuration in database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO task_configs 
                (id, name, function, args, kwargs, trigger_type, trigger_config, enabled, description, notifications, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task.id,
                task.name,
                task.function,
                json.dumps(task.args),
                json.dumps(task.kwargs),
                task.trigger_type,
                json.dumps(task.trigger_config),
                task.enabled,
                task.description,
                json.dumps(task.notifications),
                task.created_at.isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing task config: {e}")
    
    def _store_task_result(self, result: TaskResult):
        """Store task result in database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO task_results 
                (task_id, success, start_time, end_time, duration, result, error, logs, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result.task_id,
                result.success,
                result.start_time.isoformat(),
                result.end_time.isoformat(),
                result.duration,
                json.dumps(result.result) if result.result else None,
                result.error,
                json.dumps(result.logs),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing task result: {e}")
    
    def _get_task_config(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task configuration from database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM task_configs WHERE id = ?', (task_id,))
            row = cursor.fetchone()
            
            conn.close()
            
            if row:
                return {
                    'id': row[0],
                    'name': row[1],
                    'function': row[2],
                    'args': json.loads(row[3]),
                    'kwargs': json.loads(row[4]),
                    'trigger_type': row[5],
                    'trigger_config': json.loads(row[6]),
                    'enabled': bool(row[7]),
                    'description': row[8],
                    'notifications': json.loads(row[9]) if row[9] else {},
                    'created_at': row[10],
                    'last_run': row[11],
                    'next_run': row[12],
                    'run_count': row[13],
                    'success_count': row[14],
                    'failure_count': row[15]
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting task config: {e}")
            return None
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of a task"""
        try:
            job = self.scheduler.get_job(task_id)
            if not job:
                return None
            
            config = self._get_task_config(task_id)
            if not config:
                return None
            
            return {
                'id': task_id,
                'name': config['name'],
                'enabled': config['enabled'],
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'last_run': config['last_run'],
                'run_count': config['run_count'],
                'success_count': config['success_count'],
                'failure_count': config['failure_count'],
                'success_rate': config['success_count'] / max(config['run_count'], 1)
            }
            
        except Exception as e:
            logger.error(f"Error getting task status: {e}")
            return None
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all registered tasks"""
        tasks = []
        
        for job in self.scheduler.get_jobs():
            status = self.get_task_status(job.id)
            if status:
                tasks.append(status)
        
        return tasks
    
    def enable_task(self, task_id: str) -> bool:
        """Enable a task"""
        try:
            self.scheduler.resume_job(task_id)
            
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE task_configs SET enabled = 1 WHERE id = ?', (task_id,))
            conn.commit()
            conn.close()
            
            logger.info(f"Task {task_id} enabled")
            return True
            
        except Exception as e:
            logger.error(f"Error enabling task {task_id}: {e}")
            return False
    
    def disable_task(self, task_id: str) -> bool:
        """Disable a task"""
        try:
            self.scheduler.pause_job(task_id)
            
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            cursor.execute('UPDATE task_configs SET enabled = 0 WHERE id = ?', (task_id,))
            conn.commit()
            conn.close()
            
            logger.info(f"Task {task_id} disabled")
            return True
            
        except Exception as e:
            logger.error(f"Error disabling task {task_id}: {e}")
            return False
    
    def remove_task(self, task_id: str) -> bool:
        """Remove a task"""
        try:
            self.scheduler.remove_job(task_id)
            
            if task_id in self.registered_tasks:
                del self.registered_tasks[task_id]
            
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            cursor.execute('DELETE FROM task_configs WHERE id = ?', (task_id,))
            conn.commit()
            conn.close()
            
            logger.info(f"Task {task_id} removed")
            return True
            
        except Exception as e:
            logger.error(f"Error removing task {task_id}: {e}")
            return False
    
    def run_task_now(self, task_id: str) -> bool:
        """Run a task immediately"""
        try:
            if task_id not in self.registered_tasks:
                logger.error(f"Task {task_id} not found")
                return False
            
            # Run task in separate thread
            threading.Thread(
                target=self._execute_task,
                args=[task_id],
                daemon=True
            ).start()
            
            logger.info(f"Task {task_id} started immediately")
            return True
            
        except Exception as e:
            logger.error(f"Error running task {task_id}: {e}")
            return False
    
    def get_task_results(self, task_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get task execution results"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            if task_id:
                cursor.execute('''
                    SELECT * FROM task_results 
                    WHERE task_id = ? 
                    ORDER BY start_time DESC 
                    LIMIT ?
                ''', (task_id, limit))
            else:
                cursor.execute('''
                    SELECT * FROM task_results 
                    ORDER BY start_time DESC 
                    LIMIT ?
                ''', (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            results = []
            for row in rows:
                results.append({
                    'id': row[0],
                    'task_id': row[1],
                    'success': bool(row[2]),
                    'start_time': row[3],
                    'end_time': row[4],
                    'duration': row[5],
                    'result': json.loads(row[6]) if row[6] else None,
                    'error': row[7],
                    'logs': json.loads(row[8]) if row[8] else [],
                    'created_at': row[9]
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting task results: {e}")
            return []
    
    # Default system tasks
    def _cleanup_old_data(self):
        """Clean up old data and logs"""
        try:
            # Clean up old task results (older than 30 days)
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cutoff_date = (datetime.now() - timedelta(days=30)).isoformat()
            cursor.execute('DELETE FROM task_results WHERE start_time < ?', (cutoff_date,))
            
            deleted_count = cursor.rowcount
            conn.commit()
            conn.close()
            
            logger.info(f"Cleaned up {deleted_count} old task results")
            return f"Cleaned up {deleted_count} old task results"
            
        except Exception as e:
            logger.error(f"Error in data cleanup task: {e}")
            raise
    
    def _health_check(self):
        """System health check"""
        try:
            # Check database connectivity
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM task_configs')
            task_count = cursor.fetchone()[0]
            conn.close()
            
            # Check scheduler status
            scheduler_running = self.scheduler.running
            
            # Check registered tasks
            registered_count = len(self.registered_tasks)
            
            health_status = {
                'database_ok': True,
                'scheduler_running': scheduler_running,
                'task_count': task_count,
                'registered_tasks': registered_count,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info("Health check completed successfully")
            return health_status
            
        except Exception as e:
            logger.error(f"Error in health check task: {e}")
            raise
    
    def _collect_metrics(self):
        """Collect system metrics"""
        try:
            # Get task statistics
            tasks = self.get_all_tasks()
            
            metrics = {
                'total_tasks': len(tasks),
                'enabled_tasks': len([t for t in tasks if t['enabled']]),
                'total_runs': sum(t['run_count'] for t in tasks),
                'total_success': sum(t['success_count'] for t in tasks),
                'total_failures': sum(t['failure_count'] for t in tasks),
                'avg_success_rate': sum(t['success_rate'] for t in tasks) / max(len(tasks), 1),
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info("Metrics collection completed")
            return metrics
            
        except Exception as e:
            logger.error(f"Error in metrics collection task: {e}")
            raise

    # Wrapper methods to avoid serialization issues
    def _cleanup_old_data_wrapper(self):
        """Wrapper for data cleanup task"""
        return self._cleanup_old_data()
    
    def _health_check_wrapper(self):
        """Wrapper for health check task"""
        return self._health_check()
    
    def _collect_metrics_wrapper(self):
        """Wrapper for metrics collection task"""
        return self._collect_metrics() 