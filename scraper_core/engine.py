import json
#!/usr/bin/env python3
"""
Scrapelillo Core Engine - Motor Principal Optimizado

Este módulo implementa el motor principal que coordina todos los componentes
del sistema de manera eficiente y optimizada.
"""

import logging
import time
import threading
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue, PriorityQueue
import asyncio
from pathlib import Path

# Import existing components
from .config_manager import ConfigManager
from .cache_manager import CacheManager
from .html_analyzer import EnhancedHTMLAnalyzer
from .structured_data_extractor import StructuredDataExtractor
from .metrics import MetricsCollector
from .url_discovery import URLDiscoveryEngine

logger = logging.getLogger(__name__)


@dataclass
class AnalysisOptions:
    """Opciones de configuración para el análisis"""
    enable_cache: bool = True
    enable_parallel: bool = True
    max_workers: int = 4
    timeout: int = 30
    enable_structured_data: bool = True
    enable_metrics: bool = True
    force_refresh: bool = False
    user_agent: Optional[str] = None
    proxy: Optional[str] = None


@dataclass
class AnalysisResult:
    """Resultado del análisis de una URL"""
    url: str
    html_content: str
    analysis_time: float
    cache_hit: bool
    html_analysis: Optional[Any] = None
    structured_data: Optional[Any] = None
    metrics: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExtractionOptions:
    """Opciones para extracción de datos"""
    selectors: List[str] = field(default_factory=list)
    validation: bool = True
    cleaning: bool = True
    format_output: str = "json"
    include_metadata: bool = True


@dataclass
class ExtractionResult:
    """Resultado de la extracción de datos"""
    url: str
    extracted_data: Dict[str, Any]
    selectors_used: List[str]
    validation_errors: List[str]
    extraction_time: float
    success: bool


class EventObserver:
    """Sistema de observadores para actualizaciones en tiempo real"""
    
    def __init__(self):
        self.observers: Dict[str, List[callable]] = {}
        self.event_queue = Queue()
        self.running = False
        self.worker_thread = None
    
    def subscribe(self, event_type: str, callback: callable):
        """Suscribe un callback a un tipo de evento"""
        if event_type not in self.observers:
            self.observers[event_type] = []
        self.observers[event_type].append(callback)
    
    def unsubscribe(self, event_type: str, callback: callable):
        """Desuscribe un callback de un tipo de evento"""
        if event_type in self.observers:
            try:
                self.observers[event_type].remove(callback)
            except ValueError:
                pass
    
    def notify(self, event_type: str, data: Any):
        """Notifica un evento a todos los suscriptores"""
        self.event_queue.put((event_type, data))
    
    def start(self):
        """Inicia el worker thread para procesar eventos"""
        if not self.running:
            self.running = True
            self.worker_thread = threading.Thread(target=self._process_events, daemon=True)
            self.worker_thread.start()
    
    def stop(self):
        """Detiene el worker thread"""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join()
    
    def _process_events(self):
        """Procesa eventos en el worker thread"""
        while self.running:
            try:
                event_type, data = self.event_queue.get(timeout=1)
                if event_type in self.observers:
                    for callback in self.observers[event_type]:
                        try:
                            callback(data)
                        except Exception as e:
                            logger.error(f"Error in event callback: {e}")
            except Exception:
                continue


class TaskScheduler:
    """Programador de tareas con prioridades y colas"""
    
    def __init__(self):
        self.task_queue = PriorityQueue()
        self.running = False
        self.worker_threads = []
        self.max_workers = 4
    
    def schedule_task(self, priority: int, task: callable, *args, **kwargs):
        """Programa una tarea con prioridad"""
        self.task_queue.put((priority, task, args, kwargs))
    
    def start(self):
        """Inicia los worker threads"""
        if not self.running:
            self.running = True
            for i in range(self.max_workers):
                thread = threading.Thread(target=self._worker, daemon=True)
                thread.start()
                self.worker_threads.append(thread)
    
    def stop(self):
        """Detiene los worker threads"""
        self.running = False
        for thread in self.worker_threads:
            thread.join()
        self.worker_threads.clear()
    
    def _worker(self):
        """Worker thread que procesa tareas"""
        while self.running:
            try:
                priority, task, args, kwargs = self.task_queue.get(timeout=1)
                task(*args, **kwargs)
            except Exception:
                continue


class ScrapelilloEngine:
    """
    Motor principal optimizado que coordina todos los componentes del sistema
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Inicializa el motor principal
        
        Args:
            config_path: Ruta al archivo de configuración
        """
        # Configuración
        self.config = ConfigManager(config_path) if config_path else ConfigManager()
        
        # Componentes principales
        self.cache = CacheManager()
        self.analyzer = EnhancedHTMLAnalyzer(self.config)
        self.extractor = StructuredDataExtractor(self.config)
        self.metrics = MetricsCollector()
        
        # Sistema de eventos y tareas
        self.observer = EventObserver()
        self.scheduler = TaskScheduler()
        
        # Procesamiento paralelo
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.analysis_queue = Queue()
        
        # Estado interno
        self.running = False
        self.stats = {
            'total_analyses': 0,
            'cache_hits': 0,
            'total_time': 0.0,
            'errors': 0
        }
        
        # Inicializar componentes
        self._initialize_components()
        
        logger.info("Scrapelillo Engine inicializado")
    
    def _initialize_components(self):
        """Inicializa todos los componentes del sistema"""
        try:
            # Iniciar sistema de eventos
            self.observer.start()
            
            # Iniciar programador de tareas
            self.scheduler.start()
            
            # Configurar métricas
            self.metrics.start_collection()
            
            logger.info("Componentes inicializados correctamente")
            
        except Exception as e:
            logger.error(f"Error inicializando componentes: {e}")
    
    def analyze_url(self, url: str, options: Optional[AnalysisOptions] = None) -> AnalysisResult:
        """
        Analiza una URL de manera optimizada
        
        Args:
            url: URL a analizar
            options: Opciones de análisis
            
        Returns:
            AnalysisResult con los resultados
        """
        if options is None:
            options = AnalysisOptions()
        
        start_time = time.time()
        result = AnalysisResult(url=url, html_content="", analysis_time=0.0, cache_hit=False)
        
        try:
            # Verificar cache
            if options.enable_cache and not options.force_refresh:
                cached_content = self.cache.get(url)
                if cached_content:
                    result.cache_hit = True
                    result.html_content = cached_content
                    self.stats['cache_hits'] += 1
                    logger.info(f"Cache hit para {url}")
                else:
                    # Descargar contenido
                    result.html_content = self._fetch_url(url, options)
                    if options.enable_cache:
                        self.cache.set(url, result.html_content)
            else:
                # Descargar contenido sin cache
                result.html_content = self._fetch_url(url, options)
            
            # Análisis HTML
            if result.html_content:
                result.html_analysis = self.analyzer.analyze(result.html_content, url)
            
            # Datos estructurados
            if options.enable_structured_data:
                result.structured_data = self.extractor.extract_all(result.html_content, url)
            
            # Métricas
            if options.enable_metrics:
                result.metrics = self._collect_metrics(url, start_time)
            
            # Actualizar estadísticas
            self.stats['total_analyses'] += 1
            result.analysis_time = time.time() - start_time
            self.stats['total_time'] += result.analysis_time
            
            # Notificar evento
            self.observer.notify('analysis_complete', result)
            
            logger.info(f"Análisis completado para {url} en {result.analysis_time:.2f}s")
            
        except Exception as e:
            error_msg = f"Error analizando {url}: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)
            self.stats['errors'] += 1
        
        return result
    
    def analyze_urls_parallel(self, urls: List[str], options: Optional[AnalysisOptions] = None) -> List[AnalysisResult]:
        """
        Analiza múltiples URLs en paralelo
        
        Args:
            urls: Lista de URLs a analizar
            options: Opciones de análisis
            
        Returns:
            Lista de AnalysisResult
        """
        if options is None:
            options = AnalysisOptions()
        
        results = []
        futures = []
        
        # Programar análisis paralelos
        for url in urls:
            future = self.executor.submit(self.analyze_url, url, options)
            futures.append(future)
        
        # Recopilar resultados
        for future in as_completed(futures, timeout=options.timeout):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(f"Error en análisis paralelo: {e}")
                # Crear resultado de error
                error_result = AnalysisResult(
                    url="unknown",
                    html_content="",
                    analysis_time=0.0,
                    cache_hit=False,
                    errors=[str(e)]
                )
                results.append(error_result)
        
        return results
    
    def extract_data(self, html: str, selectors: List[str], options: Optional[ExtractionOptions] = None) -> ExtractionResult:
        """
        Extrae datos usando selectores específicos
        
        Args:
            html: Contenido HTML
            selectors: Lista de selectores CSS/XPath
            options: Opciones de extracción
            
        Returns:
            ExtractionResult con los datos extraídos
        """
        if options is None:
            options = ExtractionOptions()
        
        start_time = time.time()
        result = ExtractionResult(
            url="",
            extracted_data={},
            selectors_used=[],
            validation_errors=[],
            extraction_time=0.0,
            success=False
        )
        
        try:
            # Usar el extractor de datos estructurados
            extraction_result = self.extractor.extract_all(html, "")
            
            # Filtrar por selectores si se especifican
            if selectors:
                # Implementar filtrado por selectores personalizados
                pass
            
            result.extracted_data = {
                'items': [item.data for item in extraction_result.items],
                'summary': extraction_result.summary
            }
            result.selectors_used = selectors
            result.success = True
            
            # Validación
            if options.validation:
                result.validation_errors = extraction_result.errors
            
            result.extraction_time = time.time() - start_time
            
            logger.info(f"Extracción completada en {result.extraction_time:.2f}s")
            
        except Exception as e:
            error_msg = f"Error en extracción: {e}"
            logger.error(error_msg)
            result.validation_errors.append(error_msg)
        
        return result
    
    def discover_urls(self, base_url: str, options: Optional[Dict[str, Any]] = None) -> Any:
        """
        Descubre URLs usando el motor de descubrimiento
        
        Args:
            base_url: URL base para descubrir
            options: Opciones de descubrimiento
            
        Returns:
            Resultado del descubrimiento
        """
        if options is None:
            options = {}
        
        try:
            engine = URLDiscoveryEngine(
                base_url=base_url,
                delay=options.get('delay', 1.0),
                max_urls=options.get('max_urls'),
                user_agent=options.get('user_agent'),
                max_depth=options.get('max_depth', 3)
            )
            
            # Configurar callbacks
            def progress_callback(message, urls_found, endpoints_found):
                self.observer.notify('discovery_progress', {
                    'message': message,
                    'urls_found': urls_found,
                    'endpoints_found': endpoints_found
                })
            
            engine.set_callbacks(progress_callback=progress_callback)
            
            # Ejecutar descubrimiento
            result = engine.discover()
            
            # Fuzzing si está habilitado
            if options.get('fuzz_enabled') and options.get('fuzz_file'):
                engine.fuzz(options['fuzz_file'])
                result = engine.discover()  # Obtener resultado actualizado
            
            return result
            
        except Exception as e:
            logger.error(f"Error en descubrimiento de URLs: {e}")
            raise
    
    def _fetch_url(self, url: str, options: AnalysisOptions) -> str:
        """Descarga el contenido de una URL"""
        import requests
        
        headers = {}
        if options.user_agent:
            headers['User-Agent'] = options.user_agent
        
        proxies = {}
        if options.proxy:
            proxies['http'] = options.proxy
            proxies['https'] = options.proxy
        
        response = requests.get(url, headers=headers, proxies=proxies, timeout=options.timeout)
        response.raise_for_status()
        
        return response.text
    
    def _collect_metrics(self, url: str, start_time: float) -> Dict[str, Any]:
        """Recopila métricas del análisis"""
        return {
            'url': url,
            'analysis_time': time.time() - start_time,
            'timestamp': time.time(),
            'cache_hit': False,
            'content_length': 0
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del motor"""
        return {
            **self.stats,
            'cache_stats': self.cache.get_stats(),
            'metrics_stats': self.metrics.get_summary()
        }
    
    def shutdown(self):
        """Cierra el motor y libera recursos"""
        logger.info("Cerrando Scrapelillo Engine...")
        
        # Detener componentes
        self.observer.stop()
        self.scheduler.stop()
        self.executor.shutdown(wait=True)
        
        # Cerrar métricas
        self.metrics.stop_collection()
        
        logger.info("Scrapelillo Engine cerrado")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.shutdown() 