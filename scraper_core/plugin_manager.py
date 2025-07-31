"""
Plugin Manager for Professional Web Scraper

Implements comprehensive plugin management with hot reloading, dependency
management, API integration, and extensibility features.
"""

import logging
import json
import importlib
import inspect
import sys
from typing import Dict, List, Any, Optional, Union, Callable, Type
from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
from datetime import datetime
import yaml
import pkg_resources
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)


@dataclass
class PluginInfo:
    """Information about a plugin"""
    name: str
    version: str
    description: str
    author: str
    dependencies: List[str] = field(default_factory=list)
    entry_point: str = ""
    config_schema: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    loaded: bool = False
    load_time: Optional[datetime] = None
    error: Optional[str] = None


@dataclass
class PluginInstance:
    """Instance of a loaded plugin"""
    info: PluginInfo
    module: Any
    instance: Any
    hooks: Dict[str, List[Callable]] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)


class PluginHook:
    """Base class for plugin hooks"""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.callbacks: List[Callable] = []
    
    def register(self, callback: Callable):
        """Register a callback for this hook"""
        self.callbacks.append(callback)
    
    def unregister(self, callback: Callable):
        """Unregister a callback from this hook"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def call(self, *args, **kwargs) -> List[Any]:
        """Call all registered callbacks"""
        results = []
        for callback in self.callbacks:
            try:
                result = callback(*args, **kwargs)
                results.append(result)
            except Exception as e:
                logger.error(f"Error in plugin hook {self.name}: {e}")
        return results


class PluginManager:
    """
    Comprehensive plugin management system
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize plugin manager
        
        Args:
            config_manager: Configuration manager instance
        """
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        
        plugin_config = self.config.get_section('plugins')
        self.enabled = plugin_config.get('enabled', True)
        
        if not self.enabled:
            logger.info("Plugin manager disabled")
            return
        
        # Configuration
        self.plugin_directory = Path(plugin_config.get('plugin_directory', 'plugins'))
        self.auto_reload = plugin_config.get('auto_reload', True)
        self.scan_interval = plugin_config.get('scan_interval', 30)
        self.max_plugins = plugin_config.get('max_plugins', 50)
        
        # Plugin storage
        self.plugins: Dict[str, PluginInstance] = {}
        self.plugin_info: Dict[str, PluginInfo] = {}
        self.hooks: Dict[str, PluginHook] = {}
        
        # Thread safety
        self._lock = threading.Lock()
        self._stop_monitoring = False
        
        # File system monitoring
        self.observer = None
        if self.auto_reload:
            self._setup_file_monitoring()
        
        # Initialize plugin directory
        self.plugin_directory.mkdir(exist_ok=True)
        
        # Register default hooks
        self._register_default_hooks()
        
        # Load plugins
        self._discover_plugins()
        self._load_plugins()
        
        logger.info("Plugin manager initialized")
    
    def _setup_file_monitoring(self):
        """Setup file system monitoring for auto-reload"""
        try:
            self.observer = Observer()
            event_handler = PluginFileHandler(self)
            self.observer.schedule(event_handler, str(self.plugin_directory), recursive=True)
            self.observer.start()
            
            logger.info("File monitoring started for auto-reload")
            
        except Exception as e:
            logger.error(f"Error setting up file monitoring: {e}")
    
    def _register_default_hooks(self):
        """Register default plugin hooks"""
        default_hooks = [
            ('pre_scrape', 'Called before scraping starts'),
            ('post_scrape', 'Called after scraping completes'),
            ('pre_request', 'Called before making HTTP request'),
            ('post_request', 'Called after HTTP request completes'),
            ('data_transform', 'Called to transform scraped data'),
            ('error_handler', 'Called when errors occur'),
            ('config_validate', 'Called to validate configuration'),
            ('metrics_collect', 'Called to collect metrics'),
            ('export_data', 'Called before data export'),
            ('cleanup', 'Called during cleanup operations')
        ]
        
        for hook_name, description in default_hooks:
            self.hooks[hook_name] = PluginHook(hook_name, description)
    
    def _discover_plugins(self):
        """Discover available plugins"""
        try:
            for plugin_dir in self.plugin_directory.iterdir():
                if not plugin_dir.is_dir():
                    continue
                
                # Check for plugin manifest
                manifest_file = plugin_dir / 'plugin.yaml'
                if not manifest_file.exists():
                    continue
                
                try:
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        manifest = yaml.safe_load(f)
                    
                    plugin_info = PluginInfo(
                        name=manifest.get('name', plugin_dir.name),
                        version=manifest.get('version', '1.0.0'),
                        description=manifest.get('description', ''),
                        author=manifest.get('author', 'Unknown'),
                        dependencies=manifest.get('dependencies', []),
                        entry_point=manifest.get('entry_point', 'main'),
                        config_schema=manifest.get('config_schema', {}),
                        enabled=manifest.get('enabled', True)
                    )
                    
                    self.plugin_info[plugin_info.name] = plugin_info
                    logger.info(f"Discovered plugin: {plugin_info.name} v{plugin_info.version}")
                    
                except Exception as e:
                    logger.error(f"Error reading plugin manifest {manifest_file}: {e}")
                    
        except Exception as e:
            logger.error(f"Error discovering plugins: {e}")
    
    def _load_plugins(self):
        """Load enabled plugins"""
        for plugin_name, plugin_info in self.plugin_info.items():
            if not plugin_info.enabled:
                continue
            
            if len(self.plugins) >= self.max_plugins:
                logger.warning(f"Maximum number of plugins reached ({self.max_plugins})")
                break
            
            try:
                self._load_plugin(plugin_name, plugin_info)
            except Exception as e:
                logger.error(f"Error loading plugin {plugin_name}: {e}")
                plugin_info.error = str(e)
    
    def _load_plugin(self, plugin_name: str, plugin_info: PluginInfo):
        """Load a specific plugin"""
        try:
            # Check dependencies
            if not self._check_dependencies(plugin_info.dependencies):
                raise Exception(f"Missing dependencies: {plugin_info.dependencies}")
            
            # Add plugin directory to Python path
            plugin_dir = self.plugin_directory / plugin_name
            if str(plugin_dir) not in sys.path:
                sys.path.insert(0, str(plugin_dir))
            
            # Import plugin module
            module_name = plugin_info.entry_point
            module = importlib.import_module(module_name)
            
            # Find plugin class
            plugin_class = self._find_plugin_class(module)
            if not plugin_class:
                raise Exception("No plugin class found")
            
            # Create plugin instance
            plugin_instance = plugin_class()
            
            # Initialize plugin
            if hasattr(plugin_instance, 'initialize'):
                config = self._get_plugin_config(plugin_name)
                plugin_instance.initialize(config)
            
            # Register hooks
            hooks = self._discover_plugin_hooks(plugin_instance)
            
            # Create plugin instance
            plugin_inst = PluginInstance(
                info=plugin_info,
                module=module,
                instance=plugin_instance,
                hooks=hooks,
                config=self._get_plugin_config(plugin_name)
            )
            
            # Store plugin
            self.plugins[plugin_name] = plugin_inst
            plugin_info.loaded = True
            plugin_info.load_time = datetime.now()
            plugin_info.error = None
            
            logger.info(f"Plugin {plugin_name} loaded successfully")
            
        except Exception as e:
            plugin_info.loaded = False
            plugin_info.error = str(e)
            raise
    
    def _check_dependencies(self, dependencies: List[str]) -> bool:
        """Check if plugin dependencies are available"""
        for dependency in dependencies:
            try:
                pkg_resources.require(dependency)
            except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict):
                logger.warning(f"Dependency not available: {dependency}")
                return False
        return True
    
    def _find_plugin_class(self, module: Any) -> Optional[Type]:
        """Find plugin class in module"""
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and 
                hasattr(obj, '__module__') and 
                obj.__module__ == module.__name__ and
                hasattr(obj, 'name')):
                return obj
        return None
    
    def _discover_plugin_hooks(self, plugin_instance: Any) -> Dict[str, List[Callable]]:
        """Discover hooks implemented by plugin"""
        hooks = {}
        
        for hook_name in self.hooks.keys():
            hook_method = getattr(plugin_instance, f'on_{hook_name}', None)
            if hook_method and callable(hook_method):
                hooks[hook_name] = [hook_method]
                self.hooks[hook_name].register(hook_method)
        
        return hooks
    
    def _get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """Get configuration for a plugin"""
        plugin_config = self.config.get_section('plugins')
        return plugin_config.get(plugin_name, {})
    
    def register_hook(self, hook_name: str, description: str = ""):
        """Register a new plugin hook"""
        if hook_name not in self.hooks:
            self.hooks[hook_name] = PluginHook(hook_name, description)
            logger.info(f"Registered new hook: {hook_name}")
    
    def call_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """Call a plugin hook"""
        if hook_name not in self.hooks:
            logger.warning(f"Hook {hook_name} not found")
            return []
        
        return self.hooks[hook_name].call(*args, **kwargs)
    
    def get_plugin(self, plugin_name: str) -> Optional[PluginInstance]:
        """Get a loaded plugin"""
        return self.plugins.get(plugin_name)
    
    def get_all_plugins(self) -> List[Dict[str, Any]]:
        """Get information about all plugins"""
        plugins = []
        
        for name, plugin_info in self.plugin_info.items():
            plugin_data = {
                'name': plugin_info.name,
                'version': plugin_info.version,
                'description': plugin_info.description,
                'author': plugin_info.author,
                'dependencies': plugin_info.dependencies,
                'enabled': plugin_info.enabled,
                'loaded': plugin_info.loaded,
                'load_time': plugin_info.load_time.isoformat() if plugin_info.load_time else None,
                'error': plugin_info.error
            }
            
            if name in self.plugins:
                plugin_data['hooks'] = list(self.plugins[name].hooks.keys())
                plugin_data['config'] = self.plugins[name].config
            
            plugins.append(plugin_data)
        
        return plugins
    
    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a plugin"""
        if plugin_name not in self.plugin_info:
            logger.error(f"Plugin {plugin_name} not found")
            return False
        
        plugin_info = self.plugin_info[plugin_name]
        if plugin_info.enabled:
            logger.info(f"Plugin {plugin_name} is already enabled")
            return True
        
        try:
            plugin_info.enabled = True
            
            if not plugin_info.loaded:
                self._load_plugin(plugin_name, plugin_info)
            
            logger.info(f"Plugin {plugin_name} enabled")
            return True
            
        except Exception as e:
            logger.error(f"Error enabling plugin {plugin_name}: {e}")
            plugin_info.enabled = False
            return False
    
    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a plugin"""
        if plugin_name not in self.plugin_info:
            logger.error(f"Plugin {plugin_name} not found")
            return False
        
        try:
            plugin_info = self.plugin_info[plugin_name]
            plugin_info.enabled = False
            
            if plugin_name in self.plugins:
                # Unregister hooks
                plugin_inst = self.plugins[plugin_name]
                for hook_name, callbacks in plugin_inst.hooks.items():
                    for callback in callbacks:
                        self.hooks[hook_name].unregister(callback)
                
                # Cleanup plugin
                if hasattr(plugin_inst.instance, 'cleanup'):
                    plugin_inst.instance.cleanup()
                
                del self.plugins[plugin_name]
                plugin_info.loaded = False
            
            logger.info(f"Plugin {plugin_name} disabled")
            return True
            
        except Exception as e:
            logger.error(f"Error disabling plugin {plugin_name}: {e}")
            return False
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a plugin"""
        if plugin_name not in self.plugin_info:
            logger.error(f"Plugin {plugin_name} not found")
            return False
        
        try:
            # Disable plugin
            self.disable_plugin(plugin_name)
            
            # Reload module
            if plugin_name in self.plugins:
                module = self.plugins[plugin_name].module
                importlib.reload(module)
            
            # Re-enable plugin
            return self.enable_plugin(plugin_name)
            
        except Exception as e:
            logger.error(f"Error reloading plugin {plugin_name}: {e}")
            return False
    
    def reload_all_plugins(self) -> Dict[str, bool]:
        """Reload all plugins"""
        results = {}
        
        for plugin_name in self.plugin_info.keys():
            results[plugin_name] = self.reload_plugin(plugin_name)
        
        return results
    
    def install_plugin(self, plugin_path: str) -> bool:
        """Install a plugin from path"""
        try:
            plugin_path = Path(plugin_path)
            
            if not plugin_path.exists():
                logger.error(f"Plugin path does not exist: {plugin_path}")
                return False
            
            # Copy plugin to plugin directory
            plugin_name = plugin_path.name
            target_path = self.plugin_directory / plugin_name
            
            if target_path.exists():
                logger.warning(f"Plugin {plugin_name} already exists")
                return False
            
            # Copy directory
            import shutil
            shutil.copytree(plugin_path, target_path)
            
            # Reload plugins
            self._discover_plugins()
            self._load_plugins()
            
            logger.info(f"Plugin {plugin_name} installed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error installing plugin: {e}")
            return False
    
    def uninstall_plugin(self, plugin_name: str) -> bool:
        """Uninstall a plugin"""
        try:
            # Disable plugin first
            self.disable_plugin(plugin_name)
            
            # Remove from plugin directory
            plugin_dir = self.plugin_directory / plugin_name
            if plugin_dir.exists():
                import shutil
                shutil.rmtree(plugin_dir)
            
            # Remove from plugin info
            if plugin_name in self.plugin_info:
                del self.plugin_info[plugin_name]
            
            logger.info(f"Plugin {plugin_name} uninstalled successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error uninstalling plugin {plugin_name}: {e}")
            return False
    
    def get_plugin_api(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get plugin API information"""
        if plugin_name not in self.plugins:
            return None
        
        plugin_inst = self.plugins[plugin_name]
        api_info = {
            'name': plugin_inst.info.name,
            'version': plugin_inst.info.version,
            'methods': [],
            'properties': [],
            'hooks': list(plugin_inst.hooks.keys())
        }
        
        # Get methods
        for name, method in inspect.getmembers(plugin_inst.instance, inspect.ismethod):
            if not name.startswith('_'):
                api_info['methods'].append({
                    'name': name,
                    'signature': str(inspect.signature(method)),
                    'doc': method.__doc__ or ''
                })
        
        # Get properties
        for name, prop in inspect.getmembers(plugin_inst.instance, lambda x: not inspect.ismethod(x)):
            if not name.startswith('_'):
                api_info['properties'].append({
                    'name': name,
                    'type': type(prop).__name__,
                    'value': str(prop)[:100] if prop else None
                })
        
        return api_info
    
    def call_plugin_method(self, plugin_name: str, method_name: str, *args, **kwargs) -> Any:
        """Call a method on a plugin"""
        if plugin_name not in self.plugins:
            raise ValueError(f"Plugin {plugin_name} not found")
        
        plugin_inst = self.plugins[plugin_name]
        method = getattr(plugin_inst.instance, method_name, None)
        
        if not method or not callable(method):
            raise ValueError(f"Method {method_name} not found in plugin {plugin_name}")
        
        return method(*args, **kwargs)
    
    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """Get plugin configuration"""
        if plugin_name not in self.plugins:
            return {}
        
        return self.plugins[plugin_name].config.copy()
    
    def set_plugin_config(self, plugin_name: str, config: Dict[str, Any]) -> bool:
        """Set plugin configuration"""
        if plugin_name not in self.plugins:
            logger.error(f"Plugin {plugin_name} not found")
            return False
        
        try:
            plugin_inst = self.plugins[plugin_name]
            plugin_inst.config.update(config)
            
            # Notify plugin of config change
            if hasattr(plugin_inst.instance, 'on_config_changed'):
                plugin_inst.instance.on_config_changed(config)
            
            logger.info(f"Configuration updated for plugin {plugin_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error setting config for plugin {plugin_name}: {e}")
            return False
    
    def validate_plugin_config(self, plugin_name: str, config: Dict[str, Any]) -> List[str]:
        """Validate plugin configuration"""
        if plugin_name not in self.plugin_info:
            return ["Plugin not found"]
        
        errors = []
        plugin_info = self.plugin_info[plugin_name]
        schema = plugin_info.config_schema
        
        for field, field_config in schema.items():
            if field_config.get('required', False) and field not in config:
                errors.append(f"Required field '{field}' is missing")
                continue
            
            if field in config:
                value = config[field]
                field_type = field_config.get('type')
                
                # Type validation
                if field_type == 'string' and not isinstance(value, str):
                    errors.append(f"Field '{field}' must be a string")
                elif field_type == 'number' and not isinstance(value, (int, float)):
                    errors.append(f"Field '{field}' must be a number")
                elif field_type == 'boolean' and not isinstance(value, bool):
                    errors.append(f"Field '{field}' must be a boolean")
                
                # Range validation
                if field_type in ['number', 'string']:
                    min_val = field_config.get('min')
                    max_val = field_config.get('max')
                    
                    if min_val is not None and value < min_val:
                        errors.append(f"Field '{field}' must be at least {min_val}")
                    
                    if max_val is not None and value > max_val:
                        errors.append(f"Field '{field}' must be at most {max_val}")
        
        return errors
    
    def get_plugin_statistics(self) -> Dict[str, Any]:
        """Get plugin statistics"""
        total_plugins = len(self.plugin_info)
        loaded_plugins = len(self.plugins)
        enabled_plugins = len([p for p in self.plugin_info.values() if p.enabled])
        
        hook_usage = {}
        for hook_name, hook in self.hooks.items():
            hook_usage[hook_name] = len(hook.callbacks)
        
        return {
            'total_plugins': total_plugins,
            'loaded_plugins': loaded_plugins,
            'enabled_plugins': enabled_plugins,
            'disabled_plugins': total_plugins - enabled_plugins,
            'failed_plugins': len([p for p in self.plugin_info.values() if p.error]),
            'hook_usage': hook_usage,
            'plugin_directory': str(self.plugin_directory),
            'auto_reload': self.auto_reload
        }
    
    def export_plugin_data(self, filepath: str, format: str = "json"):
        """Export plugin data"""
        try:
            data = {
                'plugins': self.get_all_plugins(),
                'statistics': self.get_plugin_statistics(),
                'hooks': {name: hook.description for name, hook in self.hooks.items()},
                'export_time': datetime.now().isoformat()
            }
            
            if format.lower() == "json":
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            elif format.lower() == "yaml":
                with open(filepath, 'w', encoding='utf-8') as f:
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            logger.info(f"Plugin data exported to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting plugin data: {e}")
            return False
    
    def cleanup(self):
        """Cleanup plugin manager"""
        try:
            # Stop file monitoring
            if self.observer:
                self.observer.stop()
                self.observer.join()
            
            # Cleanup plugins
            for plugin_name in list(self.plugins.keys()):
                self.disable_plugin(plugin_name)
            
            logger.info("Plugin manager cleaned up")
            
        except Exception as e:
            logger.error(f"Error during plugin manager cleanup: {e}")


class PluginFileHandler(FileSystemEventHandler):
    """File system event handler for plugin auto-reload"""
    
    def __init__(self, plugin_manager: PluginManager):
        self.plugin_manager = plugin_manager
        self.last_reload = 0
        self.reload_cooldown = 5  # seconds
    
    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return
        
        # Prevent rapid reloading
        current_time = time.time()
        if current_time - self.last_reload < self.reload_cooldown:
            return
        
        # Check if it's a plugin file
        file_path = Path(event.src_path)
        if file_path.suffix in ['.py', '.yaml', '.yml']:
            logger.info(f"Plugin file modified: {file_path}")
            
            # Reload affected plugin
            plugin_name = file_path.parent.name
            if plugin_name in self.plugin_manager.plugin_info:
                self.plugin_manager.reload_plugin(plugin_name)
            
            self.last_reload = current_time 