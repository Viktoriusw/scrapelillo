#!/usr/bin/env python3
"""
Smart HTML Analyzer - Analizador HTML Inteligente

Analizador HTML optimizado con procesamiento incremental, cache inteligente,
análisis paralelo y detección automática de patrones.
"""

import logging
import time
import threading
from typing import Dict, List, Any, Optional, Union, Tuple, Set
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import hashlib
import json
from collections import defaultdict, Counter
import re

from bs4 import BeautifulSoup, Tag, NavigableString
from readability import Document
import lxml.etree as etree

logger = logging.getLogger(__name__)


@dataclass
class ElementPattern:
    """Patrón detectado en elementos HTML"""
    pattern_type: str  # 'repetitive', 'semantic', 'structural', 'content'
    elements: List[Tag]
    confidence: float
    selector: str
    description: str


@dataclass
class IncrementalAnalysis:
    """Análisis incremental que se actualiza en tiempo real"""
    url: str
    html_hash: str
    elements_analyzed: int
    patterns_detected: List[ElementPattern]
    content_blocks: List[Dict[str, Any]]
    semantic_structure: Dict[str, Any]
    accessibility_score: float
    performance_score: float
    last_update: float
    is_complete: bool = False


@dataclass
class PatternResult:
    """Resultado de la detección de patrones"""
    patterns: List[ElementPattern]
    total_elements: int
    pattern_coverage: float
    suggestions: List[str]


class LRUCache:
    """Cache LRU optimizado para análisis HTML"""
    
    def __init__(self, maxsize: int = 1000):
        self.maxsize = maxsize
        self.cache = {}
        self.access_order = []
        self.lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Obtiene un elemento del cache"""
        with self.lock:
            if key in self.cache:
                # Mover al final (más reciente)
                self.access_order.remove(key)
                self.access_order.append(key)
                return self.cache[key]
            return None
    
    def set(self, key: str, value: Any):
        """Establece un elemento en el cache"""
        with self.lock:
            if key in self.cache:
                # Actualizar elemento existente
                self.access_order.remove(key)
            elif len(self.cache) >= self.maxsize:
                # Eliminar elemento menos usado
                oldest = self.access_order.pop(0)
                del self.cache[oldest]
            
            self.cache[key] = value
            self.access_order.append(key)
    
    def clear(self):
        """Limpia el cache"""
        with self.lock:
            self.cache.clear()
            self.access_order.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del cache"""
        with self.lock:
            return {
                'size': len(self.cache),
                'maxsize': self.maxsize,
                'hit_rate': 0.0  # TODO: Implementar tracking de hits
            }


class PatternDetector:
    """Detector de patrones en elementos HTML"""
    
    def __init__(self):
        self.pattern_rules = {
            'repetitive': [
                self._detect_list_patterns,
                self._detect_table_patterns,
                self._detect_card_patterns
            ],
            'semantic': [
                self._detect_article_patterns,
                self._detect_navigation_patterns,
                self._detect_form_patterns
            ],
            'structural': [
                self._detect_grid_patterns,
                self._detect_layout_patterns,
                self._detect_component_patterns
            ],
            'content': [
                self._detect_text_patterns,
                self._detect_link_patterns,
                self._detect_image_patterns
            ]
        }
    
    def detect_patterns(self, soup: BeautifulSoup) -> PatternResult:
        """Detecta patrones en el HTML"""
        patterns = []
        total_elements = len(soup.find_all())
        
        for pattern_type, detectors in self.pattern_rules.items():
            for detector in detectors:
                try:
                    detected_patterns = detector(soup)
                    patterns.extend(detected_patterns)
                except Exception as e:
                    logger.warning(f"Error en detector {detector.__name__}: {e}")
        
        # Calcular cobertura
        covered_elements = set()
        for pattern in patterns:
            covered_elements.update(pattern.elements)
        
        pattern_coverage = len(covered_elements) / total_elements if total_elements > 0 else 0
        
        # Generar sugerencias
        suggestions = self._generate_suggestions(patterns)
        
        return PatternResult(
            patterns=patterns,
            total_elements=total_elements,
            pattern_coverage=pattern_coverage,
            suggestions=suggestions
        )
    
    def _detect_list_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones de listas"""
        patterns = []
        
        # Listas ordenadas y no ordenadas
        for list_type in ['ul', 'ol']:
            lists = soup.find_all(list_type)
            if len(lists) >= 2:
                # Verificar si tienen estructura similar
                for i, lst in enumerate(lists):
                    items = lst.find_all('li')
                    if len(items) >= 3:
                        # Analizar estructura de items
                        item_texts = [item.get_text(strip=True) for item in items]
                        if self._is_consistent_pattern(item_texts):
                            patterns.append(ElementPattern(
                                pattern_type='repetitive',
                                elements=[lst],
                                confidence=0.8,
                                selector=f"{list_type}:nth-of-type({i+1})",
                                description=f"Lista {list_type} con patrón consistente"
                            ))
        
        return patterns
    
    def _detect_table_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones en tablas"""
        patterns = []
        tables = soup.find_all('table')
        
        for table in tables:
            rows = table.find_all('tr')
            if len(rows) >= 3:
                # Verificar estructura de columnas
                headers = rows[0].find_all(['th', 'td'])
                if len(headers) >= 2:
                    patterns.append(ElementPattern(
                        pattern_type='structural',
                        elements=[table],
                        confidence=0.9,
                        selector="table",
                        description="Tabla con estructura consistente"
                    ))
        
        return patterns
    
    def _detect_card_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones de tarjetas/cards"""
        patterns = []
        
        # Buscar elementos que podrían ser cards
        card_selectors = [
            '.card', '.item', '.product', '.article', '.post',
            '[class*="card"]', '[class*="item"]', '[class*="product"]'
        ]
        
        for selector in card_selectors:
            cards = soup.select(selector)
            if len(cards) >= 2:
                # Verificar estructura similar
                if self._has_similar_structure(cards):
                    patterns.append(ElementPattern(
                        pattern_type='repetitive',
                        elements=cards,
                        confidence=0.7,
                        selector=selector,
                        description=f"Patrón de tarjetas: {selector}"
                    ))
        
        return patterns
    
    def _detect_article_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones de artículos"""
        patterns = []
        
        articles = soup.find_all(['article', '.article', '.post', '.entry'])
        if len(articles) >= 2:
            patterns.append(ElementPattern(
                pattern_type='semantic',
                elements=articles,
                confidence=0.8,
                selector="article, .article, .post, .entry",
                description="Patrón de artículos"
            ))
        
        return patterns
    
    def _detect_navigation_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones de navegación"""
        patterns = []
        
        nav_elements = soup.find_all(['nav', '.nav', '.navigation', '.menu'])
        if nav_elements:
            patterns.append(ElementPattern(
                pattern_type='semantic',
                elements=nav_elements,
                confidence=0.9,
                selector="nav, .nav, .navigation, .menu",
                description="Elementos de navegación"
            ))
        
        return patterns
    
    def _detect_form_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones de formularios"""
        patterns = []
        
        forms = soup.find_all('form')
        if forms:
            patterns.append(ElementPattern(
                pattern_type='semantic',
                elements=forms,
                confidence=0.9,
                selector="form",
                description="Formularios detectados"
            ))
        
        return patterns
    
    def _detect_grid_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones de grid"""
        patterns = []
        
        grid_selectors = [
            '.grid', '.row', '.col', '.flex', '.flexbox',
            '[class*="grid"]', '[class*="row"]', '[class*="col"]'
        ]
        
        for selector in grid_selectors:
            elements = soup.select(selector)
            if len(elements) >= 3:
                patterns.append(ElementPattern(
                    pattern_type='structural',
                    elements=elements,
                    confidence=0.6,
                    selector=selector,
                    description=f"Patrón de grid: {selector}"
                ))
        
        return patterns
    
    def _detect_layout_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones de layout"""
        patterns = []
        
        layout_selectors = [
            '.header', '.footer', '.sidebar', '.main', '.content',
            'header', 'footer', 'aside', 'main'
        ]
        
        for selector in layout_selectors:
            elements = soup.select(selector)
            if elements:
                patterns.append(ElementPattern(
                    pattern_type='structural',
                    elements=elements,
                    confidence=0.8,
                    selector=selector,
                    description=f"Elemento de layout: {selector}"
                ))
        
        return patterns
    
    def _detect_component_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones de componentes"""
        patterns = []
        
        # Buscar elementos que se repiten con estructura similar
        all_elements = soup.find_all()
        element_counts = Counter([elem.name for elem in all_elements])
        
        for element_name, count in element_counts.items():
            if count >= 3 and element_name not in ['div', 'span', 'p']:
                elements = soup.find_all(element_name)
                if self._has_similar_structure(elements):
                    patterns.append(ElementPattern(
                        pattern_type='structural',
                        elements=elements,
                        confidence=0.7,
                        selector=element_name,
                        description=f"Componente repetitivo: {element_name}"
                    ))
        
        return patterns
    
    def _detect_text_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones en texto"""
        patterns = []
        
        # Párrafos con estructura similar
        paragraphs = soup.find_all('p')
        if len(paragraphs) >= 3:
            text_lengths = [len(p.get_text(strip=True)) for p in paragraphs]
            if self._is_consistent_pattern(text_lengths):
                patterns.append(ElementPattern(
                    pattern_type='content',
                    elements=paragraphs,
                    confidence=0.6,
                    selector="p",
                    description="Párrafos con longitud consistente"
                ))
        
        return patterns
    
    def _detect_link_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones en enlaces"""
        patterns = []
        
        links = soup.find_all('a', href=True)
        if len(links) >= 5:
            # Agrupar por dominio
            domains = defaultdict(list)
            for link in links:
                href = link.get('href', '')
                if href.startswith('http'):
                    from urllib.parse import urlparse
                    domain = urlparse(href).netloc
                    domains[domain].append(link)
            
            # Patrones por dominio
            for domain, domain_links in domains.items():
                if len(domain_links) >= 3:
                    patterns.append(ElementPattern(
                        pattern_type='content',
                        elements=domain_links,
                        confidence=0.8,
                        selector=f"a[href*='{domain}']",
                        description=f"Enlaces al dominio: {domain}"
                    ))
        
        return patterns
    
    def _detect_image_patterns(self, soup: BeautifulSoup) -> List[ElementPattern]:
        """Detecta patrones en imágenes"""
        patterns = []
        
        images = soup.find_all('img')
        if len(images) >= 3:
            # Verificar si tienen atributos similares
            alt_texts = [img.get('alt', '') for img in images]
            if any(alt_texts):
                patterns.append(ElementPattern(
                    pattern_type='content',
                    elements=images,
                    confidence=0.7,
                    selector="img",
                    description="Imágenes con atributos alt"
                ))
        
        return patterns
    
    def _is_consistent_pattern(self, values: List[Any]) -> bool:
        """Verifica si una lista tiene un patrón consistente"""
        if len(values) < 3:
            return False
        
        # Verificar si los valores son similares en longitud o estructura
        if isinstance(values[0], str):
            lengths = [len(v) for v in values]
            avg_length = sum(lengths) / len(lengths)
            return all(abs(len(v) - avg_length) < avg_length * 0.5 for v in values)
        
        return False
    
    def _has_similar_structure(self, elements: List[Tag]) -> bool:
        """Verifica si elementos tienen estructura similar"""
        if len(elements) < 2:
            return False
        
        # Comparar estructura básica
        first_structure = self._get_element_structure(elements[0])
        for element in elements[1:]:
            if self._get_element_structure(element) != first_structure:
                return False
        
        return True
    
    def _get_element_structure(self, element: Tag) -> str:
        """Obtiene la estructura básica de un elemento"""
        structure = []
        for child in element.children:
            if hasattr(child, 'name'):
                structure.append(child.name)
        return ','.join(structure)
    
    def _generate_suggestions(self, patterns: List[ElementPattern]) -> List[str]:
        """Genera sugerencias basadas en los patrones detectados"""
        suggestions = []
        
        pattern_types = Counter([p.pattern_type for p in patterns])
        
        if pattern_types['repetitive'] > 0:
            suggestions.append("Se detectaron elementos repetitivos. Considera usar CSS Grid o Flexbox.")
        
        if pattern_types['semantic'] > 0:
            suggestions.append("Se detectaron elementos semánticos. La estructura HTML es buena.")
        
        if pattern_types['structural'] > 0:
            suggestions.append("Se detectaron patrones estructurales. Considera crear componentes reutilizables.")
        
        if pattern_types['content'] > 0:
            suggestions.append("Se detectaron patrones de contenido. Considera optimizar la estructura de datos.")
        
        return suggestions


class ParallelProcessor:
    """Procesador paralelo para análisis HTML"""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.chunk_size = 1000
    
    def process_html_chunks(self, html: str) -> List[Dict[str, Any]]:
        """Procesa HTML en chunks para mejor rendimiento"""
        soup = BeautifulSoup(html, 'lxml')
        all_elements = soup.find_all()
        
        # Dividir elementos en chunks
        chunks = [all_elements[i:i + self.chunk_size] 
                 for i in range(0, len(all_elements), self.chunk_size)]
        
        # Procesar chunks en paralelo
        futures = []
        for chunk in chunks:
            future = self.executor.submit(self._process_chunk, chunk)
            futures.append(future)
        
        # Recopilar resultados
        results = []
        for future in as_completed(futures):
            try:
                chunk_result = future.result()
                results.extend(chunk_result)
            except Exception as e:
                logger.error(f"Error procesando chunk: {e}")
        
        return results
    
    def _process_chunk(self, elements: List[Tag]) -> List[Dict[str, Any]]:
        """Procesa un chunk de elementos"""
        results = []
        
        for element in elements:
            try:
                result = {
                    'tag': element.name,
                    'attributes': dict(element.attrs),
                    'text_length': len(element.get_text(strip=True)),
                    'children_count': len(element.find_all()),
                    'depth': self._calculate_depth(element)
                }
                results.append(result)
            except Exception as e:
                logger.warning(f"Error procesando elemento {element.name}: {e}")
        
        return results
    
    def _calculate_depth(self, element: Tag) -> int:
        """Calcula la profundidad de un elemento"""
        depth = 0
        parent = element.parent
        while parent and hasattr(parent, 'name'):
            depth += 1
            parent = parent.parent
        return depth
    
    def shutdown(self):
        """Cierra el procesador paralelo"""
        self.executor.shutdown(wait=True)


class SmartHTMLAnalyzer:
    """
    Analizador HTML inteligente con procesamiento optimizado
    """
    
    def __init__(self, config_manager=None):
        """
        Inicializa el analizador inteligente
        
        Args:
            config_manager: Gestor de configuración
        """
        self.config = config_manager
        
        # Componentes
        self.cache = LRUCache(maxsize=1000)
        self.pattern_detector = PatternDetector()
        self.parallel_processor = ParallelProcessor()
        
        # Configuración
        self.enable_cache = True
        self.enable_parallel = True
        self.enable_pattern_detection = True
        
        if self.config:
            analyzer_config = self.config.get_section('smart_analyzer', {})
            self.enable_cache = analyzer_config.get('enable_cache', True)
            self.enable_parallel = analyzer_config.get('enable_parallel', True)
            self.enable_pattern_detection = analyzer_config.get('enable_pattern_detection', True)
        
        logger.info("Smart HTML Analyzer inicializado")
    
    def analyze_incremental(self, html: str, url: str = "") -> IncrementalAnalysis:
        """
        Análisis incremental que se actualiza en tiempo real
        
        Args:
            html: Contenido HTML
            url: URL de la página
            
        Returns:
            IncrementalAnalysis con resultados
        """
        start_time = time.time()
        
        # Generar hash del HTML
        html_hash = hashlib.md5(html.encode()).hexdigest()
        
        # Verificar cache
        if self.enable_cache:
            cached_result = self.cache.get(html_hash)
            if cached_result:
                logger.info("Resultado encontrado en cache")
                return cached_result
        
        # Crear análisis incremental
        analysis = IncrementalAnalysis(
            url=url,
            html_hash=html_hash,
            elements_analyzed=0,
            patterns_detected=[],
            content_blocks=[],
            semantic_structure={},
            accessibility_score=0.0,
            performance_score=0.0,
            last_update=start_time
        )
        
        try:
            # Parse HTML
            soup = BeautifulSoup(html, 'lxml')
            
            # Análisis paralelo de elementos
            if self.enable_parallel:
                element_results = self.parallel_processor.process_html_chunks(html)
                analysis.elements_analyzed = len(element_results)
            
            # Detección de patrones
            if self.enable_pattern_detection:
                pattern_result = self.pattern_detector.detect_patterns(soup)
                analysis.patterns_detected = pattern_result.patterns
            
            # Análisis semántico
            analysis.semantic_structure = self._analyze_semantic_structure(soup)
            
            # Análisis de accesibilidad
            analysis.accessibility_score = self._calculate_accessibility_score(soup)
            
            # Análisis de rendimiento
            analysis.performance_score = self._calculate_performance_score(soup)
            
            # Detectar bloques de contenido
            analysis.content_blocks = self._detect_content_blocks(soup)
            
            # Marcar como completo
            analysis.is_complete = True
            analysis.last_update = time.time()
            
            # Guardar en cache
            if self.enable_cache:
                self.cache.set(html_hash, analysis)
            
            logger.info(f"Análisis incremental completado en {time.time() - start_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Error en análisis incremental: {e}")
            analysis.is_complete = False
        
        return analysis
    
    def detect_patterns(self, elements: List[Tag]) -> PatternResult:
        """
        Detecta patrones en una lista de elementos
        
        Args:
            elements: Lista de elementos HTML
            
        Returns:
            PatternResult con patrones detectados
        """
        if not self.enable_pattern_detection:
            return PatternResult([], 0, 0.0, [])
        
        # Crear un soup temporal para el análisis
        temp_html = f"<html>{''.join(str(elem) for elem in elements)}</html>"
        soup = BeautifulSoup(temp_html, 'lxml')
        
        return self.pattern_detector.detect_patterns(soup)
    
    def _analyze_semantic_structure(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analiza la estructura semántica del HTML"""
        structure = {
            'headings': [],
            'sections': [],
            'articles': [],
            'navigation': [],
            'forms': [],
            'tables': []
        }
        
        # Headings
        for i in range(1, 7):
            headings = soup.find_all(f'h{i}')
            structure['headings'].extend([{
                'level': i,
                'text': h.get_text(strip=True),
                'id': h.get('id', '')
            } for h in headings])
        
        # Sections
        sections = soup.find_all(['section', 'article', 'aside', 'nav'])
        structure['sections'] = [{
            'tag': s.name,
            'id': s.get('id', ''),
            'class': s.get('class', [])
        } for s in sections]
        
        # Forms
        forms = soup.find_all('form')
        structure['forms'] = [{
            'action': f.get('action', ''),
            'method': f.get('method', 'get'),
            'inputs': len(f.find_all('input'))
        } for f in forms]
        
        # Tables
        tables = soup.find_all('table')
        structure['tables'] = [{
            'rows': len(t.find_all('tr')),
            'headers': len(t.find_all('th'))
        } for t in tables]
        
        return structure
    
    def _calculate_accessibility_score(self, soup: BeautifulSoup) -> float:
        """Calcula el score de accesibilidad"""
        score = 100.0
        total_checks = 0
        
        # Imágenes sin alt
        images = soup.find_all('img')
        for img in images:
            total_checks += 1
            if not img.get('alt'):
                score -= 5
        
        # Enlaces sin texto
        links = soup.find_all('a')
        for link in links:
            total_checks += 1
            if not link.get_text(strip=True):
                score -= 3
        
        # Formularios sin labels
        inputs = soup.find_all('input')
        for inp in inputs:
            total_checks += 1
            if not inp.get('id') and not inp.get('aria-label'):
                score -= 2
        
        return max(0.0, score) if total_checks > 0 else 100.0
    
    def _calculate_performance_score(self, soup: BeautifulSoup) -> float:
        """Calcula el score de rendimiento"""
        score = 100.0
        
        # Imágenes sin optimizar
        images = soup.find_all('img')
        for img in images:
            if not img.get('loading') == 'lazy':
                score -= 1
        
        # Scripts bloqueantes
        scripts = soup.find_all('script')
        for script in scripts:
            if not script.get('async') and not script.get('defer'):
                score -= 2
        
        # CSS inline excesivo
        elements_with_style = soup.find_all(attrs={'style': True})
        if len(elements_with_style) > 10:
            score -= 5
        
        return max(0.0, score)
    
    def _detect_content_blocks(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Detecta bloques de contenido principales"""
        blocks = []
        
        # Usar readability para detectar contenido principal
        try:
            doc = Document(str(soup))
            main_content = doc.summary()
            
            if main_content:
                blocks.append({
                    'type': 'main_content',
                    'content': main_content,
                    'word_count': len(main_content.split()),
                    'confidence': 0.9
                })
        except Exception as e:
            logger.warning(f"Error usando readability: {e}")
        
        # Detectar otros bloques importantes
        important_selectors = [
            'main', 'article', '.content', '.main', '.post',
            'nav', '.navigation', '.menu',
            'aside', '.sidebar', '.widget'
        ]
        
        for selector in important_selectors:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                if len(text) > 50:  # Solo bloques con contenido significativo
                    blocks.append({
                        'type': selector,
                        'content': text[:200] + '...' if len(text) > 200 else text,
                        'word_count': len(text.split()),
                        'confidence': 0.7
                    })
        
        return blocks
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del cache"""
        return self.cache.get_stats()
    
    def clear_cache(self):
        """Limpia el cache"""
        self.cache.clear()
    
    def shutdown(self):
        """Cierra el analizador"""
        self.parallel_processor.shutdown()
        logger.info("Smart HTML Analyzer cerrado") 