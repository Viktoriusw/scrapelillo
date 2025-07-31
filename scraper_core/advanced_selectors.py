"""
Advanced Selectors for Professional Web Scraper

Provides intelligent element selection and data extraction capabilities
including AI-powered selectors, visual selectors, and smart data mapping.
"""

import logging
import re
import json
import time
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from bs4 import BeautifulSoup, Tag
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class SelectorRule:
    name: str
    selectors: list
    data_type: str  # 'text', 'attribute', 'html', 'json'
    attribute: Optional[str] = None
    transform: Optional[str] = None
    required: bool = False
    multiple: bool = False
    fallback_selectors: list = field(default_factory=list)
    validation_pattern: Optional[str] = None
    confidence_threshold: float = 0.7
    description: str = ""

@dataclass
class ExtractionResult:
    selector_name: str
    value: Any
    confidence: float
    source_element: Optional[Tag] = None
    extraction_time: float = 0.0
    quality_score: float = 0.0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

class AdvancedSelectors:
    """
    Advanced selector system with AI-powered element detection and smart data extraction
    """
    def __init__(self, config_manager=None):
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        selector_config = self.config.get_section('advanced_selectors')
        self.enabled = selector_config.get('enabled', True)
        if not self.enabled:
            logger.info("Advanced selectors disabled")
            return
        self.enable_ai_selectors = selector_config.get('enable_ai_selectors', True)
        self.enable_visual_selectors = selector_config.get('enable_visual_selectors', True)
        self.enable_smart_mapping = selector_config.get('enable_smart_mapping', True)
        self.max_selector_attempts = selector_config.get('max_selector_attempts', 5)
        self.min_confidence_threshold = selector_config.get('min_confidence_threshold', 0.7)
        self.common_patterns = {
            'price': [r'[\$€£¥]\s*\d+[.,]\d{2}', r'\d+[.,]\d{2}\s*[\$€£¥]', r'price[:\s]*[\$€£¥]?\s*\d+[.,]\d{2}', r'[\$€£¥]?\s*\d+[.,]\d{2}\s*(USD|EUR|GBP|JPY)'],
            'email': [r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'],
            'phone': [r'\+?[\d\s\-\(\)]{10,}', r'\(\d{3}\)\s*\d{3}-\d{4}', r'\d{3}-\d{3}-\d{4}'],
            'date': [r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', r'\d{4}-\d{2}-\d{2}', r'\w+\s+\d{1,2},?\s+\d{4}'],
            'url': [r'https?://[^\s<>"]+', r'www\.[^\s<>"]+']
        }
        self.content_patterns = {
            'title': ['h1', 'h2', '.title', '.headline', '[class*="title"]', '[class*="headline"]', '.product-title', '.post-title'],
            'description': ['.description', '.desc', '.summary', '.excerpt', '[class*="description"]', '[class*="summary"]', 'meta[name="description"]', 'meta[property="og:description"]'],
            'price': ['.price', '.cost', '.amount', '[class*="price"]', '[class*="cost"]', '[data-price]', '[data-cost]'],
            'image': ['.image', '.img', '.photo', '.picture', '[class*="image"]', '[class*="photo"]', 'img[src*="product"]'],
            'rating': ['.rating', '.stars', '.score', '[class*="rating"]', '[class*="stars"]', '[data-rating]', '.review-score'],
            'availability': ['.availability', '.stock', '.in-stock', '.out-of-stock', '[class*="availability"]', '[class*="stock"]']
        }
        self.visual_patterns = {
            'product_card': ['.product', '.item', '.card', '.product-card', '[class*="product"]', '[class*="item"]', '[class*="card"]'],
            'navigation': ['nav', '.nav', '.navigation', '.menu', '.navbar', '[role="navigation"]', '.breadcrumb', '.pagination'],
            'sidebar': ['.sidebar', '.side', '.aside', '.widget', '[class*="sidebar"]', '[class*="widget"]'],
            'footer': ['footer', '.footer', '.foot', '.bottom', '[class*="footer"]', '[class*="bottom"]'],
            'header': ['header', '.header', '.head', '.top', '[class*="header"]', '[class*="top"]']
        }
        self.templates = self._load_predefined_templates()
        logger.info("Advanced selectors initialized")

    def _load_predefined_templates(self) -> Dict[str, List[SelectorRule]]:
        return {
            'ecommerce_product': [
                SelectorRule('title', ['h1', '.product-title', '[class*="title"]'], 'text', description="Product title"),
                SelectorRule('price', ['.price', '.cost', '[class*="price"]'], 'text', transform='extract_number', validation_pattern=r'^\d+[.,]\d{2}$', description="Product price"),
                SelectorRule('description', ['.description', '.desc', '.summary'], 'text', description="Product description"),
                SelectorRule('image', ['img[src*="product"]', '.product-image'], 'attribute', attribute='src', validation_pattern=r'https?://.*', description="Product image URL"),
                SelectorRule('rating', ['.rating', '.stars', '[class*="rating"]'], 'text', transform='extract_number', description="Product rating")
            ],
            'contact_page': [
                SelectorRule('email', ['a[href^="mailto:"]', '[class*="email"]'], 'text', transform='extract_email', validation_pattern=r'.*@.*\..*', description="Contact email"),
                SelectorRule('phone', ['a[href^="tel:"]', '[class*="phone"]'], 'text', transform='extract_number', description="Contact phone"),
                SelectorRule('address', ['.address', '[class*="address"]'], 'text', description="Contact address"),
                SelectorRule('name', ['.name', '[class*="name"]'], 'text', description="Contact name")
            ],
            'news_article': [
                SelectorRule('headline', ['h1', '.headline', '.title'], 'text', description="Article headline"),
                SelectorRule('author', ['.author', '.byline', '[class*="author"]'], 'text', description="Article author"),
                SelectorRule('date', ['.date', '.published', '[class*="date"]'], 'text', transform='extract_date', description="Publication date"),
                SelectorRule('content', ['.content', '.article-body', '.post-content'], 'text', description="Article content"),
                SelectorRule('image', ['.article-image', 'img[src*="article"]'], 'attribute', attribute='src', description="Article image")
            ]
        }

    def auto_detect_elements(self, soup: BeautifulSoup) -> Dict[str, List[Tag]]:
        detected = {}
        for content_type, selectors in self.content_patterns.items():
            elements = []
            for selector in selectors:
                try:
                    found = soup.select(selector)
                    elements.extend(found)
                except Exception:
                    continue
            if elements:
                detected[content_type] = elements
        for pattern_type, patterns in self.common_patterns.items():
            elements = []
            for element in soup.find_all(string=True):
                text = str(element)
                for pattern in patterns:
                    if re.search(pattern, text, re.IGNORECASE):
                        parent = element.parent
                        if parent and parent.name:
                            elements.append(parent)
                            break
            if elements:
                detected[f"{pattern_type}_text"] = elements
        for layout_type, selectors in self.visual_patterns.items():
            elements = []
            for selector in selectors:
                try:
                    found = soup.select(selector)
                    elements.extend(found)
                except Exception:
                    continue
            if elements:
                detected[layout_type] = elements
        return detected

    def extract_with_rules(self, soup: BeautifulSoup, rules: List[SelectorRule], base_url: str = "") -> Dict[str, ExtractionResult]:
        results = {}
        for rule in rules:
            start_time = time.time()
            result = self._extract_with_rule(soup, rule, base_url)
            result.extraction_time = time.time() - start_time
            result.quality_score = self._calculate_quality_score(result)
            results[rule.name] = result
        return results

    def _extract_with_rule(self, soup: BeautifulSoup, rule: SelectorRule, base_url: str) -> ExtractionResult:
        errors = []
        warnings = []
        value = None
        confidence = 0.0
        source_element = None
        for selector in rule.selectors:
            try:
                elements = soup.select(selector)
                if elements:
                    element = elements[0] if not rule.multiple else elements
                    value = self._extract_value(element, rule, base_url)
                    if value:
                        source_element = element
                        confidence = self._calculate_confidence(element, rule)
                        if rule.validation_pattern and value:
                            if not re.match(rule.validation_pattern, str(value)):
                                errors.append(f"Value '{value}' doesn't match validation pattern")
                                value = None
                                confidence = 0.0
                            else:
                                confidence += 0.1
                        if value and confidence >= rule.confidence_threshold:
                            break
                        elif value:
                            warnings.append(f"Low confidence ({confidence:.2f}) for selector '{selector}'")
            except Exception as e:
                errors.append(f"Error with selector '{selector}': {str(e)}")
        if not value and rule.fallback_selectors:
            for selector in rule.fallback_selectors:
                try:
                    elements = soup.select(selector)
                    if elements:
                        element = elements[0] if not rule.multiple else elements
                        value = self._extract_value(element, rule, base_url)
                        if value:
                            source_element = element
                            confidence = self._calculate_confidence(element, rule) * 0.8
                            warnings.append(f"Used fallback selector '{selector}'")
                            break
                except Exception as e:
                    errors.append(f"Error with fallback selector '{selector}': {str(e)}")
        return ExtractionResult(
            selector_name=rule.name,
            value=value,
            confidence=confidence,
            source_element=source_element,
            errors=errors,
            warnings=warnings
        )

    def _extract_value(self, element: Union[Tag, List[Tag]], rule: SelectorRule, base_url: str) -> Any:
        if isinstance(element, list):
            return [self._extract_single_value(e, rule, base_url) for e in element]
        else:
            return self._extract_single_value(element, rule, base_url)

    def _extract_single_value(self, element: Tag, rule: SelectorRule, base_url: str) -> Any:
        if rule.data_type == 'text':
            value = element.get_text(strip=True)
        elif rule.data_type == 'html':
            value = str(element)
        elif rule.data_type == 'attribute':
            if rule.attribute:
                value = element.get(rule.attribute, '')
            else:
                value = ''
        elif rule.data_type == 'json':
            try:
                value = json.loads(element.get_text(strip=True))
            except Exception:
                value = None
        else:
            value = element.get_text(strip=True)
        if value and rule.transform:
            value = self._apply_transform(value, rule.transform)
        return value

    def _apply_transform(self, value: str, transform: str) -> Any:
        if transform == 'clean':
            return self._clean_text(value)
        elif transform == 'extract_number':
            return self._extract_number(value)
        elif transform == 'extract_date':
            return self._extract_date(value)
        elif transform == 'extract_email':
            return self._extract_email(value)
        elif transform == 'extract_url':
            return self._extract_url(value)
        else:
            return value

    def _clean_text(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\w\s\-.,!?@#$%&*()]', '', text)
        return text.strip()

    def _extract_number(self, text: str) -> Optional[float]:
        numbers = re.findall(r'[\d,]+\.?\d*', text)
        if numbers:
            try:
                return float(numbers[0].replace(',', ''))
            except Exception:
                pass
        return None

    def _extract_date(self, text: str) -> Optional[str]:
        for pattern in self.common_patterns['date']:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        return None

    def _extract_email(self, text: str) -> Optional[str]:
        for pattern in self.common_patterns['email']:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        return None

    def _extract_url(self, text: str) -> Optional[str]:
        for pattern in self.common_patterns['url']:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]
        return None

    def _calculate_confidence(self, element: Tag, rule: SelectorRule) -> float:
        confidence = 0.5
        text_length = len(element.get_text(strip=True))
        if text_length > 0:
            confidence += min(0.3, text_length / 1000)
        if element.name in ['h1', 'h2', 'h3']:
            confidence += 0.2
        elif element.name in ['p', 'div']:
            confidence += 0.1
        if rule.attribute and element.get(rule.attribute):
            confidence += 0.1
        classes = element.get('class', [])
        if any(keyword in ' '.join(classes).lower() for keyword in ['title', 'name', 'price', 'description']):
            confidence += 0.1
        return min(1.0, confidence)

    def _calculate_quality_score(self, result: ExtractionResult) -> float:
        if not result.value:
            return 0.0
        score = 1.0
        score -= len(result.errors) * 0.2
        score -= len(result.warnings) * 0.1
        if result.confidence < 0.5:
            score -= 0.3
        if isinstance(result.value, str) and len(result.value.strip()) < 3:
            score -= 0.3
        return max(0.0, score)

    def get_template(self, template_name: str) -> List[SelectorRule]:
        return self.templates.get(template_name, [])

    def list_templates(self) -> List[str]:
        return list(self.templates.keys())

    def create_custom_template(self, name: str, rules: List[SelectorRule]):
        self.templates[name] = rules

    def export_template(self, template_name: str, filepath: str) -> bool:
        try:
            template = self.templates.get(template_name)
            if not template:
                return False
            template_data = {
                'name': template_name,
                'created_at': datetime.now().isoformat(),
                'rules': [
                    {
                        'name': rule.name,
                        'selectors': rule.selectors,
                        'data_type': rule.data_type,
                        'attribute': rule.attribute,
                        'transform': rule.transform,
                        'required': rule.required,
                        'multiple': rule.multiple,
                        'fallback_selectors': rule.fallback_selectors,
                        'validation_pattern': rule.validation_pattern,
                        'confidence_threshold': rule.confidence_threshold,
                        'description': rule.description
                    }
                    for rule in template
                ]
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(template_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Template '{template_name}' exported to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Error exporting template: {e}")
            return False

    def import_template(self, filepath: str) -> Optional[str]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
            name = template_data['name']
            rules = []
            for rule_data in template_data['rules']:
                rule = SelectorRule(
                    name=rule_data['name'],
                    selectors=rule_data['selectors'],
                    data_type=rule_data['data_type'],
                    attribute=rule_data.get('attribute'),
                    transform=rule_data.get('transform'),
                    required=rule_data.get('required', False),
                    multiple=rule_data.get('multiple', False),
                    fallback_selectors=rule_data.get('fallback_selectors', []),
                    validation_pattern=rule_data.get('validation_pattern'),
                    confidence_threshold=rule_data.get('confidence_threshold', 0.7),
                    description=rule_data.get('description', '')
                )
                rules.append(rule)
            self.templates[name] = rules
            logger.info(f"Template '{name}' imported from {filepath}")
            return name
        except Exception as e:
            logger.error(f"Error importing template: {e}")
            return None 