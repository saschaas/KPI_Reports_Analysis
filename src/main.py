#!/usr/bin/env python3
"""
Report Analysis Tool - Main Entry Point

Automatisierte Analyse monatlicher Berichte mit LLM-Unterstützung über Ollama.
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import List, Optional
import io

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add src directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from utils import setup_logging, ConfigLoader, FileHandler, AnalysisLogger
from core import OllamaHandler, ReportDetector, ReportAnalyzer, ResultHandler

logger = logging.getLogger(__name__)


class ReportAnalysisTool:
    """Main orchestrator for the report analysis process."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the Report Analysis Tool.
        
        Args:
            config_path: Optional path to custom config file
        """
        # Load configuration
        self.config_loader = ConfigLoader()
        self.config = self.config_loader.load_main_config()
        
        # Setup logging
        self.logger = setup_logging(self.config, "report_analyzer")
        self.analysis_logger = AnalysisLogger(self.logger)
        
        # Initialize components
        self.file_handler = FileHandler(self.config)
        self.llm_handler = self._init_ollama_handler()
        self.detector = ReportDetector(self.config_loader, self.llm_handler)
        self.analyzer = ReportAnalyzer(self.llm_handler)
        self.result_handler = ResultHandler(self.config)
        
        logger.info("Report Analysis Tool initialized successfully")
    
    def _init_ollama_handler(self) -> Optional[OllamaHandler]:
        """Initialize Ollama handler with configuration."""
        ollama_config = self.config.get("ollama", {})
        
        try:
            handler = OllamaHandler(
                model=ollama_config.get("model", "llama3.2"),
                base_url=ollama_config.get("base_url", "http://localhost:11434"),
                timeout=ollama_config.get("timeout", 60),
                temperature=ollama_config.get("temperature", 0.1),
                max_retries=self.config.get("processing", {}).get("max_retries", 3)
            )
            
            if handler.is_available():
                logger.info(f"Ollama handler initialized with model: {ollama_config.get('model')}")
                return handler
            else:
                logger.warning("Ollama service not available - running without LLM support")
                return None
                
        except Exception as e:
            logger.error(f"Failed to initialize Ollama handler: {e}")
            return None
    
    def run(self, input_path: Optional[str] = None, 
           output_filename: Optional[str] = None,
           archive_processed: bool = True) -> bool:
        """
        Run the complete analysis pipeline.
        
        Args:
            input_path: Optional specific file path to analyze
            output_filename: Optional output filename
            archive_processed: Whether to archive processed files
            
        Returns:
            True if analysis completed successfully
        """
        logger.info("=== Starting Report Analysis ===")
        
        try:
            # Validate input files
            if input_path:
                files = [Path(input_path)]
                if not files[0].exists():
                    logger.error(f"Input file not found: {input_path}")
                    return False
            else:
                validation_result = self.file_handler.validate_input_files()
                files = validation_result["valid"]
                
                if validation_result["invalid"]:
                    logger.warning(f"Found {len(validation_result['invalid'])} invalid files")
                    for invalid_file in validation_result["invalid"]:
                        logger.warning(f"  - {invalid_file}")
                
                if not files:
                    logger.error("No valid input files found")
                    return False
            
            logger.info(f"Processing {len(files)} files")
            
            # Process each file
            results = []

            for i, file_path in enumerate(files, 1):
                logger.info(f"\n--- Processing file {i}/{len(files)}: {file_path.name} ---")

                try:
                    result = self._process_single_file(file_path)
                    if result:
                        results.append(result)

                except Exception as e:
                    logger.error(f"Failed to process {file_path.name}: {e}")
                    # Create failed result
                    failed_result = self._create_failed_result(file_path, str(e))
                    results.append(failed_result)

                # Archive processed file if requested
                if archive_processed and input_path is None:  # Don't archive when processing single file
                    try:
                        # Extract report month from the result for proper archiving
                        report_month = None
                        if result:
                            report_month = self._extract_report_month(result)

                        self.file_handler.archive_processed_file(file_path, report_month)
                    except Exception as e:
                        logger.warning(f"Failed to archive {file_path.name}: {e}")
            
            # Save results
            if results:
                output_path = self.result_handler.save_results(results, output_filename)
                
                # Generate summary
                self._print_summary(results)
                
                logger.info(f"✅ Analysis completed. Results saved to: {output_path}")
                return True
            else:
                logger.error("No results generated")
                return False
                
        except Exception as e:
            logger.error(f"Analysis pipeline failed: {e}")
            return False
    
    def _extract_report_month(self, result) -> Optional[str]:
        """
        Extract report month from analysis result.

        Args:
            result: AnalysisResult object

        Returns:
            Report month in format "YYYY-MM" or None
        """
        import re

        # Priority 1: Check vm_analysis.report_month (most accurate for Veeam)
        vm_analysis = result.extracted_data.get('vm_analysis', {})
        if isinstance(vm_analysis, dict) and 'report_month' in vm_analysis:
            report_month = vm_analysis['report_month']
            if report_month:
                return str(report_month)

        # Priority 2: Extract from period_start (accurate for all reports with dates)
        period_start = result.extracted_data.get('period_start')
        if period_start and period_start != 'N/A':
            # Extract YYYY-MM from date like "2025-08-01"
            match = re.match(r'(\d{4})-(\d{2})-\d{2}', str(period_start))
            if match:
                return f"{match.group(1)}-{match.group(2)}"

        # Priority 3: Check for explicit period or zeitraum fields
        period = result.extracted_data.get('period') or result.extracted_data.get('zeitraum')
        if period:
            return str(period)

        # Priority 4: Try to extract from filename
        filename = result.file_info.get("name", "")
        date_patterns = [
            r'(20\d{2})[_-]?(\d{2})',  # 2024-01 or 2024_01 or 202401
            r'(\d{2})[_-]?(20\d{2})',  # 01-2024 or 01_2024
        ]

        for pattern in date_patterns:
            match = re.search(pattern, filename)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    if len(groups[0]) == 4:  # First is year
                        return f"{groups[0]}-{groups[1]}"
                    else:  # Second is year
                        return f"{groups[1]}-{groups[0]}"

        return None

    def _process_single_file(self, file_path: Path):
        """Process a single file through the complete pipeline."""
        # Step 1: Detect report type
        detection_result = self.detector.detect(file_path)

        if not detection_result:
            self.analysis_logger.log_analysis_start(file_path.name, "unknown")
            logger.error(f"Could not detect report type for: {file_path.name}")
            return self._create_failed_result(file_path, "Unknown report type")

        # Log with detected report type
        self.analysis_logger.log_analysis_start(file_path.name, detection_result.report_type)

        logger.info(f"Detected as: {detection_result.report_name} "
                   f"(confidence: {detection_result.confidence:.2f})")

        # Step 2: Analyze report
        analysis_result = self.analyzer.analyze(file_path, detection_result)
        
        # Log completion
        self.analysis_logger.log_analysis_complete(
            file_path.name,
            analysis_result.result_status,
            analysis_result.processing_info.get('processing_time_seconds', 0)
        )
        
        logger.info(f"Analysis completed - Status: {analysis_result.result_status}, "
                   f"Score: {analysis_result.score}")
        
        return analysis_result
    
    def _create_failed_result(self, file_path: Path, error_message: str):
        """Create a failed analysis result."""
        from core.report_analyzer import AnalysisResult
        import time
        
        return AnalysisResult(
            file_info={
                'name': file_path.name,
                'path': str(file_path),
                'size_bytes': file_path.stat().st_size if file_path.exists() else 0,
                'format': file_path.suffix[1:].lower()
            },
            report_type='unknown',
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
                'processing_time_seconds': 0,
                'retry_count': 0,
                'parser_used': 'none',
                'error': error_message
            },
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ')
        )
    
    def _print_summary(self, results: List) -> None:
        """Print analysis summary to console."""
        print("\n" + "="*60)
        print("📊 ANALYSIS SUMMARY")
        print("="*60)
        
        total = len(results)
        successful = sum(1 for r in results 
                        if r.result_status not in ['nicht_erfolgreich_analysiert', 'fehler'])
        failed = total - successful
        
        print(f"Total Files: {total}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(successful/total*100):.1f}%")
        
        if successful > 0:
            avg_score = sum(r.score for r in results) / total
            print(f"Average Score: {avg_score:.1f}/100")
        
        # Risk distribution
        risk_counts = {}
        for result in results:
            risk = result.risk_level
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
        
        print(f"\nRisk Distribution:")
        for risk, count in sorted(risk_counts.items()):
            print(f"  {risk}: {count}")
        
        # Show failed files
        if failed > 0:
            print(f"\nFailed Files:")
            for result in results:
                if result.result_status in ['nicht_erfolgreich_analysiert', 'fehler']:
                    issues = '; '.join(result.analysis_details.get('issues', []))
                    print(f"  ❌ {result.file_info['name']}: {issues}")
        
        # Show successful files with issues
        with_issues = [r for r in results 
                      if r.result_status not in ['nicht_erfolgreich_analysiert'] 
                      and r.analysis_details.get('issues')]
        
        if with_issues:
            print(f"\nFiles with Issues:")
            for result in with_issues:
                issues = '; '.join(result.analysis_details.get('issues', [])[:2])
                print(f"  ⚠️  {result.file_info['name']}: {issues}")
        
        print("="*60)
    
    def list_report_types(self) -> None:
        """List all available report types."""
        print("\n📋 Available Report Types:")
        print("-" * 40)
        
        for report_id, config in self.detector.report_configs.items():
            report_info = config.get('report_type', {})
            enabled = report_info.get('enabled', True)
            status = "✅" if enabled else "❌"
            
            print(f"{status} {report_info.get('name', report_id)}")
            print(f"   ID: {report_id}")
            print(f"   Description: {report_info.get('description', 'N/A')}")
            
            # Show supported formats
            supported_formats = config.get('supported_formats', [])
            if supported_formats:
                print(f"   Formats: {', '.join(supported_formats)}")
            
            print()
    
    def test_llm_connection(self) -> bool:
        """Test LLM connection."""
        print("\n🤖 Testing LLM Connection...")
        
        if not self.llm_handler:
            print("❌ LLM handler not initialized")
            return False
        
        if self.llm_handler.is_available():
            print("✅ LLM connection successful")
            
            # Test simple classification
            test_response = self.llm_handler.classify(
                "This is a test message",
                "Is this a test? Respond with YES or NO.",
                options=["YES", "NO"]
            )
            
            if not test_response.error:
                print(f"✅ Test classification successful: {test_response.content}")
                return True
            else:
                print(f"❌ Test classification failed: {test_response.error}")
                return False
        else:
            print("❌ LLM service not available")
            return False
    
    def clear_cache(self, older_than_hours: Optional[int] = None) -> None:
        """Clear file cache."""
        cleared = self.file_handler.clear_cache(older_than_hours)
        print(f"🧹 Cleared {cleared} cache files")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Report Analysis Tool - Analyze reports with LLM support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                           # Analyze all files in input directory
  python main.py --file report.xlsx       # Analyze specific file
  python main.py --list-types             # List available report types
  python main.py --test-llm               # Test LLM connection
  python main.py --clear-cache            # Clear file cache
        """
    )
    
    parser.add_argument('--file', '-f', type=str,
                       help='Analyze specific file instead of input directory')
    parser.add_argument('--output', '-o', type=str,
                       help='Output filename (default: auto-generated)')
    parser.add_argument('--no-archive', action='store_true',
                       help='Do not archive processed files')
    parser.add_argument('--list-types', action='store_true',
                       help='List available report types and exit')
    parser.add_argument('--test-llm', action='store_true',
                       help='Test LLM connection and exit')
    parser.add_argument('--clear-cache', action='store_true',
                       help='Clear file cache and exit')
    parser.add_argument('--config', '-c', type=str,
                       help='Path to custom configuration file')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    
    args = parser.parse_args()
    
    try:
        # Initialize tool
        tool = ReportAnalysisTool(args.config)
        
        # Handle special commands
        if args.list_types:
            tool.list_report_types()
            return 0
        
        if args.test_llm:
            success = tool.test_llm_connection()
            return 0 if success else 1
        
        if args.clear_cache:
            tool.clear_cache()
            return 0
        
        # Run analysis
        success = tool.run(
            input_path=args.file,
            output_filename=args.output,
            archive_processed=not args.no_archive
        )
        
        return 0 if success else 1
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Analysis interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())