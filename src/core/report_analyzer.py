import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import pandas as pd

from utils import RiskScorer, CheckResult, ScoreResult
from parsers import PDFParser, ExcelParser, CSVParser, HTMLParser
from core.llm_handler import OllamaHandler
from core.report_detector import DetectionResult
from analyzers import VeeamBackupAnalyzer, KeeepitBackupAnalyzer, EntraDevicesAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Complete analysis result for a report."""
    file_info: Dict[str, Any]
    report_type: str
    result_status: str
    risk_level: str
    score: float
    analysis_details: Dict[str, Any]
    extracted_data: Dict[str, Any]
    processing_info: Dict[str, Any]
    timestamp: str


class ReportAnalyzer:
    """Analyzes reports using hybrid algorithmic/LLM approach."""

    def __init__(self, llm_handler: Optional[OllamaHandler] = None):
        """
        Initialize ReportAnalyzer.

        Args:
            llm_handler: Optional Ollama handler for LLM fallback
        """
        self.llm_handler = llm_handler

        # Parser mapping
        self.parsers = {
            'pdf': PDFParser(),
            'xlsx': ExcelParser(),
            'xls': ExcelParser(),
            'csv': CSVParser(),
            'html': HTMLParser(),
            'htm': HTMLParser()
        }

        # Report-specific analyzers
        self.analyzers = {
            'veeam_backup': VeeamBackupAnalyzer,
            'keepit_backup': KeeepitBackupAnalyzer,
            'entra_devices': EntraDevicesAnalyzer
        }
    
    def analyze(self, file_path: Path, detection_result: DetectionResult) -> AnalysisResult:
        """
        Analyze a report file using hybrid approach.
        
        Args:
            file_path: Path to the report file
            detection_result: Result from report detection
            
        Returns:
            Complete analysis result
        """
        start_time = time.time()
        
        logger.info(f"Starting analysis of {file_path.name} as {detection_result.report_type}")
        
        try:
            # Primary: Algorithmic analysis
            result = self._algorithmic_analysis(file_path, detection_result)
            
            if result and result.analysis_details.get('method') == 'algorithmic':
                logger.info("Analysis completed using algorithmic method")
                return result
            
        except Exception as e:
            logger.warning(f"Algorithmic analysis failed: {e}")
        
        # Fallback: LLM analysis
        if self.llm_handler and self.llm_handler.is_available():
            try:
                result = self._llm_analysis(file_path, detection_result)
                
                if result:
                    logger.info("Analysis completed using LLM fallback")
                    return result
                    
            except Exception as e:
                logger.error(f"LLM analysis failed: {e}")
        
        # Create failed result
        processing_time = time.time() - start_time
        
        return self._create_failed_result(
            file_path, 
            detection_result,
            "Analysis failed with both methods",
            processing_time
        )
    
    def _algorithmic_analysis(self, file_path: Path, 
                            detection_result: DetectionResult) -> Optional[AnalysisResult]:
        """
        Perform algorithmic analysis of the report.
        
        Args:
            file_path: Path to the report file
            detection_result: Detection result with configuration
            
        Returns:
            Analysis result or None if failed
        """
        start_time = time.time()
        
        # Parse file
        file_format = file_path.suffix[1:].lower()
        
        if file_format not in self.parsers:
            logger.error(f"No parser available for format: {file_format}")
            return None
        
        parser = self.parsers[file_format]
        df = parser.safe_parse(file_path)
        
        if df is None or df.empty:
            logger.warning(f"Could not parse file or file is empty: {file_path.name}")
            return None
        
        # Get analysis configuration
        config = detection_result.report_config
        analysis_config = config.get('analysis', {})
        report_type = detection_result.report_type

        logger.info(f"***** report_type={report_type}, available analyzers={list(self.analyzers.keys())} *****")

        # Check if report-specific analyzer exists
        if report_type in self.analyzers:
            logger.info(f"Using report-specific analyzer for {report_type}")
            analyzer_class = self.analyzers[report_type]
            analyzer = analyzer_class(config)

            # Use analyzer's methods
            checks = analyzer.run_checks(df)
            extracted_data = analyzer.extract_fields(df)

            # Calculate score
            score_result = analyzer.scorer.calculate(checks, extracted_data)
        else:
            # Fallback to generic algorithmic checks
            logger.info(f"Using generic algorithmic checks for {report_type}")
            checks = self._run_algorithmic_checks(df, analysis_config)
            extracted_data = self._extract_fields(df, analysis_config)

            # Calculate score
            scorer = RiskScorer(analysis_config.get('scoring', {}))
            score_result = scorer.calculate(checks, extracted_data)
        
        # Get file info
        file_info = parser.get_metadata(file_path)
        
        processing_time = time.time() - start_time
        
        return AnalysisResult(
            file_info=file_info,
            report_type=detection_result.report_type,
            result_status=score_result.status.value,
            risk_level=score_result.risk_level.value,
            score=score_result.score,
            analysis_details={
                'method': 'algorithmic',
                'checks_performed': len(checks),
                'checks_passed': sum(1 for c in checks if c.passed),
                'checks_failed': sum(1 for c in checks if not c.passed),
                'issues': [c.message for c in checks if not c.passed and c.message],
                'warnings': [],
                'score_details': score_result.deduction_details
            },
            extracted_data=extracted_data,
            processing_info={
                'processing_time_seconds': round(processing_time, 2),
                'retry_count': 0,
                'parser_used': parser.__class__.__name__,
                'data_shape': f"{len(df)} rows x {len(df.columns)} columns"
            },
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ')
        )
    
    def _run_algorithmic_checks(self, df: pd.DataFrame, 
                              analysis_config: Dict[str, Any]) -> List[CheckResult]:
        """
        Run configured algorithmic checks on the data.
        
        Args:
            df: DataFrame containing parsed data
            analysis_config: Analysis configuration
            
        Returns:
            List of check results
        """
        checks = []
        algorithmic_checks = analysis_config.get('algorithmic_checks', [])
        
        for check_config in algorithmic_checks:
            check_id = check_config.get('check_id', 'unknown')
            check_name = check_config.get('name', check_id)
            check_type = check_config.get('type', 'unknown')
            parameters = check_config.get('parameters', {})
            
            try:
                if check_type == 'column_validation':
                    result = self._check_column_validation(df, parameters)
                elif check_type == 'threshold':
                    result = self._check_threshold(df, parameters)
                elif check_type == 'date_validation':
                    result = self._check_date_validation(df, parameters)
                elif check_type == 'data_quality':
                    result = self._check_data_quality(df, parameters)
                else:
                    result = CheckResult(
                        check_id=check_id,
                        name=check_name,
                        passed=False,
                        severity='low',
                        message=f"Unknown check type: {check_type}"
                    )
                
                result.check_id = check_id
                result.name = check_name
                checks.append(result)
                
            except Exception as e:
                logger.error(f"Check {check_id} failed: {e}")
                checks.append(CheckResult(
                    check_id=check_id,
                    name=check_name,
                    passed=False,
                    severity='high',
                    message=f"Check execution failed: {str(e)}"
                ))
        
        return checks
    
    def _check_column_validation(self, df: pd.DataFrame, 
                               parameters: Dict[str, Any]) -> CheckResult:
        """Check if required columns are present."""
        required_columns = parameters.get('required_columns', [])
        severity = parameters.get('severity', 'medium')
        
        missing_columns = []
        
        for required_col in required_columns:
            # Check for exact match (case-insensitive)
            if not any(required_col.lower() == col.lower() for col in df.columns):
                # Check for partial match
                if not any(required_col.lower() in col.lower() for col in df.columns):
                    missing_columns.append(required_col)
        
        passed = len(missing_columns) == 0
        
        return CheckResult(
            check_id='column_validation',
            name='Column Validation',
            passed=passed,
            severity=severity,
            message=f"Missing columns: {missing_columns}" if missing_columns else None,
            details={'missing_columns': missing_columns, 'required_columns': required_columns},
            points_deducted=len(missing_columns) * 5 if not passed else 0
        )
    
    def _check_threshold(self, df: pd.DataFrame, 
                        parameters: Dict[str, Any]) -> CheckResult:
        """Check if values exceed threshold."""
        column = parameters.get('column')
        value = parameters.get('value')
        max_count = parameters.get('max_count', 0)
        max_percentage = parameters.get('max_percentage', 0)
        severity = parameters.get('severity', 'medium')
        
        if column not in df.columns:
            return CheckResult(
                check_id='threshold',
                name='Threshold Check',
                passed=False,
                severity='high',
                message=f"Column '{column}' not found"
            )
        
        # Count occurrences
        if pd.api.types.is_numeric_dtype(df[column]):
            # Numeric threshold
            count = (df[column] > value).sum()
        else:
            # String matching
            count = (df[column].astype(str) == str(value)).sum()
        
        percentage = (count / len(df)) * 100 if len(df) > 0 else 0
        
        # Check thresholds
        passed = True
        if max_count > 0 and count > max_count:
            passed = False
        if max_percentage > 0 and percentage > max_percentage:
            passed = False
        
        return CheckResult(
            check_id='threshold',
            name='Threshold Check',
            passed=passed,
            severity=severity,
            message=f"Found {count} occurrences ({percentage:.1f}%)" if not passed else None,
            details={'count': int(count), 'percentage': percentage},
            points_deducted=count if not passed else 0
        )
    
    def _check_date_validation(self, df: pd.DataFrame, 
                             parameters: Dict[str, Any]) -> CheckResult:
        """Check date column validity."""
        column = parameters.get('column')
        check_continuity = parameters.get('check_continuity', False)
        severity = parameters.get('severity', 'low')
        
        if column not in df.columns:
            return CheckResult(
                check_id='date_validation',
                name='Date Validation',
                passed=False,
                severity='high',
                message=f"Date column '{column}' not found"
            )
        
        # Try to convert to datetime
        try:
            date_series = pd.to_datetime(df[column], errors='coerce')
            null_dates = date_series.isnull().sum()
            valid_dates = len(date_series) - null_dates
            
            passed = null_dates == 0
            message = None
            
            if null_dates > 0:
                message = f"{null_dates} invalid dates found"
            
            # Check continuity if requested
            if check_continuity and valid_dates > 1:
                date_range = date_series.dropna().sort_values()
                gaps = date_range.diff().dt.days
                large_gaps = (gaps > 7).sum()  # Gaps larger than 7 days
                
                if large_gaps > 0:
                    passed = False
                    message = f"Found {large_gaps} date gaps > 7 days"
            
            return CheckResult(
                check_id='date_validation',
                name='Date Validation',
                passed=passed,
                severity=severity,
                message=message,
                details={'valid_dates': int(valid_dates), 'invalid_dates': int(null_dates)},
                points_deducted=null_dates if not passed else 0
            )
            
        except Exception as e:
            return CheckResult(
                check_id='date_validation',
                name='Date Validation',
                passed=False,
                severity='high',
                message=f"Date validation failed: {str(e)}"
            )
    
    def _check_data_quality(self, df: pd.DataFrame, 
                          parameters: Dict[str, Any]) -> CheckResult:
        """Check general data quality."""
        severity = parameters.get('severity', 'medium')
        
        issues = []
        
        # Check for excessive null values
        null_percentage = (df.isnull().sum().sum() / (len(df) * len(df.columns))) * 100
        if null_percentage > 50:
            issues.append(f"High null values: {null_percentage:.1f}%")
        
        # Check for duplicate rows
        duplicate_count = df.duplicated().sum()
        if duplicate_count > len(df) * 0.1:  # More than 10% duplicates
            issues.append(f"Many duplicate rows: {duplicate_count}")
        
        # Check for empty string values
        if df.select_dtypes(include=['object']).shape[1] > 0:
            empty_strings = (df.select_dtypes(include=['object']) == '').sum().sum()
            if empty_strings > len(df) * 0.2:
                issues.append(f"Many empty strings: {empty_strings}")
        
        passed = len(issues) == 0
        
        return CheckResult(
            check_id='data_quality',
            name='Data Quality Check',
            passed=passed,
            severity=severity,
            message='; '.join(issues) if issues else None,
            details={'issues': issues},
            points_deducted=len(issues) * 2 if not passed else 0
        )
    
    def _extract_fields(self, df: pd.DataFrame, 
                       analysis_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract defined fields from the data.
        
        Args:
            df: DataFrame containing parsed data
            analysis_config: Analysis configuration
            
        Returns:
            Dictionary with extracted field values
        """
        extracted = {}
        extraction_fields = analysis_config.get('extraction_fields', [])
        
        for field_config in extraction_fields:
            field_name = field_config.get('field', 'unknown')
            field_type = field_config.get('type', 'count')
            source = field_config.get('source', 'all_rows')
            required = field_config.get('required', False)
            default_value = field_config.get('default')
            
            try:
                if field_type == 'count':
                    if source == 'all_rows':
                        value = len(df)
                    else:
                        # Evaluate condition
                        value = self._evaluate_condition(df, source)
                
                elif field_type == 'sum':
                    column = source
                    if column in df.columns:
                        value = df[column].sum()
                    else:
                        value = default_value or 0
                
                elif field_type == 'calculated':
                    formula = field_config.get('formula', '')
                    value = self._calculate_formula(formula, extracted, df)
                
                else:
                    value = default_value
                
                # Apply formatting
                format_type = field_config.get('format', 'raw')
                value = self._format_value(value, format_type)
                
                extracted[field_name] = value
                
            except Exception as e:
                logger.error(f"Field extraction failed for {field_name}: {e}")
                
                if required:
                    extracted[field_name] = default_value
                else:
                    extracted[field_name] = None
        
        return extracted
    
    def _evaluate_condition(self, df: pd.DataFrame, condition: str) -> int:
        """Evaluate a condition string against DataFrame."""
        try:
            # Simple condition evaluation
            if '==' in condition:
                column, value = condition.split('==')
                column = column.strip().strip('"\'')
                value = value.strip().strip('"\'')
                
                if column in df.columns:
                    return (df[column].astype(str) == value).sum()
            
            elif '>' in condition:
                column, value = condition.split('>')
                column = column.strip()
                value = float(value.strip())
                
                if column in df.columns:
                    return (df[column] > value).sum()
            
            elif '<' in condition:
                column, value = condition.split('<')
                column = column.strip()
                value = float(value.strip())
                
                if column in df.columns:
                    return (df[column] < value).sum()
            
        except Exception as e:
            logger.debug(f"Condition evaluation failed: {e}")
        
        return 0
    
    def _calculate_formula(self, formula: str, extracted: Dict[str, Any], 
                          df: pd.DataFrame) -> Any:
        """Calculate a formula using extracted data."""
        try:
            # Replace field names with their values
            for field, value in extracted.items():
                if value is not None:
                    formula = formula.replace(field, str(value))
            
            # Basic arithmetic evaluation (be careful with eval!)
            # Only allow basic operations for security
            allowed_chars = set('0123456789+-*/().% ')
            
            if all(c in allowed_chars for c in formula):
                result = eval(formula)
                return result
            
        except Exception as e:
            logger.debug(f"Formula calculation failed: {e}")
        
        return None
    
    def _format_value(self, value: Any, format_type: str) -> Any:
        """Format a value according to the specified type."""
        if value is None:
            return None
        
        try:
            if format_type == 'percentage':
                return round(float(value), 2)
            elif format_type == 'currency':
                return round(float(value), 2)
            elif format_type == 'integer':
                return int(value)
            elif format_type == 'float':
                return float(value)
            else:
                return value
                
        except (ValueError, TypeError):
            return value
    
    def _llm_analysis(self, file_path: Path, 
                     detection_result: DetectionResult) -> Optional[AnalysisResult]:
        """
        Perform LLM-based analysis as fallback.
        
        Args:
            file_path: Path to the report file
            detection_result: Detection result with configuration
            
        Returns:
            Analysis result or None if failed
        """
        start_time = time.time()
        
        # Extract content for LLM
        file_format = file_path.suffix[1:].lower()
        
        if file_format not in self.parsers:
            return None
        
        parser = self.parsers[file_format]
        text_content = parser.extract_text(file_path, max_chars=15000)
        
        if not text_content:
            return None
        
        # Get LLM analysis configuration
        config = detection_result.report_config
        llm_config = config.get('analysis', {}).get('llm_analysis', {})
        
        if not llm_config.get('enabled', False):
            return None
        
        prompt = llm_config.get('prompt', '')
        if not prompt:
            return None
        
        # Analyze with LLM
        response = self.llm_handler.analyze(text_content, prompt, extract_json=True)
        
        if response.error:
            logger.error(f"LLM analysis error: {response.error}")
            return None
        
        # Extract data from LLM response
        extracted_data = response.structured_data or {}
        
        # Create simple scoring (LLM fallback doesn't use detailed checks)
        base_score = 100
        issues = extracted_data.get('issues', [])
        score = max(0, base_score - len(issues) * 10)
        
        # Determine risk level and status
        if score >= 85:
            risk_level = 'niedrig'
            status = 'ok'
        elif score >= 70:
            risk_level = 'mittel'
            status = 'mit_einschraenkungen'
        else:
            risk_level = 'hoch'
            status = 'fehler'
        
        # Get file info
        file_info = parser.get_metadata(file_path)
        
        processing_time = time.time() - start_time
        
        return AnalysisResult(
            file_info=file_info,
            report_type=detection_result.report_type,
            result_status=status,
            risk_level=risk_level,
            score=score,
            analysis_details={
                'method': 'llm',
                'checks_performed': 1,
                'checks_passed': 1 if not issues else 0,
                'checks_failed': 1 if issues else 0,
                'issues': issues,
                'warnings': [],
                'llm_response': response.content,
                'llm_confidence': response.confidence
            },
            extracted_data=extracted_data,
            processing_info={
                'processing_time_seconds': round(processing_time, 2),
                'retry_count': 0,
                'parser_used': parser.__class__.__name__,
                'llm_duration_ms': response.duration_ms
            },
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ')
        )
    
    def _create_failed_result(self, file_path: Path, detection_result: DetectionResult,
                            error_message: str, processing_time: float) -> AnalysisResult:
        """Create a failed analysis result."""
        return AnalysisResult(
            file_info={
                'name': file_path.name,
                'path': str(file_path),
                'size_bytes': file_path.stat().st_size if file_path.exists() else 0,
                'format': file_path.suffix[1:].lower()
            },
            report_type=detection_result.report_type,
            result_status='nicht_erfolgreich_analysiert',
            risk_level='hoch',
            score=0,
            analysis_details={
                'method': 'failed',
                'checks_performed': 0,
                'checks_passed': 0,
                'checks_failed': 0,
                'issues': [error_message],
                'warnings': []
            },
            extracted_data={},
            processing_info={
                'processing_time_seconds': round(processing_time, 2),
                'retry_count': 0,
                'parser_used': 'none',
                'error': error_message
            },
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ')
        )