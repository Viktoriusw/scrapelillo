"""
Simple Task Scheduler for Professional Web Scraper

A simplified scheduler that doesn't use APScheduler to avoid serialization issues.
"""

import logging
import json
import time
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

logger = logging.getLogger(__name__)


@dataclass
class SimpleTask:
    """Represents a simple scheduled task"""
    id: str
    name: str
    function: Callable
    interval_seconds: int = 3600  # Default: 1 hour
    enabled: bool = True
    description: str = ""
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0


class SimpleTaskScheduler:
    """
    Simple task scheduler without APScheduler dependencies
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize simple task scheduler
        
        Args:
            config_manager: Configuration manager instance
        """
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        
        scheduler_config = self.config.get_section('scheduler')
        self.enabled = scheduler_config.get('enabled', True)
        
        if not self.enabled:
            logger.info("Simple task scheduler disabled")
            return
        
        # Configuration
        self.check_interval = scheduler_config.get('check_interval', 60)  # Check every 60 seconds
        
        # Database configuration
        self.database_path = scheduler_config.get('database_path', 'simple_scheduler.db')
        
        # Task registry
        self.tasks: Dict[str, SimpleTask] = {}
        
        # Thread safety
        self._lock = threading.Lock()
        self._running = False
        self._scheduler_thread = None
        
        # Initialize database
        self._init_database()
        
        # Register default tasks
        self._register_default_tasks()
        
        logger.info("Simple task scheduler initialized")
    
    def _init_database(self):
        """Initialize SQLite database for task results"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Create task results table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS simple_task_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    success BOOLEAN NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    duration REAL NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            
            # Create task configurations table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS simple_task_configs (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    enabled BOOLEAN NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    last_run TEXT,
                    next_run TEXT,
                    run_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0
                )
            ''')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize simple scheduler database: {e}")
    
    def _register_default_tasks(self):
        """Register default system tasks"""
        try:
            # Register cleanup task (every 24 hours)
            self.register_task(
                task_id="simple_cleanup",
                function=self._simple_cleanup,
                interval_seconds=86400,  # 24 hours
                description="Clean up old data and logs"
            )
            
            # Register health check task (every 30 minutes)
            self.register_task(
                task_id="simple_health_check",
                function=self._simple_health_check,
                interval_seconds=1800,  # 30 minutes
                description="System health check"
            )
            
            logger.info("Default simple tasks registered")
            
        except Exception as e:
            logger.error(f"Error registering default simple tasks: {e}")
    
    def register_task(self, task_id: str, function: Callable, interval_seconds: int = 3600,
                     description: str = "") -> bool:
        """
        Register a new task
        
        Args:
            task_id: Unique task identifier
            function: Function to execute
            interval_seconds: Interval between executions in seconds
            description: Task description
            
        Returns:
            True if registered successfully
        """
        if not self.enabled:
            return False
        
        try:
            with self._lock:
                # Create task
                task = SimpleTask(
                    id=task_id,
                    name=task_id,
                    function=function,
                    interval_seconds=interval_seconds,
                    description=description,
                    next_run=datetime.now() + timedelta(seconds=interval_seconds)
                )
                
                self.tasks[task_id] = task
                
                # Store task configuration
                self._store_task_config(task)
                
                logger.info(f"Simple task registered: {task_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error registering simple task {task_id}: {e}")
            return False
    
    def start(self):
        """Start the scheduler"""
        if not self.enabled or self._running:
            return
        
        try:
            self._running = True
            self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self._scheduler_thread.start()
            logger.info("Simple task scheduler started")
        except Exception as e:
            logger.error(f"Error starting simple scheduler: {e}")
    
    def stop(self):
        """Stop the scheduler"""
        if not self.enabled or not self._running:
            return
        
        try:
            self._running = False
            if self._scheduler_thread:
                self._scheduler_thread.join(timeout=5)
            logger.info("Simple task scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping simple scheduler: {e}")
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        while self._running:
            try:
                current_time = datetime.now()
                
                with self._lock:
                    for task_id, task in self.tasks.items():
                        if task.enabled and task.next_run and current_time >= task.next_run:
                            # Execute task in a separate thread
                            thread = threading.Thread(
                                target=self._execute_task,
                                args=(task_id,),
                                daemon=True
                            )
                            thread.start()
                
                # Sleep for check interval
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(self.check_interval)
    
    def _execute_task(self, task_id: str):
        """Execute a scheduled task"""
        start_time = datetime.now()
        
        try:
            with self._lock:
                if task_id not in self.tasks:
                    return
                
                task = self.tasks[task_id]
                
                # Update next run time
                task.next_run = datetime.now() + timedelta(seconds=task.interval_seconds)
                task.last_run = start_time
                task.run_count += 1
            
            # Execute function
            logger.info(f"Starting simple task {task_id}")
            result = task.function()
            logger.info(f"Simple task {task_id} completed successfully")
            
            # Update success count
            with self._lock:
                task.success_count += 1
            
            # Store result
            end_time = datetime.now()
            self._store_task_result(task_id, True, start_time, end_time, result, None)
            
        except Exception as e:
            # Update failure count
            with self._lock:
                if task_id in self.tasks:
                    self.tasks[task_id].failure_count += 1
            
            # Store error result
            end_time = datetime.now()
            error_msg = str(e)
            self._store_task_result(task_id, False, start_time, end_time, None, error_msg)
            
            logger.error(f"Simple task {task_id} failed: {e}")
    
    def _store_task_config(self, task: SimpleTask):
        """Store task configuration"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO simple_task_configs 
                (id, name, interval_seconds, enabled, description, created_at, last_run, next_run, 
                 run_count, success_count, failure_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task.id,
                task.name,
                task.interval_seconds,
                task.enabled,
                task.description,
                datetime.now().isoformat(),
                task.last_run.isoformat() if task.last_run else None,
                task.next_run.isoformat() if task.next_run else None,
                task.run_count,
                task.success_count,
                task.failure_count
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing simple task config: {e}")
    
    def _store_task_result(self, task_id: str, success: bool, start_time: datetime,
                          end_time: datetime, result: Any, error: str):
        """Store task result"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO simple_task_results 
                (task_id, success, start_time, end_time, duration, result, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                task_id,
                success,
                start_time.isoformat(),
                end_time.isoformat(),
                (end_time - start_time).total_seconds(),
                json.dumps(result) if result else None,
                error,
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing simple task result: {e}")
    
    def get_all_tasks(self) -> List[Dict[str, Any]]:
        """Get all registered tasks"""
        with self._lock:
            return [
                {
                    'id': task.id,
                    'name': task.name,
                    'interval_seconds': task.interval_seconds,
                    'enabled': task.enabled,
                    'description': task.description,
                    'last_run': task.last_run.isoformat() if task.last_run else None,
                    'next_run': task.next_run.isoformat() if task.next_run else None,
                    'run_count': task.run_count,
                    'success_count': task.success_count,
                    'failure_count': task.failure_count
                }
                for task in self.tasks.values()
            ]
    
    def enable_task(self, task_id: str) -> bool:
        """Enable a task"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].enabled = True
                return True
        return False
    
    def disable_task(self, task_id: str) -> bool:
        """Disable a task"""
        with self._lock:
            if task_id in self.tasks:
                self.tasks[task_id].enabled = False
                return True
        return False
    
    def remove_task(self, task_id: str) -> bool:
        """Remove a task"""
        with self._lock:
            if task_id in self.tasks:
                del self.tasks[task_id]
                return True
        return False
    
    def run_task_now(self, task_id: str) -> bool:
        """Run a task immediately"""
        with self._lock:
            if task_id in self.tasks:
                # Execute task in a separate thread
                thread = threading.Thread(
                    target=self._execute_task,
                    args=(task_id,),
                    daemon=True
                )
                thread.start()
                return True
        return False
    
    # Default task functions
    def _simple_cleanup(self):
        """Simple cleanup task"""
        try:
            logger.info("Running simple cleanup task")
            # Add cleanup logic here
            return "Cleanup completed"
        except Exception as e:
            logger.error(f"Error in simple cleanup: {e}")
            raise
    
    def _simple_health_check(self):
        """Simple health check task"""
        try:
            logger.info("Running simple health check")
            # Add health check logic here
            return "Health check completed"
        except Exception as e:
            logger.error(f"Error in simple health check: {e}")
            raise 