import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from jinja2 import Template

from core.report_analyzer import AnalysisResult

logger = logging.getLogger(__name__)


class ResultHandler:
    """Handles analysis results, formatting, and output generation."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize ResultHandler.
        
        Args:
            config: Main configuration dictionary
        """
        self.config = config
        self.output_dir = Path(config["paths"]["output_directory"])
        self.generate_html = config.get("output", {}).get("generate_html_report", True)
        
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def process_results(self, results: List[AnalysisResult], html_filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Process and format analysis results.

        Args:
            results: List of analysis results
            html_filename: Optional HTML filename to store in metadata

        Returns:
            Formatted results dictionary
        """
        # Create metadata with HTML filename
        metadata = self._create_metadata(results, html_filename)

        # Format individual results
        formatted_results = []

        for result in results:
            formatted_result = self._format_result(result)
            formatted_results.append(formatted_result)

        # Create final output structure
        output = {
            "analysis_metadata": metadata,
            "reports": formatted_results
        }

        return output
    
    def save_results(self, results: List[AnalysisResult],
                    filename: Optional[str] = None) -> Path:
        """
        Save results to JSON file.

        Args:
            results: List of analysis results
            filename: Optional filename

        Returns:
            Path to saved file
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"analysis_results_{timestamp}.json"

        # Determine report month from first result (all should be from same month typically)
        report_month = None
        if results:
            report_period = self._extract_report_period(results[0])
            if report_period != "unknown":
                # Use report period as directory (e.g., "2025-08")
                report_month = report_period

        # Create subdirectory based on report month or fall back to current month
        if report_month:
            month_dir = self.output_dir / report_month
            logger.info(f"Using report month for output directory: {report_month}")
        else:
            month_dir = self.output_dir / datetime.now().strftime("%Y-%m")
            logger.warning(f"Could not determine report month, using current month")

        month_dir.mkdir(parents=True, exist_ok=True)

        output_path = month_dir / filename

        # Determine HTML filename (same timestamp as JSON)
        html_filename = filename.replace('.json', '.html')

        # Process results with HTML filename for metadata
        output = self.process_results(results, html_filename)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"Results saved to: {output_path}")

            # Generate HTML report if enabled
            if self.generate_html:
                html_path = self._generate_html_report(output, output_path.with_suffix('.html'))
                logger.info(f"HTML report generated: {html_path}")

            return output_path

        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            raise
    
    def _create_metadata(self, results: List[AnalysisResult], html_filename: Optional[str] = None) -> Dict[str, Any]:
        """Create metadata for the analysis run."""
        successful = sum(1 for r in results
                        if r.result_status not in ['nicht_erfolgreich_analysiert', 'fehler'])
        failed = len(results) - successful

        # Calculate statistics
        if results:
            avg_score = sum(r.score for r in results) / len(results)
            processing_times = [r.processing_info.get('processing_time_seconds', 0)
                              for r in results]
            total_processing_time = sum(processing_times)
        else:
            avg_score = 0
            total_processing_time = 0

        # Count by report type
        report_types = {}
        risk_levels = {'niedrig': 0, 'mittel': 0, 'hoch': 0, 'kritisch': 0}

        for result in results:
            # Count report types
            report_type = result.report_type
            if report_type not in report_types:
                report_types[report_type] = 0
            report_types[report_type] += 1

            # Count risk levels
            risk_level = result.risk_level
            if risk_level in risk_levels:
                risk_levels[risk_level] += 1

        metadata = {
            "tool_version": "1.0.0",
            "analysis_timestamp": datetime.now().isoformat(),
            "total_files": len(results),
            "successful": successful,
            "failed": failed,
            "success_rate": (successful / len(results) * 100) if results else 0,
            "average_score": round(avg_score, 1),
            "total_processing_time_seconds": round(total_processing_time, 2),
            "report_types": report_types,
            "risk_distribution": risk_levels,
            "config_used": {
                "ollama_model": self.config.get("ollama", {}).get("model"),
                "supported_formats": self.config.get("processing", {}).get("supported_formats"),
                "fallback_to_llm": self.config.get("processing", {}).get("fallback_to_llm")
            }
        }

        # Add HTML filename if provided (so dashboard can construct correct links)
        if html_filename:
            metadata["html_filename"] = html_filename

        return metadata
    
    def _format_result(self, result: AnalysisResult) -> Dict[str, Any]:
        """Format a single analysis result."""
        # Determine report period from file name or data
        report_period = self._extract_report_period(result)
        
        return {
            "file_info": {
                "name": result.file_info.get("name", ""),
                "path": result.file_info.get("path", ""),
                "size_bytes": result.file_info.get("size_bytes", 0),
                "format": result.file_info.get("format", ""),
                "report_period": report_period
            },
            "report_type": result.report_type,
            "result_status": result.result_status,
            "risk_level": result.risk_level,
            "score": result.score,
            "analysis_details": result.analysis_details,
            "extracted_data": result.extracted_data,
            "processing_info": result.processing_info,
            "timestamp": result.timestamp,
            "summary": self._create_summary(result),
            "report_config": result.report_config
        }
    
    def _extract_report_period(self, result: AnalysisResult) -> str:
        """Extract report period from filename or extracted data."""
        import re

        # Priority 1: Check direct report_month field (for Entra devices, etc.)
        report_month = result.extracted_data.get('report_month')
        if report_month and report_month != 'N/A':
            return str(report_month)

        # Priority 2: Check vm_analysis.report_month (for Veeam backups)
        vm_analysis = result.extracted_data.get('vm_analysis', {})
        if isinstance(vm_analysis, dict) and 'report_month' in vm_analysis:
            vm_report_month = vm_analysis['report_month']
            if vm_report_month:
                return str(vm_report_month)

        # Priority 3: Extract from period_start (accurate for all reports with dates)
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

        # Pattern for YYYY-MM or YYYY_MM or YYYYMM
        date_patterns = [
            r'(20\d{2})[_-]?(\d{2})',  # 2024-01 or 2024_01 or 202401
            r'(\d{2})[_-]?(20\d{2})',  # 01-2024 or 01_2024
            r'(20\d{2})',              # Just year
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
                else:
                    return groups[0]  # Just year

        return "unknown"
    
    def _create_summary(self, result: AnalysisResult) -> str:
        """Create a human-readable summary of the analysis."""
        template_str = """
        Bericht: {report_name}
        Zeitraum: {period}
        Status: {status}
        Score: {score}/100
        Risiko: {risk_level}
        
        Verarbeitung:
        - Methode: {method}
        - Dauer: {processing_time}s
        - Checks: {checks_passed}/{checks_total}
        
        {extracted_summary}
        
        {issues_summary}
        """.strip()
        
        # Get extracted data summary
        extracted_summary = ""
        if result.extracted_data:
            key_metrics = []
            for key, value in result.extracted_data.items():
                if value is not None and key not in ['issues', 'summary', 'period']:
                    formatted_value = self._format_metric_value(key, value)
                    key_metrics.append(f"- {key}: {formatted_value}")
            
            if key_metrics:
                extracted_summary = "Kennzahlen:\n" + "\n".join(key_metrics)
        
        # Get issues summary
        issues_summary = ""
        issues = result.analysis_details.get('issues', [])
        if issues:
            issues_summary = "Probleme:\n" + "\n".join(f"- {issue}" for issue in issues[:5])
            if len(issues) > 5:
                issues_summary += f"\n- ... und {len(issues) - 5} weitere"
        
        # Format template
        summary = template_str.format(
            report_name=result.report_type.replace('_', ' ').title(),
            period=self._extract_report_period(result),
            status=result.result_status,
            score=result.score,
            risk_level=result.risk_level,
            method=result.analysis_details.get('method', 'unknown'),
            processing_time=result.processing_info.get('processing_time_seconds', 0),
            checks_passed=result.analysis_details.get('checks_passed', 0),
            checks_total=result.analysis_details.get('checks_performed', 0),
            extracted_summary=extracted_summary,
            issues_summary=issues_summary
        )
        
        return summary
    
    def _format_metric_value(self, key: str, value: Any) -> str:
        """Format a metric value for display."""
        if isinstance(value, float):
            if 'rate' in key.lower() or 'percentage' in key.lower():
                return f"{value:.1f}%"
            elif 'amount' in key.lower() or 'betrag' in key.lower():
                return f"{value:,.2f} €"
            else:
                return f"{value:.2f}"
        elif isinstance(value, int):
            return f"{value:,}"
        else:
            return str(value)
    
    def _generate_html_report(self, results_data: Dict[str, Any],
                            output_path: Path) -> Path:
        """Generate HTML report from results."""
        html_template = """
        <!DOCTYPE html>
        <html lang="de">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Veeam Backup Report Analysis</title>
            <style>
                * { box-sizing: border-box; }
                body {
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                    font-size: 14px;
                }
                .container {
                    max-width: 1400px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }
                .header {
                    border-bottom: 2px solid #e0e0e0;
                    padding-bottom: 20px;
                    margin-bottom: 30px;
                }
                .metadata {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                    gap: 15px;
                    margin-bottom: 30px;
                }
                .metric-card {
                    background: #f8f9fa;
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                }
                .metric-value {
                    font-size: 2em;
                    font-weight: bold;
                    color: #2c3e50;
                }
                .metric-label {
                    color: #6c757d;
                    margin-top: 5px;
                    font-size: 0.9em;
                }
                .report-card {
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    margin-bottom: 20px;
                    overflow: hidden;
                }
                .report-header {
                    padding: 15px 20px;
                    font-weight: bold;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                }
                .report-content {
                    padding: 25px;
                }
                .risk-niedrig { background-color: #d4edda; color: #155724; }
                .risk-mittel { background-color: #fff3cd; color: #856404; }
                .risk-hoch { background-color: #f8d7da; color: #721c24; }
                .score {
                    font-size: 1.3em;
                    font-weight: bold;
                    padding: 5px 15px;
                    border-radius: 5px;
                    background-color: white;
                }
                .section {
                    margin-bottom: 30px;
                }
                .section h3 {
                    margin-top: 0;
                    margin-bottom: 15px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #e0e0e0;
                    color: #2c3e50;
                }
                .info-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin-bottom: 20px;
                }
                .info-item {
                    background: #f8f9fa;
                    padding: 12px;
                    border-radius: 5px;
                }
                .info-label {
                    font-size: 0.85em;
                    color: #6c757d;
                    margin-bottom: 5px;
                }
                .info-value {
                    font-weight: 600;
                    color: #2c3e50;
                    font-size: 1.1em;
                }
                .vm-card {
                    border: 1px solid #dee2e6;
                    border-radius: 6px;
                    margin-bottom: 15px;
                    overflow: hidden;
                }
                .vm-header {
                    background: #f8f9fa;
                    padding: 12px 15px;
                    font-weight: 600;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    border-bottom: 1px solid #dee2e6;
                }
                .vm-name {
                    font-size: 1.1em;
                    color: #2c3e50;
                }
                .vm-score {
                    padding: 4px 12px;
                    border-radius: 4px;
                    font-size: 0.95em;
                }
                .vm-score-100 { background-color: #d4edda; color: #155724; }
                .vm-score-warning { background-color: #fff3cd; color: #856404; }
                .vm-score-danger { background-color: #f8d7da; color: #721c24; }
                .vm-content {
                    padding: 15px;
                }
                .vm-stats {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
                    gap: 10px;
                    margin-bottom: 15px;
                }
                .vm-stat {
                    background: #f8f9fa;
                    padding: 10px;
                    border-radius: 4px;
                    text-align: center;
                }
                .vm-stat-label {
                    font-size: 0.8em;
                    color: #6c757d;
                    margin-bottom: 3px;
                }
                .vm-stat-value {
                    font-weight: 600;
                    color: #2c3e50;
                    font-size: 1.1em;
                }
                .missing-days {
                    background: #fff3cd;
                    padding: 10px;
                    border-radius: 4px;
                    margin-top: 10px;
                }
                .missing-days-critical {
                    background: #f8d7da;
                }
                .missing-days h5 {
                    margin: 0 0 8px 0;
                    color: #856404;
                }
                .missing-days-critical h5 {
                    color: #721c24;
                }
                .day-list {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 5px;
                    font-size: 0.85em;
                }
                .day-tag {
                    background: white;
                    padding: 3px 8px;
                    border-radius: 3px;
                    border: 1px solid #ffc107;
                }
                .failed-backup {
                    background: #f8d7da;
                    border: 1px solid #f5c6cb;
                    padding: 10px;
                    border-radius: 4px;
                    margin-top: 10px;
                }
                .failed-backup h5 {
                    margin: 0 0 8px 0;
                    color: #721c24;
                }
                .summary-box {
                    background: #e7f3ff;
                    border-left: 4px solid #0066cc;
                    padding: 15px;
                    border-radius: 4px;
                    margin-bottom: 20px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 10px;
                    font-size: 0.9em;
                }
                th, td {
                    padding: 8px;
                    text-align: left;
                    border-bottom: 1px solid #dee2e6;
                }
                th {
                    background-color: #f8f9fa;
                    font-weight: 600;
                    color: #495057;
                }
                .footer {
                    margin-top: 40px;
                    padding-top: 20px;
                    border-top: 1px solid #e0e0e0;
                    text-align: center;
                    color: #6c757d;
                    font-size: 0.9em;
                }
                .filter-section {
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 30px;
                    border: 1px solid #dee2e6;
                }
                .filter-label {
                    font-weight: 600;
                    color: #2c3e50;
                    margin-bottom: 10px;
                    display: block;
                    font-size: 1em;
                }
                .report-select {
                    width: 100%;
                    padding: 12px 16px;
                    font-size: 1em;
                    border: 2px solid #dee2e6;
                    border-radius: 6px;
                    background-color: white;
                    color: #2c3e50;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                }
                .report-select:hover {
                    border-color: #0066cc;
                }
                .report-select:focus {
                    outline: none;
                    border-color: #0066cc;
                    box-shadow: 0 0 0 3px rgba(0, 102, 204, 0.1);
                }
                .report-card {
                    display: none;
                }
                .report-card.active {
                    display: block;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔍 Backup Report Analysis</h1>
                    <p>Analyse erstellt am {{ metadata.analysis_timestamp }}</p>
                </div>

                <div class="filter-section">
                    <label class="filter-label" for="reportSelector">Bericht auswählen:</label>
                    <select id="reportSelector" class="report-select">
                        <option value="all">Alle Berichte anzeigen ({{ metadata.total_files }} Berichte)</option>
                        {% for report in reports %}
                        <option value="report-{{ loop.index0 }}"
                                data-score="{{ report.score }}"
                                data-risk="{{ report.risk_level }}">
                            {{ report.report_type.replace('_', ' ').title() }} - {{ report.file_info.name }}
                            (Score: {{ report.score }}/100)
                        </option>
                        {% endfor %}
                    </select>
                </div>

                <div class="metadata">
                    <div class="metric-card">
                        <div class="metric-value">{{ metadata.total_files }}</div>
                        <div class="metric-label">Analysierte Dateien</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{{ "%.1f"|format(metadata.success_rate) }}%</div>
                        <div class="metric-label">Erfolgsrate</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-value">{{ "%.1f"|format(metadata.average_score) }}</div>
                        <div class="metric-label">Durchschnittsscore</div>
                    </div>
                </div>

                {% for report in reports %}
                <div class="report-card" data-report-index="report-{{ loop.index0 }}">
                    <div class="report-header risk-{{ report.risk_level }}">
                        <span>{{ report.report_type.replace('_', ' ').title() }} - {{ report.file_info.name }}</span>
                        <span class="score">{{ report.score }}/100</span>
                    </div>
                    <div class="report-content">

                        <div class="section">
                            <h3>📋 Report-Informationen</h3>
                            <div class="info-grid">
                                <div class="info-item">
                                    <div class="info-label">Berichtszeitraum</div>
                                    <div class="info-value">
                                        {% if report.extracted_data.vm_analysis and report.extracted_data.vm_analysis.report_month %}
                                            {{ format_month(report.extracted_data.vm_analysis.report_month) }}
                                        {% elif report.extracted_data.report_month %}
                                            {{ format_month(report.extracted_data.report_month) }}
                                        {% else %}
                                            {{ format_month(report.file_info.report_period) }}
                                        {% endif %}
                                    </div>
                                </div>

                                {% if report.report_type in ['veeam_backup', 'keepit_backup'] %}
                                <div class="info-item">
                                    <div class="info-label">Gesamtanzahl Backups</div>
                                    <div class="info-value">{{ report.extracted_data.total_backups }}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Erfolgreiche Backups</div>
                                    <div class="info-value" style="color: #28a745;">{{ report.extracted_data.successful_backups }}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Fehlgeschlagene Backups</div>
                                    <div class="info-value" style="color: #dc3545;">{{ report.extracted_data.failed_backups }}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Erfolgsrate</div>
                                    <div class="info-value">{{ "%.2f"|format(report.extracted_data.success_rate) }}%</div>
                                </div>
                                {% if report.report_type == 'veeam_backup' %}
                                <div class="info-item">
                                    <div class="info-label">Anzahl VMs</div>
                                    <div class="info-value">{{ report.extracted_data.unique_vms }}</div>
                                </div>
                                {% elif report.report_type == 'keepit_backup' %}
                                <div class="info-item">
                                    <div class="info-label">Anzahl Services</div>
                                    <div class="info-value">{{ report.extracted_data.unique_connectors }}</div>
                                </div>
                                {% endif %}

                                {% elif report.report_type == 'entra_devices' %}
                                <div class="info-item">
                                    <div class="info-label">Gesamtanzahl Geräte</div>
                                    <div class="info-value">{{ report.extracted_data.total_devices }}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Inaktive Geräte (>90 Tage)</div>
                                    <div class="info-value" style="color: #dc3545;">{{ report.extracted_data.inactive_devices }}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Inaktivitätsrate</div>
                                    <div class="info-value">{{ "%.1f"|format(report.extracted_data.inactive_rate) }}%</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Geräte ohne Besitzer</div>
                                    <div class="info-value" style="color: #ffc107;">{{ report.extracted_data.devices_without_owner }}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Nicht-konforme Geräte</div>
                                    <div class="info-value" style="color: #dc3545;">{{ report.extracted_data.non_compliant_devices }}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Compliance-Rate</div>
                                    <div class="info-value" style="color: #28a745;">{{ "%.1f"|format(report.extracted_data.compliance_rate) }}%</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Kürzlich registriert (30 Tage)</div>
                                    <div class="info-value">{{ report.extracted_data.recent_registrations }}</div>
                                </div>
                                <div class="info-item">
                                    <div class="info-label">Verwaltete Geräte</div>
                                    <div class="info-value">{{ report.extracted_data.managed_devices }}</div>
                                </div>
                                {% endif %}
                            </div>
                        </div>

                        {% if report.extracted_data.vm_analysis and report.extracted_data.vm_analysis.vms %}
                        <div class="section">
                            <h3>🖥️ VM-Analyse</h3>

                            {% if report.extracted_data.vm_analysis.summary %}
                            <div class="summary-box">
                                <strong>Zusammenfassung:</strong><br>
                                VMs gesamt: {{ report.extracted_data.vm_analysis.summary.total_vms }}<br>
                                Durchschnittliche Erfolgsrate: {{ "%.1f"|format(report.extracted_data.vm_analysis.summary.average_success_rate) }}%<br>
                                Durchschnittlicher Score: {{ "%.1f"|format(report.extracted_data.vm_analysis.summary.average_score) }}
                            </div>
                            {% endif %}

                            {% for vm_name, vm_data in report.extracted_data.vm_analysis.vms.items() %}
                            <div class="vm-card">
                                <div class="vm-header">
                                    <span class="vm-name">{{ vm_name }}</span>
                                    <span class="vm-score {% if vm_data.score == 100 %}vm-score-100{% elif vm_data.score >= 80 %}vm-score-warning{% else %}vm-score-danger{% endif %}">
                                        Score: {{ "%.0f"|format(vm_data.score) }}/100
                                    </span>
                                </div>
                                <div class="vm-content">
                                    <div class="vm-stats">
                                        <div class="vm-stat">
                                            <div class="vm-stat-label">Gesamt</div>
                                            <div class="vm-stat-value">{{ vm_data.total_backups }}</div>
                                        </div>
                                        <div class="vm-stat">
                                            <div class="vm-stat-label">Erfolgreich</div>
                                            <div class="vm-stat-value" style="color: #28a745;">{{ vm_data.successful_backups }}</div>
                                        </div>
                                        <div class="vm-stat">
                                            <div class="vm-stat-label">Fehlgeschlagen</div>
                                            <div class="vm-stat-value" style="color: #dc3545;">{{ vm_data.failed_backups }}</div>
                                        </div>
                                        <div class="vm-stat">
                                            <div class="vm-stat-label">Erfolgsrate</div>
                                            <div class="vm-stat-value">{{ "%.1f"|format(vm_data.success_rate) }}%</div>
                                        </div>
                                    </div>

                                    {% if vm_data.missing_days_critical > 0 %}
                                    <div class="missing-days missing-days-critical">
                                        <h5>⚠️ Kritische fehlende Backups: {{ vm_data.missing_days_critical }} Tag(e)</h5>
                                        <div class="day-list">
                                            {% for day in vm_data.missing_days_list[:10] %}
                                            <span class="day-tag">{{ day }}</span>
                                            {% endfor %}
                                            {% if vm_data.missing_days_list|length > 10 %}
                                            <span class="day-tag">... und {{ vm_data.missing_days_list|length - 10 }} weitere</span>
                                            {% endif %}
                                        </div>
                                    </div>
                                    {% elif vm_data.missing_days_recoverable > 0 %}
                                    <div class="missing-days">
                                        <h5>ℹ️ Wiederherstellbare fehlende Backups: {{ vm_data.missing_days_recoverable }} Tag(e)</h5>
                                        <p style="margin: 5px 0; font-size: 0.85em;">
                                            {% if vm_data.missing_days_recoverable == 1 %}
                                                Dieser fehlende Tag wurde am Folgetag erfolgreich gesichert: {{ vm_data.missing_days_list[0] }}
                                            {% else %}
                                                Diese fehlenden Tage wurden am Folgetag erfolgreich gesichert:
                                                {% for day in vm_data.missing_days_list[:vm_data.missing_days_recoverable] %}
                                                    {{ day }}{% if not loop.last %}, {% endif %}
                                                {% endfor %}
                                            {% endif %}
                                        </p>
                                    </div>
                                    {% endif %}

                                    {% if vm_data.failed_backup_details %}
                                    <div class="failed-backup">
                                        <h5>❌ Fehlgeschlagene Backups</h5>
                                        <table>
                                            <thead>
                                                <tr>
                                                    <th>Datum</th>
                                                    <th>Details</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {% for failed in vm_data.failed_backup_details %}
                                                <tr>
                                                    <td>{{ failed['Start Time'] if failed['Start Time'] else 'N/A' }}</td>
                                                    <td>{{ failed.Details if failed.Details else '-' }}</td>
                                                </tr>
                                                {% endfor %}
                                            </tbody>
                                        </table>
                                    </div>
                                    {% endif %}
                                </div>
                            </div>
                            {% endfor %}
                        </div>
                        {% endif %}

                        {% if report.report_type == 'keepit_backup' %}
                        <div class="section">
                            <h3>📊 Service-Breakdown</h3>

                            {% if report.extracted_data.connector_breakdown %}
                            <div class="summary-box">
                                <strong>Backup-Anzahl pro Service:</strong><br>
                                {% for connector, count in report.extracted_data.connector_breakdown.items() %}
                                    {{ connector }}: {{ count }}<br>
                                {% endfor %}
                            </div>
                            {% endif %}

                            {% if report.extracted_data.type_breakdown %}
                            <div class="summary-box" style="margin-top: 15px;">
                                <strong>Backup-Typen:</strong><br>
                                {% for type, count in report.extracted_data.type_breakdown.items() %}
                                    {{ type }}: {{ count }}<br>
                                {% endfor %}
                            </div>
                            {% endif %}

                            {% if report.extracted_data.failed_backup_details %}
                            <div class="failed-backup" style="margin-top: 15px;">
                                <h5>❌ Fehlgeschlagene Backups ({{ report.extracted_data.failed_backup_details|length }})</h5>
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Service</th>
                                            <th>Typ</th>
                                            <th>Startzeit</th>
                                            <th>Beschreibung</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {% for failed in report.extracted_data.failed_backup_details[:10] %}
                                        <tr>
                                            <td>{{ failed.connector }}</td>
                                            <td>{{ failed.type }}</td>
                                            <td>{{ failed.start_time }}</td>
                                            <td>{{ failed.description }}</td>
                                        </tr>
                                        {% endfor %}
                                        {% if report.extracted_data.failed_backup_details|length > 10 %}
                                        <tr>
                                            <td colspan="4" style="text-align: center; font-style: italic;">
                                                ... und {{ report.extracted_data.failed_backup_details|length - 10 }} weitere fehlgeschlagene Backups
                                            </td>
                                        </tr>
                                        {% endif %}
                                    </tbody>
                                </table>
                            </div>
                            {% endif %}

                            {% if report.extracted_data.missing_backup_days %}
                            <div class="missing-days" style="margin-top: 15px;">
                                <h5>⚠️ Tage ohne Backups ({{ report.extracted_data.missing_backup_days|length }})</h5>
                                <div class="day-list">
                                    {% for day in report.extracted_data.missing_backup_days[:15] %}
                                    <span class="day-tag">{{ day }}</span>
                                    {% endfor %}
                                    {% if report.extracted_data.missing_backup_days|length > 15 %}
                                    <span class="day-tag">... und {{ report.extracted_data.missing_backup_days|length - 15 }} weitere</span>
                                    {% endif %}
                                </div>
                            </div>
                            {% endif %}
                        </div>
                        {% endif %}

                        {% if report.report_type == 'entra_devices' %}
                        <div class="section">
                            <h3>💻 Betriebssystem-Verteilung</h3>
                            {% if report.extracted_data.os_breakdown %}
                            <div class="summary-box">
                                <strong>Geräte nach Betriebssystem:</strong><br>
                                {% for os, count in report.extracted_data.os_breakdown.items() %}
                                    {{ os }}: {{ count }}<br>
                                {% endfor %}
                            </div>
                            {% endif %}
                        </div>

                        {% if report.extracted_data.trust_type_breakdown %}
                        <div class="section">
                            <h3>🔐 Trust Type-Verteilung</h3>
                            <div class="summary-box">
                                <strong>Geräte nach Trust Type:</strong><br>
                                {% for trust_type, count in report.extracted_data.trust_type_breakdown.items() %}
                                    {{ trust_type }}: {{ count }}<br>
                                {% endfor %}
                            </div>
                        </div>
                        {% endif %}

                        {% if report.extracted_data.devices_without_owner_list and report.extracted_data.devices_without_owner_list|length > 0 %}
                        <div class="section">
                            <h3>👤 Geräte ohne Besitzer ({{ report.extracted_data.devices_without_owner_list|length }})</h3>
                            <div class="summary-box">
                                {% for device in report.extracted_data.devices_without_owner_list[:20] %}
                                    <strong>{{ device.displayName }}</strong><br>
                                    <span style="font-size: 0.9em; color: #666;">
                                        OS: {{ device.operatingSystem }}
                                        {% if device.operatingSystemVersion %} ({{ device.operatingSystemVersion }}){% endif %}
                                        | Registriert: {{ device.registrationTime }}
                                    </span><br><br>
                                {% endfor %}
                                {% if report.extracted_data.devices_without_owner_list|length > 20 %}
                                <em>... und {{ report.extracted_data.devices_without_owner_list|length - 20 }} weitere Geräte ohne Besitzer</em>
                                {% endif %}
                            </div>
                        </div>
                        {% endif %}

                        {% if report.extracted_data.inactive_devices_list and report.extracted_data.inactive_devices_list|length > 0 %}
                        <div class="section">
                            <h3>⏰ Inaktive Geräte >90 Tage ({{ report.extracted_data.inactive_devices_list|length }})</h3>
                            <div class="summary-box">
                                {% for device in report.extracted_data.inactive_devices_list[:20] %}
                                    <strong>{{ device.displayName }}</strong><br>
                                    <span style="font-size: 0.9em; color: #666;">
                                        OS: {{ device.operatingSystem }}
                                        | Besitzer: {{ device.registeredOwners if device.registeredOwners else 'Kein Besitzer' }}
                                        | Letzter Sign-In: {{ device.approximateLastSignInDateTime }}
                                    </span><br><br>
                                {% endfor %}
                                {% if report.extracted_data.inactive_devices_list|length > 20 %}
                                <em>... und {{ report.extracted_data.inactive_devices_list|length - 20 }} weitere inaktive Geräte</em>
                                {% endif %}
                            </div>
                        </div>
                        {% endif %}

                        {% if report.extracted_data.recent_registrations_list and report.extracted_data.recent_registrations_list|length > 0 %}
                        <div class="section">
                            <h3>🆕 Kürzlich registrierte Geräte ({{ report.extracted_data.recent_registrations_list|length }})</h3>
                            <div class="summary-box">
                                {% for device in report.extracted_data.recent_registrations_list[:15] %}
                                    <strong>{{ device.displayName }}</strong><br>
                                    <span style="font-size: 0.9em; color: #666;">
                                        OS: {{ device.operatingSystem }}
                                        | Besitzer: {{ device.registeredOwners if device.registeredOwners else 'Kein Besitzer' }}
                                        | Registriert: {{ device.registrationTime }}
                                    </span><br><br>
                                {% endfor %}
                                {% if report.extracted_data.recent_registrations_list|length > 15 %}
                                <em>... und {{ report.extracted_data.recent_registrations_list|length - 15 }} weitere kürzlich registrierte Geräte</em>
                                {% endif %}
                            </div>
                        </div>
                        {% endif %}
                        {% endif %}

                        {% if report.analysis_details.issues %}
                        <div class="section">
                            <h3>⚠️ Gefundene Probleme</h3>
                            <ul>
                            {% for issue in report.analysis_details.issues %}
                                <li>{{ issue }}</li>
                            {% endfor %}
                            </ul>
                        </div>
                        {% endif %}

                    </div>
                </div>
                {% endfor %}

                <div class="footer">
                    <p>Generiert vom Report Analysis Tool v{{ metadata.tool_version }}</p>
                    <p>🤖 Powered by Claude Code & Ollama LLM</p>
                </div>
            </div>

            <script>
                // Report filtering functionality
                (function() {
                    const selector = document.getElementById('reportSelector');
                    const reportCards = document.querySelectorAll('.report-card');
                    const metadataSection = document.querySelector('.metadata');

                    // Function to show/hide reports based on selection
                    function filterReports(selectedValue) {
                        if (selectedValue === 'all') {
                            // Show all reports and metadata
                            reportCards.forEach(card => card.classList.add('active'));
                            if (metadataSection) metadataSection.style.display = 'grid';
                        } else {
                            // Hide all first
                            reportCards.forEach(card => card.classList.remove('active'));

                            // Show only selected report
                            const selectedCard = document.querySelector(`[data-report-index="${selectedValue}"]`);
                            if (selectedCard) {
                                selectedCard.classList.add('active');
                            }

                            // Hide metadata when single report is shown
                            if (metadataSection) metadataSection.style.display = 'none';
                        }

                        // Update URL without reloading page
                        const url = new URL(window.location);
                        if (selectedValue === 'all') {
                            url.searchParams.delete('report');
                        } else {
                            url.searchParams.set('report', selectedValue);
                        }
                        window.history.pushState({}, '', url);
                    }

                    // Handle selection change
                    selector.addEventListener('change', function() {
                        filterReports(this.value);
                    });

                    // Check URL parameters on page load
                    function initializeFromURL() {
                        const params = new URLSearchParams(window.location.search);
                        const reportParam = params.get('report');

                        if (reportParam) {
                            // Set the selector to the specified report
                            selector.value = reportParam;
                            filterReports(reportParam);
                        } else {
                            // Default: show all reports
                            filterReports('all');
                        }
                    }

                    // Initialize on page load
                    initializeFromURL();

                    // Handle browser back/forward buttons
                    window.addEventListener('popstate', function() {
                        initializeFromURL();
                    });
                })();
            </script>
        </body>
        </html>
        """

        def format_month(date_str):
            """Convert '2025-08' to 'August 2025'"""
            try:
                from datetime import datetime
                months_de = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                           'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']
                year, month = date_str.split('-')
                month_name = months_de[int(month) - 1]
                return f"{month_name} {year}"
            except:
                return date_str

        try:
            template = Template(html_template)
            template.globals['format_month'] = format_month
            html_content = template.render(
                metadata=results_data["analysis_metadata"],
                reports=results_data["reports"]
            )
            
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return output_path
            
        except Exception as e:
            logger.error(f"Failed to generate HTML report: {e}")
            return output_path
    
    def create_summary_stats(self, results: List[AnalysisResult]) -> Dict[str, Any]:
        """Create summary statistics for all results."""
        if not results:
            return {}
        
        # Score distribution
        scores = [r.score for r in results]
        score_stats = {
            "min": min(scores),
            "max": max(scores),
            "avg": sum(scores) / len(scores),
            "median": sorted(scores)[len(scores) // 2]
        }
        
        # Risk distribution
        risk_counts = {}
        for result in results:
            risk = result.risk_level
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
        
        # Status distribution
        status_counts = {}
        for result in results:
            status = result.result_status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Processing time stats
        processing_times = [r.processing_info.get('processing_time_seconds', 0) 
                          for r in results]
        time_stats = {
            "total": sum(processing_times),
            "avg": sum(processing_times) / len(processing_times),
            "min": min(processing_times),
            "max": max(processing_times)
        }
        
        return {
            "score_statistics": score_stats,
            "risk_distribution": risk_counts,
            "status_distribution": status_counts,
            "processing_time_statistics": time_stats,
            "total_reports": len(results)
        }