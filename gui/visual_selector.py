#!/usr/bin/env python3
"""
Visual Element Selector - Selector Visual de Elementos HTML

Selector visual que permite seleccionar elementos HTML de manera intuitiva
con hover, click y drag & drop.
"""

import tkinter as tk
from tkinter import ttk
import logging
import time
from typing import Dict, List, Any, Optional, Callable, Tuple
from dataclasses import dataclass, field
import re
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


@dataclass
class ElementSelection:
    """Representa una selección de elementos"""
    elements: List[Tag]
    selectors: List[str]
    element_type: str
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionEvent:
    """Evento de selección"""
    event_type: str  # 'hover', 'click', 'drag_start', 'drag_end'
    element: Optional[Tag]
    position: Tuple[int, int]
    timestamp: float


class HighlightManager:
    """Gestor de resaltado de elementos"""
    
    def __init__(self, text_widget: tk.Text):
        self.text_widget = text_widget
        self.current_highlight = None
        self.highlight_tags = {
            'hover': 'hover_highlight',
            'selected': 'selected_highlight',
            'drag': 'drag_highlight'
        }
        
        # Configurar tags de resaltado
        self._setup_highlight_tags()
    
    def _setup_highlight_tags(self):
        """Configura los tags de resaltado"""
        # Hover highlight (amarillo claro)
        self.text_widget.tag_configure(
            self.highlight_tags['hover'],
            background='#FFF3CD',
            borderwidth=1,
            relief='solid'
        )
        
        # Selected highlight (azul claro)
        self.text_widget.tag_configure(
            self.highlight_tags['selected'],
            background='#D1ECF1',
            borderwidth=2,
            relief='solid'
        )
        
        # Drag highlight (verde claro)
        self.text_widget.tag_configure(
            self.highlight_tags['drag'],
            background='#D4EDDA',
            borderwidth=2,
            relief='solid'
        )
    
    def highlight_element(self, element: Tag, highlight_type: str = 'hover'):
        """Resalta un elemento en el texto"""
        # Limpiar highlight anterior del mismo tipo
        self.clear_highlight(highlight_type)
        
        # Encontrar el rango del elemento en el texto
        start_pos, end_pos = self._find_element_range(element)
        if start_pos and end_pos:
            tag_name = self.highlight_tags.get(highlight_type, 'hover')
            self.text_widget.tag_add(tag_name, start_pos, end_pos)
            self.current_highlight = (highlight_type, start_pos, end_pos)
    
    def clear_highlight(self, highlight_type: str = None):
        """Limpia el resaltado"""
        if highlight_type:
            tag_name = self.highlight_tags.get(highlight_type)
            if tag_name:
                self.text_widget.tag_remove(tag_name, '1.0', tk.END)
        else:
            # Limpiar todos los highlights
            for tag_name in self.highlight_tags.values():
                self.text_widget.tag_remove(tag_name, '1.0', tk.END)
    
    def _find_element_range(self, element: Tag) -> Tuple[Optional[str], Optional[str]]:
        """Encuentra el rango de un elemento en el texto"""
        try:
            # Convertir el elemento a string
            element_str = str(element)
            
            # Buscar en el contenido del texto
            content = self.text_widget.get('1.0', tk.END)
            start_idx = content.find(element_str)
            
            if start_idx != -1:
                # Convertir índice a posición de línea.columna
                start_pos = self.text_widget.index(f"1.0+{start_idx}c")
                end_pos = self.text_widget.index(f"1.0+{start_idx + len(element_str)}c")
                return start_pos, end_pos
            
        except Exception as e:
            logger.warning(f"Error encontrando rango del elemento: {e}")
        
        return None, None


class SelectionManager:
    """Gestor de selecciones de elementos"""
    
    def __init__(self):
        self.selected_elements: List[Tag] = []
        self.selection_history: List[ElementSelection] = []
        self.callbacks: Dict[str, List[Callable]] = {
            'selection_changed': [],
            'element_hovered': [],
            'element_clicked': []
        }
    
    def add_element(self, element: Tag):
        """Añade un elemento a la selección"""
        if element not in self.selected_elements:
            self.selected_elements.append(element)
            self._notify_callbacks('selection_changed', self.selected_elements)
    
    def remove_element(self, element: Tag):
        """Remueve un elemento de la selección"""
        if element in self.selected_elements:
            self.selected_elements.remove(element)
            self._notify_callbacks('selection_changed', self.selected_elements)
    
    def clear_selection(self):
        """Limpia toda la selección"""
        self.selected_elements.clear()
        self._notify_callbacks('selection_changed', self.selected_elements)
    
    def get_selection(self) -> ElementSelection:
        """Obtiene la selección actual"""
        if not self.selected_elements:
            return ElementSelection([], [], 'empty', 0.0)
        
        # Generar selectores para los elementos seleccionados
        selectors = self._generate_selectors(self.selected_elements)
        
        # Determinar tipo de elemento
        element_type = self._determine_element_type(self.selected_elements)
        
        # Calcular confianza
        confidence = self._calculate_confidence(self.selected_elements)
        
        return ElementSelection(
            elements=self.selected_elements.copy(),
            selectors=selectors,
            element_type=element_type,
            confidence=confidence
        )
    
    def save_selection(self, name: str = None):
        """Guarda la selección actual en el historial"""
        selection = self.get_selection()
        if selection.elements:
            if name:
                selection.metadata['name'] = name
            selection.metadata['timestamp'] = time.time()
            self.selection_history.append(selection)
    
    def register_callback(self, event_type: str, callback: Callable):
        """Registra un callback para eventos de selección"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
    
    def _notify_callbacks(self, event_type: str, data: Any):
        """Notifica a los callbacks registrados"""
        if event_type in self.callbacks:
            for callback in self.callbacks[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Error en callback {event_type}: {e}")
    
    def _generate_selectors(self, elements: List[Tag]) -> List[str]:
        """Genera selectores CSS para los elementos"""
        selectors = []
        
        for element in elements:
            # Selector por tag
            selector = element.name
            
            # Añadir ID si existe
            if element.get('id'):
                selector = f"#{element['id']}"
            
            # Añadir clases si existen
            elif element.get('class'):
                classes = ' '.join(element['class'])
                selector = f"{element.name}.{classes.replace(' ', '.')}"
            
            # Añadir atributos específicos
            elif element.get('data-testid'):
                selector = f"[data-testid='{element['data-testid']}']"
            
            selectors.append(selector)
        
        return selectors
    
    def _determine_element_type(self, elements: List[Tag]) -> str:
        """Determina el tipo de elemento"""
        if not elements:
            return 'empty'
        
        # Contar tipos de elementos
        type_counts = {}
        for element in elements:
            element_type = self._classify_element(element)
            type_counts[element_type] = type_counts.get(element_type, 0) + 1
        
        # Retornar el tipo más común
        if type_counts:
            return max(type_counts, key=type_counts.get)
        
        return 'unknown'
    
    def _classify_element(self, element: Tag) -> str:
        """Clasifica un elemento individual"""
        tag_name = element.name.lower()
        
        # Elementos de texto
        if tag_name in ['p', 'span', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            return 'text'
        
        # Enlaces
        elif tag_name == 'a':
            return 'link'
        
        # Imágenes
        elif tag_name == 'img':
            return 'image'
        
        # Formularios
        elif tag_name in ['input', 'textarea', 'select', 'button']:
            return 'form'
        
        # Tablas
        elif tag_name in ['table', 'tr', 'td', 'th']:
            return 'table'
        
        # Listas
        elif tag_name in ['ul', 'ol', 'li']:
            return 'list'
        
        # Contenedores
        elif tag_name in ['section', 'article', 'aside', 'nav', 'header', 'footer']:
            return 'container'
        
        return 'other'
    
    def _calculate_confidence(self, elements: List[Tag]) -> float:
        """Calcula la confianza de la selección"""
        if not elements:
            return 0.0
        
        # Factores que aumentan la confianza
        confidence = 0.5  # Base
        
        # Elementos con ID
        elements_with_id = sum(1 for e in elements if e.get('id'))
        confidence += (elements_with_id / len(elements)) * 0.3
        
        # Elementos con clases específicas
        elements_with_classes = sum(1 for e in elements if e.get('class'))
        confidence += (elements_with_classes / len(elements)) * 0.2
        
        # Consistencia de tipo
        element_types = [self._classify_element(e) for e in elements]
        if len(set(element_types)) == 1:
            confidence += 0.2
        
        return min(1.0, confidence)


class VisualElementSelector:
    """
    Selector visual de elementos HTML con interfaz intuitiva
    """
    
    def __init__(self, html_preview_widget: tk.Text, soup: BeautifulSoup):
        """
        Inicializa el selector visual
        
        Args:
            html_preview_widget: Widget de texto para la vista previa HTML
            soup: Objeto BeautifulSoup del HTML
        """
        self.html_widget = html_preview_widget
        self.soup = soup
        self.selection_manager = SelectionManager()
        self.highlight_manager = HighlightManager(html_preview_widget)
        
        # Estado del selector
        self.is_enabled = False
        self.drag_mode = False
        self.drag_start = None
        self.drag_end = None
        self.current_hover_element = None
        
        # Mapeo de posiciones a elementos
        self.position_to_element = {}
        self.element_to_position = {}
        
        # Configurar eventos
        self._setup_events()
        
        # Construir mapeo de elementos
        self._build_element_mapping()
        
        logger.info("Visual Element Selector inicializado")
    
    def enable_visual_selection(self):
        """Habilita la selección visual de elementos"""
        self.is_enabled = True
        self.html_widget.config(cursor="crosshair")
        logger.info("Selección visual habilitada")
    
    def disable_visual_selection(self):
        """Deshabilita la selección visual de elementos"""
        self.is_enabled = False
        self.html_widget.config(cursor="")
        self.highlight_manager.clear_highlight()
        logger.info("Selección visual deshabilitada")
    
    def _setup_events(self):
        """Configura los eventos del mouse"""
        # Eventos de mouse
        self.html_widget.bind("<Motion>", self._on_mouse_motion)
        self.html_widget.bind("<Button-1>", self._on_mouse_click)
        self.html_widget.bind("<ButtonRelease-1>", self._on_mouse_release)
        self.html_widget.bind("<Leave>", self._on_mouse_leave)
        
        # Eventos de teclado
        self.html_widget.bind("<Escape>", self._on_escape)
        self.html_widget.bind("<Control-a>", self._on_select_all)
        self.html_widget.bind("<Control-d>", self._on_deselect_all)
    
    def _build_element_mapping(self):
        """Construye el mapeo de posiciones a elementos"""
        try:
            # Obtener todas las posiciones de elementos en el texto
            content = self.html_widget.get('1.0', tk.END)
            
            # Encontrar todas las etiquetas HTML
            tag_pattern = r'<([^>]+)>'
            matches = list(re.finditer(tag_pattern, content))
            
            for match in matches:
                tag_text = match.group(0)
                start_pos = match.start()
                end_pos = match.end()
                
                # Intentar parsear el elemento
                try:
                    # Crear un soup temporal para parsear el elemento
                    temp_soup = BeautifulSoup(tag_text, 'html.parser')
                    if temp_soup.find():
                        element = temp_soup.find()
                        
                        # Mapear posición a elemento
                        start_index = self.html_widget.index(f"1.0+{start_pos}c")
                        end_index = self.html_widget.index(f"1.0+{end_pos}c")
                        
                        self.position_to_element[(start_index, end_index)] = element
                        self.element_to_position[element] = (start_index, end_index)
                
                except Exception as e:
                    logger.debug(f"Error parseando elemento: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error construyendo mapeo de elementos: {e}")
    
    def _on_mouse_motion(self, event):
        """Maneja el movimiento del mouse"""
        if not self.is_enabled:
            return
        
        # Obtener posición del cursor
        cursor_pos = self.html_widget.index(f"@{event.x},{event.y}")
        
        # Encontrar elemento bajo el cursor
        element = self._find_element_at_position(cursor_pos)
        
        if element and element != self.current_hover_element:
            self.current_hover_element = element
            self.highlight_manager.highlight_element(element, 'hover')
            self.selection_manager._notify_callbacks('element_hovered', element)
    
    def _on_mouse_click(self, event):
        """Maneja el click del mouse"""
        if not self.is_enabled:
            return
        
        # Obtener posición del cursor
        cursor_pos = self.html_widget.index(f"@{event.x},{event.y}")
        
        # Encontrar elemento bajo el cursor
        element = self._find_element_at_position(cursor_pos)
        
        if element:
            # Iniciar modo drag
            self.drag_mode = True
            self.drag_start = cursor_pos
            self.drag_end = cursor_pos
            
            # Seleccionar elemento
            self.selection_manager.add_element(element)
            self.highlight_manager.highlight_element(element, 'selected')
            self.selection_manager._notify_callbacks('element_clicked', element)
    
    def _on_mouse_release(self, event):
        """Maneja la liberación del mouse"""
        if not self.is_enabled or not self.drag_mode:
            return
        
        # Finalizar modo drag
        cursor_pos = self.html_widget.index(f"@{event.x},{event.y}")
        self.drag_end = cursor_pos
        self.drag_mode = False
        
        # Seleccionar elementos en el rango de drag
        if self.drag_start and self.drag_end:
            self._select_elements_in_range(self.drag_start, self.drag_end)
    
    def _on_mouse_leave(self, event):
        """Maneja cuando el mouse sale del widget"""
        if self.is_enabled:
            self.highlight_manager.clear_highlight('hover')
            self.current_hover_element = None
    
    def _on_escape(self, event):
        """Maneja la tecla Escape"""
        if self.is_enabled:
            self.selection_manager.clear_selection()
            self.highlight_manager.clear_highlight()
    
    def _on_select_all(self, event):
        """Selecciona todos los elementos"""
        if self.is_enabled:
            # Seleccionar todos los elementos mapeados
            for element in self.element_to_position.keys():
                self.selection_manager.add_element(element)
            self.highlight_manager.clear_highlight()
            self.highlight_manager.highlight_element(list(self.element_to_position.keys())[0], 'selected')
    
    def _on_deselect_all(self, event):
        """Deselecciona todos los elementos"""
        if self.is_enabled:
            self.selection_manager.clear_selection()
            self.highlight_manager.clear_highlight()
    
    def _find_element_at_position(self, position: str) -> Optional[Tag]:
        """Encuentra el elemento en una posición específica"""
        for (start, end), element in self.position_to_element.items():
            if self._position_in_range(position, start, end):
                return element
        return None
    
    def _position_in_range(self, pos: str, start: str, end: str) -> bool:
        """Verifica si una posición está en un rango"""
        try:
            # Convertir posiciones a índices numéricos
            pos_idx = self.html_widget.count('1.0', pos)
            start_idx = self.html_widget.count('1.0', start)
            end_idx = self.html_widget.count('1.0', end)
            
            return start_idx <= pos_idx <= end_idx
        except Exception:
            return False
    
    def _select_elements_in_range(self, start_pos: str, end_pos: str):
        """Selecciona elementos en un rango específico"""
        selected_elements = []
        
        for (element_start, element_end), element in self.position_to_element.items():
            if self._ranges_overlap(start_pos, end_pos, element_start, element_end):
                selected_elements.append(element)
        
        # Añadir elementos a la selección
        for element in selected_elements:
            self.selection_manager.add_element(element)
        
        # Resaltar elementos seleccionados
        if selected_elements:
            self.highlight_manager.highlight_element(selected_elements[0], 'selected')
    
    def _ranges_overlap(self, start1: str, end1: str, start2: str, end2: str) -> bool:
        """Verifica si dos rangos se solapan"""
        try:
            start1_idx = self.html_widget.count('1.0', start1)
            end1_idx = self.html_widget.count('1.0', end1)
            start2_idx = self.html_widget.count('1.0', start2)
            end2_idx = self.html_widget.count('1.0', end2)
            
            return not (end1_idx < start2_idx or end2_idx < start1_idx)
        except Exception:
            return False
    
    def get_current_selection(self) -> ElementSelection:
        """Obtiene la selección actual"""
        return self.selection_manager.get_selection()
    
    def register_selection_callback(self, callback: Callable):
        """Registra un callback para cambios en la selección"""
        self.selection_manager.register_callback('selection_changed', callback)
    
    def register_hover_callback(self, callback: Callable):
        """Registra un callback para eventos de hover"""
        self.selection_manager.register_callback('element_hovered', callback)
    
    def register_click_callback(self, callback: Callable):
        """Registra un callback para eventos de click"""
        self.selection_manager.register_callback('element_clicked', callback)
    
    def save_selection(self, name: str = None):
        """Guarda la selección actual"""
        self.selection_manager.save_selection(name)
    
    def get_selection_history(self) -> List[ElementSelection]:
        """Obtiene el historial de selecciones"""
        return self.selection_manager.selection_history.copy()
    
    def clear_selection_history(self):
        """Limpia el historial de selecciones"""
        self.selection_manager.selection_history.clear() 