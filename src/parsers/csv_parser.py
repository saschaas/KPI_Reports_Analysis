import logging
import csv
from pathlib import Path
from typing import Dict, Any, Optional, List
import pandas as pd
import chardet
from parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)


class CSVParser(BaseParser):
    """Parser for CSV files."""
    
    def __init__(self, encoding: str = 'utf-8'):
        """
        Initialize CSVParser.
        
        Args:
            encoding: Default encoding for CSV files
        """
        super().__init__(encoding)
        self.delimiter: Optional[str] = None
        self.detected_encoding: Optional[str] = None
    
    def parse(self, file_path: Path, delimiter: Optional[str] = None,
             encoding: Optional[str] = None) -> pd.DataFrame:
        """
        Parse CSV file and return DataFrame.

        Args:
            file_path: Path to the CSV file
            delimiter: CSV delimiter (auto-detect if None)
            encoding: File encoding (auto-detect if None)

        Returns:
            DataFrame containing CSV data
        """
        logger.info(f"CSVParser.parse() called for {file_path.name}")
        logger.info(f"Parameters: delimiter={delimiter}, encoding={encoding}")

        if not self.validate_file(file_path):
            logger.warning(f"File validation failed for {file_path.name}")
            return pd.DataFrame()

        try:
            # Detect encoding if not provided
            if not encoding:
                logger.info("Detecting encoding...")
                encoding = self._detect_encoding(file_path)
                self.detected_encoding = encoding
                logger.info(f"Detected encoding: {encoding}")

            # Detect delimiter if not provided
            if not delimiter:
                logger.info("Detecting delimiter...")
                delimiter = self._detect_delimiter(file_path, encoding)
                self.delimiter = delimiter
                logger.info(f"Detected delimiter: {repr(delimiter)}")

            # Try to parse CSV with various strategies
            df = self._parse_with_fallback(file_path, delimiter, encoding)
            
            if df is not None and not df.empty:
                # Clean the DataFrame
                df = self.clean_dataframe(df)
                
                # Try to infer better data types
                df = self._infer_dtypes(df)
                
                logger.info(f"Successfully parsed CSV: {len(df)} rows, {len(df.columns)} columns")
                return df
            
            return pd.DataFrame()
            
        except Exception as e:
            logger.error(f"Failed to parse CSV file {file_path}: {e}")
            return pd.DataFrame()
    
    def _detect_encoding(self, file_path: Path) -> str:
        """
        Detect file encoding using chardet.

        Args:
            file_path: Path to the CSV file

        Returns:
            Detected encoding
        """
        try:
            with open(file_path, 'rb') as f:
                # Read first 10KB for detection
                raw_data = f.read(10000)

                # Check for UTF-8 BOM
                if raw_data.startswith(b'\xef\xbb\xbf'):
                    logger.info("Detected UTF-8 BOM, using utf-8-sig encoding")
                    return 'utf-8-sig'

                result = chardet.detect(raw_data)

                if result['confidence'] > 0.7:
                    detected = result['encoding']
                    # Handle common encoding aliases
                    if detected.lower() in ['ascii', 'iso-8859-1']:
                        return 'latin-1'
                    return detected

        except Exception as e:
            logger.debug(f"Encoding detection failed: {e}")

        # Default fallback chain
        return 'utf-8'
    
    def _detect_delimiter(self, file_path: Path, encoding: str) -> str:
        """
        Detect CSV delimiter using csv.Sniffer.

        Args:
            file_path: Path to the CSV file
            encoding: File encoding to use

        Returns:
            Detected delimiter
        """
        # List of common delimiters to validate against
        common_delimiters = [',', ';', '\t', '|', ':']

        try:
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                # Read sample for detection
                sample = f.read(8192)
                sniffer = csv.Sniffer()
                delimiter = sniffer.sniff(sample).delimiter

                # Validate that Sniffer found a common delimiter
                if delimiter in common_delimiters:
                    logger.info(f"Sniffer detected valid delimiter: {repr(delimiter)}")
                    return delimiter
                else:
                    logger.info(f"Sniffer detected unusual delimiter {repr(delimiter)}, using fallback method")

        except Exception as e:
            logger.info(f"Delimiter detection with Sniffer failed: {e}, using fallback method")

        # Fallback: Count common delimiters in first line
        try:
            with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                first_line = f.readline()

                # Count occurrences of each delimiter
                delimiter_counts = {}
                for delim in common_delimiters:
                    delimiter_counts[delim] = first_line.count(delim)

                logger.info(f"Delimiter counts in first line: {delimiter_counts}")

                # Return delimiter with highest count
                if delimiter_counts:
                    best_delimiter = max(delimiter_counts, key=delimiter_counts.get)
                    if delimiter_counts[best_delimiter] > 0:
                        logger.info(f"Selected delimiter: {repr(best_delimiter)} (count: {delimiter_counts[best_delimiter]})")
                        return best_delimiter

        except Exception as e:
            logger.warning(f"Fallback delimiter detection failed: {e}")

        # Default to comma
        logger.info("Using default delimiter: comma")
        return ','
    
    def _parse_with_fallback(self, file_path: Path, delimiter: str,
                           encoding: str) -> Optional[pd.DataFrame]:
        """
        Parse CSV with multiple fallback strategies.

        Args:
            file_path: Path to the CSV file
            delimiter: CSV delimiter
            encoding: File encoding

        Returns:
            DataFrame or None if all strategies fail
        """
        logger.info(f"Starting CSV parsing with delimiter={repr(delimiter)}, encoding={encoding}")

        strategies = [
            # Strategy 1: Standard parsing
            lambda: pd.read_csv(file_path, sep=delimiter, encoding=encoding),

            # Strategy 2: With error handling
            lambda: pd.read_csv(file_path, sep=delimiter, encoding=encoding,
                              on_bad_lines='skip'),

            # Strategy 3: Different encoding
            lambda: pd.read_csv(file_path, sep=delimiter, encoding='latin-1',
                              on_bad_lines='skip'),

            # Strategy 4: No header
            lambda: pd.read_csv(file_path, sep=delimiter, encoding=encoding,
                              header=None, on_bad_lines='skip'),

            # Strategy 5: Different quote character
            lambda: pd.read_csv(file_path, sep=delimiter, encoding=encoding,
                              quotechar='"', on_bad_lines='skip'),

            # Strategy 6: Python engine (slower but more flexible)
            lambda: pd.read_csv(file_path, sep=delimiter, encoding=encoding,
                              engine='python', on_bad_lines='skip')
        ]

        for i, strategy in enumerate(strategies, 1):
            try:
                logger.info(f"Trying strategy {i}...")
                df = strategy()
                if df is not None and not df.empty:
                    logger.info(f"✓ Strategy {i} succeeded: {len(df)} rows, {len(df.columns)} columns")
                    logger.info(f"Column names: {list(df.columns)[:5]}..." if len(df.columns) > 5 else f"Column names: {list(df.columns)}")
                    return df
            except Exception as e:
                logger.info(f"✗ Strategy {i} failed: {e}")
                continue

        logger.error("All parsing strategies failed")
        return None
    
    def _infer_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Try to infer better data types for DataFrame columns.
        
        Args:
            df: DataFrame to process
            
        Returns:
            DataFrame with inferred types
        """
        for col in df.columns:
            # Skip if already numeric
            if pd.api.types.is_numeric_dtype(df[col]):
                continue
            
            # Try to convert to numeric
            try:
                # Remove common formatting characters
                cleaned = df[col].astype(str).str.replace(',', '').str.replace(' ', '')
                numeric = pd.to_numeric(cleaned, errors='coerce')
                
                # If more than 50% converted successfully, use numeric
                if numeric.notna().sum() > len(df) * 0.5:
                    df[col] = numeric
                    continue
            except Exception:
                pass
            
            # Try to convert to datetime
            try:
                if any(keyword in str(col).lower() 
                      for keyword in ['date', 'datum', 'time', 'zeit']):
                    datetime_col = pd.to_datetime(df[col], errors='coerce')
                    
                    # If more than 50% converted successfully, use datetime
                    if datetime_col.notna().sum() > len(df) * 0.5:
                        df[col] = datetime_col
            except Exception:
                pass
        
        return df
    
    def extract_text(self, file_path: Path, max_chars: int = 50000) -> str:
        """
        Extract text content from CSV for LLM processing.
        
        Args:
            file_path: Path to the CSV file
            max_chars: Maximum number of characters to extract
            
        Returns:
            Extracted text content
        """
        if not self.validate_file(file_path):
            return ""
        
        try:
            # Parse if not already done
            df = self.parse(file_path)
            
            if df.empty:
                return ""
            
            text_parts = []
            
            # Add header information
            text_parts.append(f"CSV File: {file_path.name}")
            text_parts.append(f"Columns ({len(df.columns)}): {', '.join(df.columns.astype(str))}")
            text_parts.append(f"Rows: {len(df)}")
            text_parts.append("")
            
            # Add sample data
            sample_size = min(100, len(df))
            text_parts.append(f"First {sample_size} rows:")
            
            for idx, row in df.head(sample_size).iterrows():
                row_text = " | ".join(f"{col}: {val}" for col, val in row.items())
                text_parts.append(f"Row {idx + 1}: {row_text}")
                
                # Check size limit
                current_text = "\n".join(text_parts)
                if len(current_text) >= max_chars:
                    break
            
            # Add summary statistics for numeric columns
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                text_parts.append("\nNumeric column statistics:")
                for col in numeric_cols:
                    stats = f"{col}: min={df[col].min():.2f}, max={df[col].max():.2f}, mean={df[col].mean():.2f}"
                    text_parts.append(stats)
            
            result = "\n".join(text_parts)
            return result[:max_chars]
            
        except Exception as e:
            logger.error(f"Failed to extract text from CSV: {e}")
            return ""
    
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from CSV file.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            Dictionary containing CSV metadata
        """
        metadata = super().get_metadata(file_path)
        
        try:
            # Add CSV-specific metadata
            metadata.update({
                "delimiter": self.delimiter or "unknown",
                "detected_encoding": self.detected_encoding or self.encoding,
                "file_encoding": self.encoding
            })
            
            # Parse to get data statistics
            df = self.parse(file_path)
            
            if not df.empty:
                metadata.update({
                    "row_count": len(df),
                    "column_count": len(df.columns),
                    "columns": list(df.columns),
                    "has_header": self._has_header(file_path),
                    "memory_usage_bytes": df.memory_usage(deep=True).sum(),
                    "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()}
                })
                
                # Check for common issues
                issues = []
                
                # Check for unnamed columns
                unnamed_cols = [col for col in df.columns if 'Unnamed' in str(col)]
                if unnamed_cols:
                    issues.append(f"Found {len(unnamed_cols)} unnamed columns")
                
                # Check for duplicate columns
                duplicate_cols = df.columns[df.columns.duplicated()].tolist()
                if duplicate_cols:
                    issues.append(f"Found duplicate column names: {duplicate_cols}")
                
                # Check for high null percentage
                null_percentages = (df.isnull().sum() / len(df) * 100)
                high_null_cols = null_percentages[null_percentages > 50].index.tolist()
                if high_null_cols:
                    issues.append(f"Columns with >50% null values: {high_null_cols}")
                
                if issues:
                    metadata["data_issues"] = issues
            
        except Exception as e:
            logger.debug(f"Could not extract CSV metadata: {e}")
        
        return metadata
    
    def _has_header(self, file_path: Path) -> bool:
        """
        Detect if CSV file has a header row.
        
        Args:
            file_path: Path to the CSV file
            
        Returns:
            True if file likely has header
        """
        try:
            # Read first two rows
            df_with_header = pd.read_csv(file_path, nrows=2)
            df_without_header = pd.read_csv(file_path, header=None, nrows=2)
            
            # Check if first row values are significantly different from data
            first_row = df_without_header.iloc[0]
            
            # Count how many values in first row are strings
            string_count = sum(1 for val in first_row if isinstance(val, str))
            
            # If most values are strings, likely a header
            return string_count > len(first_row) * 0.7
            
        except Exception:
            return True  # Default assume header exists
    
    def validate_structure(self, df: pd.DataFrame) -> List[str]:
        """
        Validate CSV structure and return list of issues.
        
        Args:
            df: DataFrame to validate
            
        Returns:
            List of validation issues
        """
        issues = []
        
        if df.empty:
            issues.append("DataFrame is empty")
            return issues
        
        # Check for reasonable dimensions
        if len(df.columns) > 1000:
            issues.append(f"Unusually high number of columns: {len(df.columns)}")
        
        if len(df) > 1000000:
            issues.append(f"Very large file: {len(df)} rows")
        
        # Check for completely empty columns
        empty_cols = df.columns[df.isnull().all()].tolist()
        if empty_cols:
            issues.append(f"Completely empty columns: {empty_cols}")
        
        # Check for single column (might be wrong delimiter)
        if len(df.columns) == 1 and self.delimiter == ',':
            issues.append("Only one column detected - might be wrong delimiter")
        
        return issues