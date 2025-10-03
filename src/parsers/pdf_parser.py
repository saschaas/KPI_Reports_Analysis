import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import pandas as pd
import pdfplumber
from PyPDF2 import PdfReader
import re
from parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """Parser for PDF files."""
    
    def __init__(self, encoding: str = 'utf-8'):
        """
        Initialize PDFParser.
        
        Args:
            encoding: Default encoding (not used for PDFs but kept for compatibility)
        """
        super().__init__(encoding)
        self.tables: List[pd.DataFrame] = []
    
    def parse(self, file_path: Path) -> pd.DataFrame:
        """
        Parse PDF file and extract tables as DataFrame.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            DataFrame containing merged tables or text data
        """
        if not self.validate_file(file_path):
            return pd.DataFrame()
        
        try:
            # Try to extract tables using pdfplumber
            tables = self._extract_tables_pdfplumber(file_path)
            
            if tables:
                # Merge all tables into one DataFrame
                df = self._merge_tables(tables)
                self.tables = tables
                logger.info(f"Extracted {len(tables)} tables from PDF")
                return df
            
            # If no tables found, try to extract structured text
            logger.info("No tables found in PDF, extracting text data")
            return self._extract_text_as_dataframe(file_path)
            
        except Exception as e:
            logger.error(f"Failed to parse PDF {file_path}: {e}")
            return pd.DataFrame()
    
    def _extract_tables_pdfplumber(self, file_path: Path) -> List[pd.DataFrame]:
        """
        Extract tables from PDF using pdfplumber with intelligent header detection.
        Handles multi-page reports where first page has header and subsequent pages continue the data.

        Args:
            file_path: Path to the PDF file

        Returns:
            List of DataFrames containing table data
        """
        tables = []
        detected_header = None  # Store header from first page for continuation pages

        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract tables from page
                    page_tables = page.extract_tables()

                    for table_num, table in enumerate(page_tables or [], 1):
                        if table and len(table) > 0:
                            try:
                                # On first page, detect the header
                                if detected_header is None:
                                    header_idx = self._detect_header_row(table)

                                    if header_idx < len(table) - 1:  # Ensure we have data rows after header
                                        detected_header = table[header_idx]
                                        data_rows = table[header_idx + 1:]
                                        logger.info(f"Header detected on page {page_num} at row {header_idx}")
                                    else:
                                        logger.debug(f"No valid header found for table on page {page_num}")
                                        continue
                                else:
                                    # Continuation page - check if this is data continuation
                                    # If first row looks like data (not a header), use stored header
                                    first_row_score = self._score_as_header(table[0])

                                    # Also check if detected_header would match the full header scan
                                    full_scan_header_idx = self._detect_header_row(table)
                                    full_scan_header_score = self._score_as_header(table[full_scan_header_idx]) if full_scan_header_idx < len(table) else 0

                                    # If the "best header" score is significantly lower than the original header,
                                    # this is likely a continuation page with data only
                                    if full_scan_header_score < 150:  # Header threshold
                                        # This is a continuation page - all rows are data
                                        data_rows = table
                                        logger.info(f"Page {page_num}: Continuation page detected (score {full_scan_header_score:.1f} < 150), using stored header")
                                    else:
                                        # This page has its own header
                                        if full_scan_header_idx < len(table) - 1:
                                            detected_header = table[full_scan_header_idx]
                                            data_rows = table[full_scan_header_idx + 1:]
                                            logger.info(f"Page {page_num}: New header detected at row {full_scan_header_idx} (score {full_scan_header_score:.1f})")
                                        else:
                                            continue

                                if detected_header:
                                    # Handle column count mismatch (common in multi-page PDFs)
                                    header_cols = len(detected_header)

                                    # Find which column is missing by checking non-None header values
                                    # Continuation pages often skip empty columns
                                    non_none_header_indices = [i for i, h in enumerate(detected_header) if h]

                                    # Pad or trim data rows to match header column count
                                    normalized_rows = []
                                    for row in data_rows:
                                        if len(row) < header_cols:
                                            # If row has fewer columns, we need to figure out which column is missing
                                            # For now, insert empty value at the first None-header position
                                            normalized_row = list(row)

                                            # Find indices with None headers (these are likely the missing columns)
                                            none_header_indices = [i for i, h in enumerate(detected_header) if not h]

                                            # Insert empty strings at None-header positions
                                            for missing_idx in none_header_indices:
                                                if missing_idx <= len(normalized_row):
                                                    normalized_row.insert(missing_idx, '')

                                            # If still not enough columns, pad at the end
                                            if len(normalized_row) < header_cols:
                                                normalized_row += [''] * (header_cols - len(normalized_row))

                                            # Trim if too long
                                            normalized_row = normalized_row[:header_cols]
                                        elif len(row) > header_cols:
                                            # Trim excess columns
                                            normalized_row = row[:header_cols]
                                        else:
                                            normalized_row = row
                                        normalized_rows.append(normalized_row)

                                    # Convert to DataFrame
                                    df = pd.DataFrame(normalized_rows, columns=detected_header)

                                    # Add metadata
                                    df['_page'] = page_num
                                    df['_table'] = table_num

                                    # Clean the DataFrame
                                    df = self._clean_table_dataframe(df)

                                    if not df.empty:
                                        logger.info(f"Extracted {len(df)} rows from page {page_num}")
                                        tables.append(df)

                            except Exception as e:
                                logger.error(f"Failed to process table on page {page_num}: {e}")

        except Exception as e:
            logger.error(f"Failed to extract tables with pdfplumber: {e}")

        return tables
    
    def _score_as_header(self, row: List) -> float:
        """
        Score a single row to determine if it looks like a header.

        Args:
            row: Single row to score

        Returns:
            Score value (higher = more likely to be a header)
        """
        # Common header keywords (case-insensitive)
        header_keywords = {
            'name', 'id', 'date', 'time', 'status', 'type', 'description',
            'total', 'count', 'amount', 'value', 'start', 'stop', 'end',
            'job', 'task', 'vm', 'machine', 'server', 'client', 'user',
            'result', 'state', 'duration', 'size', 'gb', 'mb', 'speed',
            'details', 'info', 'processed', 'backup', 'report'
        }

        score = 0
        non_empty_count = 0
        numeric_count = 0
        keyword_count = 0
        text_length = 0

        for cell in row:
            if cell and str(cell).strip():
                cell_str = str(cell).strip()
                non_empty_count += 1
                text_length += len(cell_str)

                # Check if cell is mostly numeric
                if re.match(r'^[\d\s\.,:\-/]+$', cell_str):
                    numeric_count += 1

                # Check for header keywords
                cell_lower = cell_str.lower()
                if any(keyword in cell_lower for keyword in header_keywords):
                    keyword_count += 1

        # Calculate score based on heuristics
        if non_empty_count > 0:
            # More non-empty cells is better
            score += non_empty_count * 10

            # Less numeric cells is better (headers are usually text)
            numeric_ratio = numeric_count / non_empty_count
            score += (1 - numeric_ratio) * 20

            # More keywords is better
            keyword_ratio = keyword_count / non_empty_count
            score += keyword_ratio * 30

            # Moderate text length is better (not too short, not too long)
            avg_text_length = text_length / non_empty_count
            if 3 <= avg_text_length <= 30:
                score += 15

        return score

    def _detect_header_row(self, table: List[List]) -> int:
        """
        Intelligently detect which row is the actual header in a table.

        Uses multiple heuristics:
        1. Row with most non-empty cells
        2. Row with least numeric values (headers are usually text)
        3. Row with common header keywords
        4. Row with highest text diversity

        Args:
            table: Raw table data as list of lists

        Returns:
            Index of the most likely header row
        """
        if not table or len(table) < 2:
            return 0

        scores = []

        # Analyze each row (limit to first 10 rows for performance)
        for idx, row in enumerate(table[:min(10, len(table))]):
            score = self._score_as_header(row)

            # Penalize very first row if it has very few cells (often title)
            non_empty_count = sum(1 for cell in row if cell and str(cell).strip())
            if idx == 0 and non_empty_count < len(row) * 0.5:
                score -= 20

            logger.debug(f"Row {idx}: score={score:.1f}")
            scores.append((idx, score))

        # Return the row with highest score
        if scores:
            best_idx = max(scores, key=lambda x: x[1])[0]
            logger.info(f"Header detected at row {best_idx} (score: {scores[best_idx][1]:.1f})")
            return best_idx

        return 0  # Default to first row if no clear winner

    def _clean_table_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean extracted table DataFrame.
        
        Args:
            df: Raw DataFrame from table extraction
            
        Returns:
            Cleaned DataFrame
        """
        # Remove None values in column names
        df.columns = [col if col else f"Column_{i}" 
                     for i, col in enumerate(df.columns)]
        
        # Replace None values with empty strings
        df = df.fillna('')
        
        # Remove completely empty rows
        df = df.replace('', pd.NA).dropna(how='all').fillna('')
        
        # Strip whitespace
        for col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].str.strip()
        
        # Remove metadata columns if they're all the same
        if '_page' in df.columns and df['_page'].nunique() == 1:
            self.metadata['source_page'] = df['_page'].iloc[0]
            df = df.drop('_page', axis=1)
        
        if '_table' in df.columns and df['_table'].nunique() == 1:
            self.metadata['source_table'] = df['_table'].iloc[0]
            df = df.drop('_table', axis=1)
        
        return df
    
    def _merge_tables(self, tables: List[pd.DataFrame]) -> pd.DataFrame:
        """
        Merge multiple tables into one DataFrame.

        Strategy:
        1. Group tables by identical column sets
        2. For multi-page reports, merge all tables with same structure
        3. Return the largest merged group (most data)

        Args:
            tables: List of DataFrames to merge

        Returns:
            Merged DataFrame with all data from matching tables
        """
        if not tables:
            return pd.DataFrame()

        if len(tables) == 1:
            return tables[0]

        # Group tables by column structure
        merged_groups = {}

        for table in tables:
            # Create a key based on column names (sorted for consistency)
            col_key = tuple(sorted(table.columns.tolist()))

            if col_key not in merged_groups:
                merged_groups[col_key] = []

            merged_groups[col_key].append(table)

        logger.info(f"Found {len(merged_groups)} different table structures across {len(tables)} tables")

        # Merge tables within each group
        final_tables = []
        for col_key, group_tables in merged_groups.items():
            if len(group_tables) == 1:
                final_tables.append(group_tables[0])
                logger.debug(f"Single table with {len(group_tables[0])} rows")
            else:
                # Concatenate all tables with same structure (multi-page data)
                merged = pd.concat(group_tables, ignore_index=True)
                final_tables.append(merged)
                logger.info(f"Merged {len(group_tables)} tables into {len(merged)} rows")

        # Return the largest merged group (contains most data)
        if len(final_tables) > 1:
            largest = max(final_tables, key=len)
            logger.warning(f"Multiple table structures found. Using largest with {len(largest)} rows")
            return largest

        return final_tables[0] if final_tables else pd.DataFrame()
    
    def _extract_text_as_dataframe(self, file_path: Path) -> pd.DataFrame:
        """
        Extract text from PDF and try to structure it as DataFrame.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            DataFrame with structured text data
        """
        try:
            text = self.extract_text(file_path)
            
            # Try to identify structured data in text
            lines = text.split('\n')
            
            # Look for tabular data patterns
            data_lines = []
            for line in lines:
                # Skip empty lines
                if not line.strip():
                    continue
                
                # Check if line contains multiple data points (separated by spaces/tabs)
                parts = re.split(r'\s{2,}|\t', line.strip())
                if len(parts) > 1:
                    data_lines.append(parts)
            
            if data_lines:
                # Try to identify header
                if len(data_lines) > 1:
                    # Assume first line is header if it has the same number of columns
                    max_cols = max(len(line) for line in data_lines)
                    
                    # Pad lines to have same number of columns
                    padded_lines = []
                    for line in data_lines:
                        padded = line + [''] * (max_cols - len(line))
                        padded_lines.append(padded)
                    
                    # Create DataFrame
                    df = pd.DataFrame(padded_lines[1:], columns=padded_lines[0])
                    return self.clean_dataframe(df)
            
            # If no structured data found, return text as single column DataFrame
            return pd.DataFrame({'text': [line.strip() for line in lines if line.strip()]})
            
        except Exception as e:
            logger.error(f"Failed to extract text as DataFrame: {e}")
            return pd.DataFrame()
    
    def extract_text(self, file_path: Path, max_chars: int = 50000) -> str:
        """
        Extract text content from PDF for LLM processing.
        
        Args:
            file_path: Path to the PDF file
            max_chars: Maximum number of characters to extract
            
        Returns:
            Extracted text content
        """
        if not self.validate_file(file_path):
            return ""
        
        text = ""
        
        # Try PyPDF2 first (faster)
        try:
            reader = PdfReader(file_path)
            for page_num, page in enumerate(reader.pages):
                if len(text) >= max_chars:
                    break
                
                page_text = page.extract_text()
                if page_text:
                    text += f"\n--- Page {page_num + 1} ---\n{page_text}"
            
            if text:
                return text[:max_chars]
                
        except Exception as e:
            logger.debug(f"PyPDF2 extraction failed, trying pdfplumber: {e}")
        
        # Fallback to pdfplumber (better for complex PDFs)
        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    if len(text) >= max_chars:
                        break
                    
                    page_text = page.extract_text()
                    if page_text:
                        text += f"\n--- Page {page_num + 1} ---\n{page_text}"
            
            return text[:max_chars]
            
        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            return ""
    
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from PDF file.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Dictionary containing PDF metadata
        """
        metadata = super().get_metadata(file_path)
        
        try:
            reader = PdfReader(file_path)
            
            metadata.update({
                "page_count": len(reader.pages),
                "pdf_version": reader.pdf_header if hasattr(reader, 'pdf_header') else None,
                "encrypted": reader.is_encrypted if hasattr(reader, 'is_encrypted') else False
            })
            
            # Extract document info if available
            if reader.metadata:
                info = reader.metadata
                metadata["pdf_metadata"] = {
                    "title": info.get('/Title', ''),
                    "author": info.get('/Author', ''),
                    "subject": info.get('/Subject', ''),
                    "creator": info.get('/Creator', ''),
                    "producer": info.get('/Producer', ''),
                    "creation_date": str(info.get('/CreationDate', '')),
                    "modification_date": str(info.get('/ModDate', ''))
                }
            
            # Add table count if tables were extracted
            if hasattr(self, 'tables'):
                metadata["table_count"] = len(self.tables)
                
        except Exception as e:
            logger.debug(f"Could not extract PDF metadata: {e}")
        
        return metadata
    
    def extract_images_count(self, file_path: Path) -> int:
        """
        Count number of images in PDF.
        
        Args:
            file_path: Path to the PDF file
            
        Returns:
            Number of images found
        """
        image_count = 0
        
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    if hasattr(page, 'images'):
                        image_count += len(page.images or [])
                        
        except Exception as e:
            logger.debug(f"Could not count images: {e}")
        
        return image_count