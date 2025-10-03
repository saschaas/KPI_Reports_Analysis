import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import pandas as pd
from bs4 import BeautifulSoup
import re
from parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)


class HTMLParser(BaseParser):
    """Parser for HTML files containing tables or structured data."""
    
    def __init__(self, encoding: str = 'utf-8'):
        """
        Initialize HTMLParser.
        
        Args:
            encoding: Default encoding for HTML files
        """
        super().__init__(encoding)
        self.soup: Optional[BeautifulSoup] = None
        self.tables: List[pd.DataFrame] = []
    
    def parse(self, file_path: Path, table_index: Optional[int] = None) -> pd.DataFrame:
        """
        Parse HTML file and extract tables as DataFrame.
        
        Args:
            file_path: Path to the HTML file
            table_index: Specific table index to extract (None for largest/best)
            
        Returns:
            DataFrame containing table data
        """
        if not self.validate_file(file_path):
            return pd.DataFrame()
        
        try:
            # Read HTML content
            with open(file_path, 'r', encoding=self.encoding, errors='ignore') as f:
                html_content = f.read()
            
            # Parse with BeautifulSoup
            self.soup = BeautifulSoup(html_content, 'lxml')
            
            # Try pandas HTML reader first (more robust for tables)
            try:
                tables = pd.read_html(str(file_path))
                
                if tables:
                    self.tables = [self.clean_dataframe(df) for df in tables]
                    
                    if table_index is not None and 0 <= table_index < len(self.tables):
                        return self.tables[table_index]
                    
                    # Return largest table
                    largest_table = max(self.tables, key=lambda df: len(df) * len(df.columns))
                    logger.info(f"Found {len(self.tables)} tables, returning largest")
                    return largest_table
                    
            except Exception as e:
                logger.debug(f"Pandas HTML parsing failed, trying BeautifulSoup: {e}")
            
            # Fallback to manual table extraction
            extracted_tables = self._extract_tables_manually()
            
            if extracted_tables:
                self.tables = extracted_tables
                
                if table_index is not None and 0 <= table_index < len(self.tables):
                    return self.tables[table_index]
                
                # Return largest table
                return max(self.tables, key=lambda df: len(df) * len(df.columns))
            
            # If no tables found, try to extract structured data
            return self._extract_structured_data()
            
        except Exception as e:
            logger.error(f"Failed to parse HTML file {file_path}: {e}")
            return pd.DataFrame()
    
    def _extract_tables_manually(self) -> List[pd.DataFrame]:
        """
        Manually extract tables from HTML using BeautifulSoup.
        
        Returns:
            List of DataFrames containing table data
        """
        if not self.soup:
            return []
        
        tables = []
        
        for table_elem in self.soup.find_all('table'):
            try:
                # Extract headers
                headers = []
                header_row = table_elem.find('thead')
                
                if header_row:
                    headers = [th.get_text(strip=True) 
                             for th in header_row.find_all(['th', 'td'])]
                else:
                    # Try to find headers in first row
                    first_row = table_elem.find('tr')
                    if first_row:
                        headers = [cell.get_text(strip=True) 
                                 for cell in first_row.find_all(['th', 'td'])]
                
                # Extract data rows
                rows = []
                tbody = table_elem.find('tbody') or table_elem
                
                for tr in tbody.find_all('tr'):
                    # Skip header row if already processed
                    if tr == table_elem.find('tr') and headers:
                        continue
                    
                    row = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
                    
                    if row:  # Skip empty rows
                        rows.append(row)
                
                # Create DataFrame
                if rows:
                    if headers and len(headers) == len(rows[0]):
                        df = pd.DataFrame(rows, columns=headers)
                    else:
                        df = pd.DataFrame(rows)
                    
                    df = self.clean_dataframe(df)
                    if not df.empty:
                        tables.append(df)
                        
            except Exception as e:
                logger.debug(f"Failed to extract table: {e}")
                continue
        
        return tables
    
    def _extract_structured_data(self) -> pd.DataFrame:
        """
        Extract structured data from HTML when no tables are present.
        
        Returns:
            DataFrame with extracted structured data
        """
        if not self.soup:
            return pd.DataFrame()
        
        data = []
        
        # Try to find definition lists
        for dl in self.soup.find_all('dl'):
            row = {}
            current_key = None
            
            for child in dl.children:
                if child.name == 'dt':
                    current_key = child.get_text(strip=True)
                elif child.name == 'dd' and current_key:
                    row[current_key] = child.get_text(strip=True)
            
            if row:
                data.append(row)
        
        # Try to find lists with consistent structure
        if not data:
            for ul in self.soup.find_all(['ul', 'ol']):
                list_items = []
                for li in ul.find_all('li'):
                    text = li.get_text(strip=True)
                    # Check if it's structured (e.g., "Key: Value")
                    if ':' in text:
                        parts = text.split(':', 1)
                        if len(parts) == 2:
                            list_items.append({
                                'key': parts[0].strip(),
                                'value': parts[1].strip()
                            })
                
                if list_items:
                    data.extend(list_items)
        
        # Try to find divs with consistent class structure
        if not data:
            # Look for repeated patterns
            divs_by_class = {}
            for div in self.soup.find_all('div', class_=True):
                class_name = ' '.join(div.get('class', []))
                if class_name not in divs_by_class:
                    divs_by_class[class_name] = []
                divs_by_class[class_name].append(div)
            
            # Find classes with multiple instances (likely data rows)
            for class_name, divs in divs_by_class.items():
                if len(divs) > 3:  # At least 4 similar divs
                    for div in divs:
                        row_data = self._extract_div_data(div)
                        if row_data:
                            data.append(row_data)
        
        if data:
            return pd.DataFrame(data)
        
        return pd.DataFrame()
    
    def _extract_div_data(self, div) -> Dict[str, str]:
        """
        Extract data from a div element.
        
        Args:
            div: BeautifulSoup div element
            
        Returns:
            Dictionary of extracted data
        """
        data = {}
        
        # Extract text from child elements
        for i, elem in enumerate(div.find_all(['span', 'p', 'div', 'a'])):
            text = elem.get_text(strip=True)
            if text:
                # Try to use class or id as key
                key = elem.get('class', [None])[0] or elem.get('id') or f'field_{i}'
                data[key] = text
        
        return data if len(data) > 1 else {}
    
    def extract_text(self, file_path: Path, max_chars: int = 50000) -> str:
        """
        Extract text content from HTML for LLM processing.
        
        Args:
            file_path: Path to the HTML file
            max_chars: Maximum number of characters to extract
            
        Returns:
            Extracted text content
        """
        if not self.validate_file(file_path):
            return ""
        
        try:
            # Parse if not already done
            if not self.soup:
                with open(file_path, 'r', encoding=self.encoding, errors='ignore') as f:
                    html_content = f.read()
                self.soup = BeautifulSoup(html_content, 'lxml')
            
            # Remove script and style elements
            for script in self.soup(['script', 'style']):
                script.decompose()
            
            # Extract title
            title = self.soup.title.string if self.soup.title else ""
            
            # Extract main content
            text_parts = []
            
            if title:
                text_parts.append(f"Title: {title}\n")
            
            # Extract headings and their content
            for heading_tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                for heading in self.soup.find_all(heading_tag):
                    text_parts.append(f"\n{heading_tag.upper()}: {heading.get_text(strip=True)}")
            
            # Extract table data
            if self.tables:
                text_parts.append("\n\nTables found:")
                for i, table in enumerate(self.tables):
                    text_parts.append(f"\nTable {i + 1}:")
                    text_parts.append(f"Columns: {', '.join(table.columns.astype(str))}")
                    text_parts.append(f"Rows: {len(table)}")
                    
                    # Add sample rows
                    for idx, row in table.head(5).iterrows():
                        row_text = " | ".join(str(val) for val in row.values)
                        text_parts.append(row_text)
            
            # Extract paragraph text
            paragraphs = self.soup.find_all('p')
            if paragraphs:
                text_parts.append("\n\nContent:")
                for p in paragraphs[:50]:  # Limit to first 50 paragraphs
                    text = p.get_text(strip=True)
                    if text:
                        text_parts.append(text)
            
            # Extract list items
            lists = self.soup.find_all(['ul', 'ol'])
            if lists:
                text_parts.append("\n\nList items:")
                for list_elem in lists[:10]:  # Limit to first 10 lists
                    for li in list_elem.find_all('li')[:20]:  # Limit items
                        text_parts.append(f"• {li.get_text(strip=True)}")
            
            result = "\n".join(text_parts)
            return result[:max_chars]
            
        except Exception as e:
            logger.error(f"Failed to extract text from HTML: {e}")
            return ""
    
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from HTML file.
        
        Args:
            file_path: Path to the HTML file
            
        Returns:
            Dictionary containing HTML metadata
        """
        metadata = super().get_metadata(file_path)
        
        try:
            if not self.soup:
                with open(file_path, 'r', encoding=self.encoding, errors='ignore') as f:
                    html_content = f.read()
                self.soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract meta tags
            meta_info = {}
            for meta in self.soup.find_all('meta'):
                name = meta.get('name') or meta.get('property')
                content = meta.get('content')
                
                if name and content:
                    meta_info[name] = content
            
            metadata.update({
                "title": self.soup.title.string if self.soup.title else None,
                "meta_tags": meta_info,
                "table_count": len(self.soup.find_all('table')),
                "form_count": len(self.soup.find_all('form')),
                "link_count": len(self.soup.find_all('a')),
                "image_count": len(self.soup.find_all('img')),
                "has_javascript": bool(self.soup.find_all('script')),
                "has_css": bool(self.soup.find_all(['style', 'link'])),
                "encoding": self.soup.original_encoding if hasattr(self.soup, 'original_encoding') else self.encoding
            })
            
            # Extract structured data (JSON-LD)
            json_ld_scripts = self.soup.find_all('script', type='application/ld+json')
            if json_ld_scripts:
                structured_data = []
                for script in json_ld_scripts:
                    try:
                        import json
                        data = json.loads(script.string)
                        structured_data.append(data)
                    except Exception:
                        pass
                
                if structured_data:
                    metadata["structured_data"] = structured_data
            
            # Add table statistics if parsed
            if self.tables:
                metadata["table_stats"] = []
                for i, table in enumerate(self.tables):
                    metadata["table_stats"].append({
                        "index": i,
                        "rows": len(table),
                        "columns": len(table.columns),
                        "column_names": list(table.columns)
                    })
            
        except Exception as e:
            logger.debug(f"Could not extract HTML metadata: {e}")
        
        return metadata
    
    def extract_links(self) -> List[Dict[str, str]]:
        """
        Extract all links from HTML.
        
        Returns:
            List of dictionaries containing link information
        """
        if not self.soup:
            return []
        
        links = []
        
        for a in self.soup.find_all('a', href=True):
            links.append({
                "text": a.get_text(strip=True),
                "href": a['href'],
                "title": a.get('title', '')
            })
        
        return links
    
    def extract_forms(self) -> List[Dict[str, Any]]:
        """
        Extract form information from HTML.
        
        Returns:
            List of dictionaries containing form data
        """
        if not self.soup:
            return []
        
        forms = []
        
        for form in self.soup.find_all('form'):
            form_data = {
                "action": form.get('action', ''),
                "method": form.get('method', 'get').upper(),
                "name": form.get('name', ''),
                "id": form.get('id', ''),
                "fields": []
            }
            
            # Extract form fields
            for input_elem in form.find_all(['input', 'select', 'textarea']):
                field = {
                    "type": input_elem.get('type', 'text'),
                    "name": input_elem.get('name', ''),
                    "id": input_elem.get('id', ''),
                    "required": input_elem.has_attr('required'),
                    "value": input_elem.get('value', '')
                }
                form_data["fields"].append(field)
            
            forms.append(form_data)
        
        return forms