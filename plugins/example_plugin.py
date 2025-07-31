"""
Example Plugin for Scrapelillo Pro
Demonstrates how to create custom plugins for domain-specific parsing.
"""

PLUGIN_NAME = "Example Plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Example plugin demonstrating custom parsing and filtering"


def register_parsers(plugin_manager):
    """Register custom parsers for specific domains."""
    
    def parse_news_site(html, url):
        """Parse news website structure."""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, 'lxml')
        
        # Extract news articles
        articles = []
        for article in soup.find_all(['article', 'div'], class_=lambda x: x and 'article' in x.lower()):
            title_elem = article.find(['h1', 'h2', 'h3'])
            title = title_elem.get_text(strip=True) if title_elem else ''
            
            content_elem = article.find(['p', 'div'], class_=lambda x: x and 'content' in x.lower())
            content = content_elem.get_text(strip=True) if content_elem else ''
            
            if title or content:
                articles.append({
                    'title': title,
                    'content': content,
                    'url': url
                })
        
        return {
            'type': 'news_articles',
            'articles': articles,
            'count': len(articles)
        }
    
    def parse_ecommerce_site(html, url):
        """Parse e-commerce website structure."""
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, 'lxml')
        
        # Extract products
        products = []
        for product in soup.find_all(['div', 'article'], class_=lambda x: x and 'product' in x.lower()):
            name_elem = product.find(['h1', 'h2', 'h3', 'h4'])
            name = name_elem.get_text(strip=True) if name_elem else ''
            
            price_elem = product.find(class_=lambda x: x and 'price' in x.lower())
            price = price_elem.get_text(strip=True) if price_elem else ''
            
            if name:
                products.append({
                    'name': name,
                    'price': price,
                    'url': url
                })
        
        return {
            'type': 'products',
            'products': products,
            'count': len(products)
        }
    
    # Register parsers for specific domains
    plugin_manager.register_parser('news.example.com', parse_news_site)
    plugin_manager.register_parser('shop.example.com', parse_ecommerce_site)


def register_filters(plugin_manager):
    """Register custom filters."""
    
    def filter_duplicates(data, key_field='title'):
        """Filter out duplicate entries based on a key field."""
        if not isinstance(data, list):
            return data
        
        seen = set()
        filtered = []
        
        for item in data:
            key = item.get(key_field, '')
            if key not in seen:
                seen.add(key)
                filtered.append(item)
        
        return filtered
    
    def filter_by_length(data, min_length=10):
        """Filter items by minimum text length."""
        if not isinstance(data, list):
            return data
        
        return [item for item in data if len(str(item.get('content', ''))) >= min_length]
    
    # Register filters
    plugin_manager.register_filter('remove_duplicates', filter_duplicates)
    plugin_manager.register_filter('min_length', filter_by_length)


def register_exporters(plugin_manager):
    """Register custom exporters."""
    
    def export_to_markdown(data, filepath, **kwargs):
        """Export data to Markdown format."""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                if isinstance(data, list):
                    for i, item in enumerate(data, 1):
                        f.write(f"# {i}. {item.get('title', 'Untitled')}\n\n")
                        f.write(f"{item.get('content', '')}\n\n")
                        f.write(f"URL: {item.get('url', '')}\n\n")
                        f.write("---\n\n")
                else:
                    f.write(f"# {data.get('title', 'Data Export')}\n\n")
                    f.write(f"{data.get('content', '')}\n")
            
            return True
        except Exception as e:
            logger.info(f"Error exporting to Markdown: {e}")
            return False
    
    def export_to_xml(data, filepath, **kwargs):
        """Export data to XML format."""
        try:
            import xml.etree.ElementTree as ET
            
            root = ET.Element('data')
            
            if isinstance(data, list):
                for item in data:
                    item_elem = ET.SubElement(root, 'item')
                    title_elem = ET.SubElement(item_elem, 'title')
                    title_elem.text = item.get('title', '')
                    content_elem = ET.SubElement(item_elem, 'content')
                    content_elem.text = item.get('content', '')
                    url_elem = ET.SubElement(item_elem, 'url')
                    url_elem.text = item.get('url', '')
            else:
                title_elem = ET.SubElement(root, 'title')
                title_elem.text = data.get('title', '')
                content_elem = ET.SubElement(root, 'content')
                content_elem.text = data.get('content', '')
            
            tree = ET.ElementTree(root)
            tree.write(filepath, encoding='utf-8', xml_declaration=True)
            
            return True
        except Exception as e:
            logger.info(f"Error exporting to XML: {e}")
            return False
    
    # Register exporters
    plugin_manager.register_exporter('markdown', export_to_markdown)
    plugin_manager.register_exporter('xml', export_to_xml) 