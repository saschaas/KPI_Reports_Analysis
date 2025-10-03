import logging
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk level enumeration."""
    LOW = "niedrig"
    MEDIUM = "mittel"
    HIGH = "hoch"
    CRITICAL = "kritisch"


class Status(Enum):
    """Analysis status enumeration."""
    OK = "ok"
    WITH_LIMITATIONS = "mit_einschraenkungen"
    ERROR = "fehler"
    NOT_ANALYZED = "nicht_erfolgreich_analysiert"
    NOT_APPLICABLE = "na"


@dataclass
class CheckResult:
    """Result of a single check."""
    check_id: str
    name: str
    passed: bool
    severity: str
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    points_deducted: float = 0


@dataclass
class ScoreResult:
    """Complete scoring result."""
    score: float
    base_score: float
    total_deductions: float
    risk_level: RiskLevel
    status: Status
    deduction_details: List[Dict[str, Any]] = field(default_factory=list)
    triggered_rules: List[str] = field(default_factory=list)


class RiskScorer:
    """Calculates risk scores and levels based on check results."""
    
    def __init__(self, scoring_config: Dict[str, Any]):
        """
        Initialize RiskScorer with configuration.
        
        Args:
            scoring_config: Scoring configuration from report config
        """
        self.config = scoring_config
        self.base_score = scoring_config.get("base_score", 100)
        self.deductions = scoring_config.get("deductions", [])
        self.risk_levels = scoring_config.get("risk_levels", {})
        
        # Validate configuration
        self._validate_config()
    
    def _validate_config(self) -> None:
        """Validate scoring configuration."""
        if self.base_score < 0 or self.base_score > 100:
            raise ValueError(f"Invalid base score: {self.base_score}")
        
        if not self.risk_levels:
            # Set default risk levels if not configured
            self.risk_levels = {
                "high": {"score_range": [0, 60]},
                "medium": {"score_range": [61, 85]},
                "low": {"score_range": [86, 100]}
            }
    
    def calculate(self, checks: List[CheckResult], 
                 extracted_data: Optional[Dict[str, Any]] = None) -> ScoreResult:
        """
        Calculate score based on check results and extracted data.
        
        Args:
            checks: List of check results
            extracted_data: Optional extracted data for condition evaluation
            
        Returns:
            Complete scoring result
        """
        score = float(self.base_score)
        total_deductions = 0.0
        deduction_details = []
        triggered_rules = []
        
        # Process each deduction rule
        for deduction_rule in self.deductions:
            deduction_amount = self._apply_deduction(
                deduction_rule, 
                checks, 
                extracted_data or {}
            )
            
            if deduction_amount > 0:
                score -= deduction_amount
                total_deductions += deduction_amount
                
                deduction_details.append({
                    "condition": deduction_rule.get("condition"),
                    "description": deduction_rule.get("description", "Unknown"),
                    "points": deduction_amount
                })
                
                triggered_rules.append(deduction_rule.get("condition", "unknown"))
        
        # Apply check-based deductions
        for check in checks:
            if not check.passed and check.points_deducted > 0:
                score -= check.points_deducted
                total_deductions += check.points_deducted
                
                deduction_details.append({
                    "check": check.name,
                    "severity": check.severity,
                    "points": check.points_deducted
                })
        
        # Ensure score stays within bounds
        score = max(0, min(100, score))
        
        # Determine risk level
        risk_level = self._determine_risk_level(score, checks, extracted_data)
        
        # Determine status
        status = self._determine_status(score, risk_level, checks)
        
        return ScoreResult(
            score=score,
            base_score=self.base_score,
            total_deductions=total_deductions,
            risk_level=risk_level,
            status=status,
            deduction_details=deduction_details,
            triggered_rules=triggered_rules
        )
    
    def _apply_deduction(self, rule: Dict[str, Any], checks: List[CheckResult], 
                        data: Dict[str, Any]) -> float:
        """
        Apply a single deduction rule.
        
        Args:
            rule: Deduction rule configuration
            checks: List of check results
            data: Extracted data for evaluation
            
        Returns:
            Points to deduct
        """
        condition = rule.get("condition", "")
        points = rule.get("points", 0)
        per_occurrence = rule.get("per_occurrence", False)
        max_deduction = rule.get("max_deduction", float('inf'))
        
        try:
            # Evaluate condition
            occurrences = self._evaluate_condition(condition, checks, data)
            
            if occurrences == 0:
                return 0
            
            if per_occurrence:
                deduction = min(points * occurrences, max_deduction)
            else:
                deduction = points if occurrences > 0 else 0
            
            return deduction
            
        except Exception as e:
            logger.warning(f"Failed to evaluate deduction rule '{condition}': {e}")
            return 0
    
    def _evaluate_condition(self, condition: str, checks: List[CheckResult], 
                          data: Dict[str, Any]) -> int:
        """
        Evaluate a condition string.
        
        Args:
            condition: Condition string to evaluate
            checks: List of check results
            data: Data for evaluation
            
        Returns:
            Number of occurrences (0 if false, >0 if true)
        """
        # Handle check-based conditions
        if condition == "missing_required_columns":
            failed_checks = [c for c in checks 
                           if c.check_id == "completeness" and not c.passed]
            return len(failed_checks)
        
        if condition == "data_quality_issues":
            quality_checks = [c for c in checks 
                            if "quality" in c.check_id.lower() and not c.passed]
            return len(quality_checks)
        
        if condition == "critical_errors":
            critical_checks = [c for c in checks 
                             if c.severity == "high" and not c.passed]
            return len(critical_checks)
        
        # Handle data-based conditions
        try:
            # Simple comparison conditions
            if ">" in condition:
                field, value = condition.split(">")
                field = field.strip()
                value = float(value.strip())
                
                if field in data:
                    field_value = float(data[field])
                    return int(field_value) if field_value > value else 0
            
            if "<" in condition:
                field, value = condition.split("<")
                field = field.strip()
                value = float(value.strip())
                
                if field in data:
                    field_value = float(data[field])
                    return int(field_value) if field_value < value else 0
            
            if "==" in condition:
                field, value = condition.split("==")
                field = field.strip()
                value = value.strip().strip('"\'')
                
                if field in data:
                    return 1 if str(data[field]) == value else 0
            
        except Exception as e:
            logger.debug(f"Could not evaluate condition '{condition}': {e}")
        
        return 0
    
    def _determine_risk_level(self, score: float, checks: List[CheckResult], 
                            data: Optional[Dict[str, Any]]) -> RiskLevel:
        """
        Determine risk level based on score and triggers.
        
        Args:
            score: Calculated score
            checks: List of check results
            data: Optional extracted data
            
        Returns:
            Risk level
        """
        # Check for critical triggers first
        if "critical" in self.risk_levels:
            critical_config = self.risk_levels["critical"]
            if self._check_triggers(critical_config.get("triggers", []), checks, data):
                return RiskLevel.CRITICAL
        
        # Check high risk triggers
        high_config = self.risk_levels.get("high", {})
        if "triggers" in high_config:
            if self._check_triggers(high_config["triggers"], checks, data):
                return RiskLevel.HIGH
        
        # Determine by score range
        for level_name, level_config in self.risk_levels.items():
            score_range = level_config.get("score_range", [])
            if len(score_range) == 2:
                min_score, max_score = score_range
                if min_score <= score <= max_score:
                    if level_name == "high":
                        return RiskLevel.HIGH
                    elif level_name == "medium":
                        return RiskLevel.MEDIUM
                    elif level_name == "low":
                        return RiskLevel.LOW
        
        # Default based on score
        if score <= 60:
            return RiskLevel.HIGH
        elif score <= 85:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _check_triggers(self, triggers: List[str], checks: List[CheckResult], 
                       data: Optional[Dict[str, Any]]) -> bool:
        """
        Check if any trigger conditions are met.
        
        Args:
            triggers: List of trigger conditions
            checks: List of check results
            data: Optional extracted data
            
        Returns:
            True if any trigger is activated
        """
        for trigger in triggers:
            occurrences = self._evaluate_condition(trigger, checks, data or {})
            if occurrences > 0:
                return True
        return False
    
    def _determine_status(self, score: float, risk_level: RiskLevel, 
                        checks: List[CheckResult]) -> Status:
        """
        Determine analysis status.
        
        Args:
            score: Calculated score
            risk_level: Determined risk level
            checks: List of check results
            
        Returns:
            Analysis status
        """
        # Check for critical failures
        critical_failures = [c for c in checks 
                           if c.severity == "high" and not c.passed]
        
        if critical_failures:
            return Status.ERROR
        
        # Based on risk level and score
        if risk_level == RiskLevel.CRITICAL:
            return Status.ERROR
        elif risk_level == RiskLevel.HIGH:
            return Status.ERROR if score < 40 else Status.WITH_LIMITATIONS
        elif risk_level == RiskLevel.MEDIUM:
            return Status.WITH_LIMITATIONS
        else:
            return Status.OK
    
    @staticmethod
    def format_score_summary(result: ScoreResult) -> str:
        """
        Format score result as human-readable summary.
        
        Args:
            result: Score result to format
            
        Returns:
            Formatted summary string
        """
        summary = f"""
Score: {result.score:.1f}/{result.base_score}
Risk Level: {result.risk_level.value}
Status: {result.status.value}
Total Deductions: {result.total_deductions:.1f}
"""
        
        if result.deduction_details:
            summary += "\nDeductions:\n"
            for detail in result.deduction_details:
                desc = detail.get("description") or detail.get("check", "Unknown")
                points = detail.get("points", 0)
                summary += f"  - {desc}: -{points:.1f} points\n"
        
        if result.triggered_rules:
            summary += f"\nTriggered Rules: {', '.join(result.triggered_rules)}\n"
        
        return summary.strip()