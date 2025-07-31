"""
Enhanced HTML Analyzer for Professional Web Scraper

Implements advanced HTML analysis with content detection, semantic analysis,
accessibility checking, and intelligent element classification.
"""

import logging
import re
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, field
from bs4 import BeautifulSoup, Tag, NavigableString
from readability import Document
import hashlib
from urllib.parse import urljoin, urlparse
import json
from collections import defaultdict, Counter

logger = logging.getLogger(__name__)


@dataclass
class ElementInfo:
    """Information about an HTML element"""
    tag: str
    attributes: Dict[str, str]
    text_content: str
    inner_html: str
    outer_html: str
    element_type: str
    semantic_role: str
    accessibility_score: float
    content_score: float
    position: Dict[str, int]
    parent_path: str
    children_count: int
    depth: int


@dataclass
class ContentBlock:
    """Represents a content block in the page"""
    type: str  # 'main', 'navigation', 'sidebar', 'footer', 'header'
    elements: List[ElementInfo]
    content_score: float
    text_content: str
    word_count: int
    link_count: int
    image_count: int


@dataclass
class PageStructure:
    """Structure analysis of the page"""
    title: str
    meta_description: str
    language: str
    content_blocks: List[ContentBlock]
    main_content: Optional[ContentBlock]
    navigation_blocks: List[ContentBlock]
    sidebar_blocks: List[ContentBlock]
    footer_blocks: List[ContentBlock]
    header_blocks: List[ContentBlock]
    forms: List[Dict[str, Any]]
    tables: List[Dict[str, Any]]
    images: List[Dict[str, Any]]
    links: List[Dict[str, Any]]
    accessibility_issues: List[Dict[str, Any]]
    semantic_structure: Dict[str, Any]


class EnhancedHTMLAnalyzer:
    """
    Enhanced HTML analyzer with advanced content detection and semantic analysis
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize enhanced HTML analyzer
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config = config_manager
        
        if self.config is None:
            # Use default configuration if no config manager provided
            analyzer_config = {
                'enabled': True,
                'enable_semantic_analysis': True,
                'enable_accessibility_checking': True,
                'enable_content_detection': True,
                'min_content_length': 100,
                'max_content_blocks': 10
            }
        else:
            analyzer_config = self.config.get_section('html_analyzer')
        self.enabled = analyzer_config.get('enabled', True)
        
        if not self.enabled:
            logger.info("Enhanced HTML analyzer disabled")
            return
        
        # Configuration
        self.enable_semantic_analysis = analyzer_config.get('enable_semantic_analysis', True)
        self.enable_accessibility_checking = analyzer_config.get('enable_accessibility_checking', True)
        self.enable_content_detection = analyzer_config.get('enable_content_detection', True)
        self.min_content_length = analyzer_config.get('min_content_length', 100)
        self.max_content_blocks = analyzer_config.get('max_content_blocks', 10)
        
        # Semantic patterns
        self.semantic_patterns = {
            'navigation': [
                'nav', '[role="navigation"]', '.navigation', '.nav', '.menu',
                '.navbar', '.breadcrumb', '.pagination'
            ],
            'main_content': [
                'main', '[role="main"]', '.main', '.content', '.article',
                '.post', '.entry', '.story'
            ],
            'sidebar': [
                'aside', '[role="complementary"]', '.sidebar', '.side',
                '.widget', '.panel'
            ],
            'header': [
                'header', '[role="banner"]', '.header', '.head', '.top'
            ],
            'footer': [
                'footer', '[role="contentinfo"]', '.footer', '.foot', '.bottom'
            ]
        }
        
        # Accessibility patterns
        self.accessibility_patterns = {
            'missing_alt': 'img:not([alt])',
            'missing_label': 'input:not([id]):not([aria-label]):not([aria-labelledby])',
            'missing_heading': 'section:not(:has(h1, h2, h3, h4, h5, h6))',
            'color_contrast': '[style*="color"]',
            'keyboard_navigation': 'a:not([tabindex]), button:not([tabindex])'
        }
        
        # Content scoring weights
        self.content_weights = {
            'text_length': 0.3,
            'link_density': 0.2,
            'image_density': 0.1,
            'semantic_score': 0.2,
            'position_score': 0.1,
            'structure_score': 0.1
        }
        
        logger.info("Enhanced HTML analyzer initialized")
    
    def analyze(self, html_content: str, url: str = "") -> PageStructure:
        """
        Perform comprehensive HTML analysis
        
        Args:
            html_content: HTML content to analyze
            url: URL of the page (for resolving relative links)
            
        Returns:
            PageStructure with analysis results
        """
        if not self.enabled:
            return PageStructure(
                title="", meta_description="", language="",
                content_blocks=[], main_content=None,
                navigation_blocks=[], sidebar_blocks=[],
                footer_blocks=[], header_blocks=[],
                forms=[], tables=[], images=[], links=[],
                accessibility_issues=[], semantic_structure={}
            )
        
        if not html_content or not html_content.strip():
            logger.warning("Empty HTML content provided for analysis")
            return PageStructure(
                title="", meta_description="", language="",
                content_blocks=[], main_content=None,
                navigation_blocks=[], sidebar_blocks=[],
                footer_blocks=[], header_blocks=[],
                forms=[], tables=[], images=[], links=[],
                accessibility_issues=[], semantic_structure={}
            )
        
        try:
            # Parse HTML
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Basic page information
            title = self._extract_title(soup)
            meta_description = self._extract_meta_description(soup)
            language = self._extract_language(soup)
            
            # Extract forms
            forms = self._extract_forms(soup, url)
            
            # Extract tables
            tables = self._extract_tables(soup)
            
            # Extract images
            images = self._extract_images(soup, url)
            
            # Extract links
            links = self._extract_links(soup, url)
            
            # Semantic analysis
            semantic_structure = {}
            if self.enable_semantic_analysis:
                semantic_structure = self._analyze_semantic_structure(soup)
            
            # Content detection
            content_blocks = []
            main_content = None
            if self.enable_content_detection:
                content_blocks, main_content = self._detect_content_blocks(soup)
            
            # Categorize content blocks
            navigation_blocks = [b for b in content_blocks if b.type == 'navigation']
            sidebar_blocks = [b for b in content_blocks if b.type == 'sidebar']
            footer_blocks = [b for b in content_blocks if b.type == 'footer']
            header_blocks = [b for b in content_blocks if b.type == 'header']
            
            # Accessibility analysis
            accessibility_issues = []
            if self.enable_accessibility_checking:
                accessibility_issues = self._check_accessibility(soup)
            
            return PageStructure(
                title=title,
                meta_description=meta_description,
                language=language,
                content_blocks=content_blocks,
                main_content=main_content,
                navigation_blocks=navigation_blocks,
                sidebar_blocks=sidebar_blocks,
                footer_blocks=footer_blocks,
                header_blocks=header_blocks,
                forms=forms,
                tables=tables,
                images=images,
                links=links,
                accessibility_issues=accessibility_issues,
                semantic_structure=semantic_structure
            )
            
        except Exception as e:
            logger.error(f"Error analyzing HTML: {e}")
            return PageStructure(
                title="", meta_description="", language="",
                content_blocks=[], main_content=None,
                navigation_blocks=[], sidebar_blocks=[],
                footer_blocks=[], header_blocks=[],
                forms=[], tables=[], images=[], links=[],
                accessibility_issues=[], semantic_structure={}
            )
    
    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title"""
        title_tag = soup.find('title')
        if title_tag:
            return title_tag.get_text(strip=True)
        
        # Fallback to h1
        h1_tag = soup.find('h1')
        if h1_tag:
            return h1_tag.get_text(strip=True)
        
        return ""
    
    def _extract_meta_description(self, soup: BeautifulSoup) -> str:
        """Extract meta description"""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            return meta_desc.get('content', '')
        
        # Fallback to og:description
        og_desc = soup.find('meta', attrs={'property': 'og:description'})
        if og_desc:
            return og_desc.get('content', '')
        
        return ""
    
    def _extract_language(self, soup: BeautifulSoup) -> str:
        """Extract page language"""
        # Check html lang attribute
        html_tag = soup.find('html')
        if html_tag and html_tag.get('lang'):
            return html_tag['lang']
        
        # Check meta http-equiv
        meta_lang = soup.find('meta', attrs={'http-equiv': 'content-language'})
        if meta_lang:
            return meta_lang.get('content', '')
        
        return "en"  # Default to English
    
    def _extract_forms(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Extract form information"""
        forms = []
        
        for form in soup.find_all('form'):
            form_info = {
                'action': form.get('action', ''),
                'method': form.get('method', 'get'),
                'id': form.get('id', ''),
                'class': form.get('class', []),
                'inputs': [],
                'buttons': []
            }
            
            # Resolve action URL
            if form_info['action']:
                form_info['action'] = urljoin(base_url, form_info['action'])
            
            # Extract inputs
            for input_tag in form.find_all('input'):
                input_info = {
                    'type': input_tag.get('type', 'text'),
                    'name': input_tag.get('name', ''),
                    'id': input_tag.get('id', ''),
                    'placeholder': input_tag.get('placeholder', ''),
                    'required': input_tag.has_attr('required'),
                    'value': input_tag.get('value', '')
                }
                form_info['inputs'].append(input_info)
            
            # Extract buttons
            for button in form.find_all(['button', 'input']):
                if button.name == 'button' or button.get('type') in ['submit', 'button']:
                    button_info = {
                        'type': button.get('type', 'submit'),
                        'text': button.get_text(strip=True),
                        'id': button.get('id', ''),
                        'class': button.get('class', [])
                    }
                    form_info['buttons'].append(button_info)
            
            forms.append(form_info)
        
        return forms
    
    def _extract_tables(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Extract table information"""
        tables = []
        
        for table in soup.find_all('table'):
            table_info = {
                'id': table.get('id', ''),
                'class': table.get('class', []),
                'caption': '',
                'headers': [],
                'rows': [],
                'row_count': 0,
                'column_count': 0
            }
            
            # Extract caption
            caption = table.find('caption')
            if caption:
                table_info['caption'] = caption.get_text(strip=True)
            
            # Extract headers
            headers = table.find_all(['th'])
            table_info['headers'] = [h.get_text(strip=True) for h in headers]
            
            # Extract rows
            rows = table.find_all('tr')
            table_info['row_count'] = len(rows)
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                row_data = [cell.get_text(strip=True) for cell in cells]
                table_info['rows'].append(row_data)
                
                if len(row_data) > table_info['column_count']:
                    table_info['column_count'] = len(row_data)
            
            tables.append(table_info)
        
        return tables
    
    def _extract_images(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Extract image information"""
        images = []
        
        for img in soup.find_all('img'):
            img_info = {
                'src': img.get('src', ''),
                'alt': img.get('alt', ''),
                'title': img.get('title', ''),
                'width': img.get('width', ''),
                'height': img.get('height', ''),
                'id': img.get('id', ''),
                'class': img.get('class', []),
                'loading': img.get('loading', ''),
                'decoding': img.get('decoding', '')
            }
            
            # Resolve src URL
            if img_info['src']:
                img_info['src'] = urljoin(base_url, img_info['src'])
            
            # Accessibility score
            img_info['accessibility_score'] = self._calculate_image_accessibility(img_info)
            
            images.append(img_info)
        
        return images
    
    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Extract link information"""
        links = []
        
        for link in soup.find_all('a', href=True):
            link_info = {
                'href': link.get('href', ''),
                'text': link.get_text(strip=True),
                'title': link.get('title', ''),
                'id': link.get('id', ''),
                'class': link.get('class', []),
                'target': link.get('target', ''),
                'rel': link.get('rel', []),
                'download': link.get('download', ''),
                'hreflang': link.get('hreflang', '')
            }
            
            # Resolve href URL
            if link_info['href']:
                link_info['href'] = urljoin(base_url, link_info['href'])
            
            # Categorize link
            link_info['type'] = self._categorize_link(link_info)
            
            links.append(link_info)
        
        return links
    
    def _analyze_semantic_structure(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Analyze semantic structure of the page"""
        structure = {
            'headings': [],
            'landmarks': [],
            'sections': [],
            'articles': [],
            'navigation': [],
            'asides': []
        }
        
        # Analyze headings
        for i in range(1, 7):
            headings = soup.find_all(f'h{i}')
            for heading in headings:
                structure['headings'].append({
                    'level': i,
                    'text': heading.get_text(strip=True),
                    'id': heading.get('id', ''),
                    'class': heading.get('class', [])
                })
        
        # Analyze landmarks
        landmarks = soup.find_all(['header', 'nav', 'main', 'aside', 'footer', 'section', 'article'])
        for landmark in landmarks:
            landmark_info = {
                'tag': landmark.name,
                'role': landmark.get('role', ''),
                'id': landmark.get('id', ''),
                'class': landmark.get('class', []),
                'text': landmark.get_text(strip=True)[:100]
            }
            structure['landmarks'].append(landmark_info)
        
        # Analyze sections
        sections = soup.find_all('section')
        for section in sections:
            section_info = {
                'id': section.get('id', ''),
                'class': section.get('class', []),
                'heading': '',
                'content_length': len(section.get_text(strip=True))
            }
            
            # Find section heading
            heading = section.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            if heading:
                section_info['heading'] = heading.get_text(strip=True)
            
            structure['sections'].append(section_info)
        
        return structure
    
    def _detect_content_blocks(self, soup: BeautifulSoup) -> Tuple[List[ContentBlock], Optional[ContentBlock]]:
        """Detect content blocks in the page"""
        content_blocks = []
        main_content = None
        
        # Use readability to find main content
        try:
            doc = Document(str(soup))
            main_html = doc.summary(html_partial=True)
            main_soup = BeautifulSoup(main_html, 'lxml')
            
            if main_soup.body:
                main_elements = self._analyze_elements(main_soup.body)
                main_content = ContentBlock(
                    type='main',
                    elements=main_elements,
                    content_score=self._calculate_content_score(main_elements),
                    text_content=main_soup.body.get_text(strip=True),
                    word_count=len(main_soup.body.get_text(strip=True).split()),
                    link_count=len(main_soup.body.find_all('a')),
                    image_count=len(main_soup.body.find_all('img'))
                )
                content_blocks.append(main_content)
        except Exception as e:
            logger.warning(f"Error detecting main content: {e}")
        
        # Detect other content blocks
        for block_type, selectors in self.semantic_patterns.items():
            if block_type == 'main_content':
                continue  # Already handled
            
            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    if self._is_significant_element(element):
                        block_elements = self._analyze_elements(element)
                        if len(block_elements) > 0:
                            content_block = ContentBlock(
                                type=block_type,
                                elements=block_elements,
                                content_score=self._calculate_content_score(block_elements),
                                text_content=element.get_text(strip=True),
                                word_count=len(element.get_text(strip=True).split()),
                                link_count=len(element.find_all('a')),
                                image_count=len(element.find_all('img'))
                            )
                            content_blocks.append(content_block)
        
        # Sort by content score and limit
        content_blocks.sort(key=lambda x: x.content_score, reverse=True)
        content_blocks = content_blocks[:self.max_content_blocks]
        
        return content_blocks, main_content
    
    def _analyze_elements(self, container: Tag) -> List[ElementInfo]:
        """Analyze elements within a container"""
        elements = []
        
        for element in container.find_all(recursive=True):
            if isinstance(element, NavigableString):
                continue
            
            element_info = ElementInfo(
                tag=element.name,
                attributes=dict(element.attrs),
                text_content=element.get_text(strip=True),
                inner_html=str(element),
                outer_html=str(element),
                element_type=self._classify_element(element),
                semantic_role=element.get('role', ''),
                accessibility_score=self._calculate_accessibility_score(element),
                content_score=self._calculate_element_content_score(element),
                position=self._calculate_element_position(element),
                parent_path=self._get_element_path(element),
                children_count=len(element.find_all(recursive=False)),
                depth=self._calculate_element_depth(element)
            )
            
            elements.append(element_info)
        
        return elements
    
    def _classify_element(self, element: Tag) -> str:
        """Classify element type"""
        tag = element.name.lower()
        
        if tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            return 'heading'
        elif tag == 'p':
            return 'paragraph'
        elif tag == 'a':
            return 'link'
        elif tag == 'img':
            return 'image'
        elif tag == 'table':
            return 'table'
        elif tag == 'form':
            return 'form'
        elif tag in ['ul', 'ol']:
            return 'list'
        elif tag in ['div', 'section', 'article', 'aside']:
            return 'container'
        else:
            return 'other'
    
    def _calculate_accessibility_score(self, element: Tag) -> float:
        """Calculate accessibility score for an element"""
        score = 1.0
        
        # Check for alt text on images
        if element.name == 'img' and not element.get('alt'):
            score -= 0.5
        
        # Check for labels on form elements
        if element.name in ['input', 'textarea', 'select']:
            if not (element.get('id') or element.get('aria-label') or element.get('aria-labelledby')):
                score -= 0.3
        
        # Check for semantic roles
        if element.get('role'):
            score += 0.2
        
        # Check for ARIA attributes
        aria_attrs = [attr for attr in element.attrs.keys() if attr.startswith('aria-')]
        if aria_attrs:
            score += 0.1 * len(aria_attrs)
        
        return max(0.0, min(1.0, score))
    
    def _calculate_element_content_score(self, element: Tag) -> float:
        """Calculate content score for an element"""
        score = 0.0
        
        # Text length
        text_length = len(element.get_text(strip=True))
        score += min(1.0, text_length / 1000) * self.content_weights['text_length']
        
        # Link density
        links = element.find_all('a')
        link_density = len(links) / max(1, text_length)
        score += (1.0 - min(1.0, link_density)) * self.content_weights['link_density']
        
        # Image density
        images = element.find_all('img')
        image_density = len(images) / max(1, text_length)
        score += (1.0 - min(1.0, image_density)) * self.content_weights['image_density']
        
        # Semantic score
        semantic_score = 0.0
        if element.name in ['article', 'main', 'section']:
            semantic_score = 1.0
        elif element.name in ['aside', 'nav']:
            semantic_score = 0.5
        score += semantic_score * self.content_weights['semantic_score']
        
        # Position score (elements higher in DOM get higher score)
        position_score = 1.0 - (self._calculate_element_depth(element) / 10)
        score += position_score * self.content_weights['position_score']
        
        return score
    
    def _calculate_content_score(self, elements: List[ElementInfo]) -> float:
        """Calculate overall content score for a block"""
        if not elements:
            return 0.0
        
        total_score = sum(elem.content_score for elem in elements)
        return total_score / len(elements)
    
    def _calculate_element_position(self, element: Tag) -> Dict[str, int]:
        """Calculate element position in the document"""
        # This is a simplified position calculation
        # In a real implementation, you might want to calculate actual coordinates
        return {
            'depth': self._calculate_element_depth(element),
            'sibling_index': len(list(element.previous_siblings)),
            'parent_index': len(list(element.parent.children)) if element.parent else 0
        }
    
    def _calculate_element_depth(self, element: Tag) -> int:
        """Calculate element depth in the DOM tree"""
        depth = 0
        current = element.parent
        while current and current.name:
            depth += 1
            current = current.parent
        return depth
    
    def _get_element_path(self, element: Tag) -> str:
        """Get element path in the DOM tree"""
        path_parts = []
        current = element
        
        while current and current.name:
            siblings = list(current.parent.children) if current.parent else []
            index = siblings.index(current) if current in siblings else 0
            path_parts.insert(0, f"{current.name}:{index}")
            current = current.parent
        
        return " > ".join(path_parts)
    
    def _is_significant_element(self, element: Tag) -> bool:
        """Check if element is significant enough to analyze"""
        text_length = len(element.get_text(strip=True))
        return text_length >= self.min_content_length
    
    def _check_accessibility(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """Check for accessibility issues"""
        issues = []
        
        # Check for images without alt text
        images_without_alt = soup.select('img:not([alt])')
        for img in images_without_alt:
            issues.append({
                'type': 'missing_alt',
                'element': 'img',
                'severity': 'medium',
                'description': 'Image missing alt text',
                'element_info': {
                    'src': img.get('src', ''),
                    'id': img.get('id', ''),
                    'class': img.get('class', [])
                }
            })
        
        # Check for form inputs without labels
        inputs_without_label = soup.select('input:not([id]):not([aria-label]):not([aria-labelledby])')
        for input_elem in inputs_without_label:
            issues.append({
                'type': 'missing_label',
                'element': 'input',
                'severity': 'high',
                'description': 'Form input missing label',
                'element_info': {
                    'type': input_elem.get('type', ''),
                    'name': input_elem.get('name', ''),
                    'class': input_elem.get('class', [])
                }
            })
        
        # Check for missing headings in sections
        sections_without_heading = soup.select('section:not(:has(h1, h2, h3, h4, h5, h6))')
        for section in sections_without_heading:
            issues.append({
                'type': 'missing_heading',
                'element': 'section',
                'severity': 'low',
                'description': 'Section missing heading',
                'element_info': {
                    'id': section.get('id', ''),
                    'class': section.get('class', [])
                }
            })
        
        return issues
    
    def _calculate_image_accessibility(self, img_info: Dict[str, Any]) -> float:
        """Calculate accessibility score for an image"""
        score = 1.0
        
        # Alt text
        if not img_info['alt']:
            score -= 0.5
        elif len(img_info['alt']) < 3:
            score -= 0.2
        
        # Title attribute
        if img_info['title']:
            score += 0.1
        
        # Loading attribute
        if img_info['loading'] == 'lazy':
            score += 0.1
        
        return max(0.0, min(1.0, score))
    
    def _categorize_link(self, link_info: Dict[str, Any]) -> str:
        """Categorize link type"""
        href = link_info['href'].lower()
        text = link_info['text'].lower()
        
        if href.startswith('mailto:'):
            return 'email'
        elif href.startswith('tel:'):
            return 'phone'
        elif href.startswith('#'):
            return 'anchor'
        elif href.startswith('javascript:'):
            return 'javascript'
        elif any(ext in href for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx']):
            return 'document'
        elif any(ext in href for ext in ['.jpg', '.jpeg', '.png', '.gif', '.svg']):
            return 'image'
        elif 'download' in link_info['rel'] or link_info['download']:
            return 'download'
        elif link_info['target'] == '_blank':
            return 'external'
        else:
            return 'internal'
    
    def get_analysis_summary(self, structure: PageStructure) -> Dict[str, Any]:
        """Get summary of analysis results"""
        return {
            'title': structure.title,
            'language': structure.language,
            'content_blocks_count': len(structure.content_blocks),
            'main_content_length': len(structure.main_content.text_content) if structure.main_content else 0,
            'forms_count': len(structure.forms),
            'tables_count': len(structure.tables),
            'images_count': len(structure.images),
            'links_count': len(structure.links),
            'accessibility_issues_count': len(structure.accessibility_issues),
            'semantic_landmarks_count': len(structure.semantic_structure.get('landmarks', [])),
            'headings_count': len(structure.semantic_structure.get('headings', [])),
            'sections_count': len(structure.semantic_structure.get('sections', []))
        }
    
    def export_analysis(self, structure: PageStructure, filepath: str, format: str = "json") -> bool:
        """Export analysis results"""
        try:
            data = {
                'analysis_time': datetime.now().isoformat(),
                'summary': self.get_analysis_summary(structure),
                'structure': {
                    'title': structure.title,
                    'meta_description': structure.meta_description,
                    'language': structure.language,
                    'content_blocks': [
                        {
                            'type': block.type,
                            'content_score': block.content_score,
                            'word_count': block.word_count,
                            'link_count': block.link_count,
                            'image_count': block.image_count,
                            'text_content': block.text_content[:500] + '...' if len(block.text_content) > 500 else block.text_content
                        }
                        for block in structure.content_blocks
                    ],
                    'forms': structure.forms,
                    'tables': structure.tables,
                    'images': structure.images,
                    'links': structure.links,
                    'accessibility_issues': structure.accessibility_issues,
                    'semantic_structure': structure.semantic_structure
                }
            }
            
            if format.lower() == "json":
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            logger.info(f"Analysis exported to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting analysis: {e}")
            return False 