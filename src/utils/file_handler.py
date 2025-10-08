import os
import json
import shutil
import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
import chardet

logger = logging.getLogger(__name__)


class FileHandler:
    """Handles file operations including scanning, reading, and caching."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize FileHandler with configuration.
        
        Args:
            config: Main configuration dictionary
        """
        self.config = config
        self.input_dir = Path(config["paths"]["input_directory"])
        self.output_dir = Path(config["paths"]["output_directory"])
        self.supported_formats = config["processing"]["supported_formats"]
        self.cache_enabled = config["processing"].get("cache_parsed_files", True)
        self.cache_dir = Path(config["paths"].get("cache", "./cache"))
        
        # Create directories if they don't exist
        self._ensure_directories()
        
        # Initialize file cache
        self.file_cache: Dict[str, Any] = {}
        if self.cache_enabled:
            self._load_cache_index()
    
    def _ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        for directory in [self.input_dir, self.output_dir, self.cache_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Ensured directory exists: {directory}")
    
    def scan_input_directory(self) -> List[Path]:
        """
        Scan input directory for supported file formats (only direct children, not subdirectories).

        Returns:
            List of file paths found in input directory
        """
        if not self.input_dir.exists():
            logger.warning(f"Input directory does not exist: {self.input_dir}")
            return []

        files = []
        for ext in self.supported_formats:
            pattern = f"*.{ext}"
            found_files = list(self.input_dir.glob(pattern))
            files.extend(found_files)
            if found_files:
                logger.info(f"Found {len(found_files)} {ext} files")

        # Sort files by modification time (newest first)
        files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        logger.info(f"Total files found: {len(files)}")
        return files
    
    def get_file_info(self, file_path: Path) -> Dict[str, Any]:
        """
        Get detailed information about a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Dictionary containing file information
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        stat = file_path.stat()
        
        # Try to detect encoding for text files
        encoding = None
        if file_path.suffix.lower() in ['.csv', '.txt', '.html']:
            encoding = self._detect_encoding(file_path)
        
        return {
            "name": file_path.name,
            "path": str(file_path.absolute()),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "format": file_path.suffix[1:].lower() if file_path.suffix else "unknown",
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "encoding": encoding,
            "hash": self._calculate_file_hash(file_path)
        }
    
    def _detect_encoding(self, file_path: Path) -> Optional[str]:
        """
        Detect file encoding.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Detected encoding or None
        """
        try:
            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)  # Read first 10KB
                result = chardet.detect(raw_data)
                return result['encoding'] if result['confidence'] > 0.7 else 'utf-8'
        except Exception as e:
            logger.warning(f"Could not detect encoding for {file_path}: {e}")
            return 'utf-8'
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate SHA256 hash of a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            File hash as hex string
        """
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate hash for {file_path}: {e}")
            return ""
    
    def read_file_content(self, file_path: Path, max_size_mb: float = 50) -> Optional[bytes]:
        """
        Read file content with size limit.
        
        Args:
            file_path: Path to the file
            max_size_mb: Maximum file size in MB
            
        Returns:
            File content as bytes or None if file is too large
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None
        
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        
        if file_size_mb > max_size_mb:
            logger.warning(f"File too large ({file_size_mb:.2f} MB): {file_path}")
            return None
        
        try:
            with open(file_path, 'rb') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return None
    
    def save_results(self, results: Dict[str, Any], filename: Optional[str] = None) -> Path:
        """
        Save analysis results to output directory.
        
        Args:
            results: Results dictionary to save
            filename: Optional filename (will be auto-generated if not provided)
            
        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"analysis_results_{timestamp}.json"
        
        # Create subdirectory for current month
        month_dir = self.output_dir / datetime.now().strftime("%Y-%m")
        month_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = month_dir / filename
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Results saved to: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            raise
    
    def archive_processed_file(self, file_path: Path, report_month: Optional[str] = None) -> bool:
        """
        Move processed file to archive directory.

        Args:
            file_path: Path to the file to archive
            report_month: Report month in format "YYYY-MM" (if None, uses current month)

        Returns:
            True if successful, False otherwise
        """
        # Use report month if provided, otherwise fall back to current month
        if report_month:
            archive_subdir = report_month
            logger.info(f"Archiving to report month directory: {report_month}")
        else:
            archive_subdir = datetime.now().strftime("%Y-%m")
            logger.warning(f"No report month provided, using current month for archiving")

        archive_dir = self.input_dir / "archive" / archive_subdir
        archive_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            archive_path = archive_dir / file_path.name
            
            # Add timestamp if file already exists in archive
            if archive_path.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name_parts = file_path.stem, timestamp, file_path.suffix
                archive_path = archive_dir / f"{'_'.join(name_parts[:2])}{name_parts[2]}"
            
            shutil.move(str(file_path), str(archive_path))
            logger.info(f"Archived file to: {archive_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to archive file {file_path}: {e}")
            return False
    
    def get_cached_data(self, file_path: Path, cache_key: str) -> Optional[Any]:
        """
        Get cached data for a file.
        
        Args:
            file_path: Path to the original file
            cache_key: Key identifying the cached data type
            
        Returns:
            Cached data or None if not found/expired
        """
        if not self.cache_enabled:
            return None
        
        file_hash = self._calculate_file_hash(file_path)
        cache_file = self.cache_dir / f"{file_hash}_{cache_key}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            # Check cache age
            cache_age_hours = (datetime.now() - datetime.fromtimestamp(
                cache_file.stat().st_mtime
            )).total_seconds() / 3600
            
            cache_ttl = self.config.get("analysis", {}).get("cache_ttl_hours", 24)
            
            if cache_age_hours > cache_ttl:
                logger.debug(f"Cache expired for {file_path.name}")
                cache_file.unlink()
                return None
            
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Cache hit for {file_path.name}")
                return data
                
        except Exception as e:
            logger.warning(f"Failed to read cache for {file_path}: {e}")
            return None
    
    def set_cached_data(self, file_path: Path, cache_key: str, data: Any) -> bool:
        """
        Save data to cache.
        
        Args:
            file_path: Path to the original file
            cache_key: Key identifying the cached data type
            data: Data to cache
            
        Returns:
            True if successful, False otherwise
        """
        if not self.cache_enabled:
            return False
        
        file_hash = self._calculate_file_hash(file_path)
        cache_file = self.cache_dir / f"{file_hash}_{cache_key}.json"
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            
            logger.debug(f"Cached data for {file_path.name}")
            return True
            
        except Exception as e:
            logger.warning(f"Failed to cache data for {file_path}: {e}")
            return False
    
    def clear_cache(self, older_than_hours: Optional[int] = None) -> int:
        """
        Clear cache files.
        
        Args:
            older_than_hours: Only clear files older than this (None = clear all)
            
        Returns:
            Number of files cleared
        """
        if not self.cache_dir.exists():
            return 0
        
        cleared = 0
        cutoff_time = None
        
        if older_than_hours:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
        
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                if cutoff_time:
                    file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
                    if file_time > cutoff_time:
                        continue
                
                cache_file.unlink()
                cleared += 1
                
            except Exception as e:
                logger.warning(f"Failed to clear cache file {cache_file}: {e}")
        
        logger.info(f"Cleared {cleared} cache files")
        return cleared
    
    def _load_cache_index(self) -> None:
        """Load cache index for faster lookups."""
        index_file = self.cache_dir / "index.json"
        
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    self.file_cache = json.load(f)
            except Exception:
                self.file_cache = {}
    
    def _save_cache_index(self) -> None:
        """Save cache index."""
        if not self.cache_enabled:
            return
        
        index_file = self.cache_dir / "index.json"
        
        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(self.file_cache, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save cache index: {e}")
    
    def validate_input_files(self) -> Dict[str, List[Path]]:
        """
        Validate all input files and group by status.
        
        Returns:
            Dictionary with 'valid' and 'invalid' file lists
        """
        files = self.scan_input_directory()
        
        valid_files = []
        invalid_files = []
        
        for file_path in files:
            try:
                # Check if file is readable
                if not os.access(file_path, os.R_OK):
                    logger.warning(f"File not readable: {file_path}")
                    invalid_files.append(file_path)
                    continue
                
                # Check file size
                if file_path.stat().st_size == 0:
                    logger.warning(f"Empty file: {file_path}")
                    invalid_files.append(file_path)
                    continue
                
                # Check format
                if file_path.suffix[1:].lower() not in self.supported_formats:
                    logger.warning(f"Unsupported format: {file_path}")
                    invalid_files.append(file_path)
                    continue
                
                valid_files.append(file_path)
                
            except Exception as e:
                logger.error(f"Error validating file {file_path}: {e}")
                invalid_files.append(file_path)
        
        return {
            "valid": valid_files,
            "invalid": invalid_files
        }