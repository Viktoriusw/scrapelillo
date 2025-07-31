"""
Structured Data Extractor for Professional Web Scraper

Extracts structured data from web pages including JSON-LD, Microdata, RDFa,
Open Graph, Twitter Cards, and custom selectors with validation and cleaning.
"""

import json
import logging
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
import re
from bs4 import BeautifulSoup, Tag
import extruct
import validators

logger = logging.getLogger(__name__)


@dataclass
class StructuredDataItem:
    """Represents a structured data item"""
    type: str
    data: Dict[str, Any]
    source: str  # 'json-ld', 'microdata', 'rdfa', 'opengraph', 'twitter', 'custom'
    url: str
    selector: Optional[str] = None
    confidence: float = 1.0
    validation_errors: List[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Result of structured data extraction"""
    items: List[StructuredDataItem] = field(default_factory=list)
    total_items: int = 0
    extraction_time: float = 0.0
    errors: List[str] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)


class StructuredDataExtractor:
    """
    Extracts structured data from HTML content using multiple methods
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize structured data extractor
        
        Args:
            config_manager: Configuration manager instance
        """
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        
        extractor_config = self.config.get_section('structured_data')
        self.enabled = extractor_config.get('enabled', True)
        
        if not self.enabled:
            logger.info("Structured data extractor disabled")
            return
        
        # Configuration
        self.extract_json_ld = extractor_config.get('extract_json_ld', True)
        self.extract_microdata = extractor_config.get('extract_microdata', True)
        self.extract_rdfa = extractor_config.get('extract_rdfa', True)
        self.extract_opengraph = extractor_config.get('extract_opengraph', True)
        self.extract_twitter = extractor_config.get('extract_twitter', True)
        self.extract_microformats = extractor_config.get('extract_microformats', True)
        
        # Validation settings
        self.validate_data = extractor_config.get('validate_data', True)
        self.clean_data = extractor_config.get('clean_data', True)
        self.normalize_urls = extractor_config.get('normalize_urls', True)
        
        # Custom selectors
        self.custom_selectors = extractor_config.get('custom_selectors', {})
        
        # Initialize extractors - using extruct's unified API
        self.extractors = {
            'json-ld': True,
            'microdata': True,
            'rdfa': True,
            'opengraph': True,
            'microformat': True
        }
        
        logger.info("Structured data extractor initialized")
    
    def extract_all(self, html_content: str, url: str) -> ExtractionResult:
        """
        Extract all types of structured data from HTML content
        
        Args:
            html_content: HTML content to extract from
            url: Base URL for normalization
            
        Returns:
            ExtractionResult with all extracted data
        """
        if not self.enabled:
            return ExtractionResult()
        
        import time
        start_time = time.time()
        
        result = ExtractionResult()
        soup = BeautifulSoup(html_content, 'lxml')
        
        try:
            # Extract JSON-LD
            if self.extract_json_ld:
                jsonld_items = self._extract_json_ld(soup, url)
                result.items.extend(jsonld_items)
            
            # Extract Open Graph
            if self.extract_opengraph:
                opengraph_items = self._extract_opengraph(soup, url)
                result.items.extend(opengraph_items)
            
            # Extract Twitter Cards
            if self.extract_twitter:
                twitter_items = self._extract_twitter_cards(soup, url)
                result.items.extend(twitter_items)
            
            # Extract custom selectors
            custom_items = self._extract_custom_selectors(soup, url)
            result.items.extend(custom_items)
            
            # Process and clean data
            if self.clean_data:
                result.items = self._clean_extracted_data(result.items, url)
            
            # Validate data
            if self.validate_data:
                result.items = self._validate_extracted_data(result.items)
            
            # Calculate summary
            result.total_items = len(result.items)
            result.extraction_time = time.time() - start_time
            result.summary = self._calculate_summary(result.items)
            
            logger.info(f"Extracted {result.total_items} structured data items in {result.extraction_time:.2f}s")
            
        except Exception as e:
            error_msg = f"Error extracting structured data: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)
        
        return result
    
    def _extract_json_ld(self, soup: BeautifulSoup, url: str) -> List[StructuredDataItem]:
        """Extract JSON-LD structured data"""
        items = []
        
        try:
            # Find all script tags with type application/ld+json
            script_tags = soup.find_all('script', type='application/ld+json')
            
            for script in script_tags:
                try:
                    json_data = json.loads(script.string)
                    
                    # Handle both single objects and arrays
                    if isinstance(json_data, list):
                        for item in json_data:
                            if isinstance(item, dict):
                                items.append(StructuredDataItem(
                                    type=item.get('@type', 'Unknown'),
                                    data=item,
                                    source='json-ld',
                                    url=url,
                                    selector=f"script[type='application/ld+json']"
                                ))
                    elif isinstance(json_data, dict):
                        items.append(StructuredDataItem(
                            type=json_data.get('@type', 'Unknown'),
                            data=json_data,
                            source='json-ld',
                            url=url,
                            selector=f"script[type='application/ld+json']"
                        ))
                        
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON-LD: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error extracting JSON-LD: {e}")
        
        return items
    
    def _extract_microdata(self, soup: BeautifulSoup, url: str) -> List[StructuredDataItem]:
        """Extract Microdata structured data"""
        items = []
        
        try:
            # Find elements with itemtype attribute
            microdata_elements = soup.find_all(attrs={'itemtype': True})
            
            for element in microdata_elements:
                try:
                    itemtype = element.get('itemtype', '')
                    item_data = {}
                    
                    # Extract item properties
                    for prop_element in element.find_all(attrs={'itemprop': True}):
                        prop_name = prop_element.get('itemprop')
                        prop_value = self._extract_property_value(prop_element)
                        
                        if prop_name and prop_value is not None:
                            item_data[prop_name] = prop_value
                    
                    if item_data:
                        items.append(StructuredDataItem(
                            type=itemtype.split('/')[-1] if '/' in itemtype else itemtype,
                            data=item_data,
                            source='microdata',
                            url=url,
                            selector=f"[itemtype='{itemtype}']"
                        ))
                        
                except Exception as e:
                    logger.warning(f"Error extracting microdata item: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error extracting microdata: {e}")
        
        return items
    
    def _extract_rdfa(self, soup: BeautifulSoup, url: str) -> List[StructuredDataItem]:
        """Extract RDFa structured data"""
        items = []
        
        try:
            # Find elements with typeof attribute
            rdfa_elements = soup.find_all(attrs={'typeof': True})
            
            for element in rdfa_elements:
                try:
                    typeof = element.get('typeof', '')
                    item_data = {}
                    
                    # Extract properties
                    for prop_element in element.find_all(attrs={'property': True}):
                        prop_name = prop_element.get('property')
                        prop_value = self._extract_property_value(prop_element)
                        
                        if prop_name and prop_value is not None:
                            item_data[prop_name] = prop_value
                    
                    # Extract resource attributes
                    for attr in ['about', 'resource', 'content']:
                        value = element.get(attr)
                        if value:
                            item_data[attr] = value
                    
                    if item_data:
                        items.append(StructuredDataItem(
                            type=typeof.split(':')[-1] if ':' in typeof else typeof,
                            data=item_data,
                            source='rdfa',
                            url=url,
                            selector=f"[typeof='{typeof}']"
                        ))
                        
                except Exception as e:
                    logger.warning(f"Error extracting RDFa item: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error extracting RDFa: {e}")
        
        return items
    
    def _extract_opengraph(self, soup: BeautifulSoup, url: str) -> List[StructuredDataItem]:
        """Extract Open Graph structured data"""
        items = []
        
        try:
            og_data = {}
            
            # Find all Open Graph meta tags
            og_tags = soup.find_all('meta', property=re.compile(r'^og:'))
            
            for tag in og_tags:
                property_name = tag.get('property', '')
                content = tag.get('content', '')
                
                if property_name and content:
                    # Convert og:property:name to nested structure
                    parts = property_name.split(':')
                    if len(parts) >= 2:
                        if len(parts) == 2:
                            if isinstance(og_data, dict):
                                og_data[parts[1]] = content
                        else:
                            # Handle nested properties like og:image:width
                            current = og_data
                            for part in parts[1:-1]:
                                if part not in current:
                                    current[part] = {}
                                current = current[part]
                            current[parts[-1]] = content
            
            if og_data:
                items.append(StructuredDataItem(
                    type='OpenGraph',
                    data=og_data,
                    source='opengraph',
                    url=url,
                    selector='meta[property^="og:"]'
                ))
                
        except Exception as e:
            logger.error(f"Error extracting Open Graph: {e}")
        
        return items
    
    def _extract_twitter_cards(self, soup: BeautifulSoup, url: str) -> List[StructuredDataItem]:
        """Extract Twitter Cards structured data"""
        items = []
        
        try:
            twitter_data = {}
            
            # Find all Twitter Card meta tags
            twitter_tags = soup.find_all('meta', attrs={'name': re.compile(r'^twitter:')})
            
            for tag in twitter_tags:
                name = tag.get('name', '')
                content = tag.get('content', '')
                
                if name and content:
                    # Convert twitter:property to nested structure
                    parts = name.split(':')
                    if len(parts) >= 2:
                        if len(parts) == 2:
                            twitter_data[parts[1]] = content
                        else:
                            # Handle nested properties
                            current = twitter_data
                            for part in parts[1:-1]:
                                if part not in current:
                                    current[part] = {}
                                current = current[part]
                            current[parts[-1]] = content
            
            if twitter_data:
                items.append(StructuredDataItem(
                    type='TwitterCard',
                    data=twitter_data,
                    source='twitter',
                    url=url,
                    selector='meta[name^="twitter:"]'
                ))
                
        except Exception as e:
            logger.error(f"Error extracting Twitter Cards: {e}")
        
        return items
    
    def _extract_microformats(self, soup: BeautifulSoup, url: str) -> List[StructuredDataItem]:
        """Extract Microformats structured data"""
        items = []
        
        try:
            # Find elements with microformat classes
            microformat_classes = ['h-card', 'h-entry', 'h-event', 'h-product', 'h-recipe', 'h-review']
            
            for class_name in microformat_classes:
                elements = soup.find_all(class_=class_name)
                
                for element in elements:
                    try:
                        item_data = {}
                        
                        # Extract properties based on microformat class
                        if class_name == 'h-card':
                            item_data = self._extract_h_card(element)
                        elif class_name == 'h-entry':
                            item_data = self._extract_h_entry(element)
                        elif class_name == 'h-event':
                            item_data = self._extract_h_event(element)
                        elif class_name == 'h-product':
                            item_data = self._extract_h_product(element)
                        elif class_name == 'h-recipe':
                            item_data = self._extract_h_recipe(element)
                        elif class_name == 'h-review':
                            item_data = self._extract_h_review(element)
                        
                        if item_data:
                            items.append(StructuredDataItem(
                                type=class_name[2:].title(),  # Remove 'h-' prefix and capitalize
                                data=item_data,
                                source='microformat',
                                url=url,
                                selector=f".{class_name}"
                            ))
                            
                    except Exception as e:
                        logger.warning(f"Error extracting microformat {class_name}: {e}")
                        continue
                        
        except Exception as e:
            logger.error(f"Error extracting microformats: {e}")
        
        return items
    
    def _extract_h_card(self, element: Tag) -> Dict[str, Any]:
        """Extract h-card microformat data"""
        data = {}
        
        # Extract name
        name_elem = element.find(class_='p-name')
        if name_elem:
            data['name'] = name_elem.get_text(strip=True)
        
        # Extract URL
        url_elem = element.find(class_='u-url')
        if url_elem:
            data['url'] = url_elem.get('href') or url_elem.get_text(strip=True)
        
        # Extract photo
        photo_elem = element.find(class_='u-photo')
        if photo_elem:
            data['photo'] = photo_elem.get('src') or photo_elem.get_text(strip=True)
        
        # Extract organization
        org_elem = element.find(class_='p-org')
        if org_elem:
            data['organization'] = org_elem.get_text(strip=True)
        
        return data
    
    def _extract_h_entry(self, element: Tag) -> Dict[str, Any]:
        """Extract h-entry microformat data"""
        data = {}
        
        # Extract title
        title_elem = element.find(class_='p-name')
        if title_elem:
            data['title'] = title_elem.get_text(strip=True)
        
        # Extract content
        content_elem = element.find(class_='e-content')
        if content_elem:
            data['content'] = content_elem.get_text(strip=True)
        
        # Extract published date
        published_elem = element.find(class_='dt-published')
        if published_elem:
            data['published'] = published_elem.get_text(strip=True)
        
        # Extract author
        author_elem = element.find(class_='p-author')
        if author_elem:
            data['author'] = author_elem.get_text(strip=True)
        
        return data
    
    def _extract_h_event(self, element: Tag) -> Dict[str, Any]:
        """Extract h-event microformat data"""
        data = {}
        
        # Extract name
        name_elem = element.find(class_='p-name')
        if name_elem:
            data['name'] = name_elem.get_text(strip=True)
        
        # Extract start date
        start_elem = element.find(class_='dt-start')
        if start_elem:
            data['start'] = start_elem.get_text(strip=True)
        
        # Extract end date
        end_elem = element.find(class_='dt-end')
        if end_elem:
            data['end'] = end_elem.get_text(strip=True)
        
        # Extract location
        location_elem = element.find(class_='p-location')
        if location_elem:
            data['location'] = location_elem.get_text(strip=True)
        
        return data
    
    def _extract_h_product(self, element: Tag) -> Dict[str, Any]:
        """Extract h-product microformat data"""
        data = {}
        
        # Extract name
        name_elem = element.find(class_='p-name')
        if name_elem:
            data['name'] = name_elem.get_text(strip=True)
        
        # Extract price
        price_elem = element.find(class_='p-price')
        if price_elem:
            data['price'] = price_elem.get_text(strip=True)
        
        # Extract brand
        brand_elem = element.find(class_='p-brand')
        if brand_elem:
            data['brand'] = brand_elem.get_text(strip=True)
        
        # Extract category
        category_elem = element.find(class_='p-category')
        if category_elem:
            data['category'] = category_elem.get_text(strip=True)
        
        return data
    
    def _extract_h_recipe(self, element: Tag) -> Dict[str, Any]:
        """Extract h-recipe microformat data"""
        data = {}
        
        # Extract name
        name_elem = element.find(class_='p-name')
        if name_elem:
            data['name'] = name_elem.get_text(strip=True)
        
        # Extract ingredients
        ingredients = element.find_all(class_='p-ingredient')
        if ingredients:
            data['ingredients'] = [ing.get_text(strip=True) for ing in ingredients]
        
        # Extract instructions
        instructions = element.find_all(class_='e-instructions')
        if instructions:
            data['instructions'] = [inst.get_text(strip=True) for inst in instructions]
        
        # Extract cooking time
        time_elem = element.find(class_='dt-duration')
        if time_elem:
            data['cooking_time'] = time_elem.get_text(strip=True)
        
        return data
    
    def _extract_h_review(self, element: Tag) -> Dict[str, Any]:
        """Extract h-review microformat data"""
        data = {}
        
        # Extract item reviewed
        item_elem = element.find(class_='p-item')
        if item_elem:
            data['item'] = item_elem.get_text(strip=True)
        
        # Extract rating
        rating_elem = element.find(class_='p-rating')
        if rating_elem:
            data['rating'] = rating_elem.get_text(strip=True)
        
        # Extract review content
        content_elem = element.find(class_='e-content')
        if content_elem:
            data['content'] = content_elem.get_text(strip=True)
        
        # Extract reviewer
        reviewer_elem = element.find(class_='p-reviewer')
        if reviewer_elem:
            data['reviewer'] = reviewer_elem.get_text(strip=True)
        
        return data
    
    def _extract_custom_selectors(self, soup: BeautifulSoup, url: str) -> List[StructuredDataItem]:
        """Extract data using custom CSS selectors"""
        items = []
        
        for selector_name, selector_config in self.custom_selectors.items():
            try:
                selector = selector_config.get('selector')
                data_type = selector_config.get('type', 'Custom')
                
                if not selector:
                    continue
                
                elements = soup.select(selector)
                
                for element in elements:
                    try:
                        # Extract data based on configuration
                        item_data = {}
                        
                        # Extract text content
                        if selector_config.get('extract_text', True):
                            item_data['text'] = element.get_text(strip=True)
                        
                        # Extract attributes
                        attributes = selector_config.get('attributes', [])
                        for attr in attributes:
                            value = element.get(attr)
                            if value:
                                item_data[attr] = value
                        
                        # Extract nested elements
                        nested_selectors = selector_config.get('nested_selectors', {})
                        for key, nested_selector in nested_selectors.items():
                            nested_elements = element.select(nested_selector)
                            if nested_elements:
                                if len(nested_elements) == 1:
                                    item_data[key] = nested_elements[0].get_text(strip=True)
                                else:
                                    item_data[key] = [elem.get_text(strip=True) for elem in nested_elements]
                        
                        if item_data:
                            items.append(StructuredDataItem(
                                type=data_type,
                                data=item_data,
                                source='custom',
                                url=url,
                                selector=selector,
                                confidence=selector_config.get('confidence', 0.8)
                            ))
                            
                    except Exception as e:
                        logger.warning(f"Error extracting custom selector {selector_name}: {e}")
                        continue
                        
            except Exception as e:
                logger.error(f"Error processing custom selector {selector_name}: {e}")
        
        return items
    
    def _extract_property_value(self, element: Tag) -> Any:
        """Extract value from a property element"""
        # Check for content attribute first
        content = element.get('content')
        if content:
            return content
        
        # Check for href attribute
        href = element.get('href')
        if href:
            return href
        
        # Check for src attribute
        src = element.get('src')
        if src:
            return src
        
        # Get text content
        text = element.get_text(strip=True)
        if text:
            return text
        
        return None
    
    def _clean_extracted_data(self, items: List[StructuredDataItem], base_url: str) -> List[StructuredDataItem]:
        """Clean and normalize extracted data"""
        cleaned_items = []
        
        for item in items:
            try:
                cleaned_data = self._clean_data_dict(item.data, base_url)
                
                cleaned_item = StructuredDataItem(
                    type=item.type,
                    data=cleaned_data,
                    source=item.source,
                    url=item.url,
                    selector=item.selector,
                    confidence=item.confidence,
                    validation_errors=item.validation_errors
                )
                
                cleaned_items.append(cleaned_item)
                
            except Exception as e:
                logger.warning(f"Error cleaning item {item.type}: {e}")
                cleaned_items.append(item)
        
        return cleaned_items
    
    def _clean_data_dict(self, data: Dict[str, Any], base_url: str) -> Dict[str, Any]:
        """Clean a data dictionary recursively"""
        cleaned = {}
        
        for key, value in data.items():
            if isinstance(value, dict):
                cleaned[key] = self._clean_data_dict(value, base_url)
            elif isinstance(value, list):
                cleaned[key] = [self._clean_data_dict(item, base_url) if isinstance(item, dict) else item for item in value]
            elif isinstance(value, str):
                cleaned_value = value.strip()
                
                # Normalize URLs
                if self.normalize_urls and self._is_url_field(key):
                    cleaned_value = self._normalize_url(cleaned_value, base_url)
                
                # Clean common issues
                cleaned_value = self._clean_string_value(cleaned_value)
                
                if cleaned_value:
                    cleaned[key] = cleaned_value
            else:
                cleaned[key] = value
        
        return cleaned
    
    def _is_url_field(self, field_name: str) -> bool:
        """Check if a field name suggests it contains a URL"""
        url_indicators = ['url', 'href', 'src', 'link', 'image', 'photo', 'logo', 'icon']
        return any(indicator in field_name.lower() for indicator in url_indicators)
    
    def _normalize_url(self, url: str, base_url: str) -> str:
        """Normalize a URL relative to base URL"""
        if not url:
            return url
        
        try:
            # Handle relative URLs
            if url.startswith('//'):
                parsed_base = urlparse(base_url)
                return f"{parsed_base.scheme}:{url}"
            elif url.startswith('/'):
                return urljoin(base_url, url)
            elif not url.startswith(('http://', 'https://')):
                return urljoin(base_url, url)
            else:
                return url
        except Exception:
            return url
    
    def _clean_string_value(self, value: str) -> str:
        """Clean a string value"""
        if not value:
            return value
        
        # Remove excessive whitespace
        value = re.sub(r'\s+', ' ', value)
        
        # Remove common HTML entities
        value = value.replace('&nbsp;', ' ')
        value = value.replace('&amp;', '&')
        value = value.replace('&lt;', '<')
        value = value.replace('&gt;', '>')
        value = value.replace('&quot;', '"')
        
        return value.strip()
    
    def _validate_extracted_data(self, items: List[StructuredDataItem]) -> List[StructuredDataItem]:
        """Validate extracted data and add validation errors"""
        validated_items = []
        
        for item in items:
            validation_errors = []
            
            try:
                # Validate required fields based on type
                if item.type == 'Product':
                    validation_errors.extend(self._validate_product(item.data))
                elif item.type == 'Article':
                    validation_errors.extend(self._validate_article(item.data))
                elif item.type == 'Event':
                    validation_errors.extend(self._validate_event(item.data))
                elif item.type == 'Organization':
                    validation_errors.extend(self._validate_organization(item.data))
                elif item.type == 'Person':
                    validation_errors.extend(self._validate_person(item.data))
                
                # Validate URLs
                validation_errors.extend(self._validate_urls(item.data))
                
                # Update item with validation errors
                item.validation_errors = validation_errors
                
                # Adjust confidence based on validation
                if validation_errors:
                    item.confidence = max(0.1, item.confidence - len(validation_errors) * 0.1)
                
                validated_items.append(item)
                
            except Exception as e:
                logger.warning(f"Error validating item {item.type}: {e}")
                item.validation_errors.append(f"Validation error: {e}")
                validated_items.append(item)
        
        return validated_items
    
    def _validate_product(self, data: Dict[str, Any]) -> List[str]:
        """Validate product data"""
        errors = []
        
        if not data.get('name'):
            errors.append("Product name is required")
        
        if not data.get('price') and not data.get('offers'):
            errors.append("Product price or offers information is recommended")
        
        return errors
    
    def _validate_article(self, data: Dict[str, Any]) -> List[str]:
        """Validate article data"""
        errors = []
        
        if not data.get('headline') and not data.get('name'):
            errors.append("Article headline or name is required")
        
        if not data.get('author') and not data.get('publisher'):
            errors.append("Article author or publisher is recommended")
        
        return errors
    
    def _validate_event(self, data: Dict[str, Any]) -> List[str]:
        """Validate event data"""
        errors = []
        
        if not data.get('name'):
            errors.append("Event name is required")
        
        if not data.get('startDate') and not data.get('start'):
            errors.append("Event start date is required")
        
        return errors
    
    def _validate_organization(self, data: Dict[str, Any]) -> List[str]:
        """Validate organization data"""
        errors = []
        
        if not data.get('name'):
            errors.append("Organization name is required")
        
        return errors
    
    def _validate_person(self, data: Dict[str, Any]) -> List[str]:
        """Validate person data"""
        errors = []
        
        if not data.get('name'):
            errors.append("Person name is required")
        
        return errors
    
    def _validate_urls(self, data: Dict[str, Any]) -> List[str]:
        """Validate URLs in data"""
        errors = []
        
        def check_urls(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if self._is_url_field(key) and isinstance(value, str):
                        if not validators.url(value):
                            errors.append(f"Invalid URL in field '{key}': {value}")
                    elif isinstance(value, (dict, list)):
                        check_urls(value)
            elif isinstance(obj, list):
                for item in obj:
                    check_urls(item)
        
        check_urls(data)
        return errors
    
    def _calculate_summary(self, items: List[StructuredDataItem]) -> Dict[str, int]:
        """Calculate summary statistics"""
        summary = {
            'total_items': len(items),
            'json_ld': 0,
            'microdata': 0,
            'rdfa': 0,
            'opengraph': 0,
            'twitter': 0,
            'microformat': 0,
            'custom': 0,
            'validated': 0,
            'with_errors': 0
        }
        
        for item in items:
            summary[item.source] += 1
            
            if item.validation_errors:
                summary['with_errors'] += 1
            else:
                summary['validated'] += 1
        
        return summary
    
    def export_structured_data(self, items: List[StructuredDataItem], file_path: str, format: str = "json") -> bool:
        """
        Export structured data to file
        
        Args:
            items: List of structured data items
            file_path: Path to export file
            format: Export format (json, csv)
            
        Returns:
            True if exported successfully
        """
        try:
            if format.lower() == "json":
                return self._export_structured_data_json(items, file_path)
            elif format.lower() == "csv":
                return self._export_structured_data_csv(items, file_path)
            else:
                logger.error(f"Unsupported export format: {format}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to export structured data: {e}")
            return False
    
    def _export_structured_data_json(self, items: List[StructuredDataItem], file_path: str) -> bool:
        """Export structured data as JSON"""
        try:
            export_data = {
                'extraction_time': datetime.now().isoformat(),
                'total_items': len(items),
                'items': [asdict(item) for item in items]
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            logger.info(f"Structured data exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export JSON structured data: {e}")
            return False
    
    def _export_structured_data_csv(self, items: List[StructuredDataItem], file_path: str) -> bool:
        """Export structured data as CSV"""
        try:
            import csv
            
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow(['Type', 'Source', 'URL', 'Selector', 'Confidence', 'Data', 'Validation Errors'])
                
                # Write data
                for item in items:
                    writer.writerow([
                        item.type,
                        item.source,
                        item.url,
                        item.selector or '',
                        item.confidence,
                        json.dumps(item.data, ensure_ascii=False),
                        '; '.join(item.validation_errors) if item.validation_errors else ''
                    ])
            
            logger.info(f"Structured data exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export CSV structured data: {e}")
            return False 