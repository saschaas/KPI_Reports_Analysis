from abc import ABC, abstractmethod
from typing import Dict, Any, List
import pandas as pd
from utils.scoring import RiskScorer, CheckResult


class BaseAnalyzer(ABC):
    """Base class for report-specific analyzers."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize BaseAnalyzer.
        
        Args:
            config: Analysis configuration dictionary
        """
        self.config = config
        self.scorer = RiskScorer(config.get('scoring', {}))
    
    @abstractmethod
    def run_checks(self, data: pd.DataFrame) -> List[CheckResult]:
        """
        Run configured checks on the data.
        
        Args:
            data: DataFrame containing parsed report data
            
        Returns:
            List of check results
        """
        pass
    
    @abstractmethod
    def extract_fields(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Extract defined fields from the data.
        
        Args:
            data: DataFrame containing parsed report data
            
        Returns:
            Dictionary with extracted field values
        """
        pass
    
    def analyze(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Perform complete analysis of report data.
        
        Args:
            data: DataFrame containing parsed report data
            
        Returns:
            Complete analysis result
        """
        # Run checks
        checks = self.run_checks(data)
        
        # Extract fields
        fields = self.extract_fields(data)
        
        # Calculate score
        score_result = self.scorer.calculate(checks, fields)
        
        # Format result
        return self._format_result(checks, fields, score_result)
    
    def _format_result(self, checks: List[CheckResult], fields: Dict[str, Any], 
                      score_result) -> Dict[str, Any]:
        """Format analysis result into standard structure."""
        return {
            "checks": [
                {
                    "check_id": check.check_id,
                    "name": check.name,
                    "passed": check.passed,
                    "severity": check.severity,
                    "message": check.message,
                    "details": check.details
                } for check in checks
            ],
            "extracted_fields": fields,
            "score": score_result.score,
            "risk_level": score_result.risk_level.value,
            "status": score_result.status.value,
            "deduction_details": score_result.deduction_details
        }