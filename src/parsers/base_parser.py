from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Abstract base class for file parsers."""
    
    def __init__(self, encoding: str = 'utf-8'):
        """
        Initialize BaseParser.
        
        Args:
            encoding: Default encoding for text files
        """
        self.encoding = encoding
        self.metadata: Dict[str, Any] = {}
    
    @abstractmethod
    def parse(self, file_path: Path) -> pd.DataFrame:
        """
        Parse file and return structured data as DataFrame.
        
        Args:
            file_path: Path to the file to parse
            
        Returns:
            DataFrame containing structured data
        """
        pass
    
    @abstractmethod
    def extract_text(self, file_path: Path, max_chars: int = 50000) -> str:
        """
        Extract text content from file for LLM processing.
        
        Args:
            file_path: Path to the file
            max_chars: Maximum number of characters to extract
            
        Returns:
            Extracted text content
        """
        pass
    
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary containing file metadata
        """
        stat = file_path.stat()
        
        self.metadata = {
            "name": file_path.name,
            "filename": file_path.name,
            "path": str(file_path.absolute()),
            "size_bytes": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime),
            "modified": datetime.fromtimestamp(stat.st_mtime),
            "format": file_path.suffix[1:].lower(),
            "parser": self.__class__.__name__
        }
        
        return self.metadata
    
    def validate_file(self, file_path: Path) -> bool:
        """
        Validate if file can be parsed.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file is valid, False otherwise
        """
        if not file_path.exists():
            logger.error(f"File does not exist: {file_path}")
            return False
        
        if file_path.stat().st_size == 0:
            logger.error(f"File is empty: {file_path}")
            return False
        
        if not file_path.is_file():
            logger.error(f"Path is not a file: {file_path}")
            return False
        
        return True
    
    def extract_columns(self, df: pd.DataFrame) -> List[str]:
        """
        Extract column names from DataFrame.
        
        Args:
            df: DataFrame to extract columns from
            
        Returns:
            List of column names
        """
        if df is None or df.empty:
            return []
        
        return list(df.columns)
    
    def extract_sample_data(self, df: pd.DataFrame, rows: int = 5) -> Dict[str, Any]:
        """
        Extract sample data from DataFrame.
        
        Args:
            df: DataFrame to sample from
            rows: Number of rows to sample
            
        Returns:
            Dictionary containing sample data
        """
        if df is None or df.empty:
            return {"sample": [], "row_count": 0, "column_count": 0}
        
        sample = df.head(rows).to_dict(orient='records')
        
        return {
            "sample": sample,
            "row_count": len(df),
            "column_count": len(df.columns),
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()}
        }
    
    def clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and standardize DataFrame.
        
        Args:
            df: DataFrame to clean
            
        Returns:
            Cleaned DataFrame
        """
        if df is None or df.empty:
            return df
        
        # Remove completely empty rows
        df = df.dropna(how='all')
        
        # Remove completely empty columns
        df = df.dropna(axis=1, how='all')
        
        # Strip whitespace from string columns
        for col in df.columns:
            if df[col].dtype == 'object':
                try:
                    df[col] = df[col].str.strip()
                except (AttributeError, TypeError):
                    pass
        
        # Reset index
        df = df.reset_index(drop=True)
        
        return df
    
    def detect_date_columns(self, df: pd.DataFrame) -> List[str]:
        """
        Detect columns that likely contain date values.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            List of column names likely containing dates
        """
        date_columns = []
        
        for col in df.columns:
            # Check column name for date indicators
            col_lower = col.lower()
            if any(keyword in col_lower for keyword in 
                   ['date', 'datum', 'time', 'zeit', 'created', 'modified', 'timestamp']):
                date_columns.append(col)
                continue
            
            # Try to parse as date
            if df[col].dtype == 'object':
                try:
                    pd.to_datetime(df[col].dropna().head(10), errors='coerce')
                    non_null_parsed = pd.to_datetime(df[col].dropna().head(10), 
                                                    errors='coerce').notna().sum()
                    if non_null_parsed >= 5:  # At least half should parse as dates
                        date_columns.append(col)
                except Exception:
                    pass
        
        return date_columns
    
    def convert_dates(self, df: pd.DataFrame, date_columns: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Convert date columns to datetime objects.
        
        Args:
            df: DataFrame with date columns
            date_columns: List of columns to convert (auto-detect if None)
            
        Returns:
            DataFrame with converted date columns
        """
        if date_columns is None:
            date_columns = self.detect_date_columns(df)
        
        # NOTE: Do NOT auto-convert dates here! Let the analyzer handle date parsing
        # with the correct format (DD/MM/YYYY vs MM/DD/YYYY). Auto-parsing often
        # misinterprets European dates as American format.
        # for col in date_columns:
        #     if col in df.columns:
        #         try:
        #             df[col] = pd.to_datetime(df[col], errors='coerce')
        #             logger.debug(f"Converted column {col} to datetime")
        #         except Exception as e:
        #             logger.warning(f"Failed to convert column {col} to datetime: {e}")
        
        return df
    
    def safe_parse(self, file_path: Path) -> Optional[pd.DataFrame]:
        """
        Safely parse file with error handling.
        
        Args:
            file_path: Path to the file to parse
            
        Returns:
            DataFrame or None if parsing fails
        """
        try:
            if not self.validate_file(file_path):
                return None
            
            df = self.parse(file_path)
            
            if df is not None:
                df = self.clean_dataframe(df)
                df = self.convert_dates(df)
                self.get_metadata(file_path)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to parse {file_path}: {e}")
            return None
    
    def get_summary_stats(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get summary statistics for DataFrame.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Dictionary containing summary statistics
        """
        if df is None or df.empty:
            return {}
        
        stats = {
            "row_count": len(df),
            "column_count": len(df.columns),
            "memory_usage_bytes": df.memory_usage(deep=True).sum(),
            "null_counts": df.isnull().sum().to_dict(),
            "duplicate_rows": df.duplicated().sum()
        }
        
        # Add numeric column statistics
        numeric_cols = df.select_dtypes(include=['number']).columns
        if len(numeric_cols) > 0:
            stats["numeric_stats"] = {}
            for col in numeric_cols:
                stats["numeric_stats"][col] = {
                    "mean": float(df[col].mean()) if pd.notna(df[col].mean()) else None,
                    "min": float(df[col].min()) if pd.notna(df[col].min()) else None,
                    "max": float(df[col].max()) if pd.notna(df[col].max()) else None,
                    "std": float(df[col].std()) if pd.notna(df[col].std()) else None
                }
        
        return stats