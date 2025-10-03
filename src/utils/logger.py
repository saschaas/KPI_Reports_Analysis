import logging
import logging.handlers
import colorlog
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


def setup_logging(config: Dict[str, Any], log_name: Optional[str] = None) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        config: Main configuration dictionary
        log_name: Optional specific logger name
        
    Returns:
        Configured logger instance
    """
    logging_config = config.get("logging", {})
    
    # Get configuration values
    log_level = logging_config.get("level", "INFO")
    log_format = logging_config.get("format", 
                                   "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_enabled = logging_config.get("console", True)
    file_enabled = logging_config.get("file", True)
    
    # Create logger
    logger = logging.getLogger(log_name or "report_analyzer")
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler with color support
    if console_enabled:
        console_handler = colorlog.StreamHandler()
        console_handler.setLevel(getattr(logging, log_level.upper()))
        
        # Color formatter
        color_format = colorlog.ColoredFormatter(
            "%(log_color)s" + log_format,
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            }
        )
        console_handler.setFormatter(color_format)
        logger.addHandler(console_handler)
    
    # File handler with rotation
    if file_enabled:
        log_dir = Path(config.get("paths", {}).get("logs", "./logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Create log file with date
        log_file = log_dir / f"report_analyzer_{datetime.now().strftime('%Y%m%d')}.log"
        
        # Rotating file handler
        max_bytes = logging_config.get("max_file_size_mb", 10) * 1024 * 1024
        backup_count = logging_config.get("backup_count", 5)
        
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        
        # Standard formatter for file
        file_formatter = logging.Formatter(log_format)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Log initial setup message
    logger.info(f"Logging initialized - Level: {log_level}, Console: {console_enabled}, File: {file_enabled}")
    
    return logger


class AnalysisLogger:
    """Specialized logger for analysis operations with structured logging."""
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize AnalysisLogger.
        
        Args:
            logger: Base logger instance
        """
        self.logger = logger
        self.context: Dict[str, Any] = {}
    
    def set_context(self, **kwargs) -> None:
        """
        Set context for structured logging.
        
        Args:
            **kwargs: Context key-value pairs
        """
        self.context.update(kwargs)
    
    def clear_context(self) -> None:
        """Clear logging context."""
        self.context.clear()
    
    def _format_message(self, message: str) -> str:
        """
        Format message with context.
        
        Args:
            message: Base message
            
        Returns:
            Formatted message with context
        """
        if not self.context:
            return message
        
        context_str = " | ".join(f"{k}={v}" for k, v in self.context.items())
        return f"{message} | {context_str}"
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message with context."""
        self.set_context(**kwargs)
        self.logger.debug(self._format_message(message))
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message with context."""
        self.set_context(**kwargs)
        self.logger.info(self._format_message(message))
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message with context."""
        self.set_context(**kwargs)
        self.logger.warning(self._format_message(message))
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message with context."""
        self.set_context(**kwargs)
        self.logger.error(self._format_message(message))
    
    def critical(self, message: str, **kwargs) -> None:
        """Log critical message with context."""
        self.set_context(**kwargs)
        self.logger.critical(self._format_message(message))
    
    def log_analysis_start(self, file_name: str, report_type: str) -> None:
        """
        Log the start of file analysis.
        
        Args:
            file_name: Name of file being analyzed
            report_type: Type of report
        """
        self.info(
            "Starting analysis",
            file=file_name,
            report_type=report_type,
            timestamp=datetime.now().isoformat()
        )
    
    def log_analysis_complete(self, file_name: str, status: str, 
                            duration_seconds: float) -> None:
        """
        Log completion of file analysis.
        
        Args:
            file_name: Name of file analyzed
            status: Analysis status
            duration_seconds: Time taken for analysis
        """
        self.info(
            "Analysis complete",
            file=file_name,
            status=status,
            duration=f"{duration_seconds:.2f}s",
            timestamp=datetime.now().isoformat()
        )
    
    def log_error_with_traceback(self, message: str, exception: Exception, 
                                **kwargs) -> None:
        """
        Log error with exception traceback.
        
        Args:
            message: Error message
            exception: Exception instance
            **kwargs: Additional context
        """
        import traceback
        
        self.set_context(**kwargs)
        self.error(f"{message}: {str(exception)}")
        self.debug(f"Traceback: {traceback.format_exc()}")
    
    def log_performance_metric(self, operation: str, duration_ms: float, 
                              **kwargs) -> None:
        """
        Log performance metrics.
        
        Args:
            operation: Name of operation
            duration_ms: Duration in milliseconds
            **kwargs: Additional metrics
        """
        self.debug(
            f"Performance metric: {operation}",
            duration_ms=duration_ms,
            **kwargs
        )