import os
import yaml
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Handles loading and validation of configuration files."""
    
    def __init__(self, env_path: Optional[str] = None):
        """
        Initialize ConfigLoader with environment variables.
        
        Args:
            env_path: Path to .env file (optional)
        """
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()
        
        self.base_path = Path(__file__).parent.parent.parent
        self.config_cache: Dict[str, Dict[str, Any]] = {}
    
    def load_main_config(self) -> Dict[str, Any]:
        """
        Load the main configuration file.
        
        Returns:
            Dictionary containing main configuration
        """
        config_path = self.base_path / "config" / "main_config.yaml"
        
        if "main" in self.config_cache:
            return self.config_cache["main"]
        
        try:
            config = self._load_yaml_file(config_path)
            
            # Override with environment variables if present
            config = self._apply_env_overrides(config)
            
            # Validate configuration
            self._validate_main_config(config)
            
            self.config_cache["main"] = config
            logger.info("Main configuration loaded successfully")
            return config
            
        except Exception as e:
            logger.error(f"Failed to load main configuration: {e}")
            raise
    
    def load_report_config(self, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a specific report configuration.
        
        Args:
            report_id: ID of the report configuration to load
            
        Returns:
            Dictionary containing report configuration or None if not found
        """
        if report_id in self.config_cache:
            return self.config_cache[report_id]
        
        report_path = self.base_path / "config" / "report_types" / f"{report_id}.yaml"
        
        if not report_path.exists():
            logger.warning(f"Report configuration not found: {report_id}")
            return None
        
        try:
            config = self._load_yaml_file(report_path)
            self._validate_report_config(config)
            self.config_cache[report_id] = config
            logger.info(f"Report configuration loaded: {report_id}")
            return config
            
        except Exception as e:
            logger.error(f"Failed to load report configuration {report_id}: {e}")
            return None
    
    def load_all_report_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        Load all available report configurations.
        
        Returns:
            Dictionary mapping report IDs to their configurations
        """
        reports = {}
        report_dir = self.base_path / "config" / "report_types"
        
        if not report_dir.exists():
            logger.warning("Report configurations directory not found")
            return reports
        
        for report_file in report_dir.glob("*.yaml"):
            try:
                config = self._load_yaml_file(report_file)
                
                if not config.get("report_type", {}).get("enabled", True):
                    logger.debug(f"Skipping disabled report: {report_file.stem}")
                    continue
                
                report_id = config["report_type"]["id"]
                self._validate_report_config(config)
                reports[report_id] = config
                self.config_cache[report_id] = config
                
            except Exception as e:
                logger.error(f"Failed to load report {report_file.name}: {e}")
                continue
        
        logger.info(f"Loaded {len(reports)} report configurations")
        return reports
    
    def _load_yaml_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Load a YAML file.
        
        Args:
            file_path: Path to the YAML file
            
        Returns:
            Dictionary containing parsed YAML content
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {file_path}: {e}")
        except IOError as e:
            raise IOError(f"Cannot read file {file_path}: {e}")
    
    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply environment variable overrides to configuration.
        
        Args:
            config: Original configuration dictionary
            
        Returns:
            Configuration with environment overrides applied
        """
        # Ollama settings
        if os.getenv("OLLAMA_MODEL"):
            config.setdefault("ollama", {})["model"] = os.getenv("OLLAMA_MODEL")
        if os.getenv("OLLAMA_BASE_URL"):
            config.setdefault("ollama", {})["base_url"] = os.getenv("OLLAMA_BASE_URL")
        if os.getenv("OLLAMA_TIMEOUT"):
            config.setdefault("ollama", {})["timeout"] = int(os.getenv("OLLAMA_TIMEOUT"))
        
        # Path settings
        if os.getenv("INPUT_DIRECTORY"):
            config.setdefault("paths", {})["input_directory"] = os.getenv("INPUT_DIRECTORY")
        if os.getenv("OUTPUT_DIRECTORY"):
            config.setdefault("paths", {})["output_directory"] = os.getenv("OUTPUT_DIRECTORY")
        if os.getenv("CONFIG_DIRECTORY"):
            config.setdefault("paths", {})["report_configs"] = os.getenv("CONFIG_DIRECTORY")
        if os.getenv("LOGS_DIRECTORY"):
            config.setdefault("paths", {})["logs"] = os.getenv("LOGS_DIRECTORY")
        
        # Processing settings
        if os.getenv("MAX_RETRIES"):
            config.setdefault("processing", {})["max_retries"] = int(os.getenv("MAX_RETRIES"))
        if os.getenv("FALLBACK_TO_LLM"):
            config.setdefault("processing", {})["fallback_to_llm"] = \
                os.getenv("FALLBACK_TO_LLM").lower() == "true"
        if os.getenv("ENABLE_PARALLEL_PROCESSING"):
            config.setdefault("processing", {})["parallel_processing"] = \
                os.getenv("ENABLE_PARALLEL_PROCESSING").lower() == "true"
        
        # Logging settings
        if os.getenv("LOG_LEVEL"):
            config.setdefault("logging", {})["level"] = os.getenv("LOG_LEVEL")
        if os.getenv("LOG_TO_CONSOLE"):
            config.setdefault("logging", {})["console"] = \
                os.getenv("LOG_TO_CONSOLE").lower() == "true"
        if os.getenv("LOG_TO_FILE"):
            config.setdefault("logging", {})["file"] = \
                os.getenv("LOG_TO_FILE").lower() == "true"
        
        return config
    
    def _validate_main_config(self, config: Dict[str, Any]) -> None:
        """
        Validate main configuration structure.
        
        Args:
            config: Configuration dictionary to validate
            
        Raises:
            ValueError: If configuration is invalid
        """
        required_sections = ["ollama", "paths", "processing", "logging"]
        
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        # Validate Ollama configuration
        if not config["ollama"].get("model"):
            raise ValueError("Ollama model not specified")
        if not config["ollama"].get("base_url"):
            raise ValueError("Ollama base URL not specified")
        
        # Validate paths
        if not config["paths"].get("input_directory"):
            raise ValueError("Input directory not specified")
        if not config["paths"].get("output_directory"):
            raise ValueError("Output directory not specified")
        
        # Validate processing formats
        supported_formats = config["processing"].get("supported_formats", [])
        if not supported_formats:
            raise ValueError("No supported file formats specified")
        
        logger.debug("Main configuration validation passed")
    
    def _validate_report_config(self, config: Dict[str, Any]) -> None:
        """
        Validate report configuration structure.
        
        Args:
            config: Report configuration dictionary to validate
            
        Raises:
            ValueError: If configuration is invalid
        """
        if "report_type" not in config:
            raise ValueError("Missing 'report_type' section")
        
        report_type = config["report_type"]
        if not report_type.get("id"):
            raise ValueError("Report ID not specified")
        if not report_type.get("name"):
            raise ValueError("Report name not specified")
        
        # Validate identification section
        if "identification" not in config:
            raise ValueError("Missing 'identification' section")
        
        identification = config["identification"]
        has_patterns = bool(identification.get("filename_patterns"))
        has_identifiers = bool(identification.get("content_identifiers"))
        has_llm = identification.get("llm_classification", {}).get("enabled", False)
        
        if not (has_patterns or has_identifiers or has_llm):
            raise ValueError("No identification methods configured")
        
        # Validate analysis section
        if "analysis" in config:
            analysis = config["analysis"]
            
            # Validate scoring if present
            if "scoring" in analysis:
                scoring = analysis["scoring"]
                if "base_score" not in scoring:
                    raise ValueError("Base score not specified in scoring configuration")
                if scoring["base_score"] < 0 or scoring["base_score"] > 100:
                    raise ValueError("Base score must be between 0 and 100")
        
        logger.debug(f"Report configuration validation passed: {report_type.get('id')}")
    
    def get_report_ids(self) -> List[str]:
        """
        Get list of all available report configuration IDs.
        
        Returns:
            List of report IDs
        """
        report_dir = self.base_path / "config" / "report_types"
        
        if not report_dir.exists():
            return []
        
        report_ids = []
        for report_file in report_dir.glob("*.yaml"):
            try:
                config = self._load_yaml_file(report_file)
                if config.get("report_type", {}).get("enabled", True):
                    report_ids.append(config["report_type"]["id"])
            except Exception:
                continue
        
        return report_ids
    
    def reload_configs(self) -> None:
        """Clear configuration cache and force reload on next access."""
        self.config_cache.clear()
        logger.info("Configuration cache cleared")