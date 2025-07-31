import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
from bs4 import BeautifulSoup
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
import pandas as pd
import json
import time
import threading
from queue import Queue
from datetime import datetime
import webbrowser
from readability import Document
import os
from collections import deque
import logging
from concurrent.futures import ThreadPoolExecutor
import hashlib

# Import new professional scraper components
from scraper_core.config_manager import ConfigManager
from scraper_core.ethical_scraper import EthicalScraper
from scraper_core.cache_manager import CacheManager
from scraper_core.proxy_manager import ProxyManager
from scraper_core.user_agent_manager import UserAgentManager
from scraper_core.metrics import MetricsCollector
from scraper_core.structured_data_extractor import StructuredDataExtractor
from scraper_core.crawler import IntelligentCrawler
from scraper_core.etl_pipeline import ETLPipeline
from scraper_core.simple_scheduler import SimpleTaskScheduler
from scraper_core.plugin_manager import PluginManager
try:
    from scraper_core.html_analyzer import EnhancedHTMLAnalyzer
except ImportError:
    # Fallback si el módulo no está disponible
    class EnhancedHTMLAnalyzer:
        def __init__(self):
            pass
        def analyze(self, html_content, url=""):
            return None
from scraper_core.advanced_selectors import AdvancedSelectors, SelectorRule
from scraper_core.url_discovery import URLDiscoveryEngine, DiscoveryResult

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BasicHTMLAnalyzer:
    """Wrapper para EnhancedHTMLAnalyzer para mantener compatibilidad con la GUI"""
    
    def __init__(self, html_content):
        try:
            self.enhanced_analyzer = EnhancedHTMLAnalyzer()
        except Exception as e:
            logger.warning(f"Error inicializando EnhancedHTMLAnalyzer: {e}")
            self.enhanced_analyzer = None
        
        self.html_content = html_content
        self.url = None
        self._dom_tree = None
        self._element_map = {}
        self._line_to_element = {}
        
        # Parse HTML for basic operations
        try:
            self.soup = BeautifulSoup(html_content, 'lxml')
        except Exception as e:
            logger.error(f"Error parseando HTML: {e}")
            self.soup = None
            return
        
        self.elements_found = {
            'titles': [],
            'paragraphs': [],
            'links': [],
            'images': [],
            'tables': []
        }
        self.analyze_structure()
    
    def set_url(self, url):
        """Establece la URL asociada al analizador"""
        self.url = url
    
    def get_element_type(self, element):
        """Determina el tipo de elemento para colorear"""
        if element.name == 'img':
            return 'image'
        elif element.name == 'a':
            return 'link'
        elif element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            return 'title'
        elif element.name == 'p':
            return 'text'
        elif element.name == 'table':
            return 'table'
        return 'other'
    
    def _build_dom_tree(self):
        """Construye el árbol DOM y el mapa de elementos"""
        dom_tree = []
        def traverse(element, depth=0, path="", parent_path="", parent_id=None):
            if element.name:
                if element.parent:
                    siblings = [sib for sib in element.parent.find_all(element.name, recursive=False)]
                    index = siblings.index(element)
                else:
                    index = 0
                current_path = f"{parent_path} > {element.name}:{index}" if parent_path else f"{element.name}:{index}"
                node_id = len(dom_tree)
                node = {
                    'tag': element.name,
                    'depth': depth,
                    'attrs': dict(element.attrs),
                    'text': element.get_text(strip=True)[:50] + '...' if element.get_text(strip=True) else '',
                    'path': current_path,
                    'parent_id': parent_id,
                    'node_id': node_id
                }
                dom_tree.append(node)
                self._element_map[current_path] = element
                for child in element.children:
                    if getattr(child, 'name', None):
                        traverse(child, depth + 1, current_path, current_path, node_id)
        if self.soup.html:
            traverse(self.soup.html)
        else:
            traverse(self.soup)
        return dom_tree
    
    def get_dom_tree(self):
        """Obtiene el árbol DOM con cache"""
        if self._dom_tree is None:
            self._dom_tree = self._build_dom_tree()
        return self._dom_tree
    
    def get_element_details(self, element_path):
        """Obtiene detalles de un elemento específico usando el mapa cacheado"""
        if hasattr(self, 'soup') and self.soup:
            try:
                if ':' in element_path:
                    tag_name, index_str = element_path.split(':', 1)
                    try:
                        index = int(index_str)
                        elements = self.soup.find_all(tag_name)
                        if 0 <= index < len(elements):
                            return elements[index]
                    except (ValueError, IndexError):
                        pass
                return self._element_map.get(element_path)
            except Exception as e:
                logger.warning(f"Error obteniendo elemento {element_path}: {e}")
        return self._element_map.get(element_path)
    
    def analyze_structure(self):
        """Analiza la estructura HTML de manera eficiente"""
        for tag in self.soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a', 'img', 'table']):
            if tag.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                self.elements_found['titles'].append({
                    'text': tag.get_text(strip=True),
                    'tag': tag.name
                })
            elif tag.name == 'p':
                self.elements_found['paragraphs'].append({
                    'text': tag.get_text(strip=True)
                })
            elif tag.name == 'a' and tag.get('href'):
                self.elements_found['links'].append({
                    'text': tag.get_text(strip=True),
                    'href': tag['href']
                })
            elif tag.name == 'img':
                self.elements_found['images'].append({
                    'alt': tag.get('alt', ''),
                    'src': tag.get('src', '')
                })
            elif tag.name == 'table':
                table_data = []
                for row in tag.find_all('tr'):
                    cols = [col.get_text(strip=True) for col in row.find_all(['th', 'td'])]
                    if cols:
                        table_data.append(cols)
                if table_data:
                    self.elements_found['tables'].append(table_data)
        
        # Detectar elementos interesantes adicionales
        self.detect_interesting_elements()
    
    def detect_interesting_elements(self):
        """Detecta elementos interesantes como productos, precios, etc."""
        self.interesting_elements = {
            'products': [],
            'prices': [],
            'contact_info': [],
            'social_media': [],
            'forms': [],
            'buttons': [],
            'navigation': []
        }
        
        # Detectar productos (elementos con clases comunes de productos)
        product_selectors = [
            '[class*="product"]', '[class*="item"]', '[class*="card"]',
            '[class*="listing"]', '[class*="goods"]', '[class*="merchandise"]'
        ]
        for selector in product_selectors:
            for element in self.soup.select(selector):
                text = element.get_text(strip=True)
                if text and len(text) > 10:
                    self.interesting_elements['products'].append({
                        'text': text[:100] + '...' if len(text) > 100 else text,
                        'element': element.name,
                        'classes': element.get('class', [])
                    })
        
        # Detectar precios (patrones de precio)
        import re
        price_patterns = [
            r'\$\d+\.?\d*',  # $10.99
            r'\d+\.?\d*\s*(?:USD|EUR|GBP)',  # 10.99 USD
            r'\d+\.?\d*\s*€',  # 10.99 €
            r'\d+\.?\d*\s*£',  # 10.99 £
        ]
        
        for pattern in price_patterns:
            for element in self.soup.find_all(text=re.compile(pattern, re.IGNORECASE)):
                if element.parent:
                    text = element.parent.get_text(strip=True)
                    if text:
                        self.interesting_elements['prices'].append({
                            'text': text[:100] + '...' if len(text) > 100 else text,
                            'price': element.strip(),
                            'element': element.parent.name
                        })
        
        # Detectar información de contacto
        contact_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'\+?[\d\s\-\(\)]{10,}',  # Teléfono
            r'\b\d{1,3}[-.\s]?\d{1,3}[-.\s]?\d{1,4}\b'  # Teléfono simple
        ]
        
        for pattern in contact_patterns:
            for element in self.soup.find_all(text=re.compile(pattern, re.IGNORECASE)):
                if element.parent:
                    text = element.parent.get_text(strip=True)
                    if text:
                        self.interesting_elements['contact_info'].append({
                            'text': text[:100] + '...' if len(text) > 100 else text,
                            'contact': element.strip(),
                            'type': 'email' if '@' in element else 'phone'
                        })
        
        # Detectar redes sociales
        social_patterns = [
            'facebook.com', 'twitter.com', 'instagram.com', 'linkedin.com',
            'youtube.com', 'tiktok.com', 'snapchat.com'
        ]
        
        for pattern in social_patterns:
            for element in self.soup.find_all('a', href=re.compile(pattern, re.IGNORECASE)):
                text = element.get_text(strip=True)
                href = element.get('href', '')
                if text or href:
                    self.interesting_elements['social_media'].append({
                        'text': text or href,
                        'platform': pattern.split('.')[0],
                        'url': href
                    })
        
        # Detectar formularios
        for form in self.soup.find_all('form'):
            form_text = form.get_text(strip=True)
            if form_text:
                self.interesting_elements['forms'].append({
                    'text': form_text[:100] + '...' if len(form_text) > 100 else form_text,
                    'action': form.get('action', ''),
                    'method': form.get('method', 'get')
                })
        
        # Detectar botones
        for button in self.soup.find_all(['button', 'input']):
            if button.name == 'button':
                text = button.get_text(strip=True)
            else:
                text = button.get('value', '') or button.get('alt', '')
            
            if text:
                self.interesting_elements['buttons'].append({
                    'text': text,
                    'type': button.get('type', 'button'),
                    'element': button.name
                })
        
        # Detectar navegación
        nav_selectors = [
            'nav', '[class*="nav"]', '[class*="menu"]', '[class*="breadcrumb"]'
        ]
        
        for selector in nav_selectors:
            for element in self.soup.select(selector):
                text = element.get_text(strip=True)
                if text:
                    self.interesting_elements['navigation'].append({
                        'text': text[:100] + '...' if len(text) > 100 else text,
                        'element': element.name,
                        'classes': element.get('class', [])
                    })
    
    def compare_with(self, other_analyzer):
        """Compara este DOM con otro y retorna las diferencias de manera eficiente"""
        differences = {
            'added': [],
            'removed': [],
            'modified': []
        }
        
        this_tree = self.get_dom_tree()
        other_tree = other_analyzer.get_dom_tree()
        
        this_dict = {node['path']: node for node in this_tree}
        other_dict = {node['path']: node for node in other_tree}
        
        for path, node in this_dict.items():
            if path not in other_dict:
                differences['added'].append(node)
            else:
                other_node = other_dict[path]
                if (node['attrs'] != other_node['attrs'] or 
                    node['text'] != other_node['text']):
                    differences['modified'].append({
                        'path': path,
                        'this': node,
                        'other': other_node
                    })
        
        for path, node in other_dict.items():
            if path not in this_dict:
                differences['removed'].append(node)
        
        return differences
    
    def get_main_content(self):
        """Detecta el contenido principal usando readability-lxml."""
        try:
            doc = Document(str(self.soup))
            main_html = doc.summary(html_partial=True)
            title = doc.title()
            main_soup = BeautifulSoup(main_html, 'lxml')
            return main_soup, title
        except Exception as e:
            logger.error(f"Error al detectar contenido principal: {e}")
            return None, None
    
    def get_element_path(self, element):
        """Devuelve la ruta (key) de un elemento BeautifulSoup en el mapa."""
        for path, el in self._element_map.items():
            if el is element:
                return path
        
        if hasattr(self, 'soup') and self.soup and element:
            try:
                tag_name = element.name
                if tag_name:
                    elements = self.soup.find_all(tag_name)
                    for i, el in enumerate(elements):
                        if el is element:
                            return f"{tag_name}:{i}"
            except Exception as e:
                logger.warning(f"Error creando path para elemento: {e}")
        
        return None


class URLListManager(tk.Toplevel):
    """Ventana para añadir lista de URLs al scraper principal"""
    
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.parent = parent
        self.main_app = main_app
        self.title("Añadir Lista de URLs")
        self.geometry("700x500")
        self.minsize(600, 400)
        
        # Variables
        self.urls = []
        self.current_urls = []
        
        # Configurar la interfaz
        self.setup_ui()
        
        # Aplicar tema
        self.main_app.apply_light_theme_to_toplevel(self)
    
    def setup_ui(self):
        """Configura los elementos de la interfaz"""
        # Frame principal
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_label = ttk.Label(main_frame, text="📋 Gestión de Lista de URLs", font=('Arial', 14, 'bold'))
        title_label.pack(pady=(0, 10))
        
        # Frame para métodos de entrada
        input_frame = ttk.LabelFrame(main_frame, text="Métodos de Entrada", padding=10)
        input_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Botones de entrada
        button_frame = ttk.Frame(input_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="📁 Cargar desde archivo", command=self.load_urls_from_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="✏️ Editar manualmente", command=self.edit_urls_manually).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="📋 Pegar desde portapapeles", command=self.paste_from_clipboard).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🌐 Obtener URLs actuales", command=self.get_current_urls).pack(side=tk.LEFT, padx=5)
        
        # Frame para vista previa
        preview_frame = ttk.LabelFrame(main_frame, text="Vista Previa de URLs", padding=10)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Frame para controles de la lista
        list_controls = ttk.Frame(preview_frame)
        list_controls.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(list_controls, text="URLs en la lista:").pack(side=tk.LEFT)
        self.url_count_label = ttk.Label(list_controls, text="0")
        self.url_count_label.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(list_controls, text="🗑️ Limpiar lista", command=self.clear_url_list).pack(side=tk.RIGHT, padx=2)
        ttk.Button(list_controls, text="❌ Eliminar seleccionada", command=self.remove_selected_url).pack(side=tk.RIGHT, padx=2)
        ttk.Button(list_controls, text="✅ Validar URLs", command=self.validate_urls).pack(side=tk.RIGHT, padx=2)
        
        # Lista de URLs con scrollbar
        list_frame = ttk.Frame(preview_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Listbox para mostrar las URLs
        self.url_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, height=15)
        self.url_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.url_listbox.yview)
        
        # Frame para botones de acción
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(action_frame, text="💾 Guardar lista", command=self.save_url_list).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="📤 Añadir al scraper", command=self.add_to_scraper).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="🔄 Reemplazar en scraper", command=self.replace_in_scraper).pack(side=tk.LEFT, padx=2)
        ttk.Button(action_frame, text="❌ Cerrar", command=self.destroy).pack(side=tk.RIGHT, padx=2)
        
        # Barra de estado
        self.status_bar = ttk.Label(main_frame, text="Listo para añadir URLs", relief=tk.SUNKEN)
        self.status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def load_urls_from_file(self):
        """Carga URLs desde un archivo de texto"""
        file_path = filedialog.askopenfilename(
            title="Seleccionar archivo de URLs",
            filetypes=[
                ("Archivos de texto", "*.txt"), 
                ("Archivos CSV", "*.csv"),
                ("Todos los archivos", "*.*")
            ]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Procesar diferentes formatos
                if file_path.endswith('.csv'):
                    import csv
                    from io import StringIO
                    csv_reader = csv.reader(StringIO(content))
                    self.urls = [row[0].strip() for row in csv_reader if row and row[0].strip()]
                else:
                    # Archivo de texto simple
                    self.urls = [line.strip() for line in content.splitlines() if line.strip()]
                
                self.update_url_list()
                self.status_bar.config(text=f"Se cargaron {len(self.urls)} URLs desde {file_path}")
                
            except Exception as e:
                logger.error(f"Error al cargar el archivo: {e}")
                messagebox.showerror("Error", f"Error al cargar el archivo: {str(e)}")
    
    def edit_urls_manually(self):
        """Permite editar URLs manualmente"""
        edit_window = tk.Toplevel(self)
        edit_window.title("Editar URLs Manualmente")
        edit_window.geometry("600x400")
        
        # Frame principal
        main_frame = ttk.Frame(edit_window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Ingrese las URLs (una por línea):", font=('Arial', 10, 'bold')).pack(pady=(0, 10))
        
        # Text widget para editar URLs
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        text_widget = tk.Text(text_frame, wrap=tk.NONE)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        # Insertar URLs actuales si existen
        if self.urls:
            text_widget.insert(tk.END, '\n'.join(self.urls))
        
        # Botones
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def save_urls():
            content = text_widget.get(1.0, tk.END).strip()
            if content:
                self.urls = [line.strip() for line in content.splitlines() if line.strip()]
                self.update_url_list()
                self.status_bar.config(text=f"Se actualizaron {len(self.urls)} URLs")
                edit_window.destroy()
            else:
                messagebox.showwarning("Advertencia", "No se ingresaron URLs")
        
        ttk.Button(button_frame, text="💾 Guardar", command=save_urls).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="❌ Cancelar", command=edit_window.destroy).pack(side=tk.RIGHT, padx=2)
        
        # Aplicar tema
        self.main_app.apply_light_theme_to_toplevel(edit_window)
    
    def paste_from_clipboard(self):
        """Pega URLs desde el portapapeles"""
        try:
            clipboard_content = self.clipboard_get()
            if clipboard_content:
                # Procesar contenido del portapapeles
                lines = clipboard_content.splitlines()
                new_urls = [line.strip() for line in lines if line.strip()]
                
                if new_urls:
                    # Preguntar si añadir o reemplazar
                    response = messagebox.askyesnocancel(
                        "Pegar URLs", 
                        f"Se encontraron {len(new_urls)} URLs en el portapapeles.\n\n¿Desea añadirlas a la lista actual?"
                    )
                    
                    if response is True:  # Añadir
                        self.urls.extend(new_urls)
                        self.status_bar.config(text=f"Se añadieron {len(new_urls)} URLs desde el portapapeles")
                    elif response is False:  # Reemplazar
                        self.urls = new_urls
                        self.status_bar.config(text=f"Se reemplazaron con {len(new_urls)} URLs desde el portapapeles")
                    
                    self.update_url_list()
                else:
                    messagebox.showwarning("Advertencia", "No se encontraron URLs válidas en el portapapeles")
            else:
                messagebox.showwarning("Advertencia", "El portapapeles está vacío")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error al pegar desde el portapapeles: {str(e)}")
    
    def get_current_urls(self):
        """Obtiene las URLs actuales del scraper principal"""
        try:
            current_text = self.main_app.url_text.get(1.0, tk.END).strip()
            if current_text:
                current_urls = [line.strip() for line in current_text.splitlines() if line.strip()]
                if current_urls:
                    self.urls = current_urls
                    self.update_url_list()
                    self.status_bar.config(text=f"Se obtuvieron {len(self.urls)} URLs del scraper principal")
                else:
                    messagebox.showinfo("Información", "No hay URLs en el scraper principal")
            else:
                messagebox.showinfo("Información", "No hay URLs en el scraper principal")
                
        except Exception as e:
            messagebox.showerror("Error", f"Error al obtener URLs actuales: {str(e)}")
    
    def update_url_list(self):
        """Actualiza la lista de URLs en el Listbox"""
        self.url_listbox.delete(0, tk.END)
        for url in self.urls:
            self.url_listbox.insert(tk.END, url)
        self.url_count_label.config(text=str(len(self.urls)))
    
    def clear_url_list(self):
        """Limpia la lista de URLs"""
        if self.urls:
            if messagebox.askyesno("Confirmar", "¿Está seguro de que desea limpiar la lista de URLs?"):
                self.urls = []
                self.update_url_list()
                self.status_bar.config(text="Lista de URLs limpiada")
        else:
            messagebox.showinfo("Información", "La lista ya está vacía")
    
    def remove_selected_url(self):
        """Elimina la URL seleccionada de la lista"""
        selection = self.url_listbox.curselection()
        if selection:
            index = selection[0]
            removed_url = self.urls.pop(index)
            self.update_url_list()
            self.status_bar.config(text=f"URL eliminada: {removed_url}")
        else:
            messagebox.showwarning("Advertencia", "Por favor seleccione una URL para eliminar")
    
    def validate_urls(self):
        """Valida las URLs en la lista"""
        if not self.urls:
            messagebox.showinfo("Información", "No hay URLs para validar")
            return
        
        valid_urls = []
        invalid_urls = []
        
        for url in self.urls:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                if parsed.scheme and parsed.netloc:
                    valid_urls.append(url)
                else:
                    invalid_urls.append(url)
            except Exception:
                invalid_urls.append(url)
        
        # Mostrar resultados
        result_message = f"Validación completada:\n\n"
        result_message += f"✅ URLs válidas: {len(valid_urls)}\n"
        result_message += f"❌ URLs inválidas: {len(invalid_urls)}\n"
        
        if invalid_urls:
            result_message += f"\nURLs inválidas:\n"
            for url in invalid_urls[:10]:  # Mostrar solo las primeras 10
                result_message += f"  - {url}\n"
            if len(invalid_urls) > 10:
                result_message += f"  ... y {len(invalid_urls) - 10} más"
        
        messagebox.showinfo("Resultado de Validación", result_message)
        
        # Opcionalmente, limpiar URLs inválidas
        if invalid_urls and messagebox.askyesno("Limpiar URLs", "¿Desea eliminar las URLs inválidas?"):
            self.urls = valid_urls
            self.update_url_list()
            self.status_bar.config(text=f"Se eliminaron {len(invalid_urls)} URLs inválidas")
    
    def save_url_list(self):
        """Guarda la lista de URLs en un archivo"""
        if not self.urls:
            messagebox.showwarning("Advertencia", "No hay URLs para guardar")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="Guardar lista de URLs",
            defaultextension=".txt",
            filetypes=[
                ("Archivos de texto", "*.txt"),
                ("Archivos CSV", "*.csv"),
                ("Todos los archivos", "*.*")
            ],
            initialfile=f"url_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    if file_path.endswith('.csv'):
                        import csv
                        writer = csv.writer(f)
                        for url in self.urls:
                            writer.writerow([url])
                    else:
                        f.write('\n'.join(self.urls))
                
                messagebox.showinfo("Éxito", f"Lista de URLs guardada en:\n{file_path}")
                self.status_bar.config(text=f"Lista guardada: {file_path}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Error al guardar la lista: {str(e)}")
    
    def add_to_scraper(self):
        """Añade las URLs al scraper principal"""
        if not self.urls:
            messagebox.showwarning("Advertencia", "No hay URLs para añadir")
            return
        
        try:
            # Obtener URLs actuales del scraper
            current_text = self.main_app.url_text.get(1.0, tk.END).strip()
            current_urls = [line.strip() for line in current_text.splitlines() if line.strip()] if current_text else []
            
            # Añadir nuevas URLs (evitar duplicados)
            added_count = 0
            for url in self.urls:
                if url not in current_urls:
                    current_urls.append(url)
                    added_count += 1
            
            # Actualizar el scraper principal
            self.main_app.url_text.delete(1.0, tk.END)
            self.main_app.url_text.insert(1.0, '\n'.join(current_urls))
            
            messagebox.showinfo("Éxito", f"Se añadieron {added_count} URLs al scraper principal")
            self.status_bar.config(text=f"Añadidas {added_count} URLs al scraper")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al añadir URLs: {str(e)}")
    
    def replace_in_scraper(self):
        """Reemplaza las URLs en el scraper principal"""
        if not self.urls:
            messagebox.showwarning("Advertencia", "No hay URLs para reemplazar")
            return
        
        if messagebox.askyesno("Confirmar", "¿Está seguro de que desea reemplazar todas las URLs en el scraper principal?"):
            try:
                # Reemplazar URLs en el scraper principal
                self.main_app.url_text.delete(1.0, tk.END)
                self.main_app.url_text.insert(1.0, '\n'.join(self.urls))
                
                messagebox.showinfo("Éxito", f"Se reemplazaron las URLs en el scraper principal con {len(self.urls)} URLs")
                self.status_bar.config(text=f"Reemplazadas {len(self.urls)} URLs en el scraper")
                
            except Exception as e:
                messagebox.showerror("Error", f"Error al reemplazar URLs: {str(e)}")


class WebScraperApp:
    """Aplicación principal con interfaz gráfica profesional"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Scrapelillo Professional")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 700)
        
        # Initialize configuration manager
        self.config_manager = ConfigManager()
        
        # Variables de estado
        self.current_url = ""
        self.html_content = ""
        self.analyzer = None
        self.selected_dom_elements = set()
        self.all_analyzers = []  # Lista de todos los analizadores
        self.all_html_contents = []  # Lista de todos los contenidos HTML
        self._cancel_requested = False
        self._line_to_element = {}  # Inicializar el mapa de líneas a elementos
        self._tree_item_map = {}  # Mapa para el árbol DOM
        
        # Initialize professional scraper components with error handling
        try:
            self.ethical_scraper = EthicalScraper(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize EthicalScraper: {e}")
            self.ethical_scraper = None
        
        try:
            self.cache_manager = CacheManager(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize CacheManager: {e}")
            self.cache_manager = None
        
        try:
            self.proxy_manager = ProxyManager(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize ProxyManager: {e}")
            self.proxy_manager = None
        
        try:
            self.user_agent_manager = UserAgentManager(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize UserAgentManager: {e}")
            self.user_agent_manager = None
        
        try:
            self.metrics_collector = MetricsCollector(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize MetricsCollector: {e}")
            self.metrics_collector = None
        
        try:
            self.structured_data_extractor = StructuredDataExtractor(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize StructuredDataExtractor: {e}")
            self.structured_data_extractor = None
        
        try:
            self.crawler = IntelligentCrawler(self.config_manager, self.ethical_scraper)
        except Exception as e:
            logger.error(f"Failed to initialize IntelligentCrawler: {e}")
            self.crawler = None
        
        try:
            self.etl_pipeline = ETLPipeline(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize ETLPipeline: {e}")
            self.etl_pipeline = None
        
        try:
            self.scheduler = SimpleTaskScheduler(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize SimpleTaskScheduler: {e}")
            self.scheduler = None
        
        try:
            self.plugin_manager = PluginManager(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize PluginManager: {e}")
            self.plugin_manager = None
        
        try:
            self.html_analyzer = EnhancedHTMLAnalyzer(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize EnhancedHTMLAnalyzer: {e}")
            self.html_analyzer = None
        
        try:
            self.advanced_selectors = AdvancedSelectors(self.config_manager)
        except Exception as e:
            logger.error(f"Failed to initialize AdvancedSelectors: {e}")
            self.advanced_selectors = None
        
        # Start scheduler
        if self.scheduler:
            try:
                self.scheduler.start()
            except Exception as e:
                logger.warning(f"Could not start simple scheduler: {e}")
                # Continue without scheduler
        
        # Cola para comunicación entre hilos
        self.queue = Queue()
        
        # Configurar la interfaz
        self.setup_ui()
        self.set_light_theme()
        
        # Verificar mensajes en la cola periódicamente
        self.root.after(100, self.process_queue)
    
    def setup_ui(self):
        """Configura los elementos de la interfaz de usuario"""
        # Frame principal
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Panel superior (URL y botones)
        top_panel = ttk.Frame(main_frame)
        top_panel.pack(fill=tk.X, pady=(0, 10))
        
        # URL input
        url_frame = ttk.Frame(top_panel)
        url_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(url_frame, text="URLs (una por línea):").pack(side=tk.LEFT)
        self.url_text = tk.Text(url_frame, height=2, width=50)
        self.url_text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Action buttons
        button_frame = ttk.Frame(top_panel)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Analizar", command=self.start_analysis_thread).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Crawlear", command=self.start_crawling).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Descubrir URLs", command=self.start_url_discovery).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Extraer Datos", command=self.extract_structured_data).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Selectores Avanzados", command=self.show_advanced_selectors).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Exportar", command=self.export_data).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Añadir lista", command=self.show_url_list_window).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Cargar Sesión", command=self.load_crawler_session).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Métricas", command=self.show_metrics).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Plugins", command=self.show_plugins).pack(side=tk.LEFT, padx=2)
        self.cancel_button = ttk.Button(button_frame, text="Cancelar", command=self.cancel_analysis, state=tk.DISABLED)
        self.cancel_button.pack(side=tk.LEFT, padx=2)
        
        # Panel central (vista previa y selección)
        center_panel = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        center_panel.pack(fill=tk.BOTH, expand=True)
        
        # Panel izquierdo (vista previa HTML)
        left_panel = ttk.Frame(center_panel, padding=5)
        center_panel.add(left_panel, weight=2)
        
        # Frame para la vista previa HTML y sus controles
        preview_frame = ttk.Frame(left_panel)
        preview_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(preview_frame, text="Vista Previa HTML").pack()
        
        # Frame para el texto y scrollbars
        text_frame = ttk.Frame(preview_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbars
        vsb = ttk.Scrollbar(text_frame, orient="vertical")
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb = ttk.Scrollbar(text_frame, orient="horizontal")
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Text widget para HTML
        self.html_preview = tk.Text(text_frame, wrap=tk.NONE, yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.html_preview.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configurar scrollbars
        vsb.config(command=self.html_preview.yview)
        hsb.config(command=self.html_preview.xview)
        
        # Configurar tags para diferentes estados
        self.html_preview.tag_configure("selected", background="lightblue")
        self.html_preview.tag_configure("hover", background="lightyellow")
        
        # Vincular eventos del mouse
        self.html_preview.bind("<Button-1>", self.on_html_click)
        self.html_preview.bind("<Motion>", self.on_html_motion)
        self.html_preview.bind("<Leave>", self.on_html_leave)
        
        # Botones para la vista previa
        preview_buttons = ttk.Frame(preview_frame)
        preview_buttons.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(preview_buttons, text="Añadir al DOM", command=self.add_selection_to_dom).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_buttons, text="Exportar Selección", command=self.export_selection).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_buttons, text="Copiar Selección", command=self.copy_selection).pack(side=tk.LEFT, padx=5)
        
        # Panel derecho (selección de elementos y árbol DOM)
        right_panel = ttk.Frame(center_panel, padding=5)
        center_panel.add(right_panel, weight=1)
        
        # --- Búsqueda y selector CSS ---
        search_frame = ttk.Frame(right_panel)
        search_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(search_frame, text="Buscar tag/clase/id:").pack(side=tk.LEFT)
        self.search_entry = ttk.Entry(search_frame, width=15)
        self.search_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(search_frame, text="Buscar", command=self.search_dom_tree).pack(side=tk.LEFT, padx=2)
        ttk.Label(search_frame, text="Selector CSS:").pack(side=tk.LEFT, padx=(10,0))
        self.selector_entry = ttk.Entry(search_frame, width=20)
        self.selector_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(search_frame, text="Seleccionar por patrón", command=self.select_by_css).pack(side=tk.LEFT, padx=2)
        
        # Elementos seleccionables
        selection_frame = ttk.LabelFrame(right_panel, text="Selección de Elementos DOM", padding=10)
        selection_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Botones de acción
        button_frame = ttk.Frame(selection_frame)
        button_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(button_frame, text="Seleccionar", command=self.select_dom_element).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Deseleccionar", command=self.deselect_dom_element).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Exportar Selección", command=self.export_selected_elements).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Exportar por Tipo", command=self.export_elements_by_type).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Ver HTML", command=self.view_element_html).pack(side=tk.RIGHT, padx=2)
        ttk.Button(button_frame, text="Resaltar en HTML", command=self.highlight_selected_element).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Detectar Contenido Principal", command=self.detect_main_content).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Elementos Interesantes", command=self.show_interesting_elements).pack(side=tk.LEFT, padx=2)
        
        # Lista de elementos seleccionados
        list_frame = ttk.Frame(selection_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Frame para controles de la lista
        list_controls = ttk.Frame(list_frame)
        list_controls.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(list_controls, text=f"Elementos seleccionados: {len(self.selected_dom_elements)}").pack(side=tk.LEFT)
        ttk.Button(list_controls, text="Limpiar Todo", command=self.clear_all_selections).pack(side=tk.RIGHT, padx=2)
        ttk.Button(list_controls, text="Seleccionar Todo", command=self.select_all_elements).pack(side=tk.RIGHT, padx=2)
        
        # Listbox con scrollbar
        listbox_frame = ttk.Frame(list_frame)
        listbox_frame.pack(fill=tk.BOTH, expand=True)
        
        self.selected_listbox = tk.Listbox(listbox_frame, height=5)
        listbox_scrollbar = ttk.Scrollbar(listbox_frame, orient=tk.VERTICAL, command=self.selected_listbox.yview)
        self.selected_listbox.configure(yscrollcommand=listbox_scrollbar.set)
        
        self.selected_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        listbox_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Árbol DOM con colores
        dom_frame = ttk.LabelFrame(right_panel, text="Estructura DOM", padding=10)
        dom_frame.pack(fill=tk.BOTH, expand=True)
        
        # Frame para controles del árbol DOM
        dom_controls = ttk.Frame(dom_frame)
        dom_controls.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(dom_controls, text="Filtrar por tipo:").pack(side=tk.LEFT, padx=5)
        self.dom_filter = ttk.Combobox(dom_controls, values=['Todos', 'Imágenes', 'Enlaces', 'Títulos', 'Texto', 'Tablas'])
        self.dom_filter.set('Todos')
        self.dom_filter.pack(side=tk.LEFT, padx=5)
        self.dom_filter.bind('<<ComboboxSelected>>', self.filter_dom_tree)
        
        ttk.Button(dom_controls, text="Comparar DOMs", command=self.compare_doms).pack(side=tk.RIGHT, padx=5)
        
        # Árbol DOM con colores
        self.dom_tree = ttk.Treeview(dom_frame, columns=('attributes', 'text', 'type'), selectmode='browse')
        self.dom_tree.heading('#0', text='Tag')
        self.dom_tree.heading('attributes', text='Atributos')
        self.dom_tree.heading('text', text='Texto')
        self.dom_tree.heading('type', text='Tipo')
        
        # Configurar colores para diferentes tipos de elementos
        self.dom_tree.tag_configure('image', background='#FFEBEE', foreground='#B71C1C')
        self.dom_tree.tag_configure('link', background='#E3F2FD', foreground='#0D47A1')
        self.dom_tree.tag_configure('title', background='#E8F5E9', foreground='#1B5E20')
        self.dom_tree.tag_configure('text', background='#FFF3E0', foreground='#4E342E')
        self.dom_tree.tag_configure('table', background='#F3E5F5', foreground='#6A1B9A')
        self.dom_tree.tag_configure('other', background='#FFFFFF', foreground='#222222')
        
        vsb_dom = ttk.Scrollbar(dom_frame, orient="vertical", command=self.dom_tree.yview)
        vsb_dom.pack(side=tk.RIGHT, fill=tk.Y)
        self.dom_tree.configure(yscrollcommand=vsb_dom.set)
        
        self.dom_tree.pack(fill=tk.BOTH, expand=True)
        
        # Configurar evento de doble clic en el árbol DOM
        self.dom_tree.bind("<Double-1>", self.on_dom_tree_double_click)
        self.dom_tree.bind("<<TreeviewSelect>>", self.show_quick_preview)
        
        # Panel de previsualización rápida
        preview_frame = ttk.LabelFrame(right_panel, text="Previsualización rápida", padding=5)
        preview_frame.pack(fill=tk.X, pady=(5, 0))
        self.quick_preview = tk.Text(preview_frame, height=6, wrap=tk.WORD, state=tk.DISABLED)
        self.quick_preview.pack(fill=tk.BOTH, expand=True)
        
        # Barra de estado
        self.status_bar = ttk.Label(main_frame, text="Listo", relief=tk.SUNKEN)
        self.status_bar.pack(fill=tk.X, pady=(10, 0))
    
    def cancel_analysis(self):
        """Cancela el análisis en curso"""
        self._cancel_requested = True
        self.status_bar.config(text="Cancelando análisis...")
        self.cancel_button.config(state=tk.DISABLED)
    
    def start_analysis_thread(self):
        """Inicia el análisis en un hilo separado para no bloquear la GUI. Soporta múltiples URLs."""
        urls = self.url_text.get(1.0, tk.END).strip().splitlines()
        urls = [u.strip() for u in urls if u.strip()]
        if not urls:
            messagebox.showerror("Error", "Por favor ingrese al menos una URL válida")
            return
        
        self._cancel_requested = False
        self.cancel_button.config(state=tk.NORMAL)
        
        # Mostrar progreso inmediatamente
        self.status_bar.config(text="Iniciando análisis...")
        self.root.update()
        
        threading.Thread(target=self.analyze_multiple_websites, args=(urls,), daemon=True).start()
    
    def analyze_multiple_websites(self, urls):
        """Analiza varias URLs con modo simplificado para evitar congelamiento"""
        self.all_html_contents = []
        self.all_analyzers = []
        
        def process_url(url):
            """Procesa una URL individual con análisis simplificado"""
            if self._cancel_requested:
                return None
            
            try:
                # Actualizar progreso
                self.queue.put(('status', f"Descargando {url}..."))
                
                if self.ethical_scraper:
                    result = self.ethical_scraper.get_page(url)
                else:
                    # Fallback to basic requests
                    import requests
                    try:
                        response = requests.get(url, timeout=30)
                        result = type('MockResult', (), {
                            'content': response.text,
                            'status_code': response.status_code,
                            'headers': dict(response.headers),
                            'error': None
                        })()
                    except Exception as e:
                        result = type('MockResult', (), {
                            'content': '',
                            'status_code': 0,
                            'headers': {},
                            'error': str(e)
                        })()
                
                # Extraer el contenido HTML del resultado
                if hasattr(result, 'content'):
                    html_content = result.content
                elif hasattr(result, 'html'):
                    html_content = result.html
                else:
                    html_content = str(result)
                
                # Análisis ultra-simplificado para evitar congelamiento
                soup = BeautifulSoup(html_content, 'lxml')
                
                # Crear analizador básico con datos mínimos
                analyzer = BasicHTMLAnalyzer(html_content)
                
                # Análisis estructural básico (sin operaciones pesadas)
                try:
                    # Solo elementos principales
                    analyzer.elements_found = {
                        'titles': [],
                        'paragraphs': [],
                        'links': [],
                        'images': [],
                        'tables': []
                    }
                    
                    # Detectar elementos interesantes automáticamente
                    analyzer.detect_interesting_elements()
                    
                    # Extraer solo elementos básicos
                    for tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                        analyzer.elements_found['titles'].append({
                            'text': tag.get_text(strip=True),
                            'tag': tag.name
                        })
                    
                    for tag in soup.find_all('p'):
                        analyzer.elements_found['paragraphs'].append({
                            'text': tag.get_text(strip=True)
                        })
                    
                    for tag in soup.find_all('a', href=True):
                        analyzer.elements_found['links'].append({
                            'text': tag.get_text(strip=True),
                            'href': tag['href']
                        })
                    
                    for tag in soup.find_all('img'):
                        analyzer.elements_found['images'].append({
                            'alt': tag.get('alt', ''),
                            'src': tag.get('src', '')
                        })
                    
                    for tag in soup.find_all('table'):
                        table_data = []
                        for row in tag.find_all('tr'):
                            cols = [col.get_text(strip=True) for col in row.find_all(['th', 'td'])]
                            if cols:
                                table_data.append(cols)
                        if table_data:
                            analyzer.elements_found['tables'].append(table_data)
                    
                except Exception as e:
                    logger.warning(f"Error en análisis estructural para {url}: {e}")
                
                # Datos básicos del enhanced analyzer
                try:
                    enhanced_result = {
                        'title': soup.find('title').get_text(strip=True) if soup.find('title') else '',
                        'meta_description': soup.find('meta', attrs={'name': 'description'}).get('content', '') if soup.find('meta', attrs={'name': 'description'}) else '',
                        'forms_count': len(soup.find_all('form')),
                        'tables_count': len(soup.find_all('table')),
                        'images_count': len(soup.find_all('img')),
                        'links_count': len(soup.find_all('a'))
                    }
                    analyzer.enhanced_data = enhanced_result
                except Exception as e:
                    logger.warning(f"Error en datos básicos para {url}: {e}")
                
                return (url, html_content, analyzer)
                
            except Exception as e:
                logger.error(f"Error analizando {url}: {e}")
                self.queue.put(('error', f"Error durante el análisis de {url}: {str(e)}"))
                return None
        
        # Procesamiento secuencial para evitar congelamiento
        for i, url in enumerate(urls):
            if self._cancel_requested:
                break
            
            try:
                # Actualizar progreso
                self.queue.put(('status', f"Procesando {i+1}/{len(urls)}: {url}"))
                
                # Procesar URL
                result = process_url(url)
                if result:
                    url, html_content, analyzer = result
                    self.all_html_contents.append(html_content)
                    self.all_analyzers.append(analyzer)
                    
                    # Mostrar la primera URL en la interfaz
                    if not self.current_url:
                        self.current_url = url
                        self.html_content = html_content
                        self.analyzer = analyzer
                        self.queue.put(('update_preview', html_content))
                        # Usar DOM tree simplificado
                        self.queue.put(('update_dom_tree_simple', analyzer))
                        
                # Pausa breve para permitir actualización de GUI
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error procesando URL {url}: {e}")
                self.queue.put(('status', f"Error en {url}: {str(e)}"))
                continue
        
        if not self._cancel_requested:
            # Mostrar información sobre elementos interesantes detectados
            if hasattr(self, 'analyzer') and self.analyzer and hasattr(self.analyzer, 'interesting_elements'):
                total_interesting = sum(len(items) for items in self.analyzer.interesting_elements.values())
                if total_interesting > 0:
                    self.queue.put(('status', f"Análisis completado de {len(urls)} URLs - {total_interesting} elementos interesantes detectados"))
                else:
                    self.queue.put(('status', f"Análisis completado de {len(urls)} URLs"))
            else:
                self.queue.put(('status', f"Análisis completado de {len(urls)} URLs"))
        else:
            self.queue.put(('status', "Análisis cancelado"))
        
        self.cancel_button.config(state=tk.DISABLED)
    
    def process_queue(self):
        """Procesa los mensajes en la cola para actualizar la GUI"""
        try:
            while not self.queue.empty():
                msg_type, data = self.queue.get_nowait()
                
                if msg_type == 'update_preview':
                    self.update_html_preview(data)
                elif msg_type == 'update_dom_tree':
                    self.update_dom_tree(data)
                elif msg_type == 'update_dom_tree_simple':
                    self.update_dom_tree_simple(data)
                elif msg_type == 'status':
                    self.status_bar.config(text=data)
                elif msg_type == 'error':
                    messagebox.showerror("Error", data)
                    self.status_bar.config(text="Error")
                elif msg_type == 'crawling_complete':
                    self.show_crawling_results(data)
        
        except Exception as e:
            logger.error(f"Error procesando cola: {e}")
        
        # Volver a verificar la cola después de 100ms
        self.root.after(100, self.process_queue)
    
    def update_html_preview(self, html_content):
        """Actualiza el panel de vista previa HTML usando el soup existente"""
        try:
            self.html_preview.config(state=tk.NORMAL)
            self.html_preview.delete(1.0, tk.END)
            
            if self.analyzer and self.analyzer.soup:
                # Limitar el HTML formateado para evitar congelamiento
                formatted_html = self.analyzer.soup.prettify()
                # Limitar a las primeras 2000 líneas
                lines = formatted_html.split('\n')
                if len(lines) > 2000:
                    formatted_html = '\n'.join(lines[:2000]) + '\n\n... (HTML truncado para evitar congelamiento)'
            else:
                soup = BeautifulSoup(html_content, 'lxml')
                formatted_html = soup.prettify()
                # Limitar a las primeras 2000 líneas
                lines = formatted_html.split('\n')
                if len(lines) > 2000:
                    formatted_html = '\n'.join(lines[:2000]) + '\n\n... (HTML truncado para evitar congelamiento)'
            
            self.formatted_html = formatted_html
            self.html_preview.insert(tk.END, formatted_html)
            self.html_preview.config(state=tk.DISABLED)
            self.html_preview.see("1.0")
            
            # Construir mapa de líneas a elementos para eventos de UI (simplificado)
            if self.analyzer:
                self._build_line_to_element_map()
                
        except Exception as e:
            logger.error(f"Error actualizando HTML preview: {e}")
            self.html_preview.config(state=tk.NORMAL)
            self.html_preview.delete(1.0, tk.END)
            self.html_preview.insert(tk.END, f"Error cargando HTML: {str(e)}")
            self.html_preview.config(state=tk.DISABLED)
    
    def _build_line_to_element_map(self):
        """Construye un mapa de líneas a elementos para eventos de UI mejorado"""
        self._line_to_element = {}
        if not self.analyzer:
            return
        
        try:
            # Obtener el HTML formateado línea por línea
            lines = self.formatted_html.split('\n')
            
            # Limitar el número de líneas para evitar congelamiento
            max_lines = min(1000, len(lines))  # Aumentar límite para mejor cobertura
            lines = lines[:max_lines]
            
            # Crear mapa de elementos más completo
            element_to_path = {}
            soup = self.analyzer.soup
            if soup:
                # Elementos principales con mejor identificación
                main_tags = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a', 'img', 'p', 'div', 'span', 'li', 'ul', 'ol', 'table', 'tr', 'td', 'th']
                element_count = 0
                
                for tag_name in main_tags:
                    if element_count >= 200:  # Aumentar límite
                        break
                    
                    for tag in soup.find_all(tag_name)[:15]:  # Máximo 15 por tipo
                        if element_count >= 200:
                            break
                        
                        # Crear identificador único más robusto
                        tag_text = tag.get_text(strip=True)
                        tag_attrs = str(tag.attrs)
                        element_id = f"{tag_name}_{element_count}_{hash(tag_text + tag_attrs) % 10000}"
                        element_to_path[element_id] = f"{tag_name}:{element_count}"
                        element_count += 1
            
            # Buscar elementos en líneas de manera más precisa
            for i, line in enumerate(lines, 1):
                if i > max_lines:
                    break
                
                # Buscar elementos que contengan esta línea
                for element_id, path in list(element_to_path.items()):
                    # Buscar por contenido del elemento en la línea
                    if any(attr in line for attr in ['class=', 'id=', 'href=', 'src=']):
                        self._line_to_element[i] = path
                        break
                    # Buscar por texto del elemento
                    elif path in element_to_path and element_to_path[path] in line:
                        self._line_to_element[i] = path
                        break
                        
        except Exception as e:
            logger.warning(f"Error construyendo mapa de líneas: {e}")
            # Continuar sin mapa de líneas
    
    def on_html_motion(self, event):
        """Maneja el movimiento del mouse sobre el HTML preview"""
        try:
            # Obtener la línea actual
            index = self.html_preview.index(f"@{event.x},{event.y}")
            line = int(index.split('.')[0])
            
            # Limpiar el resaltado anterior
            if hasattr(self, '_last_hover_line') and self._last_hover_line:
                self.html_preview.tag_remove("hover", f"{self._last_hover_line}.0", f"{self._last_hover_line}.end")
            
            # Resaltar la línea actual
            self.html_preview.tag_add("hover", f"{line}.0", f"{line}.end")
            self._last_hover_line = line
            
            # Actualizar la barra de estado si hay un elemento en esta línea
            if line in self._line_to_element:
                path = self._line_to_element[line]
                element = self.analyzer.get_element_details(path)
                if element:
                    self.status_bar.config(text=f"Elemento: {element.name} - {path}")
            else:
                self.status_bar.config(text="Listo")
                
        except Exception as e:
            logger.error(f"Error en on_html_motion: {e}")
    
    def on_html_click(self, event):
        """Maneja el clic en el HTML preview con selección mejorada"""
        try:
            # Obtener la línea actual
            index = self.html_preview.index(f"@{event.x},{event.y}")
            line = int(index.split('.')[0])
            
            # Verificar si hay un elemento en esta línea
            if line in self._line_to_element:
                path = self._line_to_element[line]
                
                # Alternar selección
                if path in self.selected_dom_elements:
                    self.selected_dom_elements.remove(path)
                    self.html_preview.tag_remove("selected", f"{line}.0", f"{line}.end")
                    # Remover resaltado del árbol DOM
                    if path in self._tree_item_map:
                        item_id = self._tree_item_map[path]
                        self.dom_tree.selection_remove(item_id)
                else:
                    self.selected_dom_elements.add(path)
                    self.html_preview.tag_add("selected", f"{line}.0", f"{line}.end")
                    # Resaltar en el árbol DOM
                    if path in self._tree_item_map:
                        item_id = self._tree_item_map[path]
                        self.dom_tree.selection_add(item_id)
                        self.dom_tree.see(item_id)
                
                # Actualizar la lista de selección
                self.update_selected_list()
                
                # Mostrar información del elemento seleccionado
                if self.analyzer:
                    element = self.analyzer.get_element_details(path)
                    if element:
                        element_text = element.get_text(strip=True)
                        element_type = self.analyzer.get_element_type(element)
                        self.status_bar.config(text=f"Elemento seleccionado: {element.name} ({element_type}) - {element_text[:50]}{'...' if len(element_text) > 50 else ''}")
                
        except Exception as e:
            logger.error(f"Error en on_html_click: {e}")
    
    def on_html_leave(self, event):
        """Maneja cuando el mouse sale del HTML preview"""
        if hasattr(self, '_last_hover_line') and self._last_hover_line:
            self.html_preview.tag_remove("hover", f"{self._last_hover_line}.0", f"{self._last_hover_line}.end")
            self._last_hover_line = None
        self.status_bar.config(text="Listo")
    
    def update_selected_list(self):
        """Actualiza la lista de elementos seleccionados"""
        self.selected_listbox.delete(0, tk.END)
        for path in sorted(self.selected_dom_elements):
            try:
                # Mostrar información más útil en la lista
                element = self.analyzer.get_element_details(path) if self.analyzer else None
                if element:
                    element_text = element.get_text(strip=True)
                    display_text = f"{element.name}: {element_text[:50]}{'...' if len(element_text) > 50 else ''}"
                else:
                    display_text = path
                
                self.selected_listbox.insert(tk.END, display_text)
                
                # Resaltar en el árbol DOM si es posible
                if path in self._tree_item_map:
                    item_id = self._tree_item_map[path]
                    self.dom_tree.selection_set(item_id)
                    self.dom_tree.see(item_id)
                    
            except Exception as e:
                logger.warning(f"Error actualizando elemento {path}: {e}")
                # Mostrar el path como fallback
                self.selected_listbox.insert(tk.END, path)
        
        # Actualizar contador
        self.update_selection_counter()

    def update_selection_counter(self):
        """Actualiza el contador de elementos seleccionados"""
        # Buscar el label del contador y actualizarlo
        for widget in self.root.winfo_children():
            if hasattr(widget, 'winfo_children'):
                for child in widget.winfo_children():
                    if hasattr(child, 'winfo_children'):
                        for grandchild in child.winfo_children():
                            if isinstance(grandchild, ttk.Label) and "Elementos seleccionados:" in grandchild.cget('text'):
                                grandchild.config(text=f"Elementos seleccionados: {len(self.selected_dom_elements)}")
                                return

    def clear_all_selections(self):
        """Limpia todas las selecciones"""
        self.selected_dom_elements.clear()
        self.update_selected_list()
        # Limpiar resaltados en el HTML preview
        if hasattr(self, 'html_preview'):
            self.html_preview.tag_remove("selected", "1.0", tk.END)

    def select_all_elements(self):
        """Selecciona todos los elementos del DOM"""
        if not self.analyzer:
            messagebox.showwarning("Advertencia", "No hay página analizada")
            return
        
        # Obtener todos los elementos del DOM
        dom_tree = self.analyzer.get_dom_tree()
        for node in dom_tree:
            self.selected_dom_elements.add(node['path'])
        
        self.update_selected_list()
        messagebox.showinfo("Éxito", f"Se seleccionaron {len(self.selected_dom_elements)} elementos")

    def on_dom_tree_double_click(self, event):
        """Maneja el doble clic en el árbol DOM"""
        self.select_dom_element()
    
    def select_dom_element(self):
        """Selecciona el elemento actual del árbol DOM usando la ruta real"""
        item = self.dom_tree.focus()
        if item:
            try:
                # Obtener el path del elemento desde los tags del item
                tags = self.dom_tree.item(item, 'tags')
                if tags:
                    element_path = tags[0]  # El primer tag es el path
                    if element_path and element_path not in self.selected_dom_elements:
                        self.selected_dom_elements.add(element_path)
                        self.update_selected_list()
                        self.status_bar.config(text=f"Elemento seleccionado: {element_path}")
                else:
                    # Fallback: intentar obtener el path de otra manera
                    element_path = self.get_element_path(item)
                    if element_path and element_path not in self.selected_dom_elements:
                        self.selected_dom_elements.add(element_path)
                        self.update_selected_list()
                        self.status_bar.config(text=f"Elemento seleccionado: {element_path}")
            except Exception as e:
                logger.warning(f"Error seleccionando elemento del DOM: {e}")
                messagebox.showwarning("Advertencia", "No se pudo seleccionar el elemento")
    
    def deselect_dom_element(self):
        """Deselecciona el elemento actual"""
        selection = self.selected_listbox.curselection()
        if selection:
            try:
                selected_text = self.selected_listbox.get(selection[0])
                
                # Encontrar el path del elemento en el texto seleccionado
                element_path = None
                for path in self.selected_dom_elements:
                    if path in selected_text:
                        element_path = path
                        break
                
                if element_path:
                    self.selected_dom_elements.discard(element_path)
                    self.update_selected_list()
                    self.status_bar.config(text=f"Elemento deseleccionado: {element_path}")
                else:
                    messagebox.showwarning("Advertencia", "No se pudo identificar el elemento a deseleccionar")
                    
            except Exception as e:
                logger.warning(f"Error deseleccionando elemento: {e}")
                messagebox.showwarning("Advertencia", "Error al deseleccionar el elemento")
    
    def view_element_html(self):
        """Muestra el HTML completo del elemento seleccionado"""
        selection = self.selected_listbox.curselection()
        if not selection:
            messagebox.showwarning("Advertencia", "Por favor seleccione un elemento primero")
            return
        
        if not self.analyzer:
            messagebox.showwarning("Advertencia", "No hay página analizada. Por favor analice una URL primero.")
            return
        
        try:
            # Obtener el elemento seleccionado
            selected_text = self.selected_listbox.get(selection[0])
            
            # Extraer el path del elemento del texto mostrado
            element_path = None
            if ':' in selected_text:
                # Buscar el path en el texto
                for path in self.selected_dom_elements:
                    if path in selected_text:
                        element_path = path
                        break
            
            if not element_path:
                messagebox.showwarning("Advertencia", "No se pudo identificar el elemento seleccionado")
                return
            
            # Obtener el elemento
            element = self.analyzer.get_element_details(element_path)
            if element:
                html_window = tk.Toplevel(self.root)
                html_window.title(f"HTML del elemento: {element_path}")
                html_window.geometry("800x600")
                
                # Frame principal
                main_frame = ttk.Frame(html_window, padding=10)
                main_frame.pack(fill=tk.BOTH, expand=True)
                
                # Información del elemento
                info_frame = ttk.LabelFrame(main_frame, text="Información del Elemento", padding=5)
                info_frame.pack(fill=tk.X, pady=(0, 10))
                
                ttk.Label(info_frame, text=f"Tag: {element.name}").pack(anchor=tk.W)
                ttk.Label(info_frame, text=f"Path: {element_path}").pack(anchor=tk.W)
                
                # Atributos
                if element.attrs:
                    attrs_text = ", ".join([f'{k}="{v}"' for k, v in element.attrs.items()])
                    ttk.Label(info_frame, text=f"Atributos: {attrs_text}").pack(anchor=tk.W)
                
                # Texto del elemento
                element_text = element.get_text(strip=True)
                if element_text:
                    ttk.Label(info_frame, text=f"Texto: {element_text[:100]}{'...' if len(element_text) > 100 else ''}").pack(anchor=tk.W)
                
                # HTML del elemento
                html_frame = ttk.LabelFrame(main_frame, text="HTML del Elemento", padding=5)
                html_frame.pack(fill=tk.BOTH, expand=True)
                
                html_text = tk.Text(html_frame, wrap=tk.WORD)
                html_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                
                # Scrollbar
                scrollbar = ttk.Scrollbar(html_frame, orient=tk.VERTICAL, command=html_text.yview)
                html_text.configure(yscrollcommand=scrollbar.set)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                
                # Insertar HTML formateado
                html_content = str(element)
                html_text.insert(tk.END, html_content)
                html_text.config(state=tk.DISABLED)
                
                # Botones
                button_frame = ttk.Frame(main_frame)
                button_frame.pack(fill=tk.X, pady=(10, 0))
                
                ttk.Button(button_frame, text="📋 Copiar HTML", 
                          command=lambda: self.copy_to_clipboard(html_content)).pack(side=tk.LEFT, padx=2)
                ttk.Button(button_frame, text="📋 Copiar Texto", 
                          command=lambda: self.copy_to_clipboard(element_text)).pack(side=tk.LEFT, padx=2)
                ttk.Button(button_frame, text="❌ Cerrar", 
                          command=html_window.destroy).pack(side=tk.RIGHT, padx=2)
                
                # Aplicar tema
                self.apply_light_theme_to_toplevel(html_window)
                
            else:
                messagebox.showwarning("Advertencia", "No se pudo obtener el elemento seleccionado")
                
        except Exception as e:
            logger.error(f"Error mostrando HTML del elemento: {e}")
            messagebox.showerror("Error", f"Error mostrando HTML del elemento: {str(e)}")
    
    def copy_to_clipboard(self, text):
        """Copia texto al portapapeles"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copiado", "El contenido se ha copiado al portapapeles")
    
    def get_element_path(self, item):
        """Obtiene la ruta real de un elemento en el árbol DOM"""
        tags = self.dom_tree.item(item, 'tags')
        if tags:
            return tags[0]
        return None
    
    def search_dom_tree(self):
        """Busca y resalta nodos en el árbol DOM por tag, clase o id"""
        query = self.search_entry.get().strip().lower()
        if not query:
            return
        # Limpiar selección previa
        for item in self.dom_tree.get_children(''):
            self.dom_tree.selection_remove(item)
        # Buscar y seleccionar
        def match(node):
            tag = self.dom_tree.item(node, 'text').lower()
            attrs = self.dom_tree.item(node, 'values')[0].lower()
            return (query in tag) or (f'class={query}' in attrs) or (f'id={query}' in attrs)
        matches = []
        def recurse(item):
            if match(item):
                matches.append(item)
            for child in self.dom_tree.get_children(item):
                recurse(child)
        for item in self.dom_tree.get_children(''):
            recurse(item)
        if matches:
            self.dom_tree.selection_set(matches)
            self.dom_tree.see(matches[0])
            self.show_quick_preview()

    def select_by_css(self):
        """Selecciona todos los nodos que coincidan con el selector CSS ingresado con funcionalidad avanzada"""
        selector = self.selector_entry.get().strip()
        if not selector or not self.analyzer:
            return
        
        try:
            # Usar selectores avanzados si están disponibles
            if hasattr(self, 'advanced_selectors') and self.advanced_selectors:
                # Intentar usar selectores avanzados primero
                detected_elements = self.advanced_selectors.auto_detect_elements(self.analyzer.soup)
                
                # Buscar en elementos detectados automáticamente
                for element_type, elements in detected_elements.items():
                    if selector.lower() in element_type.lower():
                        for element in elements:
                            path = self.analyzer.get_element_path(element)
                            if path:
                                self.selected_dom_elements.add(path)
            
            # Búsqueda CSS tradicional
            elements = self.analyzer.soup.select(selector)
            
            # Obtener sus rutas de manera más eficiente
            dom_tree = self.analyzer.get_dom_tree()
            element_to_path = {}
            
            # Crear mapa de elementos a rutas
            for node in dom_tree:
                element = self.analyzer.get_element_details(node['path'])
                if element:
                    element_to_path[id(element)] = node['path']
            
            # Encontrar rutas de elementos seleccionados
            paths = set()
            for el in elements:
                if id(el) in element_to_path:
                    paths.add(element_to_path[id(el)])
            
            # Añadir a selección
            for path in paths:
                self.selected_dom_elements.add(path)
            
            self.update_selected_list()
            
            # Mostrar estadísticas
            if paths:
                messagebox.showinfo("Selección CSS", 
                                  f"Se seleccionaron {len(paths)} elementos con el selector '{selector}'")
            else:
                messagebox.showwarning("Sin resultados", 
                                     f"No se encontraron elementos con el selector '{selector}'")
                
        except Exception as e:
            logger.error(f"Error en selección CSS: {e}")
            messagebox.showerror("Error", f"Error en selección CSS: {str(e)}")

    def show_url_list_window(self):
        """Muestra la ventana para añadir lista de URLs"""
        URLListManager(self.root, self)

    def export_selection(self):
        """Exporta la selección actual del HTML a un archivo"""
        try:
            # Obtener la selección actual
            selected_text = self.html_preview.get("sel.first", "sel.last")
            if not selected_text:
                messagebox.showwarning("Advertencia", "Por favor seleccione texto para exportar")
                return
            
            # Preguntar por el formato de exportación
            export_format = self.ask_export_format()
            if not export_format:
                return
                
            # Preguntar por el archivo de destino
            default_filename = f"html_selection_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            file_ext = {
                'TXT': '.txt',
                'HTML': '.html'
            }[export_format]
            
            file_path = filedialog.asksaveasfilename(
                defaultextension=file_ext,
                filetypes=[(f"{export_format} files", f"*{file_ext}")],
                initialfile=default_filename
            )
            
            if not file_path:
                return
                
            # Exportar según el formato
            with open(file_path, 'w', encoding='utf-8') as f:
                if export_format == 'HTML':
                    # Crear un documento HTML completo
                    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>HTML Selection Export</title>
    <style>
        body {{ font-family: monospace; white-space: pre-wrap; }}
    </style>
</head>
<body>
{selected_text}
</body>
</html>"""
                    f.write(html_content)
                else:  # TXT
                    f.write(selected_text)
                    
            messagebox.showinfo("Éxito", f"Selección exportada correctamente a {file_path}")
            
        except tk.TclError:  # No hay selección
            messagebox.showwarning("Advertencia", "Por favor seleccione texto para exportar")
        except Exception as e:
            messagebox.showerror("Error", f"Error al exportar la selección: {str(e)}")
    
    def copy_selection(self):
        """Copia la selección actual al portapapeles"""
        try:
            selected_text = self.html_preview.get("sel.first", "sel.last")
            if selected_text:
                self.root.clipboard_clear()
                self.root.clipboard_append(selected_text)
                messagebox.showinfo("Copiado", "Texto copiado al portapapeles")
            else:
                messagebox.showwarning("Advertencia", "Por favor seleccione texto para copiar")
        except tk.TclError:
            messagebox.showwarning("Advertencia", "Por favor seleccione texto para copiar")
        except Exception as e:
            messagebox.showerror("Error", f"Error al copiar la selección: {str(e)}")

    def add_selection_to_dom(self):
        """Añade la selección actual al panel de selección DOM"""
        try:
            # Obtener la selección actual
            selected_text = self.html_preview.get("sel.first", "sel.last")
            if not selected_text:
                messagebox.showwarning("Advertencia", "Por favor seleccione texto para añadir")
                return
            
            # Crear un elemento BeautifulSoup temporal para analizar la selección
            temp_soup = BeautifulSoup(selected_text, 'lxml')
            
            # Si la selección es un elemento HTML válido
            if temp_soup.find():
                # Obtener el elemento raíz de la selección
                root_element = temp_soup.find()
                
                # Buscar este elemento en el HTML original
                if self.analyzer:
                    # Obtener todos los elementos que coincidan con el tag
                    matching_elements = self.analyzer.soup.find_all(root_element.name)
                    
                    # Para cada elemento coincidente, verificar si coincide con la selección
                    for element in matching_elements:
                        if str(element) == str(root_element):
                            # Obtener la ruta del elemento
                            path = self.analyzer.get_element_path(element)
                            if path and path not in self.selected_dom_elements:
                                self.selected_dom_elements.add(path)
                                self.update_selected_list()
                                messagebox.showinfo("Éxito", "Elemento añadido a la selección DOM")
                                return
                    
                    messagebox.showwarning("Advertencia", "No se pudo encontrar una coincidencia exacta en el DOM")
                else:
                    messagebox.showwarning("Advertencia", "No hay página analizada")
            else:
                messagebox.showwarning("Advertencia", "La selección no es un elemento HTML válido")
                
        except tk.TclError:
            messagebox.showwarning("Advertencia", "Por favor seleccione texto para añadir")
        except Exception as e:
            messagebox.showerror("Error", f"Error al añadir la selección: {str(e)}")

    def ask_export_format(self):
        """Muestra un diálogo para seleccionar el formato de exportación"""
        class ExportDialog(tk.Toplevel):
            def __init__(self, parent):
                super().__init__(parent)
                self.parent = parent
                self.result = None
                
                self.title("Formato de Exportación")
                self.geometry("300x200")
                self.resizable(False, False)
                
                ttk.Label(self, text="Seleccione el formato de exportación:").pack(pady=10)
                
                self.format_var = tk.StringVar(value='JSON')
                
                formats = ['JSON', 'CSV', 'TXT', 'HTML']
                for fmt in formats:
                    ttk.Radiobutton(self, text=fmt, variable=self.format_var, value=fmt).pack(anchor=tk.W)
                
                button_frame = ttk.Frame(self)
                button_frame.pack(pady=10)
                
                ttk.Button(button_frame, text="Aceptar", command=self.on_accept).pack(side=tk.LEFT, padx=5)
                ttk.Button(button_frame, text="Cancelar", command=self.on_cancel).pack(side=tk.RIGHT, padx=5)
            
            def on_accept(self):
                self.result = self.format_var.get()
                self.destroy()
            
            def on_cancel(self):
                self.result = None
                self.destroy()
        
        dialog = ExportDialog(self.root)
        self.root.wait_window(dialog)
        return dialog.result

    def highlight_selected_element(self):
        """Resalta el elemento seleccionado en la vista previa HTML"""
        selection = self.selected_listbox.curselection()
        if selection and self.analyzer and hasattr(self, 'formatted_html'):
            element_path = self.selected_listbox.get(selection[0])
            element = self.analyzer.get_element_details(element_path)
            if element:
                try:
                    # Limpiar resaltados anteriores
                    self.html_preview.tag_remove("selected", "1.0", tk.END)
                    
                    # Buscar el elemento en el HTML formateado
                    start_index = self.html_preview.search(str(element), "1.0", tk.END)
                    if start_index:
                        end_index = f"{start_index}+{len(str(element))}c"
                        self.html_preview.tag_add("selected", start_index, end_index)
                        self.html_preview.see(start_index)  # Scroll hasta el elemento
                        self.status_bar.config(text="Elemento resaltado en la vista previa.")
                    else:
                        messagebox.showwarning("Advertencia", "No se pudo encontrar el elemento en la vista previa")
                except Exception as e:
                    messagebox.showerror("Error", f"No se pudo resaltar el elemento: {e}")

    def export_selected_elements(self):
        """Exporta los elementos seleccionados del DOM"""
        if not self.selected_dom_elements:
            messagebox.showwarning("Advertencia", "No hay elementos seleccionados para exportar")
            return
        
        if not self.analyzer:
            messagebox.showwarning("Advertencia", "No hay página analizada. Por favor analice una URL primero.")
            return
        
        # Preguntar por el formato de exportación
        export_format = self.ask_export_format()
        if not export_format:
            return
        
        # Preguntar por el archivo de destino
        default_filename = f"dom_elements_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        file_ext = {
            'JSON': '.json',
            'CSV': '.csv',
            'TXT': '.txt',
            'HTML': '.html'
        }[export_format]
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=file_ext,
            filetypes=[(f"{export_format} files", f"*{file_ext}")],
            initialfile=default_filename
        )
        
        if not file_path:
            return
        
        try:
            # Recopilar información de los elementos seleccionados
            elements_data = []
            for element_path in sorted(self.selected_dom_elements):
                element = self.analyzer.get_element_details(element_path)
                if element:
                    element_info = {
                        'path': element_path,
                        'tag': element.name,
                        'attributes': dict(element.attrs),
                        'text_content': element.get_text(strip=True),
                        'html_content': str(element),
                        'element_type': self.analyzer.get_element_type(element)
                    }
                    elements_data.append(element_info)
            
            # Exportar según el formato
            if export_format == 'JSON':
                self.export_elements_json(elements_data, file_path)
            elif export_format == 'CSV':
                self.export_elements_csv(elements_data, file_path)
            elif export_format == 'TXT':
                self.export_elements_txt(elements_data, file_path)
            elif export_format == 'HTML':
                self.export_elements_html(elements_data, file_path)
            
            messagebox.showinfo("Éxito", f"Elementos exportados correctamente a {file_path}")
            
        except Exception as e:
            logger.error(f"Error exportando elementos: {e}")
            messagebox.showerror("Error", f"Error al exportar elementos: {str(e)}")

    def export_elements_json(self, elements_data, file_path):
        """Exporta elementos en formato JSON"""
        export_data = {
            'export_info': {
                'timestamp': datetime.now().isoformat(),
                'total_elements': len(elements_data),
                'source_url': self.current_url
            },
            'elements': elements_data
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

    def export_elements_csv(self, elements_data, file_path):
        """Exporta elementos en formato CSV"""
        import csv
        
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Escribir encabezados
            writer.writerow(['Path', 'Tag', 'Element Type', 'Text Content', 'Attributes', 'HTML Content'])
            
            # Escribir datos
            for element in elements_data:
                # Limitar el contenido de texto para CSV
                text_content = element['text_content'][:200] + '...' if len(element['text_content']) > 200 else element['text_content']
                html_content = element['html_content'][:500] + '...' if len(element['html_content']) > 500 else element['html_content']
                attributes_str = ', '.join([f"{k}={v}" for k, v in element['attributes'].items()])
                
                writer.writerow([
                    element['path'],
                    element['tag'],
                    element['element_type'],
                    text_content,
                    attributes_str,
                    html_content
                ])

    def export_elements_txt(self, elements_data, file_path):
        """Exporta elementos en formato TXT"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("EXPORTACIÓN DE ELEMENTOS DEL DOM\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"URL de origen: {self.current_url}\n")
            f.write(f"Fecha de exportación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total de elementos: {len(elements_data)}\n\n")
            
            for i, element in enumerate(elements_data, 1):
                f.write(f"ELEMENTO {i}:\n")
                f.write("-" * 40 + "\n")
                f.write(f"Path: {element['path']}\n")
                f.write(f"Tag: {element['tag']}\n")
                f.write(f"Tipo: {element['element_type']}\n")
                f.write(f"Atributos: {element['attributes']}\n")
                f.write(f"Contenido de texto: {element['text_content']}\n")
                f.write(f"HTML: {element['html_content']}\n\n")

    def export_elements_html(self, elements_data, file_path):
        """Exporta elementos en formato HTML"""
        html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Elementos del DOM Exportados - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .element {{ background: #f8f9fa; padding: 15px; margin: 15px 0; border-radius: 5px; border-left: 4px solid #007bff; }}
        .element-header {{ font-weight: bold; color: #007bff; margin-bottom: 10px; }}
        .element-info {{ margin: 5px 0; }}
        .html-preview {{ background: #e9ecef; padding: 10px; border-radius: 3px; margin: 10px 0; font-family: monospace; white-space: pre-wrap; font-size: 12px; }}
        .text-content {{ background: #fff3cd; padding: 10px; border-radius: 3px; margin: 10px 0; }}
        .attributes {{ background: #d1ecf1; padding: 10px; border-radius: 3px; margin: 10px 0; font-family: monospace; }}
        .summary {{ background: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Elementos del DOM Exportados</h1>
        
        <div class="summary">
            <h2>📋 Resumen</h2>
            <p><strong>URL de origen:</strong> <a href="{self.current_url}" target="_blank">{self.current_url}</a></p>
            <p><strong>Fecha de exportación:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Total de elementos:</strong> {len(elements_data)}</p>
        </div>
        
        <h2>📄 Elementos Seleccionados</h2>"""
        
        for i, element in enumerate(elements_data, 1):
            # Escapar HTML para mostrar en la página
            import html
            text_content_escaped = html.escape(element['text_content'])
            html_content_escaped = html.escape(element['html_content'])
            
            html_content += f"""
        <div class="element">
            <div class="element-header">Elemento {i}: {element['tag']} ({element['element_type']})</div>
            <div class="element-info"><strong>Path:</strong> {element['path']}</div>
            <div class="element-info"><strong>Tag:</strong> {element['tag']}</div>
            <div class="element-info"><strong>Tipo:</strong> {element['element_type']}</div>
            
            <div class="attributes">
                <strong>Atributos:</strong><br>
                {', '.join([f'{k}="{v}"' for k, v in element['attributes'].items()])}
            </div>
            
            <div class="text-content">
                <strong>Contenido de texto:</strong><br>
                {text_content_escaped}
            </div>
            
            <div class="html-preview">
                <strong>HTML:</strong><br>
                {html_content_escaped}
            </div>
        </div>"""
        
        html_content += """
    </div>
</body>
</html>"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

    def export_elements_by_type(self):
        """Exporta elementos del DOM agrupados por tipo"""
        if not self.analyzer:
            messagebox.showwarning("Advertencia", "No hay página analizada. Por favor analice una URL primero.")
            return
        
        # Crear ventana de selección de tipo
        type_window = tk.Toplevel(self.root)
        type_window.title("Exportar Elementos por Tipo")
        type_window.geometry("400x300")
        type_window.resizable(False, False)
        
        # Frame principal
        main_frame = ttk.Frame(type_window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_frame, text="Selecciona el tipo de elementos a exportar:", font=('Arial', 12, 'bold')).pack(pady=(0, 10))
        
        # Opciones de tipo
        type_var = tk.StringVar(value='all')
        
        types = [
            ('Todos los elementos', 'all'),
            ('Solo enlaces (a)', 'link'),
            ('Solo imágenes (img)', 'image'),
            ('Solo títulos (h1-h6)', 'title'),
            ('Solo párrafos (p)', 'text'),
            ('Solo tablas (table)', 'table'),
            ('Solo formularios (form)', 'form'),
            ('Solo listas (ul, ol)', 'list')
        ]
        
        for text, value in types:
            ttk.Radiobutton(main_frame, text=text, variable=type_var, value=value).pack(anchor=tk.W, pady=2)
        
        # Botones
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        ttk.Button(button_frame, text="Exportar", 
                  command=lambda: self._export_by_type(type_var.get(), type_window)).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Cancelar", 
                  command=type_window.destroy).pack(side=tk.RIGHT, padx=2)

    def _export_by_type(self, element_type, type_window):
        """Realiza la exportación por tipo"""
        try:
            # Obtener todos los elementos del DOM
            dom_tree = self.analyzer.get_dom_tree()
            
            # Filtrar elementos por tipo
            filtered_elements = []
            for node in dom_tree:
                element = self.analyzer.get_element_details(node['path'])
                if element:
                    current_type = self.analyzer.get_element_type(element)
                    
                    # Aplicar filtros según el tipo seleccionado
                    if element_type == 'all':
                        include = True
                    elif element_type == 'link' and element.name == 'a':
                        include = True
                    elif element_type == 'image' and element.name == 'img':
                        include = True
                    elif element_type == 'title' and element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        include = True
                    elif element_type == 'text' and element.name == 'p':
                        include = True
                    elif element_type == 'table' and element.name == 'table':
                        include = True
                    elif element_type == 'form' and element.name == 'form':
                        include = True
                    elif element_type == 'list' and element.name in ['ul', 'ol']:
                        include = True
                    else:
                        include = False
                    
                    if include:
                        element_info = {
                            'path': node['path'],
                            'tag': element.name,
                            'attributes': dict(element.attrs),
                            'text_content': element.get_text(strip=True),
                            'html_content': str(element),
                            'element_type': current_type
                        }
                        filtered_elements.append(element_info)
            
            if not filtered_elements:
                messagebox.showwarning("Advertencia", f"No se encontraron elementos del tipo seleccionado")
                return
            
            # Preguntar por el formato de exportación
            export_format = self.ask_export_format()
            if not export_format:
                return
            
            # Preguntar por el archivo de destino
            type_name = element_type.replace('_', ' ').title()
            default_filename = f"dom_{element_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            file_ext = {
                'JSON': '.json',
                'CSV': '.csv',
                'TXT': '.txt',
                'HTML': '.html'
            }[export_format]
            
            file_path = filedialog.asksaveasfilename(
                defaultextension=file_ext,
                filetypes=[(f"{export_format} files", f"*{file_ext}")],
                initialfile=default_filename
            )
            
            if not file_path:
                return
            
            # Exportar según el formato
            if export_format == 'JSON':
                self.export_elements_json(filtered_elements, file_path)
            elif export_format == 'CSV':
                self.export_elements_csv(filtered_elements, file_path)
            elif export_format == 'TXT':
                self.export_elements_txt(filtered_elements, file_path)
            elif export_format == 'HTML':
                self.export_elements_html(filtered_elements, file_path)
            
            # Cerrar ventana de selección
            type_window.destroy()
            
            messagebox.showinfo("Éxito", f"Se exportaron {len(filtered_elements)} elementos de tipo '{type_name}' a {file_path}")
            
        except Exception as e:
            logger.error(f"Error exportando por tipo: {e}")
            messagebox.showerror("Error", f"Error al exportar por tipo: {str(e)}")

    def show_quick_preview(self, event=None):
        """Muestra un resumen rápido del nodo seleccionado en el panel inferior derecho"""
        item = self.dom_tree.focus()
        if item and self.analyzer:
            element_path = self.get_element_path(item)
            element = self.analyzer.get_element_details(element_path)
            if element:
                resumen = f"Tag: {element.name}\nAtributos: {dict(element.attrs)}\nTexto: {element.get_text(strip=True)[:200]}"
                self.quick_preview.config(state=tk.NORMAL)
                self.quick_preview.delete(1.0, tk.END)
                self.quick_preview.insert(tk.END, resumen)
                self.quick_preview.config(state=tk.DISABLED)
            else:
                self.quick_preview.config(state=tk.NORMAL)
                self.quick_preview.delete(1.0, tk.END)
                self.quick_preview.insert(tk.END, "No se pudo obtener el elemento.")
                self.quick_preview.config(state=tk.DISABLED)

    def show_interesting_elements(self, event=None):
        """Muestra los elementos interesantes detectados en la página"""
        if not self.analyzer:
            messagebox.showwarning("Advertencia", "No hay contenido analizado para mostrar")
            return
        
        # Crear ventana para mostrar elementos interesantes
        interesting_window = tk.Toplevel(self.root)
        interesting_window.title("Elementos Interesantes Detectados")
        interesting_window.geometry("900x700")
        
        # Centrar la ventana
        interesting_window.update_idletasks()
        x = (interesting_window.winfo_screenwidth() // 2) - (900 // 2)
        y = (interesting_window.winfo_screenheight() // 2) - (700 // 2)
        interesting_window.geometry(f"900x700+{x}+{y}")
        
        # Frame principal
        main_frame = ttk.Frame(interesting_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Notebook para pestañas
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Crear pestañas para cada categoría de elementos interesantes
        if hasattr(self.analyzer, 'interesting_elements'):
            for category, items in self.analyzer.interesting_elements.items():
                if items:  # Solo crear pestañas si hay elementos
                    # Crear frame para esta categoría
                    category_frame = ttk.Frame(notebook)
                    notebook.add(category_frame, text=category.replace('_', ' ').title())
                    
                    # Crear Treeview para esta categoría
                    tree = ttk.Treeview(category_frame, columns=('content', 'details', 'type'), show='headings')
                    tree.heading('content', text='Contenido')
                    tree.heading('details', text='Detalles')
                    tree.heading('type', text='Tipo')
                    
                    # Configurar columnas
                    tree.column('content', width=400)
                    tree.column('details', width=200)
                    tree.column('type', width=100)
                    
                    # Scrollbar
                    scrollbar = ttk.Scrollbar(category_frame, orient=tk.VERTICAL, command=tree.yview)
                    tree.configure(yscrollcommand=scrollbar.set)
                    
                    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                    
                    # Insertar elementos
                    for item in items:
                        if isinstance(item, dict):
                            content = item.get('text', '')[:100] + '...' if len(item.get('text', '')) > 100 else item.get('text', '')
                            details = str(item.get('element', '')) + ' ' + str(item.get('classes', ''))
                            item_type = item.get('type', '')
                            tree.insert('', 'end', values=(content, details, item_type))
                        else:
                            tree.insert('', 'end', values=(str(item)[:100], '', ''))
        
        # Pestaña de estadísticas
        stats_frame = ttk.Frame(notebook)
        notebook.add(stats_frame, text="Estadísticas")
        
        stats_text = tk.Text(stats_frame, wrap=tk.WORD, font=("Consolas", 10))
        stats_scroll = ttk.Scrollbar(stats_frame, orient=tk.VERTICAL, command=stats_text.yview)
        stats_text.configure(yscrollcommand=stats_scroll.set)
        
        stats_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        stats_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Mostrar estadísticas
        if hasattr(self.analyzer, 'interesting_elements'):
            stats_text.insert(tk.END, "ESTADÍSTICAS DE ELEMENTOS INTERESANTES\n")
            stats_text.insert(tk.END, "=" * 60 + "\n\n")
            
            total_elements = 0
            for category, items in self.analyzer.interesting_elements.items():
                count = len(items)
                total_elements += count
                stats_text.insert(tk.END, f"{category.replace('_', ' ').title()}: {count} elementos\n")
            
            stats_text.insert(tk.END, f"\nTotal de elementos interesantes: {total_elements}\n")
            
            # Mostrar también estadísticas de elementos básicos
            if hasattr(self.analyzer, 'elements_found'):
                stats_text.insert(tk.END, "\nESTADÍSTICAS DE ELEMENTOS BÁSICOS\n")
                stats_text.insert(tk.END, "=" * 60 + "\n\n")
                
                for category, items in self.analyzer.elements_found.items():
                    stats_text.insert(tk.END, f"{category.title()}: {len(items)}\n")
        
        stats_text.config(state=tk.DISABLED)

    def detect_main_content(self):
        """Detecta y resalta el contenido principal usando readability-lxml."""
        if not self.analyzer:
            messagebox.showwarning("Advertencia", "Primero analiza una página.")
            return
        main_soup, title = self.analyzer.get_main_content()
        if not main_soup or not main_soup.body:
            messagebox.showwarning("No detectado", "No se pudo detectar el contenido principal.")
            return
        # Obtener HTML limpio del contenido principal
        main_html = main_soup.body.decode_contents() if main_soup.body else str(main_soup)
        # Resaltar en la vista previa HTML
        self.html_preview.tag_configure('main_content', background='#FFF59D')
        idx = self.html_preview.search(main_html[:40], '1.0', tk.END)  # Buscar por el inicio del contenido
        if idx:
            end_idx = f"{idx}+{len(main_html)}c"
            self.html_preview.tag_add('main_content', idx, end_idx)
            self.html_preview.see(idx)
        # Agregar a seleccionados si se puede mapear
        # Buscar el nodo más grande que contenga el HTML
        dom_tree = self.analyzer.get_dom_tree()
        for node in dom_tree:
            element = self.analyzer.get_element_details(node['path'])
            if element and main_html.strip() in str(element):
                self.selected_dom_elements.add(node['path'])
                self.update_selected_list()
                break
        # Mostrar en previsualización rápida
        self.quick_preview.config(state=tk.NORMAL)
        self.quick_preview.delete(1.0, tk.END)
        self.quick_preview.insert(tk.END, main_html[:1000])
        self.quick_preview.config(state=tk.DISABLED)
        # Mostrar título en barra de estado
        if title:
            self.status_bar.config(text=f"Contenido principal detectado: {title}")
        else:
            self.status_bar.config(text="Contenido principal detectado.")
        # Guardar para exportación
        self.main_content_html = main_html
        self.main_content_title = title

    def export_data(self):
        """Exporta los datos seleccionados a un archivo, incluyendo el contenido principal si existe."""
        # Preguntar por el formato de exportación
        export_format = self.ask_export_format()
        if not export_format:
            return
        # Preguntar por el archivo de destino
        default_filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        file_ext = {
            'TXT': '.txt',
            'HTML': '.html',
            'CSV': '.csv',
            'JSON': '.json'
        }[export_format]
        file_path = filedialog.asksaveasfilename(
            defaultextension=file_ext,
            filetypes=[(f"{export_format} files", f"*{file_ext}")],
            initialfile=default_filename
        )
        if not file_path:
            return
        # Exportar según el formato
        try:
            main_title = getattr(self, 'main_content_title', None) or 'Contenido Principal'
            main_html = getattr(self, 'main_content_html', None)
            if export_format == 'JSON':
                data = {'main_content': {'title': main_title, 'html': main_html}}
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            elif export_format == 'CSV':
                import csv
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow(['title', 'html'])
                    writer.writerow([main_title, main_html])
            elif export_format == 'TXT':
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"{main_title}\n{'='*80}\n{main_html}")
            elif export_format == 'HTML':
                with open(file_path, 'w', encoding='utf-8') as f:
                    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset=\"UTF-8\">
    <title>{main_title}</title>
</head>
<body>
{main_html}
</body>
</html>"""
                    f.write(html_content)
            messagebox.showinfo("Éxito", f"Contenido principal exportado correctamente a {file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Error al exportar el contenido principal: {str(e)}")

    def start_crawling(self):
        """Inicia el crawling inteligente de las URLs"""
        urls = self.url_text.get(1.0, tk.END).strip().splitlines()
        urls = [u.strip() for u in urls if u.strip()]
        if not urls:
            messagebox.showerror("Error", "Por favor ingrese al menos una URL válida")
            return
        
        # Preguntar por la estrategia de crawling
        strategy = self.ask_crawling_strategy()
        if not strategy:
            return
        
        self._cancel_requested = False
        self.cancel_button.config(state=tk.NORMAL)
        
        # Iniciar crawling en hilo separado
        threading.Thread(target=self._perform_crawling, args=(urls, strategy), daemon=True).start()
        self.status_bar.config(text="Crawleando...")

    def ask_crawling_strategy(self):
        """Pregunta por la estrategia de crawling"""
        class CrawlingStrategyDialog(tk.Toplevel):
            def __init__(self, parent):
                super().__init__(parent)
                self.parent = parent
                self.result = None
                
                self.title("Estrategia de Crawling")
                self.geometry("300x200")
                self.resizable(False, False)
                
                ttk.Label(self, text="Seleccione la estrategia de crawling:").pack(pady=10)
                
                self.strategy_var = tk.StringVar(value='breadth_first')
                
                strategies = [
                    ('Breadth First', 'breadth_first'),
                    ('Depth First', 'depth_first'),
                    ('Priority Based', 'priority')
                ]
                
                for text, value in strategies:
                    ttk.Radiobutton(self, text=text, variable=self.strategy_var, value=value).pack(anchor=tk.W)
                
                button_frame = ttk.Frame(self)
                button_frame.pack(pady=10)
                
                ttk.Button(button_frame, text="Aceptar", command=self.on_accept).pack(side=tk.LEFT, padx=5)
                ttk.Button(button_frame, text="Cancelar", command=self.on_cancel).pack(side=tk.RIGHT, padx=5)
            
            def on_accept(self):
                self.result = self.strategy_var.get()
                self.destroy()
            
            def on_cancel(self):
                self.result = None
                self.destroy()
        
        dialog = CrawlingStrategyDialog(self.root)
        self.root.wait_window(dialog)
        return dialog.result

    def _perform_crawling(self, urls, strategy):
        """Realiza el crawling de las URLs con actualizaciones en tiempo real"""
        try:
            # Crear ventana de progreso
            progress_window = tk.Toplevel(self.root)
            progress_window.title("Crawling en Progreso")
            progress_window.geometry("600x400")
            progress_window.resizable(False, False)
            
            # Frame principal
            main_frame = ttk.Frame(progress_window, padding=10)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Título
            ttk.Label(main_frame, text="🕷️ Crawling en Progreso", font=('Arial', 14, 'bold')).pack(pady=(0, 10))
            
            # Información de estado
            status_frame = ttk.LabelFrame(main_frame, text="Estado", padding=10)
            status_frame.pack(fill=tk.X, pady=(0, 10))
            
            status_label = ttk.Label(status_frame, text="Iniciando crawling...")
            status_label.pack()
            
            # Estadísticas en tiempo real
            stats_frame = ttk.LabelFrame(main_frame, text="Estadísticas", padding=10)
            stats_frame.pack(fill=tk.X, pady=(0, 10))
            
            pages_label = ttk.Label(stats_frame, text="Páginas encontradas: 0")
            pages_label.pack()
            
            links_label = ttk.Label(stats_frame, text="Enlaces totales: 0")
            links_label.pack()
            
            errors_label = ttk.Label(stats_frame, text="Errores: 0")
            errors_label.pack()
            
            # Log de actividad
            log_frame = ttk.LabelFrame(main_frame, text="Actividad", padding=5)
            log_frame.pack(fill=tk.BOTH, expand=True)
            
            log_text = tk.Text(log_frame, height=10, wrap=tk.WORD)
            log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
            log_text.configure(yscrollcommand=log_scrollbar.set)
            log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Barra de progreso
            progress_var = tk.DoubleVar()
            progress_bar = ttk.Progressbar(main_frame, variable=progress_var, maximum=100)
            progress_bar.pack(fill=tk.X, pady=(10, 0))
            
            # Botón de cancelar
            cancel_button = ttk.Button(main_frame, text="Cancelar", 
                                     command=lambda: self._cancel_crawling(progress_window))
            cancel_button.pack(pady=(10, 0))
            
            def update_progress(message, pages=0, links=0, errors=0):
                """Actualiza la información de progreso"""
                try:
                    status_label.config(text=message)
                    pages_label.config(text=f"Páginas encontradas: {pages}")
                    links_label.config(text=f"Enlaces totales: {links}")
                    errors_label.config(text=f"Errores: {errors}")
                    
                    # Agregar al log
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    log_text.insert(tk.END, f"[{timestamp}] {message}\n")
                    log_text.see(tk.END)
                    
                    # Actualizar barra de progreso (estimación)
                    if pages > 0:
                        progress = min((pages / 100) * 100, 95)  # Máximo 95% hasta completar
                        progress_var.set(progress)
                    
                    progress_window.update()
                except Exception:
                    pass  # Ignorar errores de GUI si la ventana se cierra
            
            # Iniciar crawling con callbacks
            def on_page_found(url, depth):
                """Callback cuando se encuentra una página"""
                update_progress(f"Página encontrada: {url} (profundidad {depth})")
            
            def on_link_found(url, source_url):
                """Callback cuando se encuentra un enlace"""
                update_progress(f"Enlace encontrado: {url}")
            
            def on_error(url, error):
                """Callback cuando ocurre un error"""
                update_progress(f"Error en {url}: {error}")
            
                        # Realizar crawling
            if self.crawler:
                result = self.crawler.crawl(urls, strategy)
            else:
                result = {"error": "Crawler not available"}
            
            # Completar progreso
            progress_var.set(100)
            update_progress("Crawling completado!", 
                          result.total_pages, 
                          result.total_links, 
                          len(result.errors))
            
            # Cerrar ventana de progreso después de 2 segundos
            progress_window.after(2000, progress_window.destroy)
            
            if not self._cancel_requested:
                self.queue.put(('crawling_complete', result))
            
        except Exception as e:
            logger.error(f"Error durante el crawling: {e}")
            self.queue.put(('error', f"Error durante el crawling: {str(e)}"))

    def _cancel_crawling(self, progress_window):
        """Cancela el crawling en progreso"""
        self._cancel_requested = True
        progress_window.destroy()
        self.status_bar.config(text="Crawling cancelado")

    def show_crawling_results(self, result):
        """Muestra los resultados del crawling"""
        try:
            # Crear ventana de resultados
            results_window = tk.Toplevel(self.root)
            results_window.title("Resultados del Crawling")
            results_window.geometry("1200x800")
            
            # Frame principal
            main_frame = ttk.Frame(results_window, padding=10)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Notebook para diferentes vistas
            notebook = ttk.Notebook(main_frame)
            notebook.pack(fill=tk.BOTH, expand=True)
            
            # Pestaña de resumen
            summary_frame = ttk.Frame(notebook)
            notebook.add(summary_frame, text="Resumen")
            
            # Resumen de estadísticas
            summary_stats_frame = ttk.LabelFrame(summary_frame, text="Estadísticas del Crawling", padding=10)
            summary_stats_frame.pack(fill=tk.X, pady=(0, 10))
            
            # Crear frame para estadísticas en dos columnas
            stats_frame = ttk.Frame(summary_stats_frame)
            stats_frame.pack(fill=tk.X)
            
            # Columna izquierda
            left_stats = ttk.Frame(stats_frame)
            left_stats.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            # Columna derecha
            right_stats = ttk.Frame(stats_frame)
            right_stats.pack(side=tk.RIGHT, fill=tk.X, expand=True)
            
            # Estadísticas principales
            ttk.Label(left_stats, text=f"📄 Páginas encontradas: {result.total_pages}", font=('Arial', 10, 'bold')).pack(anchor=tk.W)
            ttk.Label(left_stats, text=f"🔗 Enlaces totales: {result.total_links}").pack(anchor=tk.W)
            ttk.Label(left_stats, text=f"🖼️ Imágenes totales: {result.total_images}").pack(anchor=tk.W)
            ttk.Label(left_stats, text=f"⏱️ Tiempo de crawling: {result.crawl_time:.2f} segundos").pack(anchor=tk.W)
            ttk.Label(left_stats, text=f"❌ Errores: {len(result.errors)}").pack(anchor=tk.W)
            
            # Estadísticas adicionales
            if result.pages:
                avg_links = sum(len(page.links) for page in result.pages) / len(result.pages)
                avg_images = sum(len(page.images) for page in result.pages) / len(result.pages)
                depths = [page.crawl_depth for page in result.pages]
                max_depth = max(depths) if depths else 0
                
                ttk.Label(right_stats, text=f"📊 Enlaces promedio por página: {avg_links:.1f}").pack(anchor=tk.W)
                ttk.Label(right_stats, text=f"📊 Imágenes promedio por página: {avg_images:.1f}").pack(anchor=tk.W)
                ttk.Label(right_stats, text=f"📊 Profundidad máxima: {max_depth}").pack(anchor=tk.W)
                ttk.Label(right_stats, text=f"📊 Tasa de éxito: {((len(result.pages) - len(result.errors)) / len(result.pages) * 100):.1f}%").pack(anchor=tk.W)
            
            # Información de paginación
            if result.pagination_info:
                ttk.Label(summary_stats_frame, text=f"📑 Páginas con paginación: {len(result.pagination_info)}", font=('Arial', 9, 'bold')).pack(anchor=tk.W, pady=(10, 0))
            
            # Pestaña de páginas
            pages_frame = ttk.Frame(notebook)
            notebook.add(pages_frame, text="Páginas")
            
            # Frame para controles de páginas
            pages_controls = ttk.Frame(pages_frame)
            pages_controls.pack(fill=tk.X, pady=(0, 10))
            
            ttk.Label(pages_controls, text="Filtrar por profundidad:").pack(side=tk.LEFT)
            depth_var = tk.StringVar(value="Todas")
            depth_combo = ttk.Combobox(pages_controls, textvariable=depth_var, values=["Todas", "0", "1", "2", "3"], width=10)
            depth_combo.pack(side=tk.LEFT, padx=5)
            
            ttk.Label(pages_controls, text="Buscar:").pack(side=tk.LEFT, padx=(20, 0))
            search_var = tk.StringVar()
            search_entry = ttk.Entry(pages_controls, textvariable=search_var, width=30)
            search_entry.pack(side=tk.LEFT, padx=5)
            
            # Treeview para las páginas
            columns = ('url', 'title', 'links', 'images', 'depth', 'content_length')
            pages_tree = ttk.Treeview(pages_frame, columns=columns, show='headings')
            
            pages_tree.heading('url', text='URL')
            pages_tree.heading('title', text='Título')
            pages_tree.heading('links', text='Enlaces')
            pages_tree.heading('images', text='Imágenes')
            pages_tree.heading('depth', text='Profundidad')
            pages_tree.heading('content_length', text='Tamaño')
            
            pages_tree.column('url', width=350)
            pages_tree.column('title', width=250)
            pages_tree.column('links', width=80)
            pages_tree.column('images', width=80)
            pages_tree.column('depth', width=80)
            pages_tree.column('content_length', width=100)
            
            # Insertar páginas
            for page in result.pages:
                content_size = f"{page.content_length:,}" if page.content_length else "0"
                pages_tree.insert('', 'end', values=(
                    page.url,
                    page.title[:50] + '...' if len(page.title) > 50 else page.title,
                    len(page.links),
                    len(page.images),
                    page.crawl_depth,
                    content_size
                ))
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(pages_frame, orient=tk.VERTICAL, command=pages_tree.yview)
            pages_tree.configure(yscrollcommand=scrollbar.set)
            
            pages_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Pestaña de enlaces
            links_frame = ttk.Frame(notebook)
            notebook.add(links_frame, text="Enlaces")
            
            # Treeview para enlaces
            links_columns = ('url', 'source_page', 'depth')
            links_tree = ttk.Treeview(links_frame, columns=links_columns, show='headings')
            
            links_tree.heading('url', text='URL del Enlace')
            links_tree.heading('source_page', text='Página Origen')
            links_tree.heading('depth', text='Profundidad')
            
            links_tree.column('url', width=500)
            links_tree.column('source_page', width=300)
            links_tree.column('depth', width=100)
            
            # Insertar enlaces
            all_links = set()
            for page in result.pages:
                for link in page.links:
                    all_links.add((link, page.url, page.crawl_depth))
            
            for link_url, source_page, depth in sorted(all_links):
                links_tree.insert('', 'end', values=(link_url, source_page, depth))
            
            # Scrollbar para enlaces
            links_scrollbar = ttk.Scrollbar(links_frame, orient=tk.VERTICAL, command=links_tree.yview)
            links_tree.configure(yscrollcommand=links_scrollbar.set)
            
            links_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            links_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Pestaña de errores
            errors_frame = ttk.Frame(notebook)
            notebook.add(errors_frame, text="Errores")
            
            if result.errors:
                errors_text = tk.Text(errors_frame, wrap=tk.WORD)
                errors_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                
                for i, error in enumerate(result.errors, 1):
                    errors_text.insert(tk.END, f"{i}. {error}\n")
                
                errors_text.config(state=tk.DISABLED)
            else:
                ttk.Label(errors_frame, text="✅ No se encontraron errores durante el crawling", 
                         font=('Arial', 12)).pack(expand=True)
            
            # Botones de acción
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X, pady=(10, 0))
            
            # Frame para botones de exportación
            export_frame = ttk.LabelFrame(button_frame, text="Exportar Datos", padding=5)
            export_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            ttk.Button(export_frame, text="📄 JSON Completo", 
                      command=lambda: self.export_crawling_results(result, 'json')).pack(side=tk.LEFT, padx=2)
            ttk.Button(export_frame, text="📊 CSV Resumen", 
                      command=lambda: self.export_crawling_results(result, 'csv')).pack(side=tk.LEFT, padx=2)
            ttk.Button(export_frame, text="📋 TXT Reporte", 
                      command=lambda: self.export_crawling_results(result, 'txt')).pack(side=tk.LEFT, padx=2)
            ttk.Button(export_frame, text="🌐 HTML Reporte", 
                      command=lambda: self.export_crawling_results(result, 'html')).pack(side=tk.LEFT, padx=2)
            
            # Frame para botones de acción
            action_frame = ttk.LabelFrame(button_frame, text="Acciones", padding=5)
            action_frame.pack(side=tk.RIGHT, fill=tk.X)
            
            ttk.Button(action_frame, text="🔍 Analizar Páginas", 
                      command=lambda: self.analyze_crawled_pages(result)).pack(side=tk.LEFT, padx=2)
            ttk.Button(action_frame, text="📊 Ver Métricas", 
                      command=lambda: self.show_crawler_metrics(result)).pack(side=tk.LEFT, padx=2)
            ttk.Button(action_frame, text="💾 Guardar Sesión", 
                      command=lambda: self.save_crawler_session(result)).pack(side=tk.LEFT, padx=2)
            ttk.Button(action_frame, text="❌ Cerrar", 
                      command=results_window.destroy).pack(side=tk.RIGHT, padx=2)
            
        except Exception as e:
            logger.error(f"Error mostrando resultados del crawling: {e}")
            messagebox.showerror("Error", f"Error mostrando resultados: {str(e)}")

    def export_crawling_results(self, result, format_type):
        """Exporta los resultados del crawling en diferentes formatos"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=f'.{format_type}',
            filetypes=[(f"{format_type.upper()} files", f"*.{format_type}")],
            initialfile=f"crawling_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_type}"
        )
        
        if file_path:
            try:
                if format_type == 'json':
                    success = self.crawler.export_crawl_results(file_path, format_type)
                elif format_type == 'csv':
                    success = self.export_crawling_csv(result, file_path)
                elif format_type == 'txt':
                    success = self.export_crawling_txt(result, file_path)
                elif format_type == 'html':
                    success = self.export_crawling_html(result, file_path)
                else:
                    messagebox.showerror("Error", f"Formato no soportado: {format_type}")
                    return
                
                if success:
                    messagebox.showinfo("Éxito", f"Resultados del crawling exportados a {file_path}")
                else:
                    messagebox.showerror("Error", "Error al exportar resultados del crawling")
                    
            except Exception as e:
                messagebox.showerror("Error", f"Error al exportar: {str(e)}")

    def export_crawling_csv(self, result, file_path):
        """Exporta resultados del crawling en formato CSV"""
        try:
            import csv
            
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Escribir resumen
                writer.writerow(['RESUMEN DEL CRAWLING'])
                writer.writerow(['Páginas encontradas', result.total_pages])
                writer.writerow(['Enlaces totales', result.total_links])
                writer.writerow(['Imágenes totales', result.total_images])
                writer.writerow(['Tiempo de crawling', f"{result.crawl_time:.2f} segundos"])
                writer.writerow(['Errores', len(result.errors)])
                writer.writerow([])
                
                # Escribir páginas
                writer.writerow(['PÁGINAS ENCONTRADAS'])
                writer.writerow(['URL', 'Título', 'Enlaces', 'Imágenes', 'Profundidad', 'Tamaño'])
                
                for page in result.pages:
                    writer.writerow([
                        page.url,
                        page.title,
                        len(page.links),
                        len(page.images),
                        page.crawl_depth,
                        page.content_length or 0
                    ])
                
                writer.writerow([])
                
                # Escribir enlaces únicos
                writer.writerow(['ENLACES ÚNICOS'])
                writer.writerow(['URL', 'Página Origen', 'Profundidad'])
                
                all_links = set()
                for page in result.pages:
                    for link in page.links:
                        all_links.add((link, page.url, page.crawl_depth))
                
                for link_url, source_page, depth in sorted(all_links):
                    writer.writerow([link_url, source_page, depth])
                
                writer.writerow([])
                
                # Escribir errores
                if result.errors:
                    writer.writerow(['ERRORES'])
                    for error in result.errors:
                        writer.writerow([error])
            
            return True
        except Exception as e:
            logger.error(f"Error exportando CSV: {e}")
            return False

    def export_crawling_txt(self, result, file_path):
        """Exporta resultados del crawling en formato TXT"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("REPORTE DE CRAWLING\n")
                f.write("=" * 80 + "\n\n")
                
                # Resumen
                f.write("RESUMEN:\n")
                f.write("-" * 40 + "\n")
                f.write(f"Páginas encontradas: {result.total_pages}\n")
                f.write(f"Enlaces totales: {result.total_links}\n")
                f.write(f"Imágenes totales: {result.total_images}\n")
                f.write(f"Tiempo de crawling: {result.crawl_time:.2f} segundos\n")
                f.write(f"Errores: {len(result.errors)}\n\n")
                
                # Estadísticas adicionales
                if result.pages:
                    avg_links = sum(len(page.links) for page in result.pages) / len(result.pages)
                    avg_images = sum(len(page.images) for page in result.pages) / len(result.pages)
                    depths = [page.crawl_depth for page in result.pages]
                    max_depth = max(depths) if depths else 0
                    
                    f.write(f"Enlaces promedio por página: {avg_links:.1f}\n")
                    f.write(f"Imágenes promedio por página: {avg_images:.1f}\n")
                    f.write(f"Profundidad máxima: {max_depth}\n")
                    f.write(f"Tasa de éxito: {((len(result.pages) - len(result.errors)) / len(result.pages) * 100):.1f}%\n\n")
                
                # Páginas
                f.write("PÁGINAS ENCONTRADAS:\n")
                f.write("-" * 40 + "\n")
                for i, page in enumerate(result.pages, 1):
                    f.write(f"{i}. {page.url}\n")
                    f.write(f"   Título: {page.title}\n")
                    f.write(f"   Enlaces: {len(page.links)}\n")
                    f.write(f"   Imágenes: {len(page.images)}\n")
                    f.write(f"   Profundidad: {page.crawl_depth}\n")
                    f.write(f"   Tamaño: {page.content_length or 0:,} bytes\n\n")
                
                # Enlaces únicos
                f.write("ENLACES ÚNICOS:\n")
                f.write("-" * 40 + "\n")
                all_links = set()
                for page in result.pages:
                    for link in page.links:
                        all_links.add(link)
                
                for i, link in enumerate(sorted(all_links), 1):
                    f.write(f"{i}. {link}\n")
                
                f.write(f"\nTotal de enlaces únicos: {len(all_links)}\n\n")
                
                # Errores
                if result.errors:
                    f.write("ERRORES:\n")
                    f.write("-" * 40 + "\n")
                    for i, error in enumerate(result.errors, 1):
                        f.write(f"{i}. {error}\n")
                else:
                    f.write("No se encontraron errores durante el crawling.\n")
            
            return True
        except Exception as e:
            logger.error(f"Error exportando TXT: {e}")
            return False

    def export_crawling_html(self, result, file_path):
        """Exporta resultados del crawling en formato HTML"""
        try:
            html_content = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reporte de Crawling - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }}
        h2 {{ color: #555; margin-top: 30px; }}
        .summary {{ background: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .summary-item {{ margin: 5px 0; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #007bff; }}
        .pages-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .pages-table th, .pages-table td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        .pages-table th {{ background-color: #007bff; color: white; }}
        .pages-table tr:nth-child(even) {{ background-color: #f2f2f2; }}
        .error {{ color: #dc3545; }}
        .success {{ color: #28a745; }}
        .info {{ color: #17a2b8; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Reporte de Crawling</h1>
        <p><strong>Fecha:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="summary">
            <h2>📈 Resumen</h2>
            <div class="stats">
                <div class="stat-card">
                    <strong>📄 Páginas encontradas:</strong><br>
                    <span class="info">{result.total_pages}</span>
                </div>
                <div class="stat-card">
                    <strong>🔗 Enlaces totales:</strong><br>
                    <span class="info">{result.total_links}</span>
                </div>
                <div class="stat-card">
                    <strong>🖼️ Imágenes totales:</strong><br>
                    <span class="info">{result.total_images}</span>
                </div>
                <div class="stat-card">
                    <strong>⏱️ Tiempo de crawling:</strong><br>
                    <span class="info">{result.crawl_time:.2f} segundos</span>
                </div>
                <div class="stat-card">
                    <strong>❌ Errores:</strong><br>
                    <span class="error">{len(result.errors)}</span>
                </div>
            </div>
        </div>
        
        <h2>📋 Páginas Encontradas</h2>
        <table class="pages-table">
            <thead>
                <tr>
                    <th>URL</th>
                    <th>Título</th>
                    <th>Enlaces</th>
                    <th>Imágenes</th>
                    <th>Profundidad</th>
                    <th>Tamaño</th>
                </tr>
            </thead>
            <tbody>"""
            
            for page in result.pages:
                content_size = f"{page.content_length:,}" if page.content_length else "0"
                html_content += f"""
                <tr>
                    <td><a href="{page.url}" target="_blank">{page.url}</a></td>
                    <td>{page.title}</td>
                    <td>{len(page.links)}</td>
                    <td>{len(page.images)}</td>
                    <td>{page.crawl_depth}</td>
                    <td>{content_size} bytes</td>
                </tr>"""
            
            html_content += """
            </tbody>
        </table>
        
        <h2>🔗 Enlaces Únicos</h2>
        <ul>"""
            
            all_links = set()
            for page in result.pages:
                for link in page.links:
                    all_links.add(link)
            
            for link in sorted(all_links):
                html_content += f'<li><a href="{link}" target="_blank">{link}</a></li>'
            
            html_content += f"""
        </ul>
        <p><strong>Total de enlaces únicos:</strong> {len(all_links)}</p>
        
        <h2>❌ Errores</h2>"""
            
            if result.errors:
                html_content += "<ul>"
                for error in result.errors:
                    html_content += f'<li class="error">{error}</li>'
                html_content += "</ul>"
            else:
                html_content += '<p class="success">✅ No se encontraron errores durante el crawling.</p>'
            
            html_content += """
    </div>
</body>
</html>"""
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return True
        except Exception as e:
            logger.error(f"Error exportando HTML: {e}")
            return False

    def analyze_crawled_pages(self, result):
        """Analiza las páginas encontradas por el crawler"""
        try:
            # Verificar que el resultado sea válido
            if not hasattr(result, 'pages') or not result.pages:
                messagebox.showwarning("Advertencia", "No hay páginas para analizar")
                return
            
            # Crear analizadores para las páginas encontradas
            self.all_html_contents = []
            self.all_analyzers = []
            
            for page in result.pages:
                try:
                    # Obtener el contenido HTML de la página
                    if self.ethical_scraper:
                        page_result = self.ethical_scraper.get_page(page.url)
                    else:
                        # Fallback to basic requests
                        import requests
                        try:
                            response = requests.get(page.url, timeout=30)
                            page_result = type('MockResult', (), {
                                'content': response.text,
                                'status_code': response.status_code,
                                'headers': dict(response.headers),
                                'error': None
                            })()
                        except Exception as e:
                            page_result = type('MockResult', (), {
                                'content': '',
                                'status_code': 0,
                                'headers': {},
                                'error': str(e)
                            })()
                    
                    # Extraer contenido HTML
                    if hasattr(page_result, 'content'):
                        html_content = page_result.content
                    elif hasattr(page_result, 'html'):
                        html_content = page_result.html
                    else:
                        html_content = str(page_result)
                    
                    # Crear analizador
                    analyzer = BasicHTMLAnalyzer(html_content)
                    analyzer.analyze_structure()
                    
                    self.all_html_contents.append(html_content)
                    self.all_analyzers.append(analyzer)
                    
                except Exception as e:
                    logger.warning(f"Error procesando página {getattr(page, 'url', 'unknown')}: {e}")
                    continue
            
            # Mostrar la primera página en la interfaz
            if self.all_analyzers:
                first_page = result.pages[0]
                self.current_url = getattr(first_page, 'url', 'Unknown URL')
                self.html_content = self.all_html_contents[0]
                self.analyzer = self.all_analyzers[0]
                
                self.queue.put(('update_preview', self.html_content))
                self.queue.put(('update_dom_tree', self.analyzer.get_dom_tree()))
                self.queue.put(('status', f"Analizadas {len(self.all_analyzers)} páginas del crawler"))
                
                messagebox.showinfo("Éxito", f"Se analizaron {len(self.all_analyzers)} páginas del crawler")
            else:
                messagebox.showwarning("Advertencia", "No se pudieron analizar páginas del crawler")
            
        except Exception as e:
            logger.error(f"Error analizando páginas del crawler: {e}")
            messagebox.showerror("Error", f"Error analizando páginas: {str(e)}")

    def show_crawler_metrics(self, result):
        """Muestra métricas detalladas del crawler"""
        try:
            # Verificar que el resultado sea válido
            if not hasattr(result, 'pages') or not result.pages:
                messagebox.showwarning("Advertencia", "No hay datos de métricas disponibles")
                return
            
            # Crear ventana de métricas
            metrics_window = tk.Toplevel(self.root)
            metrics_window.title("Métricas Detalladas del Crawler")
            metrics_window.geometry("800x600")
            
            # Notebook para diferentes métricas
            notebook = ttk.Notebook(metrics_window)
            notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Pestaña de rendimiento
            performance_frame = ttk.Frame(notebook)
            notebook.add(performance_frame, text="Rendimiento")
            
            performance_text = tk.Text(performance_frame, wrap=tk.WORD)
            performance_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Calcular métricas
            if result.pages:
                try:
                    avg_links = sum(len(getattr(page, 'links', [])) for page in result.pages) / len(result.pages)
                    avg_images = sum(len(getattr(page, 'images', [])) for page in result.pages) / len(result.pages)
                    depths = [getattr(page, 'crawl_depth', 0) for page in result.pages]
                    max_depth = max(depths) if depths else 0
                    min_depth = min(depths) if depths else 0
                    
                    # Distribución por profundidad
                    depth_distribution = {}
                    for depth in depths:
                        depth_distribution[depth] = depth_distribution.get(depth, 0) + 1
                    
                    performance_text.insert(tk.END, "📊 MÉTRICAS DE RENDIMIENTO\n")
                    performance_text.insert(tk.END, "=" * 50 + "\n\n")
                    performance_text.insert(tk.END, f"⏱️ Tiempo total: {getattr(result, 'crawl_time', 0):.2f} segundos\n")
                    performance_text.insert(tk.END, f"📄 Páginas por segundo: {len(result.pages) / getattr(result, 'crawl_time', 1):.2f}\n")
                    performance_text.insert(tk.END, f"🔗 Enlaces promedio por página: {avg_links:.1f}\n")
                    performance_text.insert(tk.END, f"🖼️ Imágenes promedio por página: {avg_images:.1f}\n")
                    performance_text.insert(tk.END, f"📊 Profundidad mínima: {min_depth}\n")
                    performance_text.insert(tk.END, f"📊 Profundidad máxima: {max_depth}\n")
                    
                    # Calcular tasa de éxito
                    total_errors = len(getattr(result, 'errors', []))
                    success_rate = ((len(result.pages) - total_errors) / len(result.pages) * 100) if result.pages else 0
                    performance_text.insert(tk.END, f"📊 Tasa de éxito: {success_rate:.1f}%\n\n")
                    
                    performance_text.insert(tk.END, "📈 DISTRIBUCIÓN POR PROFUNDIDAD\n")
                    performance_text.insert(tk.END, "-" * 40 + "\n")
                    for depth in sorted(depth_distribution.keys()):
                        percentage = (depth_distribution[depth] / len(result.pages)) * 100
                        performance_text.insert(tk.END, f"Profundidad {depth}: {depth_distribution[depth]} páginas ({percentage:.1f}%)\n")
                        
                except Exception as e:
                    logger.warning(f"Error calculando métricas de rendimiento: {e}")
                    performance_text.insert(tk.END, f"Error calculando métricas: {str(e)}\n")
            
            performance_text.config(state=tk.DISABLED)
            
            # Pestaña de análisis de contenido
            content_frame = ttk.Frame(notebook)
            notebook.add(content_frame, text="Análisis de Contenido")
            
            content_text = tk.Text(content_frame, wrap=tk.WORD)
            content_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            if result.pages:
                try:
                    # Análisis de tamaños de contenido
                    content_sizes = [getattr(page, 'content_length', 0) or 0 for page in result.pages]
                    if content_sizes:
                        avg_size = sum(content_sizes) / len(content_sizes)
                        max_size = max(content_sizes)
                        min_size = min(content_sizes)
                        
                        content_text.insert(tk.END, "📏 ANÁLISIS DE TAMAÑOS\n")
                        content_text.insert(tk.END, "=" * 40 + "\n")
                        content_text.insert(tk.END, f"Tamaño promedio: {avg_size:,.0f} bytes\n")
                        content_text.insert(tk.END, f"Tamaño máximo: {max_size:,.0f} bytes\n")
                        content_text.insert(tk.END, f"Tamaño mínimo: {min_size:,.0f} bytes\n\n")
                    
                    # Análisis de títulos
                    titles = [getattr(page, 'title', '') for page in result.pages if getattr(page, 'title', '')]
                    if titles:
                        content_text.insert(tk.END, "📝 ANÁLISIS DE TÍTULOS\n")
                        content_text.insert(tk.END, "-" * 30 + "\n")
                        content_text.insert(tk.END, f"Total de títulos: {len(titles)}\n")
                        content_text.insert(tk.END, f"Títulos únicos: {len(set(titles))}\n")
                        
                        # Títulos más largos
                        longest_titles = sorted(titles, key=len, reverse=True)[:5]
                        content_text.insert(tk.END, "\nTítulos más largos:\n")
                        for i, title in enumerate(longest_titles, 1):
                            content_text.insert(tk.END, f"{i}. {title[:100]}...\n")
                            
                except Exception as e:
                    logger.warning(f"Error analizando contenido: {e}")
                    content_text.insert(tk.END, f"Error analizando contenido: {str(e)}\n")
            
            content_text.config(state=tk.DISABLED)
            
            # Botones de acción
            button_frame = ttk.Frame(metrics_window)
            button_frame.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Button(button_frame, text="Exportar Métricas", 
                      command=lambda: self.export_crawler_metrics(result)).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Cerrar", 
                      command=metrics_window.destroy).pack(side=tk.RIGHT, padx=2)
            
        except Exception as e:
            logger.error(f"Error mostrando métricas del crawler: {e}")
            messagebox.showerror("Error", f"Error mostrando métricas: {str(e)}")

    def save_crawler_session(self, result):
        """Guarda la sesión del crawler para recuperarla más tarde"""
        try:
            # Verificar que el resultado sea válido
            if not hasattr(result, 'pages') or not result.pages:
                messagebox.showwarning("Advertencia", "No hay datos de sesión para guardar")
                return
            
            # Crear directorio de sesiones si no existe
            sessions_dir = "crawler_sessions"
            if not os.path.exists(sessions_dir):
                os.makedirs(sessions_dir)
            
            # Generar nombre de archivo
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            session_file = os.path.join(sessions_dir, f"session_{timestamp}.json")
            
            # Preparar datos de la sesión
            session_data = {
                'timestamp': timestamp,
                'crawl_time': getattr(result, 'crawl_time', 0),
                'total_pages': getattr(result, 'total_pages', len(result.pages)),
                'total_links': getattr(result, 'total_links', 0),
                'total_images': getattr(result, 'total_images', 0),
                'errors': getattr(result, 'errors', []),
                'pages': []
            }
            
            # Guardar información básica de cada página
            for page in result.pages:
                try:
                    page_data = {
                        'url': getattr(page, 'url', ''),
                        'title': getattr(page, 'title', ''),
                        'crawl_depth': getattr(page, 'crawl_depth', 0),
                        'content_length': getattr(page, 'content_length', 0),
                        'links_count': len(getattr(page, 'links', [])),
                        'images_count': len(getattr(page, 'images', [])),
                        'links': list(getattr(page, 'links', [])),
                        'images': list(getattr(page, 'images', []))
                    }
                    session_data['pages'].append(page_data)
                except Exception as e:
                    logger.warning(f"Error procesando página para sesión: {e}")
                    continue
            
            # Guardar archivo
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            messagebox.showinfo("Éxito", f"Sesión guardada en:\n{session_file}")
            
        except Exception as e:
            logger.error(f"Error guardando sesión del crawler: {e}")
            messagebox.showerror("Error", f"Error guardando sesión: {str(e)}")

    def export_crawler_metrics(self, result):
        """Exporta las métricas del crawler a archivo"""
        try:
            # Verificar que el resultado sea válido
            if not hasattr(result, 'pages') or not result.pages:
                messagebox.showwarning("Advertencia", "No hay métricas para exportar")
                return
            
            file_path = filedialog.asksaveasfilename(
                defaultextension='.json',
                filetypes=[("JSON files", "*.json")],
                initialfile=f"crawler_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            if file_path:
                # Preparar métricas para exportación
                metrics_data = {
                    'export_timestamp': datetime.now().isoformat(),
                    'crawl_time': getattr(result, 'crawl_time', 0),
                    'total_pages': getattr(result, 'total_pages', len(result.pages)),
                    'total_links': getattr(result, 'total_links', 0),
                    'total_images': getattr(result, 'total_images', 0),
                    'errors': getattr(result, 'errors', []),
                    'pages_summary': []
                }
                
                # Resumen de páginas
                for page in result.pages:
                    try:
                        page_summary = {
                            'url': getattr(page, 'url', ''),
                            'title': getattr(page, 'title', ''),
                            'crawl_depth': getattr(page, 'crawl_depth', 0),
                            'content_length': getattr(page, 'content_length', 0),
                            'links_count': len(getattr(page, 'links', [])),
                            'images_count': len(getattr(page, 'images', []))
                        }
                        metrics_data['pages_summary'].append(page_summary)
                    except Exception as e:
                        logger.warning(f"Error procesando página para exportación: {e}")
                        continue
                
                # Calcular métricas adicionales
                if result.pages:
                    try:
                        depths = [getattr(page, 'crawl_depth', 0) for page in result.pages]
                        content_sizes = [getattr(page, 'content_length', 0) or 0 for page in result.pages]
                        
                        metrics_data['calculated_metrics'] = {
                            'max_depth': max(depths) if depths else 0,
                            'min_depth': min(depths) if depths else 0,
                            'avg_content_size': sum(content_sizes) / len(content_sizes) if content_sizes else 0,
                            'max_content_size': max(content_sizes) if content_sizes else 0,
                            'min_content_size': min(content_sizes) if content_sizes else 0,
                            'success_rate': ((len(result.pages) - len(getattr(result, 'errors', []))) / len(result.pages) * 100) if result.pages else 0
                        }
                    except Exception as e:
                        logger.warning(f"Error calculando métricas adicionales: {e}")
                        metrics_data['calculated_metrics'] = {"error": str(e)}
                
                # Guardar archivo
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(metrics_data, f, ensure_ascii=False, indent=2)
                
                messagebox.showinfo("Éxito", f"Métricas del crawler exportadas a:\n{file_path}")
                
        except Exception as e:
            logger.error(f"Error exportando métricas del crawler: {e}")
            messagebox.showerror("Error", f"Error exportando métricas: {str(e)}")

    def load_crawler_session(self):
        """Carga una sesión guardada del crawler"""
        try:
            sessions_dir = "crawler_sessions"
            if not os.path.exists(sessions_dir):
                messagebox.showinfo("Información", "No hay sesiones guardadas. Primero ejecuta un crawling y guárdalo.")
                return
            
            # Buscar archivos de sesión
            session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.json')]
            if not session_files:
                messagebox.showinfo("Información", "No hay sesiones guardadas. Primero ejecuta un crawling y guárdalo.")
                return
            
            # Crear ventana de selección
            session_window = tk.Toplevel(self.root)
            session_window.title("Cargar Sesión de Crawler")
            session_window.geometry("500x400")
            
            # Frame principal
            main_frame = ttk.Frame(session_window, padding=10)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            ttk.Label(main_frame, text="Selecciona una sesión para cargar:", font=('Arial', 12, 'bold')).pack(pady=(0, 10))
            
            # Lista de sesiones
            list_frame = ttk.Frame(main_frame)
            list_frame.pack(fill=tk.BOTH, expand=True)
            
            # Treeview para sesiones
            columns = ('timestamp', 'pages', 'links', 'time')
            session_tree = ttk.Treeview(list_frame, columns=columns, show='headings')
            
            session_tree.heading('timestamp', text='Fecha/Hora')
            session_tree.heading('pages', text='Páginas')
            session_tree.heading('links', text='Enlaces')
            session_tree.heading('time', text='Tiempo')
            
            session_tree.column('timestamp', width=150)
            session_tree.column('pages', width=80)
            session_tree.column('links', width=80)
            session_tree.column('time', width=100)
            
            # Cargar sesiones
            for session_file in sorted(session_files, reverse=True):
                try:
                    with open(os.path.join(sessions_dir, session_file), 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                    
                    # Formatear timestamp
                    timestamp = session_data.get('timestamp', '')
                    if timestamp:
                        try:
                            dt = datetime.strptime(timestamp, '%Y%m%d_%H%M%S')
                            formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                        except Exception:
                            formatted_time = timestamp
                    else:
                        formatted_time = "Desconocido"
                    
                    session_tree.insert('', 'end', values=(
                        formatted_time,
                        session_data.get('total_pages', 0),
                        session_data.get('total_links', 0),
                        f"{session_data.get('crawl_time', 0):.1f}s"
                    ), tags=(session_file,))
                    
                except Exception as e:
                    logger.error(f"Error cargando sesión {session_file}: {e}")
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=session_tree.yview)
            session_tree.configure(yscrollcommand=scrollbar.set)
            
            session_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Botones
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X, pady=(10, 0))
            
            ttk.Button(button_frame, text="Cargar Sesión", 
                      command=lambda: self._load_selected_session(session_tree, sessions_dir, session_window)).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Eliminar Sesión", 
                      command=lambda: self._delete_selected_session(session_tree, sessions_dir)).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Cerrar", 
                      command=session_window.destroy).pack(side=tk.RIGHT, padx=2)
            
        except Exception as e:
            logger.error(f"Error cargando sesiones: {e}")
            messagebox.showerror("Error", f"Error cargando sesiones: {str(e)}")

    def _load_selected_session(self, session_tree, sessions_dir, session_window):
        """Carga la sesión seleccionada"""
        selection = session_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Por favor selecciona una sesión")
            return
        
        session_file = session_tree.item(selection[0])['tags'][0]
        session_path = os.path.join(sessions_dir, session_file)
        
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # Crear un objeto de resultado simulado
            class SessionResult:
                def __init__(self, data):
                    self.total_pages = data.get('total_pages', 0)
                    self.total_links = data.get('total_links', 0)
                    self.total_images = data.get('total_images', 0)
                    self.crawl_time = data.get('crawl_time', 0)
                    self.errors = data.get('errors', [])
                    self.pages = []
                    
                    # Convertir páginas
                    for page_data in data.get('pages', []):
                        class Page:
                            def __init__(self, p_data):
                                self.url = p_data.get('url', '')
                                self.title = p_data.get('title', '')
                                self.crawl_depth = p_data.get('crawl_depth', 0)
                                self.content_length = p_data.get('content_length', 0)
                                self.links = set(p_data.get('links', []))
                                self.images = set(p_data.get('images', []))
                        
                        self.pages.append(Page(page_data))
            
            result = SessionResult(session_data)
            
            # Cerrar ventana de selección
            session_window.destroy()
            
            # Mostrar resultados
            self.show_crawling_results(result)
            
        except Exception as e:
            logger.error(f"Error cargando sesión {session_file}: {e}")
            messagebox.showerror("Error", f"Error cargando sesión: {str(e)}")

    def _delete_selected_session(self, session_tree, sessions_dir):
        """Elimina la sesión seleccionada"""
        selection = session_tree.selection()
        if not selection:
            messagebox.showwarning("Advertencia", "Por favor selecciona una sesión")
            return
        
        session_file = session_tree.item(selection[0])['tags'][0]
        session_path = os.path.join(sessions_dir, session_file)
        
        if messagebox.askyesno("Confirmar", f"¿Estás seguro de que quieres eliminar la sesión {session_file}?"):
            try:
                os.remove(session_path)
                session_tree.delete(selection[0])
                messagebox.showinfo("Éxito", "Sesión eliminada correctamente")
            except Exception as e:
                logger.error(f"Error eliminando sesión {session_file}: {e}")
                messagebox.showerror("Error", f"Error eliminando sesión: {str(e)}")

    def extract_structured_data(self):
        """Extrae datos estructurados de las páginas analizadas"""
        if not self.all_html_contents:
            messagebox.showwarning("Advertencia", "No hay páginas analizadas. Por favor analice URLs primero.")
            return
        
        try:
            # Extraer datos estructurados de todas las páginas
            all_results = []
            for i, html_content in enumerate(self.all_html_contents):
                url = f"URL_{i+1}"  # URL placeholder
                if self.structured_data_extractor:
                    result = self.structured_data_extractor.extract_all(html_content, url)
                else:
                    result = {"error": "Structured data extractor not available"}
                all_results.append(result)
            
            # Mostrar resultados
            self.show_structured_data_results(all_results)
            
        except Exception as e:
            logger.error(f"Error extrayendo datos estructurados: {e}")
            messagebox.showerror("Error", f"Error extrayendo datos estructurados: {str(e)}")

    def show_structured_data_results(self, results):
        """Muestra los resultados de extracción de datos estructurados"""
        # Crear ventana de resultados
        results_window = tk.Toplevel(self.root)
        results_window.title("Datos Estructurados Extraídos")
        results_window.geometry("800x600")
        
        # Notebook para diferentes tipos de datos
        notebook = ttk.Notebook(results_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Pestaña de resumen
        summary_frame = ttk.Frame(notebook)
        notebook.add(summary_frame, text="Resumen")
        
        summary_text = tk.Text(summary_frame, wrap=tk.WORD)
        summary_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        total_items = sum(len(result.items) for result in results)
        summary_text.insert(tk.END, f"Total de elementos extraídos: {total_items}\n\n")
        
        for i, result in enumerate(results):
            summary_text.insert(tk.END, f"URL {i+1}:\n")
            summary_text.insert(tk.END, f"  - Elementos: {len(result.items)}\n")
            summary_text.insert(tk.END, f"  - Tiempo: {result.extraction_time:.2f}s\n")
            summary_text.insert(tk.END, f"  - Errores: {len(result.errors)}\n\n")
        
        # Pestaña de datos JSON-LD
        jsonld_frame = ttk.Frame(notebook)
        notebook.add(jsonld_frame, text="JSON-LD")
        
        jsonld_text = tk.Text(jsonld_frame, wrap=tk.WORD)
        jsonld_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        jsonld_items = []
        for result in results:
            jsonld_items.extend([item for item in result.items if item.source == 'json-ld'])
        
        if jsonld_items:
            jsonld_text.insert(tk.END, json.dumps([item.data for item in jsonld_items], indent=2, ensure_ascii=False))
        else:
            jsonld_text.insert(tk.END, "No se encontraron datos JSON-LD")
        
        # Botones de acción
        button_frame = ttk.Frame(results_window)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(button_frame, text="Exportar JSON", 
                  command=lambda: self.export_structured_data(results, 'json')).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Exportar CSV", 
                  command=lambda: self.export_structured_data(results, 'csv')).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Cerrar", 
                  command=results_window.destroy).pack(side=tk.RIGHT, padx=2)

    def export_structured_data(self, results, format_type):
        """Exporta los datos estructurados"""
        try:
            # Verificar que los resultados sean válidos
            if not results:
                messagebox.showwarning("Advertencia", "No hay datos estructurados para exportar")
                return
            
            file_path = filedialog.asksaveasfilename(
                defaultextension=f'.{format_type}',
                filetypes=[(f"{format_type.upper()} files", f"*.{format_type}")],
                initialfile=f"structured_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{format_type}"
            )
            
            if file_path:
                try:
                    # Combinar todos los items
                    all_items = []
                    for result in results:
                        if hasattr(result, 'items') and result.items:
                            all_items.extend(result.items)
                        elif isinstance(result, dict) and 'items' in result:
                            all_items.extend(result['items'])
                        elif isinstance(result, list):
                            all_items.extend(result)
                    
                    if not all_items:
                        messagebox.showwarning("Advertencia", "No se encontraron elementos para exportar")
                        return
                    
                    # Exportar
                    if self.structured_data_extractor:
                        success = self.structured_data_extractor.export_structured_data(all_items, file_path, format_type)
                    else:
                        # Fallback manual export
                        success = self._manual_export_structured_data(all_items, file_path, format_type)
                    
                    if success:
                        messagebox.showinfo("Éxito", f"Datos estructurados exportados a {file_path}")
                    else:
                        messagebox.showerror("Error", "Error al exportar datos estructurados")
                        
                except Exception as e:
                    logger.error(f"Error procesando datos para exportación: {e}")
                    messagebox.showerror("Error", f"Error procesando datos: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error exportando datos estructurados: {e}")
            messagebox.showerror("Error", f"Error al exportar: {str(e)}")
    
    def _manual_export_structured_data(self, items, file_path, format_type):
        """Exportación manual de datos estructurados como fallback"""
        try:
            if format_type.lower() == 'json':
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(items, f, ensure_ascii=False, indent=2)
                return True
            elif format_type.lower() == 'csv':
                if items and isinstance(items[0], dict):
                    import csv
                    with open(file_path, 'w', newline='', encoding='utf-8') as f:
                        if items:
                            writer = csv.DictWriter(f, fieldnames=items[0].keys())
                            writer.writeheader()
                            writer.writerows(items)
                    return True
                else:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        for item in items:
                            f.write(f"{item}\n")
                    return True
            else:
                # Exportación como texto plano
                with open(file_path, 'w', encoding='utf-8') as f:
                    for item in items:
                        f.write(f"{item}\n")
                return True
        except Exception as e:
            logger.error(f"Error en exportación manual: {e}")
            return False

    def show_metrics(self):
        """Muestra las métricas del sistema con información detallada"""
        try:
            # Obtener métricas básicas
            if self.metrics_collector:
                metrics_summary = self.metrics_collector.get_metrics_summary()
            else:
                metrics_summary = {"error": "Metrics collector not available"}
            
            # Obtener estadísticas de otros componentes con manejo de errores
            crawler_stats = {}
            if self.crawler:
                try:
                    crawler_stats = self.crawler.get_crawl_statistics()
                except Exception as e:
                    logger.warning(f"Error getting crawler stats: {e}")
                    crawler_stats = {"error": str(e)}
            
            etl_stats = {}
            if self.etl_pipeline:
                try:
                    etl_stats = self.etl_pipeline.get_processing_statistics()
                except Exception as e:
                    logger.warning(f"Error getting ETL stats: {e}")
                    etl_stats = {"error": str(e)}
            
            plugin_stats = {}
            if self.plugin_manager:
                try:
                    plugin_stats = self.plugin_manager.get_plugin_statistics()
                except Exception as e:
                    logger.warning(f"Error getting plugin stats: {e}")
                    plugin_stats = {"error": str(e)}
            
            # Obtener métricas de selectores avanzados
            selector_stats = {}
            if hasattr(self, 'advanced_selectors') and self.advanced_selectors:
                try:
                    selector_stats = {
                        'templates_available': len(self.advanced_selectors.list_templates()),
                        'patterns_loaded': len(self.advanced_selectors.common_patterns),
                        'content_patterns': len(self.advanced_selectors.content_patterns),
                        'visual_patterns': len(self.advanced_selectors.visual_patterns),
                        'enable_ai_selectors': getattr(self.advanced_selectors, 'enable_ai_selectors', False),
                        'enable_smart_mapping': getattr(self.advanced_selectors, 'enable_smart_mapping', False)
                    }
                except Exception as e:
                    logger.warning(f"Error getting advanced selectors stats: {e}")
                    selector_stats = {"error": str(e)}
            
            # Obtener métricas de análisis actual
            analysis_stats = {}
            if hasattr(self, 'analyzer') and self.analyzer:
                try:
                    dom_tree = self.analyzer.get_dom_tree()
                    analysis_stats = {
                        'total_elements': len(dom_tree),
                        'selected_elements': len(self.selected_dom_elements),
                        'selection_rate': len(self.selected_dom_elements) / len(dom_tree) if dom_tree else 0,
                        'analyzed_urls': len(self.all_analyzers)
                    }
                except Exception as e:
                    logger.warning(f"Error getting analysis stats: {e}")
                    analysis_stats = {"error": str(e)}
            
            # Crear ventana de métricas
            metrics_window = tk.Toplevel(self.root)
            metrics_window.title("Métricas del Sistema")
            metrics_window.geometry("900x700")
            
            # Notebook para diferentes métricas
            notebook = ttk.Notebook(metrics_window)
            notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Pestaña de rendimiento
            performance_frame = ttk.Frame(notebook)
            notebook.add(performance_frame, text="Rendimiento")
            
            performance_text = tk.Text(performance_frame, wrap=tk.WORD)
            performance_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            if metrics_summary.get('enabled', False) and 'performance' in metrics_summary:
                perf = metrics_summary['performance']
                performance_text.insert(tk.END, f"Rendimiento del Scraper:\n")
                performance_text.insert(tk.END, f"  - Total de requests: {perf.get('total_requests', 0)}\n")
                performance_text.insert(tk.END, f"  - Requests exitosos: {perf.get('successful_requests', 0)}\n")
                performance_text.insert(tk.END, f"  - Tasa de éxito: {perf.get('success_rate', 0):.2%}\n")
                performance_text.insert(tk.END, f"  - Tiempo promedio de respuesta: {perf.get('avg_response_time', 0):.2f}s\n")
                performance_text.insert(tk.END, f"  - Requests por minuto: {perf.get('requests_per_minute', 0):.1f}\n")
                performance_text.insert(tk.END, f"  - Tiempo de actividad: {perf.get('uptime_hours', 0):.1f} horas\n\n")
            else:
                performance_text.insert(tk.END, "Métricas de rendimiento no disponibles\n\n")
            
            # Pestaña de caché
            cache_frame = ttk.Frame(notebook)
            notebook.add(cache_frame, text="Caché")
            
            cache_text = tk.Text(cache_frame, wrap=tk.WORD)
            cache_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            if metrics_summary.get('enabled', False) and 'cache' in metrics_summary:
                cache = metrics_summary['cache']
                cache_text.insert(tk.END, f"Estadísticas de Caché:\n")
                cache_text.insert(tk.END, f"  - Hits: {cache.get('hits', 0)}\n")
                cache_text.insert(tk.END, f"  - Misses: {cache.get('misses', 0)}\n")
                cache_text.insert(tk.END, f"  - Tasa de hit: {cache.get('hit_rate', 0):.2%}\n")
                cache_text.insert(tk.END, f"  - Total de requests: {cache.get('total_requests', 0)}\n")
                cache_text.insert(tk.END, f"  - Tamaño total: {cache.get('total_size_bytes', 0)} bytes\n\n")
            else:
                cache_text.insert(tk.END, "Estadísticas de caché no disponibles\n\n")
            
            # Pestaña de errores
            errors_frame = ttk.Frame(notebook)
            notebook.add(errors_frame, text="Errores")
            
            errors_text = tk.Text(errors_frame, wrap=tk.WORD)
            errors_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            if metrics_summary.get('enabled', False) and 'errors' in metrics_summary:
                errors = metrics_summary['errors']
                errors_text.insert(tk.END, f"Estadísticas de Errores:\n")
                errors_text.insert(tk.END, f"  - Total de errores: {errors.get('total_errors', 0)}\n")
                errors_text.insert(tk.END, f"  - Último error: {errors.get('last_error', 'N/A')}\n\n")
                
                if errors.get('top_errors'):
                    errors_text.insert(tk.END, "Errores más comunes:\n")
                    for error_type, count in errors['top_errors']:
                        errors_text.insert(tk.END, f"  - {error_type}: {count}\n")
            else:
                errors_text.insert(tk.END, "Estadísticas de errores no disponibles\n\n")
            
            # Pestaña de selectores avanzados
            selectors_frame = ttk.Frame(notebook)
            notebook.add(selectors_frame, text="Selectores Avanzados")
            
            selectors_text = tk.Text(selectors_frame, wrap=tk.WORD)
            selectors_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            if selector_stats and 'error' not in selector_stats:
                selectors_text.insert(tk.END, f"Estadísticas de Selectores Avanzados:\n")
                selectors_text.insert(tk.END, f"  - Templates disponibles: {selector_stats.get('templates_available', 0)}\n")
                selectors_text.insert(tk.END, f"  - Patrones cargados: {selector_stats.get('patterns_loaded', 0)}\n")
                selectors_text.insert(tk.END, f"  - Patrones de contenido: {selector_stats.get('content_patterns', 0)}\n")
                selectors_text.insert(tk.END, f"  - Patrones visuales: {selector_stats.get('visual_patterns', 0)}\n")
                selectors_text.insert(tk.END, f"  - IA habilitada: {selector_stats.get('enable_ai_selectors', False)}\n")
                selectors_text.insert(tk.END, f"  - Mapeo inteligente: {selector_stats.get('enable_smart_mapping', False)}\n\n")
            else:
                selectors_text.insert(tk.END, "Selectores avanzados no disponibles\n\n")
            
            # Pestaña de análisis
            analysis_frame = ttk.Frame(notebook)
            notebook.add(analysis_frame, text="Análisis")
            
            analysis_text = tk.Text(analysis_frame, wrap=tk.WORD)
            analysis_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            if analysis_stats and 'error' not in analysis_stats:
                analysis_text.insert(tk.END, f"Estadísticas de Análisis:\n")
                analysis_text.insert(tk.END, f"  - URLs analizadas: {analysis_stats.get('analyzed_urls', 0)}\n")
                analysis_text.insert(tk.END, f"  - Elementos totales: {analysis_stats.get('total_elements', 0)}\n")
                analysis_text.insert(tk.END, f"  - Elementos seleccionados: {analysis_stats.get('selected_elements', 0)}\n")
                analysis_text.insert(tk.END, f"  - Tasa de selección: {analysis_stats.get('selection_rate', 0):.2%}\n\n")
            else:
                analysis_text.insert(tk.END, "No hay datos de análisis disponibles\n\n")
            
            # Pestaña de plugins
            plugins_frame = ttk.Frame(notebook)
            notebook.add(plugins_frame, text="Plugins")
            
            plugins_text = tk.Text(plugins_frame, wrap=tk.WORD)
            plugins_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            plugins_text.insert(tk.END, f"Estadísticas de Plugins:\n")
            plugins_text.insert(tk.END, f"  - Total de plugins: {plugin_stats.get('total_plugins', 0)}\n")
            plugins_text.insert(tk.END, f"  - Plugins cargados: {plugin_stats.get('loaded_plugins', 0)}\n")
            plugins_text.insert(tk.END, f"  - Plugins habilitados: {plugin_stats.get('enabled_plugins', 0)}\n")
            plugins_text.insert(tk.END, f"  - Plugins fallidos: {plugin_stats.get('failed_plugins', 0)}\n")
            plugins_text.insert(tk.END, f"  - Directorio: {plugin_stats.get('plugin_directory', 'N/A')}\n")
            plugins_text.insert(tk.END, f"  - Auto-reload: {plugin_stats.get('auto_reload', False)}\n\n")
            
            # Uso de hooks
            if plugin_stats.get('hook_usage'):
                plugins_text.insert(tk.END, "Uso de Hooks:\n")
                for hook_name, usage in plugin_stats['hook_usage'].items():
                    plugins_text.insert(tk.END, f"  - {hook_name}: {usage} callbacks\n")
            
            # Botones de acción
            button_frame = ttk.Frame(metrics_window)
            button_frame.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Button(button_frame, text="Exportar Métricas", 
                      command=lambda: self.export_metrics(metrics_summary)).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Limpiar Métricas", 
                      command=self.clear_metrics).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Cerrar", 
                      command=metrics_window.destroy).pack(side=tk.RIGHT, padx=2)
            
        except Exception as e:
            logger.error(f"Error mostrando métricas: {e}")
            messagebox.showerror("Error", f"Error mostrando métricas: {str(e)}")

    def export_metrics(self, metrics_summary):
        """Exporta las métricas a archivo"""
        try:
            # Verificar que las métricas sean válidas
            if not metrics_summary or metrics_summary.get('error'):
                messagebox.showwarning("Advertencia", "No hay métricas válidas para exportar")
                return
            
            file_path = filedialog.asksaveasfilename(
                defaultextension='.json',
                filetypes=[("JSON files", "*.json")],
                initialfile=f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            if file_path:
                try:
                    if self.metrics_collector:
                        success = self.metrics_collector.export_metrics(file_path, 'json')
                    else:
                        # Fallback manual export
                        success = self._manual_export_metrics(metrics_summary, file_path)
                    
                    if success:
                        messagebox.showinfo("Éxito", f"Métricas exportadas a {file_path}")
                    else:
                        messagebox.showerror("Error", "Error al exportar métricas")
                except Exception as e:
                    logger.error(f"Error en exportación de métricas: {e}")
                    messagebox.showerror("Error", f"Error al exportar: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error exportando métricas: {e}")
            messagebox.showerror("Error", f"Error al exportar: {str(e)}")

    def _manual_export_metrics(self, metrics_summary, file_path):
        """Exportación manual de métricas como fallback"""
        try:
            # Preparar datos para exportación
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'metrics': metrics_summary
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error en exportación manual de métricas: {e}")
            return False

    def clear_metrics(self):
        """Limpia las métricas"""
        try:
            if self.metrics_collector:
                success = self.metrics_collector.reset_metrics()
                if success:
                    messagebox.showinfo("Éxito", "Métricas limpiadas")
                else:
                    messagebox.showerror("Error", "No se pudieron limpiar las métricas")
            else:
                messagebox.showerror("Error", "Metrics collector no disponible")
        except Exception as e:
            logger.error(f"Error limpiando métricas: {e}")
            messagebox.showerror("Error", f"Error limpiando métricas: {str(e)}")

    def show_advanced_selectors(self):
        """Muestra la ventana de selectores avanzados"""
        try:
            # Verificar que los selectores avanzados estén disponibles
            if not hasattr(self, 'advanced_selectors') or not self.advanced_selectors:
                messagebox.showerror("Error", "Selectores avanzados no disponibles")
                return
            
            # Crear ventana
            window = tk.Toplevel(self.root)
            window.title("Selectores Avanzados")
            window.geometry("1000x700")
            
            # Notebook para diferentes funcionalidades
            notebook = ttk.Notebook(window)
            notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Pestaña de detección automática
            auto_frame = ttk.Frame(notebook)
            notebook.add(auto_frame, text="Detección Automática")
            
            auto_text = tk.Text(auto_frame, wrap=tk.WORD)
            auto_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            auto_text.insert(tk.END, "🔍 DETECCIÓN AUTOMÁTICA DE ELEMENTOS\n")
            auto_text.insert(tk.END, "=" * 50 + "\n\n")
            auto_text.insert(tk.END, "Esta función detecta automáticamente elementos comunes en la página:\n")
            auto_text.insert(tk.END, "• Títulos y subtítulos\n")
            auto_text.insert(tk.END, "• Enlaces de navegación\n")
            auto_text.insert(tk.END, "• Contenido principal\n")
            auto_text.insert(tk.END, "• Formularios\n")
            auto_text.insert(tk.END, "• Imágenes\n")
            auto_text.insert(tk.END, "• Botones\n\n")
            
            auto_text.insert(tk.END, "Haz clic en 'Detectar Elementos' para comenzar.\n")
            auto_text.config(state=tk.DISABLED)
            
            ttk.Button(auto_frame, text="Detectar Elementos", 
                      command=lambda: self._auto_detect_elements(window)).pack(pady=10)
            
            # Pestaña de templates
            templates_frame = ttk.Frame(notebook)
            notebook.add(templates_frame, text="Templates")
            
            templates_text = tk.Text(templates_frame, wrap=tk.WORD)
            templates_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            try:
                templates = self.advanced_selectors.list_templates()
                templates_text.insert(tk.END, "📋 TEMPLATES DISPONIBLES\n")
                templates_text.insert(tk.END, "=" * 40 + "\n\n")
                
                if templates:
                    for i, template in enumerate(templates, 1):
                        templates_text.insert(tk.END, f"{i}. {template}\n")
                    templates_text.insert(tk.END, f"\nTotal: {len(templates)} templates\n")
                else:
                    templates_text.insert(tk.END, "No hay templates disponibles\n")
                    
            except Exception as e:
                logger.warning(f"Error listando templates: {e}")
                templates_text.insert(tk.END, f"Error cargando templates: {str(e)}\n")
            
            templates_text.config(state=tk.DISABLED)
            
            # Botones para templates
            template_buttons = ttk.Frame(templates_frame)
            template_buttons.pack(pady=10)
            
            ttk.Button(template_buttons, text="Aplicar Template", 
                      command=lambda: self._apply_template(templates, window)).pack(side=tk.LEFT, padx=5)
            ttk.Button(template_buttons, text="Exportar Template", 
                      command=lambda: self._export_template(templates)).pack(side=tk.LEFT, padx=5)
            ttk.Button(template_buttons, text="Importar Template", 
                      command=self._import_template).pack(side=tk.LEFT, padx=5)
            
            # Pestaña de extracción inteligente
            extraction_frame = ttk.Frame(notebook)
            notebook.add(extraction_frame, text="Extracción Inteligente")
            
            extraction_text = tk.Text(extraction_frame, wrap=tk.WORD)
            extraction_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            extraction_text.insert(tk.END, "🧠 EXTRACCIÓN INTELIGENTE DE DATOS\n")
            extraction_text.insert(tk.END, "=" * 50 + "\n\n")
            extraction_text.insert(tk.END, "Tipos de datos que se pueden extraer:\n")
            extraction_text.insert(tk.END, "• Información de contacto\n")
            extraction_text.insert(tk.END, "• Precios y productos\n")
            extraction_text.insert(tk.END, "• Fechas y horarios\n")
            extraction_text.insert(tk.END, "• Direcciones y ubicaciones\n")
            extraction_text.insert(tk.END, "• Información de empresa\n")
            extraction_text.insert(tk.END, "• Enlaces sociales\n\n")
            
            extraction_text.insert(tk.END, "Selecciona el tipo de datos a extraer:\n")
            extraction_text.config(state=tk.DISABLED)
            
            # Botones de extracción
            extraction_buttons = ttk.Frame(extraction_frame)
            extraction_buttons.pack(pady=10)
            
            data_types = ["contacto", "precios", "fechas", "direcciones", "empresa", "sociales"]
            for data_type in data_types:
                ttk.Button(extraction_buttons, text=data_type.title(), 
                          command=lambda dt=data_type: self._extract_intelligent_data(dt, window)).pack(side=tk.LEFT, padx=2)
            
            # Botones de acción
            button_frame = ttk.Frame(window)
            button_frame.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Button(button_frame, text="Cerrar", 
                      command=window.destroy).pack(side=tk.RIGHT, padx=2)
            
        except Exception as e:
            logger.error(f"Error mostrando selectores avanzados: {e}")
            messagebox.showerror("Error", f"Error mostrando selectores avanzados: {str(e)}")

    def _auto_detect_elements(self, window):
        """Detecta elementos automáticamente usando selectores avanzados"""
        try:
            detected = self.advanced_selectors.auto_detect_elements(self.analyzer.soup)
            
            # Limpiar árbol anterior
            for item in window.winfo_children():
                if isinstance(item, ttk.Notebook):
                    for tab in item.winfo_children():
                        if isinstance(tab, ttk.Frame):
                            for widget in tab.winfo_children():
                                if isinstance(widget, ttk.LabelFrame):
                                    for child in widget.winfo_children():
                                        if isinstance(child, ttk.Treeview):
                                            child.delete(*child.get_children())
            
            # Mostrar resultados
            for element_type, elements in detected.items():
                confidence = min(0.9, len(elements) / 10)  # Calcular confianza basada en cantidad
                window.winfo_children()[0].winfo_children()[0].winfo_children()[1].winfo_children()[0].insert(
                    '', 'end', values=(element_type, len(elements), f"{confidence:.2f}")
                )
            
            messagebox.showinfo("Detección Completada", 
                              f"Se detectaron {sum(len(elements) for elements in detected.values())} elementos en {len(detected)} categorías")
            
        except Exception as e:
            logger.error(f"Error en detección automática: {e}")
            messagebox.showerror("Error", f"Error en detección automática: {str(e)}")

    def _apply_template(self, templates_list, window):
        """Aplica un template seleccionado"""
        selection = templates_list.curselection()
        if not selection:
            messagebox.showwarning("Advertencia", "Por favor seleccione un template")
            return
        
        template_name = templates_list.get(selection[0])
        try:
            template = self.advanced_selectors.get_template(template_name)
            if template:
                results = self.advanced_selectors.extract_with_rules(self.analyzer.soup, template, self.current_url)
                
                # Mostrar resultados
                result_text = f"Resultados del template '{template_name}':\n\n"
                for rule_name, result in results.items():
                    result_text += f"📋 {rule_name}:\n"
                    result_text += f"   Valor: {result.value}\n"
                    result_text += f"   Confianza: {result.confidence:.2f}\n"
                    result_text += f"   Calidad: {result.quality_score:.2f}\n"
                    if result.errors:
                        result_text += f"   Errores: {', '.join(result.errors)}\n"
                    result_text += "\n"
                
                # Buscar el text widget de resultados
                for widget in window.winfo_children():
                    if isinstance(widget, ttk.Frame):
                        for child in widget.winfo_children():
                            if isinstance(child, ttk.Notebook):
                                for tab in child.winfo_children():
                                    if isinstance(tab, ttk.Frame):
                                        for grandchild in tab.winfo_children():
                                            if isinstance(grandchild, ttk.LabelFrame):
                                                for greatgrandchild in grandchild.winfo_children():
                                                    if isinstance(greatgrandchild, tk.Text):
                                                        greatgrandchild.delete(1.0, tk.END)
                                                        greatgrandchild.insert(1.0, result_text)
                                                        break
                
                messagebox.showinfo("Template Aplicado", 
                                  f"Template '{template_name}' aplicado exitosamente")
            else:
                messagebox.showerror("Error", f"No se pudo cargar el template '{template_name}'")
                
        except Exception as e:
            logger.error(f"Error aplicando template: {e}")
            messagebox.showerror("Error", f"Error aplicando template: {str(e)}")

    def _export_template(self, templates_list):
        """Exporta un template seleccionado"""
        selection = templates_list.curselection()
        if not selection:
            messagebox.showwarning("Advertencia", "Por favor seleccione un template")
            return
        
        template_name = templates_list.get(selection[0])
        file_path = filedialog.asksaveasfilename(
            defaultextension='.json',
            filetypes=[("JSON files", "*.json")],
            initialfile=f"{template_name}_template.json"
        )
        
        if file_path:
            try:
                success = self.advanced_selectors.export_template(template_name, file_path)
                if success:
                    messagebox.showinfo("Éxito", f"Template exportado a {file_path}")
                else:
                    messagebox.showerror("Error", "Error exportando template")
            except Exception as e:
                messagebox.showerror("Error", f"Error: {str(e)}")

    def _import_template(self):
        """Importa un template desde archivo"""
        file_path = filedialog.askopenfilename(
            title="Seleccionar archivo de template",
            filetypes=[("JSON files", "*.json")]
        )
        
        if file_path:
            try:
                template_name = self.advanced_selectors.import_template(file_path)
                if template_name:
                    messagebox.showinfo("Éxito", f"Template '{template_name}' importado correctamente")
                    # Recargar lista de templates
                    self.show_advanced_selectors()
                else:
                    messagebox.showerror("Error", "Error importando template")
            except Exception as e:
                messagebox.showerror("Error", f"Error: {str(e)}")

    def _extract_intelligent_data(self, data_type, window):
        """Extrae datos de manera inteligente según el tipo especificado"""
        try:
            # Crear reglas personalizadas según el tipo
            rules = []
            
            if data_type == 'Precios' or data_type == 'Todos':
                rules.append(SelectorRule('precio', ['.price', '.cost', '[class*="price"]'], 'text', 
                                        transform='extract_number', validation_pattern=r'^\d+[.,]\d{2}$'))
            
            if data_type == 'Emails' or data_type == 'Todos':
                rules.append(SelectorRule('email', ['a[href^="mailto:"]', '[class*="email"]'], 'text',
                                        transform='extract_email', validation_pattern=r'.*@.*\..*'))
            
            if data_type == 'Teléfonos' or data_type == 'Todos':
                rules.append(SelectorRule('telefono', ['a[href^="tel:"]', '[class*="phone"]'], 'text',
                                        transform='extract_number'))
            
            if data_type == 'Fechas' or data_type == 'Todos':
                rules.append(SelectorRule('fecha', ['.date', '.published', '[class*="date"]'], 'text',
                                        transform='extract_date'))
            
            if data_type == 'URLs' or data_type == 'Todos':
                rules.append(SelectorRule('url', ['a[href]'], 'attribute', attribute='href',
                                        validation_pattern=r'https?://.*'))
            
            if rules:
                results = self.advanced_selectors.extract_with_rules(self.analyzer.soup, rules, self.current_url)
                
                # Mostrar resultados
                result_text = f"Extracción inteligente de {data_type}:\n\n"
                for rule_name, result in results.items():
                    result_text += f"🎯 {rule_name}:\n"
                    result_text += f"   Valor: {result.value}\n"
                    result_text += f"   Confianza: {result.confidence:.2f}\n"
                    result_text += f"   Calidad: {result.quality_score:.2f}\n"
                    result_text += f"   Tiempo: {result.extraction_time:.3f}s\n"
                    if result.errors:
                        result_text += f"   Errores: {', '.join(result.errors)}\n"
                    if result.warnings:
                        result_text += f"   Advertencias: {', '.join(result.warnings)}\n"
                    result_text += "\n"
                
                # Buscar el text widget de resultados
                for widget in window.winfo_children():
                    if isinstance(widget, ttk.Frame):
                        for child in widget.winfo_children():
                            if isinstance(child, ttk.Notebook):
                                for tab in child.winfo_children():
                                    if isinstance(tab, ttk.Frame):
                                        for grandchild in tab.winfo_children():
                                            if isinstance(grandchild, ttk.LabelFrame):
                                                for greatgrandchild in grandchild.winfo_children():
                                                    if isinstance(greatgrandchild, tk.Text):
                                                        greatgrandchild.delete(1.0, tk.END)
                                                        greatgrandchild.insert(1.0, result_text)
                                                        break
                
                messagebox.showinfo("Extracción Completada", 
                                  f"Extracción de {data_type} completada con {len(results)} resultados")
            else:
                messagebox.showwarning("Advertencia", "No se pudieron crear reglas para el tipo especificado")
                
        except Exception as e:
            logger.error(f"Error en extracción inteligente: {e}")
            messagebox.showerror("Error", f"Error en extracción inteligente: {str(e)}")

    def _save_extraction_results(self, results_text):
        """Guarda los resultados de extracción"""
        content = results_text.get(1.0, tk.END)
        if not content.strip():
            messagebox.showwarning("Advertencia", "No hay resultados para guardar")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension='.txt',
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"extraction_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("Éxito", f"Resultados guardados en {file_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Error guardando resultados: {str(e)}")

    def _show_extraction_metrics(self):
        """Muestra métricas de extracción"""
        try:
            # Crear ventana de métricas
            metrics_window = tk.Toplevel(self.root)
            metrics_window.title("Métricas de Extracción")
            metrics_window.geometry("600x400")
            
            metrics_text = tk.Text(metrics_window, wrap=tk.WORD)
            metrics_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Calcular métricas básicas
            if hasattr(self, 'analyzer') and self.analyzer:
                dom_tree = self.analyzer.get_dom_tree()
                total_elements = len(dom_tree)
                selected_elements = len(self.selected_dom_elements)
                
                metrics_text.insert(tk.END, "📊 MÉTRICAS DE EXTRACCIÓN\n")
                metrics_text.insert(tk.END, "=" * 40 + "\n\n")
                metrics_text.insert(tk.END, f"Total de elementos en DOM: {total_elements}\n")
                metrics_text.insert(tk.END, f"Elementos seleccionados: {selected_elements}\n")
                metrics_text.insert(tk.END, f"Tasa de selección: {(selected_elements/total_elements*100):.1f}%\n\n")
                
                # Métricas por tipo de elemento
                element_types = {}
                for node in dom_tree:
                    element = self.analyzer.get_element_details(node['path'])
                    if element:
                        element_type = self.analyzer.get_element_type(element)
                        element_types[element_type] = element_types.get(element_type, 0) + 1
                
                metrics_text.insert(tk.END, "📈 DISTRIBUCIÓN POR TIPO:\n")
                metrics_text.insert(tk.END, "-" * 30 + "\n")
                for element_type, count in element_types.items():
                    percentage = (count / total_elements) * 100
                    metrics_text.insert(tk.END, f"{element_type.capitalize()}: {count} ({percentage:.1f}%)\n")
            
            metrics_text.config(state=tk.DISABLED)
            
            # Botón de cerrar
            ttk.Button(metrics_window, text="Cerrar", 
                      command=metrics_window.destroy).pack(pady=10)
            
        except Exception as e:
            logger.error(f"Error mostrando métricas de extracción: {e}")
            messagebox.showerror("Error", f"Error mostrando métricas: {str(e)}")

    def show_plugins(self):
        """Muestra la gestión de plugins"""
        try:
            # Obtener información de plugins
            plugins = self.plugin_manager.get_all_plugins()
            
            # Crear ventana de plugins
            plugins_window = tk.Toplevel(self.root)
            plugins_window.title("Gestión de Plugins")
            plugins_window.geometry("800x600")
            
            # Frame principal
            main_frame = ttk.Frame(plugins_window, padding=10)
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Lista de plugins
            list_frame = ttk.LabelFrame(main_frame, text="Plugins Disponibles", padding=5)
            list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            
            # Treeview para plugins
            columns = ('name', 'version', 'status', 'description')
            plugin_tree = ttk.Treeview(list_frame, columns=columns, show='headings')
            
            plugin_tree.heading('name', text='Nombre')
            plugin_tree.heading('version', text='Versión')
            plugin_tree.heading('status', text='Estado')
            plugin_tree.heading('description', text='Descripción')
            
            plugin_tree.column('name', width=150)
            plugin_tree.column('version', width=80)
            plugin_tree.column('status', width=100)
            plugin_tree.column('description', width=300)
            
            # Insertar plugins
            for plugin in plugins:
                status = "Habilitado" if plugin['enabled'] else "Deshabilitado"
                if plugin.get('error'):
                    status = "Error"
                
                plugin_tree.insert('', 'end', values=(
                    plugin['name'],
                    plugin['version'],
                    status,
                    plugin['description'][:50] + '...' if len(plugin['description']) > 50 else plugin['description']
                ))
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=plugin_tree.yview)
            plugin_tree.configure(yscrollcommand=scrollbar.set)
            
            plugin_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Botones de acción
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X)
            
            ttk.Button(button_frame, text="Habilitar Plugin", 
                      command=lambda: self.enable_selected_plugin(plugin_tree)).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Deshabilitar Plugin", 
                      command=lambda: self.disable_selected_plugin(plugin_tree)).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Recargar Plugin", 
                      command=lambda: self.reload_selected_plugin(plugin_tree)).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Instalar Plugin", 
                      command=self.install_plugin).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Exportar Info", 
                      command=self.export_plugin_info).pack(side=tk.LEFT, padx=2)
            ttk.Button(button_frame, text="Cerrar", 
                      command=plugins_window.destroy).pack(side=tk.RIGHT, padx=2)
            
        except Exception as e:
            logger.error(f"Error mostrando plugins: {e}")
            messagebox.showerror("Error", f"Error mostrando plugins: {str(e)}")

    def enable_selected_plugin(self, plugin_tree):
        """Habilita el plugin seleccionado"""
        try:
            selection = plugin_tree.selection()
            if not selection:
                messagebox.showwarning("Advertencia", "Selecciona un plugin para habilitar")
                return
            
            plugin_name = plugin_tree.item(selection[0])['text']
            if self.plugin_manager:
                success = self.plugin_manager.enable_plugin(plugin_name)
                if success:
                    messagebox.showinfo("Éxito", f"Plugin '{plugin_name}' habilitado")
                    self.show_plugins()  # Actualizar vista
                else:
                    messagebox.showerror("Error", f"No se pudo habilitar el plugin '{plugin_name}'")
            else:
                messagebox.showerror("Error", "Plugin manager no disponible")
        except Exception as e:
            logger.error(f"Error habilitando plugin: {e}")
            messagebox.showerror("Error", f"Error habilitando plugin: {str(e)}")

    def disable_selected_plugin(self, plugin_tree):
        """Deshabilita el plugin seleccionado"""
        try:
            selection = plugin_tree.selection()
            if not selection:
                messagebox.showwarning("Advertencia", "Selecciona un plugin para deshabilitar")
                return
            
            plugin_name = plugin_tree.item(selection[0])['text']
            if self.plugin_manager:
                success = self.plugin_manager.disable_plugin(plugin_name)
                if success:
                    messagebox.showinfo("Éxito", f"Plugin '{plugin_name}' deshabilitado")
                    self.show_plugins()  # Actualizar vista
                else:
                    messagebox.showerror("Error", f"No se pudo deshabilitar el plugin '{plugin_name}'")
            else:
                messagebox.showerror("Error", "Plugin manager no disponible")
        except Exception as e:
            logger.error(f"Error deshabilitando plugin: {e}")
            messagebox.showerror("Error", f"Error deshabilitando plugin: {str(e)}")

    def reload_selected_plugin(self, plugin_tree):
        """Recarga el plugin seleccionado"""
        try:
            selection = plugin_tree.selection()
            if not selection:
                messagebox.showwarning("Advertencia", "Selecciona un plugin para recargar")
                return
            
            plugin_name = plugin_tree.item(selection[0])['text']
            if self.plugin_manager:
                success = self.plugin_manager.reload_plugin(plugin_name)
                if success:
                    messagebox.showinfo("Éxito", f"Plugin '{plugin_name}' recargado")
                    self.show_plugins()  # Actualizar vista
                else:
                    messagebox.showerror("Error", f"No se pudo recargar el plugin '{plugin_name}'")
            else:
                messagebox.showerror("Error", "Plugin manager no disponible")
        except Exception as e:
            logger.error(f"Error recargando plugin: {e}")
            messagebox.showerror("Error", f"Error recargando plugin: {str(e)}")

    def install_plugin(self):
        """Instala un nuevo plugin"""
        try:
            plugin_file = filedialog.askopenfilename(
                title="Seleccionar archivo de plugin",
                filetypes=[("Python files", "*.py"), ("All files", "*.*")]
            )
            
            if plugin_file and self.plugin_manager:
                success = self.plugin_manager.install_plugin(plugin_file)
                if success:
                    messagebox.showinfo("Éxito", "Plugin instalado correctamente")
                    self.show_plugins()  # Actualizar vista
                else:
                    messagebox.showerror("Error", "No se pudo instalar el plugin")
            elif not self.plugin_manager:
                messagebox.showerror("Error", "Plugin manager no disponible")
        except Exception as e:
            logger.error(f"Error instalando plugin: {e}")
            messagebox.showerror("Error", f"Error instalando plugin: {str(e)}")

    def export_plugin_info(self):
        """Exporta información de los plugins"""
        try:
            if not self.plugin_manager:
                messagebox.showerror("Error", "Plugin manager no disponible")
                return
            
            file_path = filedialog.asksaveasfilename(
                defaultextension='.json',
                filetypes=[("JSON files", "*.json")],
                initialfile=f"plugin_info_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            
            if file_path:
                plugin_info = self.plugin_manager.get_plugin_statistics()
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(plugin_info, f, ensure_ascii=False, indent=2)
                
                messagebox.showinfo("Éxito", f"Información de plugins exportada a:\n{file_path}")
        except Exception as e:
            logger.error(f"Error exportando información de plugins: {e}")
            messagebox.showerror("Error", f"Error exportando información: {str(e)}")

    def set_light_theme(self):
        """Configura un tema claro para la interfaz y ajusta colores de widgets y tags."""
        style = ttk.Style()
        style.theme_use('default')
        bg = '#FFFFFF'
        fg = '#222222'
        entry_bg = '#F7F7F7'
        select_bg = '#D0E2FF'
        select_fg = '#222222'
        # General
        self.root.configure(bg=bg)
        style.configure('.', background=bg, foreground=fg, fieldbackground=entry_bg)
        style.configure('TLabel', background=bg, foreground=fg)
        style.configure('TFrame', background=bg)
        style.configure('TButton', background=select_bg, foreground=fg)
        style.configure('TEntry', fieldbackground=entry_bg, foreground=fg)
        style.configure('TCombobox', fieldbackground=entry_bg, background=entry_bg, foreground=fg)
        style.map('TButton', background=[('active', select_bg)], foreground=[('active', fg)])
        # Listbox y Text
        self.html_preview.config(bg=bg, fg=fg, insertbackground=fg, selectbackground=select_bg, selectforeground=select_fg, highlightbackground=bg, highlightcolor=bg)
        self.selected_listbox.config(bg=bg, fg=fg, selectbackground=select_bg, selectforeground=select_fg, highlightbackground=bg, highlightcolor=bg)
        self.quick_preview.config(bg=bg, fg=fg, insertbackground=fg, selectbackground=select_bg, selectforeground=select_fg, highlightbackground=bg, highlightcolor=bg)
        self.url_text.config(bg=bg, fg=fg, insertbackground=fg, selectbackground=select_bg, selectforeground=select_fg, highlightbackground=bg, highlightcolor=bg)
        # Treeview
        style.configure('Treeview', background=bg, fieldbackground=bg, foreground=fg)
        style.map('Treeview', background=[('selected', select_bg)], foreground=[('selected', select_fg)])
        style.configure('Treeview.Heading', background=select_bg, foreground=fg)
        # Barra de estado (usar estilo ttk)
        style.configure('StatusBar.TLabel', background=bg, foreground=fg)
        self.status_bar.configure(style='StatusBar.TLabel')
        # Ajustar tags de color para fondo claro y máxima visibilidad
        self.html_preview.tag_configure('color_image', foreground='#B71C1C', background='#FFEBEE')
        self.html_preview.tag_configure('color_link', foreground='#0D47A1', background='#E3F2FD')
        self.html_preview.tag_configure('color_title', foreground='#1B5E20', background='#E8F5E9')
        self.html_preview.tag_configure('color_text', foreground='#4E342E', background='#FFF3E0')
        self.html_preview.tag_configure('color_table', foreground='#6A1B9A', background='#F3E5F5')
        self.html_preview.tag_configure('color_other', foreground='#222222', background='#FFFFFF')
        self.html_preview.tag_configure('selected', background='#D0E2FF')
        self.html_preview.tag_configure('hover', background='#B3E5FC')
        self._light_theme_bg = bg
        self._light_theme_fg = fg

    def apply_light_theme_to_toplevel(self, window):
        """Aplica el tema claro a una ventana Toplevel y sus widgets."""
        try:
            style = ttk.Style()
            bg = '#FFFFFF'
            fg = '#222222'
            entry_bg = '#F7F7F7'
            select_bg = '#D0E2FF'
            select_fg = '#222222'

            # Configurar estilos para widgets ttk
            style.configure('TLabel', background=bg, foreground=fg)
            style.configure('TFrame', background=bg)
            style.configure('TButton', background=select_bg, foreground=fg)
            style.configure('TEntry', fieldbackground=entry_bg, foreground=fg)

            # Configurar widgets no-ttk de manera segura
            for widget in window.winfo_children():
                try:
                    if isinstance(widget, tk.Text):
                        widget.configure(
                            bg=bg,
                            fg=fg,
                            selectbackground=select_bg,
                            selectforeground=select_fg
                        )
                    elif isinstance(widget, tk.Listbox):
                        widget.configure(
                            bg=bg,
                            fg=fg,
                            selectbackground=select_bg,
                            selectforeground=select_fg
                        )
                    elif isinstance(widget, tk.Frame):
                        widget.configure(bg=bg)
                    elif isinstance(widget, tk.Label):
                        widget.configure(bg=bg, fg=fg)
                    elif isinstance(widget, tk.Button):
                        widget.configure(bg=select_bg, fg=fg)
                    elif isinstance(widget, tk.Entry):
                        widget.configure(
                            bg=entry_bg,
                            fg=fg
                        )
                except Exception as e:
                    # Ignorar errores de configuración de widgets individuales
                    pass
                
                # Aplicar recursivamente a widgets hijos de manera segura
                try:
                    if hasattr(widget, 'winfo_children'):
                        self.apply_light_theme_to_toplevel(widget)
                except Exception as e:
                    # Ignorar errores de recursión
                    pass
        except Exception as e:
            # Ignorar errores generales del tema
            pass

    def filter_dom_tree(self, event=None):
        """Filtra el árbol DOM según el tipo seleccionado"""
        filter_type = self.dom_filter.get().lower()
        
        # Obtener todos los items
        all_items = self.dom_tree.get_children()
        
        if filter_type == 'todos':
            # Mostrar todos los items
            for item in all_items:
                self.dom_tree.item(item, open=True)
                self.show_item_and_children(item, True)
        else:
            # Ocultar todos primero
            for item in all_items:
                self.dom_tree.item(item, open=False)
                self.show_item_and_children(item, False)
            
            # Mostrar solo los del tipo seleccionado
            for item in all_items:
                try:
                    # Obtener el tipo del elemento
                    values = self.dom_tree.item(item)['values']
                    if len(values) >= 3:
                        node_type = values[2].lower()
                        if node_type == filter_type:
                            self.dom_tree.item(item, open=True)
                            self.show_item_and_children(item, True)
                except Exception as e:
                    logger.warning(f"Error filtrando elemento: {e}")
                    continue

    def show_item_and_children(self, item, show):
        """Muestra u oculta un item y sus hijos"""
        self.dom_tree.item(item, open=show)
        for child in self.dom_tree.get_children(item):
            self.show_item_and_children(child, show)

    def compare_doms(self):
        """Compara los DOMs de diferentes URLs"""
        if len(self.all_analyzers) < 2:
            messagebox.showwarning("Advertencia", "Se necesitan al menos dos URLs para comparar")
            return
        
        # Crear ventana de comparación
        compare_window = tk.Toplevel(self.root)
        compare_window.title("Comparación de DOMs")
        compare_window.geometry("800x600")
        
        # Frame para selección de URLs
        url_frame = ttk.Frame(compare_window, padding=10)
        url_frame.pack(fill=tk.X)
        
        ttk.Label(url_frame, text="URL 1:").pack(side=tk.LEFT)
        url1_var = tk.StringVar()
        url1_combo = ttk.Combobox(url_frame, textvariable=url1_var, width=40)
        url1_combo['values'] = [f"URL_{i+1}" for i in range(len(self.all_analyzers))]
        url1_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(url_frame, text="URL 2:").pack(side=tk.LEFT)
        url2_var = tk.StringVar()
        url2_combo = ttk.Combobox(url_frame, textvariable=url2_var, width=40)
        url2_combo['values'] = [f"URL_{i+1}" for i in range(len(self.all_analyzers))]
        url2_combo.pack(side=tk.LEFT, padx=5)
        
        # Frame para resultados
        result_frame = ttk.Frame(compare_window, padding=10)
        result_frame.pack(fill=tk.BOTH, expand=True)
        
        # Notebook para diferentes vistas
        notebook = ttk.Notebook(result_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Pestaña de diferencias
        diff_frame = ttk.Frame(notebook)
        notebook.add(diff_frame, text="Diferencias")
        
        # Árbol de diferencias
        diff_tree = ttk.Treeview(diff_frame, columns=('type', 'details'), selectmode='browse')
        diff_tree.heading('#0', text='Elemento')
        diff_tree.heading('type', text='Tipo de Cambio')
        diff_tree.heading('details', text='Detalles')
        
        diff_tree.column('#0', width=200)
        diff_tree.column('type', width=100)
        diff_tree.column('details', width=400)
        
        # Configurar colores para diferentes tipos de cambios
        diff_tree.tag_configure('added', background='#90EE90')    # Verde claro
        diff_tree.tag_configure('removed', background='#FFB6C1')  # Rosa claro
        diff_tree.tag_configure('modified', background='#FFD700') # Dorado
        
        diff_tree.pack(fill=tk.BOTH, expand=True)
        
        def update_comparison(*args):
            """Actualiza la comparación cuando se seleccionan nuevas URLs"""
            try:
                idx1 = int(url1_var.get().split('_')[1]) - 1
                idx2 = int(url2_var.get().split('_')[1]) - 1
                
                analyzer1 = self.all_analyzers[idx1]
                analyzer2 = self.all_analyzers[idx2]
                
                # Limpiar árbol anterior
                diff_tree.delete(*diff_tree.get_children())
                
                # Obtener diferencias
                differences = analyzer1.compare_with(analyzer2)
                
                # Mostrar diferencias
                for diff_type, items in differences.items():
                    for item in items:
                        if diff_type == 'modified':
                            tag = 'modified'
                            details = f"Cambios en atributos o contenido"
                        else:
                            tag = diff_type
                            details = str(item)
                        
                        diff_tree.insert('', 'end',
                                       text=item.get('path', 'N/A'),
                                       values=(diff_type.capitalize(), details),
                                       tags=(tag,))
                
            except (ValueError, IndexError):
                pass
        
        # Vincular actualización a cambios en las URLs
        url1_var.trace('w', update_comparison)
        url2_var.trace('w', update_comparison)
        
        # Establecer valores iniciales
        if len(self.all_analyzers) >= 2:
            url1_var.set("URL_1")
            url2_var.set("URL_2")

    def update_dom_tree(self, dom_tree):
        """Actualiza el árbol DOM con estructura completa y desplegables en cascada"""
        self.dom_tree.delete(*self.dom_tree.get_children())
        self._tree_item_map = {}
        
        # Limitar elementos para evitar congelamiento pero mantener estructura
        max_elements = min(2000, len(dom_tree))
        dom_tree = dom_tree[:max_elements]
        
        # Crear diccionario de elementos por profundidad para estructura jerárquica
        elements_by_depth = {}
        for node in dom_tree:
            depth = node.get('depth', 0)
            if depth not in elements_by_depth:
                elements_by_depth[depth] = []
            elements_by_depth[depth].append(node)
        
        # Función recursiva para insertar elementos con estructura jerárquica
        def insert_element_recursive(node, parent_item=''):
            tag = node['tag']
            attrs = ", ".join(f"{k}={v}" for k, v in node['attrs'].items())
            text = node['text']
            path = node['path']
            
            element = self.analyzer.get_element_details(path)
            element_type = self.analyzer.get_element_type(element) if element else 'other'
            
            # Crear texto del nodo con información relevante
            node_text = f"{tag}"
            if text and len(text) > 0:
                node_text += f" - {text[:30]}{'...' if len(text) > 30 else ''}"
            
            # Insertar elemento en el árbol
            item_id = self.dom_tree.insert(
                parent_item, 'end',
                text=node_text,
                values=(attrs, text, element_type.capitalize()),
                tags=(path, element_type),
                open=False  # Inicialmente cerrado para mejor rendimiento
            )
            self._tree_item_map[path] = item_id
            
            # Buscar y insertar hijos recursivamente
            children = [n for n in dom_tree if n.get('parent_id') == node.get('node_id')]
            for child in children:
                insert_element_recursive(child, item_id)
        
        # Insertar elementos raíz (profundidad 0)
        root_elements = [node for node in dom_tree if node.get('depth', 0) == 0]
        for root_node in root_elements:
            insert_element_recursive(root_node)
        
        # Expandir solo los primeros niveles para mejor visualización
        for item in self.dom_tree.get_children():
            self.dom_tree.item(item, open=True)
            # Expandir solo el primer nivel de hijos
            for child in self.dom_tree.get_children(item):
                self.dom_tree.item(child, open=False)
        
        # Actualizar contador
        self.status_bar.config(text=f"DOM cargado: {len(dom_tree)} elementos")

    def update_dom_tree_simple(self, analyzer):
        """Actualiza el árbol DOM con estructura simplificada pero completa"""
        try:
            self.dom_tree.delete(*self.dom_tree.get_children())
            self._tree_item_map = {}
            
            # Crear estructura DOM completa pero optimizada
            soup = analyzer.soup
            if not soup:
                return
            
            # Función para crear estructura jerárquica completa
            def build_tree_structure(element, parent_item='', depth=0, max_depth=5):
                if depth > max_depth:  # Limitar profundidad para evitar congelamiento
                    return
                
                # Obtener todos los elementos hijos directos
                children = [child for child in element.children if hasattr(child, 'name') and child.name]
                
                for i, child in enumerate(children[:50]):  # Limitar a 50 hijos por elemento
                    tag_name = child.name
                    text_content = child.get_text(strip=True)
                    
                    # Crear texto del nodo
                    node_text = f"{tag_name}"
                    if text_content and len(text_content) > 0:
                        node_text += f" - {text_content[:30]}{'...' if len(text_content) > 30 else ''}"
                    
                    # Determinar tipo de elemento
                    element_type = analyzer.get_element_type(child)
                    
                    # Crear path único
                    path = f"{tag_name}:{i}:{depth}"
                    
                    # Insertar en el árbol
                    item_id = self.dom_tree.insert(
                        parent_item, 'end',
                        text=node_text,
                        values=('', text_content[:50], element_type.capitalize()),
                        tags=(path, element_type),
                        open=False
                    )
                    self._tree_item_map[path] = item_id
                    
                    # Recursivamente procesar hijos
                    build_tree_structure(child, item_id, depth + 1, max_depth)
            
            # Procesar desde el elemento raíz
            if soup.html:
                build_tree_structure(soup.html)
            else:
                build_tree_structure(soup)
            
            # Expandir solo los primeros niveles
            for item in self.dom_tree.get_children():
                self.dom_tree.item(item, open=True)
                # Expandir solo el primer nivel de hijos
                for child in self.dom_tree.get_children(item):
                    self.dom_tree.item(child, open=False)
            
            # Actualizar contador
            total_elements = len(self._tree_item_map)
            self.status_bar.config(text=f"DOM completo cargado: {total_elements} elementos")
            
        except Exception as e:
            logger.error(f"Error actualizando DOM tree completo: {e}")
            self.status_bar.config(text="Error cargando DOM completo")

    def start_url_discovery(self):
        """Inicia el proceso de descubrimiento de URLs"""
        urls = self.url_text.get(1.0, tk.END).strip().splitlines()
        urls = [u.strip() for u in urls if u.strip()]
        if not urls:
            messagebox.showerror("Error", "Por favor ingrese al menos una URL válida")
            return
        
        # Mostrar diálogo de configuración
        self.show_url_discovery_dialog(urls[0])  # Usar la primera URL
    
    def show_url_discovery_dialog(self, base_url):
        """Muestra el diálogo de configuración para el descubrimiento de URLs"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Descubrimiento de URLs")
        dialog.geometry("600x500")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Centrar la ventana
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (dialog.winfo_screenheight() // 2) - (500 // 2)
        dialog.geometry(f"600x500+{x}+{y}")
        
        # Frame principal
        main_frame = ttk.Frame(dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # URL base
        url_frame = ttk.Frame(main_frame)
        url_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(url_frame, text="URL Base:").pack(side=tk.LEFT)
        url_var = tk.StringVar(value=base_url)
        url_entry = ttk.Entry(url_frame, textvariable=url_var, width=50)
        url_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Configuración
        config_frame = ttk.LabelFrame(main_frame, text="Configuración", padding="10")
        config_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Primera fila
        row1 = ttk.Frame(config_frame)
        row1.pack(fill=tk.X, pady=2)
        
        ttk.Label(row1, text="Delay (segundos):").pack(side=tk.LEFT)
        delay_var = tk.DoubleVar(value=1.0)
        delay_spin = ttk.Spinbox(row1, from_=0.1, to=10.0, increment=0.1, textvariable=delay_var, width=10)
        delay_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="Máx URLs:").pack(side=tk.LEFT, padx=(20, 0))
        max_urls_var = tk.StringVar(value="100")
        max_urls_entry = ttk.Entry(row1, textvariable=max_urls_var, width=10)
        max_urls_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1, text="Profundidad:").pack(side=tk.LEFT, padx=(20, 0))
        depth_var = tk.IntVar(value=3)
        depth_spin = ttk.Spinbox(row1, from_=1, to=10, textvariable=depth_var, width=10)
        depth_spin.pack(side=tk.LEFT, padx=5)
        
        # Segunda fila
        row2 = ttk.Frame(config_frame)
        row2.pack(fill=tk.X, pady=2)
        
        ttk.Label(row2, text="User-Agent:").pack(side=tk.LEFT)
        ua_var = tk.StringVar(value="Mozilla/5.0 (compatible; Scrapelillo/1.0)")
        ua_entry = ttk.Entry(row2, textvariable=ua_var, width=40)
        ua_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # Fuzzing
        fuzz_frame = ttk.LabelFrame(main_frame, text="Fuzzing de Directorios", padding="10")
        fuzz_frame.pack(fill=tk.X, pady=(0, 10))
        
        fuzz_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(fuzz_frame, text="Habilitar fuzzing", variable=fuzz_var).pack(anchor=tk.W)
        
        fuzz_file_frame = ttk.Frame(fuzz_frame)
        fuzz_file_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(fuzz_file_frame, text="Wordlist:").pack(side=tk.LEFT)
        fuzz_file_var = tk.StringVar()
        fuzz_file_entry = ttk.Entry(fuzz_file_frame, textvariable=fuzz_file_var, width=40)
        fuzz_file_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        def browse_fuzz_file():
            filename = filedialog.askopenfilename(
                title="Seleccionar wordlist",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            if filename:
                fuzz_file_var.set(filename)
        
        ttk.Button(fuzz_file_frame, text="Buscar", command=browse_fuzz_file).pack(side=tk.RIGHT)
        
        # Botones
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def start_discovery():
            try:
                # Validar configuración
                url = url_var.get().strip()
                if not url:
                    messagebox.showerror("Error", "URL base es requerida")
                    return
                
                delay = delay_var.get()
                max_urls_str = max_urls_var.get()
                max_urls = int(max_urls_str) if max_urls_str.isdigit() else None
                depth = depth_var.get()
                user_agent = ua_var.get()
                
                # Validar fuzzing
                fuzz_enabled = fuzz_var.get()
                fuzz_file = fuzz_file_var.get().strip()
                if fuzz_enabled and not fuzz_file:
                    messagebox.showerror("Error", "Seleccione un archivo wordlist para fuzzing")
                    return
                if fuzz_enabled and not os.path.isfile(fuzz_file):
                    messagebox.showerror("Error", f"Archivo wordlist no encontrado: {fuzz_file}")
                    return
                
                dialog.destroy()
                self._perform_url_discovery(url, delay, max_urls, depth, user_agent, fuzz_enabled, fuzz_file)
                
            except ValueError as e:
                messagebox.showerror("Error", f"Error en configuración: {e}")
        
        ttk.Button(button_frame, text="Iniciar Descubrimiento", command=start_discovery).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Cancelar", command=dialog.destroy).pack(side=tk.RIGHT, padx=2)
    
    def _perform_url_discovery(self, base_url, delay, max_urls, depth, user_agent, fuzz_enabled, fuzz_file):
        """Ejecuta el descubrimiento de URLs en un hilo separado"""
        def discovery_thread():
            try:
                # Crear motor de descubrimiento
                engine = URLDiscoveryEngine(
                    base_url=base_url,
                    delay=delay,
                    max_urls=max_urls,
                    user_agent=user_agent,
                    max_depth=depth
                )
                
                # Configurar callbacks
                def progress_callback(message, urls_found, endpoints_found):
                    self.root.after(0, lambda: self._update_discovery_progress(progress_window, message, urls_found, endpoints_found))
                
                def url_found_callback(url, depth):
                    self.root.after(0, lambda: self._on_url_found(urls_tree, url, depth))
                
                def endpoint_found_callback(endpoint):
                    self.root.after(0, lambda: self._on_endpoint_found(endpoints_tree, endpoint))
                
                def error_callback(url, error):
                    self.root.after(0, lambda: self._on_discovery_error(errors_tree, url, error))
                
                engine.set_callbacks(
                    progress_callback=progress_callback,
                    url_found_callback=url_found_callback,
                    endpoint_found_callback=endpoint_found_callback,
                    error_callback=error_callback
                )
                
                # Ejecutar descubrimiento
                result = engine.discover()
                
                # Ejecutar fuzzing si está habilitado
                if fuzz_enabled:
                    engine.fuzz(fuzz_file)
                    result = engine.discover()  # Obtener resultado actualizado
                
                # Mostrar resultados
                self.root.after(0, lambda: self._show_discovery_results(result))
                
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Error en descubrimiento: {e}"))
            finally:
                self.root.after(0, lambda: progress_window.destroy())
        
        # Crear ventana de progreso
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Descubriendo URLs...")
        progress_window.geometry("500x400")
        progress_window.transient(self.root)
        progress_window.grab_set()
        
        # Centrar ventana
        progress_window.update_idletasks()
        x = (progress_window.winfo_screenwidth() // 2) - (500 // 2)
        y = (progress_window.winfo_screenheight() // 2) - (400 // 2)
        progress_window.geometry(f"500x400+{x}+{y}")
        
        # Frame principal
        main_frame = ttk.Frame(progress_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Información
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(info_frame, text="Descubriendo URLs en:").pack(anchor=tk.W)
        ttk.Label(info_frame, text=base_url, font=("TkDefaultFont", 10, "bold")).pack(anchor=tk.W)
        
        # Progreso
        progress_frame = ttk.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.progress_label = ttk.Label(progress_frame, text="Iniciando...")
        self.progress_label.pack(anchor=tk.W)
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='indeterminate')
        self.progress_bar.pack(fill=tk.X, pady=5)
        self.progress_bar.start()
        
        # Estadísticas
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.urls_label = ttk.Label(stats_frame, text="URLs encontradas: 0")
        self.urls_label.pack(side=tk.LEFT, padx=(0, 20))
        
        self.endpoints_label = ttk.Label(stats_frame, text="Endpoints encontrados: 0")
        self.endpoints_label.pack(side=tk.LEFT)
        
        # Árboles de resultados
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # URLs encontradas
        urls_frame = ttk.Frame(notebook)
        notebook.add(urls_frame, text="URLs")
        
        urls_tree = ttk.Treeview(urls_frame, columns=('depth', 'status'), selectmode='browse')
        urls_tree.heading('#0', text='URL')
        urls_tree.heading('depth', text='Profundidad')
        urls_tree.heading('status', text='Estado')
        
        urls_tree.column('#0', width=300)
        urls_tree.column('depth', width=100)
        urls_tree.column('status', width=100)
        
        urls_scrollbar = ttk.Scrollbar(urls_frame, orient="vertical", command=urls_tree.yview)
        urls_tree.configure(yscrollcommand=urls_scrollbar.set)
        
        urls_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        urls_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Endpoints encontrados
        endpoints_frame = ttk.Frame(notebook)
        notebook.add(endpoints_frame, text="Endpoints")
        
        endpoints_tree = ttk.Treeview(endpoints_frame, columns=('type',), selectmode='browse')
        endpoints_tree.heading('#0', text='Endpoint')
        endpoints_tree.heading('type', text='Tipo')
        
        endpoints_tree.column('#0', width=300)
        endpoints_tree.column('type', width=100)
        
        endpoints_scrollbar = ttk.Scrollbar(endpoints_frame, orient="vertical", command=endpoints_tree.yview)
        endpoints_tree.configure(yscrollcommand=endpoints_scrollbar.set)
        
        endpoints_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        endpoints_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Errores
        errors_frame = ttk.Frame(notebook)
        notebook.add(errors_frame, text="Errores")
        
        errors_tree = ttk.Treeview(errors_frame, columns=('error',), selectmode='browse')
        errors_tree.heading('#0', text='URL')
        errors_tree.heading('error', text='Error')
        
        errors_tree.column('#0', width=200)
        errors_tree.column('error', width=300)
        
        errors_scrollbar = ttk.Scrollbar(errors_frame, orient="vertical", command=errors_tree.yview)
        errors_tree.configure(yscrollcommand=errors_scrollbar.set)
        
        errors_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        errors_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Botón cancelar
        cancel_frame = ttk.Frame(main_frame)
        cancel_frame.pack(fill=tk.X, pady=(10, 0))
        
        def cancel_discovery():
            if hasattr(self, 'discovery_engine'):
                self.discovery_engine.cancel()
            progress_window.destroy()
        
        ttk.Button(cancel_frame, text="Cancelar", command=cancel_discovery).pack(side=tk.RIGHT)
        
        # Guardar referencias para callbacks
        self.discovery_engine = None
        self.progress_window = progress_window
        self.urls_tree = urls_tree
        self.endpoints_tree = endpoints_tree
        self.errors_tree = errors_tree
        
        # Iniciar hilo
        thread = threading.Thread(target=discovery_thread, daemon=True)
        thread.start()
    
    def _update_discovery_progress(self, progress_window, message, urls_found, endpoints_found):
        """Actualiza el progreso del descubrimiento"""
        if hasattr(self, 'progress_label'):
            self.progress_label.config(text=message)
        if hasattr(self, 'urls_label'):
            self.urls_label.config(text=f"URLs encontradas: {urls_found}")
        if hasattr(self, 'endpoints_label'):
            self.endpoints_label.config(text=f"Endpoints encontrados: {endpoints_found}")
    
    def _on_url_found(self, urls_tree, url, depth):
        """Callback cuando se encuentra una URL"""
        urls_tree.insert('', 'end', text=url, values=(depth, 'OK'))
    
    def _on_endpoint_found(self, endpoints_tree, endpoint):
        """Callback cuando se encuentra un endpoint"""
        endpoint_type = "API" if "/api/" in endpoint else "Archivo" if "." in endpoint.split("/")[-1] else "Ruta"
        endpoints_tree.insert('', 'end', text=endpoint, values=(endpoint_type,))
    
    def _on_discovery_error(self, errors_tree, url, error):
        """Callback cuando ocurre un error"""
        errors_tree.insert('', 'end', text=url, values=(error,))
    
    def _show_discovery_results(self, result):
        """Muestra los resultados del descubrimiento"""
        results_window = tk.Toplevel(self.root)
        results_window.title("Resultados del Descubrimiento de URLs")
        results_window.geometry("800x600")
        results_window.transient(self.root)
        
        # Centrar ventana
        results_window.update_idletasks()
        x = (results_window.winfo_screenwidth() // 2) - (800 // 2)
        y = (results_window.winfo_screenheight() // 2) - (600 // 2)
        results_window.geometry(f"800x600+{x}+{y}")
        
        # Frame principal
        main_frame = ttk.Frame(results_window, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Información general
        info_frame = ttk.LabelFrame(main_frame, text="Información General", padding="10")
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        info_text = f"""
        URL Base: {result.base_url}
        Duración: {result.duration:.2f} segundos
        Total de requests: {result.total_requests}
        URLs descubiertas: {len(result.discovered_urls)}
        Endpoints descubiertos: {len(result.discovered_endpoints)}
        Archivos JS escaneados: {len(result.js_files_scanned)}
        Errores: {len(result.errors)}
        """
        
        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT)
        info_label.pack(anchor=tk.W)
        
        # Notebook para diferentes vistas
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # URLs descubiertas
        urls_frame = ttk.Frame(notebook)
        notebook.add(urls_frame, text=f"URLs ({len(result.discovered_urls)})")
        
        urls_tree = ttk.Treeview(urls_frame, selectmode='browse')
        urls_tree.heading('#0', text='URL')
        
        urls_scrollbar = ttk.Scrollbar(urls_frame, orient="vertical", command=urls_tree.yview)
        urls_tree.configure(yscrollcommand=urls_scrollbar.set)
        
        urls_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        urls_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        for url in sorted(result.discovered_urls):
            urls_tree.insert('', 'end', text=url)
        
        # Endpoints descubiertos
        endpoints_frame = ttk.Frame(notebook)
        notebook.add(endpoints_frame, text=f"Endpoints ({len(result.discovered_endpoints)})")
        
        endpoints_tree = ttk.Treeview(endpoints_frame, selectmode='browse')
        endpoints_tree.heading('#0', text='Endpoint')
        
        endpoints_scrollbar = ttk.Scrollbar(endpoints_frame, orient="vertical", command=endpoints_tree.yview)
        endpoints_tree.configure(yscrollcommand=endpoints_scrollbar.set)
        
        endpoints_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        endpoints_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        for endpoint in sorted(result.discovered_endpoints):
            endpoints_tree.insert('', 'end', text=endpoint)
        
        # Resultados de fuzzing
        if result.fuzz_results:
            fuzz_frame = ttk.Frame(notebook)
            notebook.add(fuzz_frame, text=f"Fuzzing ({len(result.fuzz_results)})")
            
            fuzz_tree = ttk.Treeview(fuzz_frame, columns=('status',), selectmode='browse')
            fuzz_tree.heading('#0', text='URL')
            fuzz_tree.heading('status', text='Código')
            
            fuzz_tree.column('#0', width=400)
            fuzz_tree.column('status', width=100)
            
            fuzz_scrollbar = ttk.Scrollbar(fuzz_frame, orient="vertical", command=fuzz_tree.yview)
            fuzz_tree.configure(yscrollcommand=fuzz_scrollbar.set)
            
            fuzz_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            fuzz_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            for url, code in sorted(result.fuzz_results.items()):
                fuzz_tree.insert('', 'end', text=url, values=(code,))
        
        # Errores
        if result.errors:
            errors_frame = ttk.Frame(notebook)
            notebook.add(errors_frame, text=f"Errores ({len(result.errors)})")
            
            errors_tree = ttk.Treeview(errors_frame, selectmode='browse')
            errors_tree.heading('#0', text='Error')
            
            errors_scrollbar = ttk.Scrollbar(errors_frame, orient="vertical", command=errors_tree.yview)
            errors_tree.configure(yscrollcommand=errors_scrollbar.set)
            
            errors_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            errors_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            for error in result.errors:
                errors_tree.insert('', 'end', text=error)
        
        # Botones de acción
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def export_results():
            self._export_discovery_results(result)
        
        def add_to_scraper():
            all_urls = list(result.discovered_urls) + list(result.discovered_endpoints)
            if all_urls:
                current_urls = self.url_text.get(1.0, tk.END).strip()
                new_urls = '\n'.join(all_urls)
                if current_urls:
                    self.url_text.delete(1.0, tk.END)
                    self.url_text.insert(1.0, current_urls + '\n' + new_urls)
                else:
                    self.url_text.insert(1.0, new_urls)
                results_window.destroy()
                messagebox.showinfo("Éxito", f"Se añadieron {len(all_urls)} URLs al scraper")
        
        ttk.Button(button_frame, text="Exportar Resultados", command=export_results).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Añadir al Scraper", command=add_to_scraper).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Cerrar", command=results_window.destroy).pack(side=tk.RIGHT, padx=2)
    
    def _export_discovery_results(self, result):
        """Exporta los resultados del descubrimiento"""
        filename = filedialog.asksaveasfilename(
            title="Exportar resultados del descubrimiento",
            defaultextension=".json",
            filetypes=[
                ("JSON files", "*.json"),
                ("CSV files", "*.csv"),
                ("Text files", "*.txt"),
                ("All files", "*.*")
            ]
        )
        
        if not filename:
            return
        
        try:
            if filename.endswith('.json'):
                self._export_discovery_json(result, filename)
            elif filename.endswith('.csv'):
                self._export_discovery_csv(result, filename)
            elif filename.endswith('.txt'):
                self._export_discovery_txt(result, filename)
            else:
                self._export_discovery_json(result, filename)
            
            messagebox.showinfo("Éxito", f"Resultados exportados a: {filename}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error exportando resultados: {e}")
    
    def _export_discovery_json(self, result, filename):
        """Exporta resultados en formato JSON"""
        import json
        
        data = {
            'base_url': result.base_url,
            'duration': result.duration,
            'total_requests': result.total_requests,
            'discovered_urls': list(result.discovered_urls),
            'discovered_endpoints': list(result.discovered_endpoints),
            'js_files_scanned': list(result.js_files_scanned),
            'fuzz_results': result.fuzz_results,
            'errors': result.errors,
            'timestamp': result.start_time.isoformat()
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def _export_discovery_csv(self, result, filename):
        """Exporta resultados en formato CSV"""
        import csv
        
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Escribir información general
            writer.writerow(['Tipo', 'Valor'])
            writer.writerow(['URL Base', result.base_url])
            writer.writerow(['Duración (segundos)', result.duration])
            writer.writerow(['Total Requests', result.total_requests])
            writer.writerow(['URLs Descubiertas', len(result.discovered_urls)])
            writer.writerow(['Endpoints Descubiertos', len(result.discovered_endpoints)])
            writer.writerow([])
            
            # URLs descubiertas
            writer.writerow(['URLs Descubiertas'])
            for url in sorted(result.discovered_urls):
                writer.writerow([url])
            writer.writerow([])
            
            # Endpoints descubiertos
            writer.writerow(['Endpoints Descubiertos'])
            for endpoint in sorted(result.discovered_endpoints):
                writer.writerow([endpoint])
            writer.writerow([])
            
            # Resultados de fuzzing
            if result.fuzz_results:
                writer.writerow(['Resultados de Fuzzing', 'Código'])
                for url, code in sorted(result.fuzz_results.items()):
                    writer.writerow([url, code])
                writer.writerow([])
            
            # Errores
            if result.errors:
                writer.writerow(['Errores'])
                for error in result.errors:
                    writer.writerow([error])
    
    def _export_discovery_txt(self, result, filename):
        """Exporta resultados en formato texto"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("RESULTADOS DEL DESCUBRIMIENTO DE URLS\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"URL Base: {result.base_url}\n")
            f.write(f"Duración: {result.duration:.2f} segundos\n")
            f.write(f"Total de requests: {result.total_requests}\n")
            f.write(f"URLs descubiertas: {len(result.discovered_urls)}\n")
            f.write(f"Endpoints descubiertos: {len(result.discovered_endpoints)}\n")
            f.write(f"Archivos JS escaneados: {len(result.js_files_scanned)}\n")
            f.write(f"Errores: {len(result.errors)}\n\n")
            
            f.write("URLS DESCUBIERTAS:\n")
            f.write("-" * 20 + "\n")
            for url in sorted(result.discovered_urls):
                f.write(f"{url}\n")
            f.write("\n")
            
            f.write("ENDPOINTS DESCUBIERTOS:\n")
            f.write("-" * 25 + "\n")
            for endpoint in sorted(result.discovered_endpoints):
                f.write(f"{endpoint}\n")
            f.write("\n")
            
            if result.fuzz_results:
                f.write("RESULTADOS DE FUZZING:\n")
                f.write("-" * 25 + "\n")
                for url, code in sorted(result.fuzz_results.items()):
                    f.write(f"{url} - Código: {code}\n")
                f.write("\n")
            
            if result.errors:
                f.write("ERRORES:\n")
                f.write("-" * 8 + "\n")
                for error in result.errors:
                    f.write(f"{error}\n")


if __name__ == "__main__":
    try:
        # Iniciar la aplicación mejorada directamente
        root = tk.Tk()
        app = WebScraperApp(root)
        root.mainloop()
    except Exception as e:
        logger.error(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
        # Show error dialog if tkinter is available
        try:
            import tkinter.messagebox as messagebox
            messagebox.showerror("Error", f"Error starting application:\n{str(e)}")
        except Exception:
            logger.info(f"Error starting application: {e}")