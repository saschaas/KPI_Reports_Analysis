import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
import pandas as pd

from utils import ConfigLoader
from parsers import PDFParser, ExcelParser, CSVParser, HTMLParser
from core.llm_handler import OllamaHandler

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    """Result of report type detection."""
    report_type: str
    report_name: str
    confidence: float
    detection_method: str  # 'filename', 'content', 'llm', 'manual'
    matched_patterns: List[str]
    report_config: Dict[str, Any]


class ReportDetector:
    """Detects report type using a 3-stage process."""
    
    def __init__(self, config_loader: ConfigLoader, llm_handler: Optional[OllamaHandler] = None):
        """
        Initialize ReportDetector.
        
        Args:
            config_loader: Configuration loader instance
            llm_handler: Optional Ollama handler for LLM classification
        """
        self.config_loader = config_loader
        self.llm_handler = llm_handler
        self.report_configs = config_loader.load_all_report_configs()
        
        # Parser mapping
        self.parsers = {
            'pdf': PDFParser(),
            'xlsx': ExcelParser(),
            'xls': ExcelParser(),
            'csv': CSVParser(),
            'html': HTMLParser()
        }
        
        logger.info(f"Loaded {len(self.report_configs)} report configurations")
    
    def detect(self, file_path: Path) -> Optional[DetectionResult]:
        """
        Detect report type using 3-stage process.
        
        Args:
            file_path: Path to the file to detect
            
        Returns:
            Detection result or None if detection failed
        """
        logger.info(f"Starting detection for: {file_path.name}")
        
        # Stage 1: Filename matching
        result = self._match_filename(file_path)
        if result:
            logger.info(f"Detected via filename: {result.report_type}")
            return result
        
        # Stage 2: Content matching
        result = self._match_content(file_path)
        if result:
            logger.info(f"Detected via content: {result.report_type}")
            return result
        
        # Stage 3: LLM classification
        if self.llm_handler and self.llm_handler.is_available():
            result = self._classify_with_llm(file_path)
            if result:
                logger.info(f"Detected via LLM: {result.report_type}")
                return result
        
        # Stage 4: Manual selection (user interaction)
        result = self._manual_selection(file_path)
        if result:
            logger.info(f"Detected via manual selection: {result.report_type}")
            return result
        
        logger.warning(f"Could not detect report type for: {file_path.name}")
        return None
    
    def _match_filename(self, file_path: Path) -> Optional[DetectionResult]:
        """
        Match filename against configured patterns (Stage 1).
        
        Args:
            file_path: Path to the file
            
        Returns:
            Detection result or None
        """
        filename = file_path.name
        
        for report_id, config in self.report_configs.items():
            if not config.get('report_type', {}).get('enabled', True):
                continue
            
            identification = config.get('identification', {})
            patterns = identification.get('filename_patterns', [])
            
            for pattern in patterns:
                try:
                    if re.match(pattern, filename, re.IGNORECASE):
                        logger.debug(f"Filename matched pattern '{pattern}' for {report_id}")
                        
                        return DetectionResult(
                            report_type=report_id,
                            report_name=config['report_type']['name'],
                            confidence=0.95,
                            detection_method='filename',
                            matched_patterns=[pattern],
                            report_config=config
                        )
                except re.error as e:
                    logger.error(f"Invalid regex pattern '{pattern}': {e}")
        
        return None
    
    def _match_content(self, file_path: Path) -> Optional[DetectionResult]:
        """
        Match file content against configured identifiers (Stage 2).
        
        Args:
            file_path: Path to the file
            
        Returns:
            Detection result or None
        """
        # Parse file to get content
        file_format = file_path.suffix[1:].lower()
        
        if file_format not in self.parsers:
            logger.warning(f"No parser available for format: {file_format}")
            return None
        
        try:
            parser = self.parsers[file_format]
            df = parser.safe_parse(file_path)
            text_content = parser.extract_text(file_path, max_chars=10000)
            
            if df is None and not text_content:
                logger.warning(f"Could not extract content from {file_path.name}")
                return None
            
            # Get columns if DataFrame available
            columns = list(df.columns) if df is not None and not df.empty else []
            
            # Check each report configuration
            scores = {}
            
            for report_id, config in self.report_configs.items():
                if not config.get('report_type', {}).get('enabled', True):
                    continue
                
                identification = config.get('identification', {})
                content_identifiers = identification.get('content_identifiers', {})
                
                if not content_identifiers:
                    continue
                
                score, matched = self._calculate_content_score(
                    columns, text_content, content_identifiers
                )
                
                if score > 0:
                    scores[report_id] = (score, matched, config)
            
            # Return best match if above threshold
            if scores:
                best_match = max(scores.items(), key=lambda x: x[1][0])
                report_id, (score, matched, config) = best_match
                
                min_matches = config['identification']['content_identifiers'].get('min_matches', 2)
                
                if score >= min_matches:
                    return DetectionResult(
                        report_type=report_id,
                        report_name=config['report_type']['name'],
                        confidence=min(0.9, score / (min_matches + 2)),
                        detection_method='content',
                        matched_patterns=matched,
                        report_config=config
                    )
            
        except Exception as e:
            logger.error(f"Content matching failed for {file_path.name}: {e}")
        
        return None
    
    def _calculate_content_score(self, columns: List[str], text: str, 
                                identifiers: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        Calculate content matching score.
        
        Args:
            columns: List of column names
            text: Text content
            identifiers: Content identifiers configuration
            
        Returns:
            Tuple of (score, matched patterns)
        """
        score = 0
        matched = []
        
        # Check required columns
        required_cols = identifiers.get('required_columns', [])
        for col in required_cols:
            if any(col.lower() in c.lower() for c in columns):
                score += 2  # Higher weight for required columns
                matched.append(f"column:{col}")
        
        # Check optional columns
        optional_cols = identifiers.get('optional_columns', [])
        for col in optional_cols:
            if any(col.lower() in c.lower() for c in columns):
                score += 1
                matched.append(f"optional_column:{col}")
        
        # Check required keywords in text
        required_keywords = identifiers.get('required_keywords', [])
        text_lower = text.lower()
        
        for keyword in required_keywords:
            if keyword.lower() in text_lower:
                score += 1.5
                matched.append(f"keyword:{keyword}")
        
        # Check optional keywords
        optional_keywords = identifiers.get('optional_keywords', [])
        for keyword in optional_keywords:
            if keyword.lower() in text_lower:
                score += 0.5
                matched.append(f"optional_keyword:{keyword}")
        
        return score, matched
    
    def _classify_with_llm(self, file_path: Path) -> Optional[DetectionResult]:
        """
        Classify using LLM (Stage 3).
        
        Args:
            file_path: Path to the file
            
        Returns:
            Detection result or None
        """
        if not self.llm_handler:
            return None
        
        # Extract content for LLM
        file_format = file_path.suffix[1:].lower()
        
        if file_format not in self.parsers:
            return None
        
        try:
            parser = self.parsers[file_format]
            text_content = parser.extract_text(file_path, max_chars=5000)
            
            if not text_content:
                return None
            
            # Try each report configuration with LLM
            for report_id, config in self.report_configs.items():
                if not config.get('report_type', {}).get('enabled', True):
                    continue
                
                llm_config = config.get('identification', {}).get('llm_classification', {})
                
                if not llm_config.get('enabled', False):
                    continue
                
                prompt = llm_config.get('prompt', '')
                if not prompt:
                    continue
                
                # Classify with LLM
                response = self.llm_handler.classify(
                    text_content,
                    prompt,
                    options=['JA', 'NEIN', 'YES', 'NO']
                )
                
                if response.error:
                    logger.error(f"LLM classification error: {response.error}")
                    continue
                
                # Check response
                answer = response.content.upper()
                
                if 'JA' in answer or 'YES' in answer:
                    confidence_threshold = llm_config.get('confidence_threshold', 0.7)
                    
                    if response.confidence >= confidence_threshold:
                        return DetectionResult(
                            report_type=report_id,
                            report_name=config['report_type']['name'],
                            confidence=response.confidence,
                            detection_method='llm',
                            matched_patterns=[f"LLM classification: {response.content}"],
                            report_config=config
                        )
            
        except Exception as e:
            logger.error(f"LLM classification failed for {file_path.name}: {e}")
        
        return None
    
    def _manual_selection(self, file_path: Path) -> Optional[DetectionResult]:
        """
        Manual report type selection by user (Stage 4).
        
        Args:
            file_path: Path to the file
            
        Returns:
            Detection result or None
        """
        print(f"\n=== Manual Report Type Selection ===")
        print(f"File: {file_path.name}")
        
        # Show file preview
        self._show_file_preview(file_path)
        
        # List available report types
        print("\nAvailable report types:")
        report_list = []
        
        for report_id, config in self.report_configs.items():
            if config.get('report_type', {}).get('enabled', True):
                report_list.append((report_id, config))
                print(f"{len(report_list)}. {config['report_type']['name']}")
                print(f"   Description: {config['report_type'].get('description', 'N/A')}")
        
        print(f"{len(report_list) + 1}. Skip this file")
        print(f"{len(report_list) + 2}. Mark as unknown type")
        
        # Get user input
        try:
            choice = input("\nSelect report type (enter number): ").strip()
            
            if not choice.isdigit():
                return None
            
            choice_num = int(choice)
            
            if choice_num == len(report_list) + 1:
                # Skip file
                return None
            elif choice_num == len(report_list) + 2:
                # Mark as unknown
                return DetectionResult(
                    report_type='unknown',
                    report_name='Unknown Report Type',
                    confidence=1.0,
                    detection_method='manual',
                    matched_patterns=['User marked as unknown'],
                    report_config={}
                )
            elif 1 <= choice_num <= len(report_list):
                # Valid report type selection
                report_id, config = report_list[choice_num - 1]
                
                return DetectionResult(
                    report_type=report_id,
                    report_name=config['report_type']['name'],
                    confidence=1.0,
                    detection_method='manual',
                    matched_patterns=['User manual selection'],
                    report_config=config
                )
            
        except (ValueError, KeyboardInterrupt):
            pass
        
        return None
    
    def _show_file_preview(self, file_path: Path) -> None:
        """
        Show preview of file content for manual identification.
        
        Args:
            file_path: Path to the file
        """
        file_format = file_path.suffix[1:].lower()
        
        if file_format not in self.parsers:
            print(f"Cannot preview format: {file_format}")
            return
        
        try:
            parser = self.parsers[file_format]
            
            # Get structured data
            df = parser.safe_parse(file_path)
            
            if df is not None and not df.empty:
                print(f"\nFile structure:")
                print(f"- Format: {file_format.upper()}")
                print(f"- Rows: {len(df)}")
                print(f"- Columns: {len(df.columns)}")
                print(f"\nColumn names:")
                for i, col in enumerate(df.columns[:20], 1):
                    print(f"  {i}. {col}")
                
                if len(df.columns) > 20:
                    print(f"  ... and {len(df.columns) - 20} more columns")
                
                print(f"\nFirst 3 rows:")
                print(df.head(3).to_string(max_cols=5, max_colwidth=20))
            
            # Get text preview
            text = parser.extract_text(file_path, max_chars=1000)
            
            if text:
                print(f"\nText preview (first 500 chars):")
                print("-" * 40)
                print(text[:500])
                print("-" * 40)
                
                # Extract potential keywords
                keywords = self._extract_keywords(text)
                if keywords:
                    print(f"\nDetected keywords: {', '.join(keywords[:10])}")
            
        except Exception as e:
            print(f"Preview generation failed: {e}")
    
    def _extract_keywords(self, text: str) -> List[str]:
        """
        Extract potential keywords from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of keywords
        """
        # Common report-related keywords
        keyword_patterns = [
            r'\b(bericht|report)\b',
            r'\b(monat|month)\b',
            r'\b(jahr|year|20\d{2})\b',
            r'\b(backup|sicherung)\b',
            r'\b(server|host|system)\b',
            r'\b(fehler|error|problem)\b',
            r'\b(status|zustand|state)\b',
            r'\b(transaktion|transaction)\b',
            r'\b(summe|total|gesamt)\b',
            r'\b(datum|date|zeit|time)\b'
        ]
        
        keywords = set()
        text_lower = text.lower()
        
        for pattern in keyword_patterns:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            keywords.update(matches)
        
        return sorted(list(keywords))
    
    def reload_configs(self) -> None:
        """Reload report configurations."""
        self.report_configs = self.config_loader.load_all_report_configs()
        logger.info(f"Reloaded {len(self.report_configs)} report configurations")