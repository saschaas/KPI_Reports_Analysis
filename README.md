# 🔍 Report Analysis Tool

Ein Python-basiertes Tool zur automatisierten Analyse monatlicher Berichte mit LLM-Unterstützung über Ollama. Das Tool analysiert Berichte von IT-Outsourcing-Anbietern und liefert strukturierte Erkenntnisse über IT-Infrastruktur, Backup-Jobs, Server-Status, E-Mail-Nutzung, Vorfälle und mehr.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

## ✨ Features

### 🎯 Kernfunktionalitäten
- **3-Stufen-Berichtserkennung**: Dateiname → Inhaltsanalyse → LLM-Klassifizierung → Manuelle Auswahl
- **Hybrid-Analyse**: Algorithmische Checks mit LLM-Fallback für maximale Flexibilität
- **Multi-Format-Support**: PDF, Excel (xlsx/xls), CSV, HTML
- **Intelligentes Scoring**: Risikobewertung mit konfigurierbaren Regeln
- **Moderne Web-UI**: Interaktive HTML-Dashboard-Ansicht

### 🔧 Technische Highlights
- **Modulare Architektur**: Einfach erweiterbar für neue Berichtstypen
- **Konfigurationsgesteuert**: YAML-basierte Berichtsdefinitionen
- **Caching**: Optimierte Performance durch intelligentes Caching
- **Fehlertoleranz**: Robuste Verarbeitung mit detailliertem Logging
- **LLM-Integration**: Ollama-basierte KI-Unterstützung

## 🚀 Quick Start

### 1. Installation

```bash
# Repository klonen
git clone <repository-url>
cd report_analysis_tool

# Dependencies installieren
pip install -r requirements.txt

# Umgebungsvariablen einrichten
cp .env.example .env
# .env bearbeiten und Ollama-Konfiguration anpassen
```

### 2. Ollama Setup

```bash
# Ollama installieren (falls noch nicht vorhanden)
curl -fsSL https://ollama.ai/install.sh | sh

# Ollama-Service starten
ollama serve

# Empfohlenes Modell herunterladen
ollama pull llama3.2
```

### 3. Erste Analyse

```bash
# Testberichte ins input-Verzeichnis kopieren
cp your_reports/* input/

# Analyse starten
python src/main.py

# Ergebnisse ansehen
cat output/$(ls -t output/ | head -n1)/results.json

# HTML-Dashboard öffnen
open output/$(ls -t output/ | head -n1)/results.html
```

## 📁 Projektstruktur

```
report_analysis_tool/
├── config/                     # Konfigurationsdateien
│   ├── main_config.yaml       # Hauptkonfiguration
│   └── report_types/           # Berichtsdefinitionen
│       └── example_report.yaml
├── src/                        # Quellcode
│   ├── main.py                # Hauptprogramm
│   ├── core/                  # Kernkomponenten
│   │   ├── llm_handler.py     # Ollama-Integration
│   │   ├── report_detector.py # 3-Stufen-Erkennung
│   │   ├── report_analyzer.py # Hybrid-Analyse
│   │   └── result_handler.py  # Ergebnisverarbeitung
│   ├── parsers/               # Datei-Parser
│   │   ├── base_parser.py     # Parser-Basisklasse
│   │   ├── pdf_parser.py      # PDF-Verarbeitung
│   │   ├── excel_parser.py    # Excel-Verarbeitung
│   │   ├── csv_parser.py      # CSV-Verarbeitung
│   │   └── html_parser.py     # HTML-Verarbeitung
│   └── utils/                 # Hilfsfunktionen
│       ├── config_loader.py   # Konfigurationsverwaltung
│       ├── file_handler.py    # Dateiverwaltung
│       ├── logger.py          # Logging-System
│       └── scoring.py         # Bewertungssystem
├── input/                     # Eingabeordner für Berichte
├── output/                    # Ausgabeordner für Ergebnisse
├── logs/                      # Log-Dateien
├── web_interface/             # Web-Dashboard
│   └── dashboard.html         # Interaktive Ergebnisansicht
├── requirements.txt           # Python-Dependencies
├── .env.example              # Umgebungsvariablen-Template
└── README.md                 # Diese Datei
```

## ⚙️ Konfiguration

### Hauptkonfiguration (`config/main_config.yaml`)

```yaml
ollama:
  model: "llama3.2"
  base_url: "http://localhost:11434"
  timeout: 60
  temperature: 0.1

paths:
  input_directory: "./input"
  output_directory: "./output"
  report_configs: "./config/report_types"
  logs: "./logs"

processing:
  max_retries: 3
  fallback_to_llm: true
  parallel_processing: false
  supported_formats: ["pdf", "xlsx", "xls", "csv", "html"]

logging:
  level: "INFO"
  console: true
  file: true
```

### Berichtsdefinition (Beispiel)

```yaml
report_type:
  id: "backup_report"
  name: "Backup-Bericht"
  description: "Monatlicher Backup-Status-Bericht"
  enabled: true

identification:
  filename_patterns:
    - ".*backup.*\\.xlsx$"
    - ".*sicherung.*\\.pdf$"
  
  content_identifiers:
    required_columns:
      - "Datum"
      - "Job-Name"
      - "Status"
    required_keywords:
      - "Backup"
      - "Sicherung"
    min_matches: 2

analysis:
  algorithmic_checks:
    - check_id: "completeness"
      name: "Vollständigkeitsprüfung"
      type: "column_validation"
      parameters:
        required_columns: ["Datum", "Job-Name", "Status"]
        severity: "high"
    
    - check_id: "failure_rate"
      name: "Fehlerquoten-Prüfung"
      type: "threshold"
      parameters:
        column: "Status"
        value: "Fehler"
        max_count: 5
        severity: "medium"

  scoring:
    base_score: 100
    deductions:
      - condition: "failed_jobs > 0"
        points: 10
        per_occurrence: true
        max_deduction: 50
```

## 📊 3-Stufen-Erkennung

Das Tool verwendet einen intelligenten 3-Stufen-Prozess zur Berichtserkennung:

### Stufe 1: Dateiname-Analyse
- Prüfung gegen konfigurierte Regex-Pattern
- Schnellste Methode für eindeutige Dateinamen
- Beispiel: `backup_september_2024.xlsx` → Backup-Bericht

### Stufe 2: Inhaltsanalyse
- Extraktion von Spaltennamen und Schlüsselwörtern
- Scoring basierend auf Übereinstimmungen
- Mindestanzahl an Treffern erforderlich

### Stufe 3: LLM-Klassifizierung
- KI-basierte Analyse bei unklaren Fällen
- Berichtsspezifische Prompts
- Konfidenz-basierte Entscheidung

### Stufe 4: Manuelle Auswahl
- Interaktive Nutzerauswahl bei Unsicherheit
- Dateivorschau und Schlüsselwort-Extraktion
- Möglichkeit zum Überspringen oder als "Unbekannt" markieren

## 🔄 Hybrid-Analyse-Ansatz

### Primär: Algorithmische Analyse
- **Schnell und deterministisch**
- Konfigurierte Checks (Schwellenwerte, Validierungen)
- Extraktion definierter Werte
- Präzise Ergebnisse für strukturierte Daten

### Fallback: LLM-Analyse
- **Flexibel und robust**
- Aktivierung bei Fehlern oder unerwarteten Formaten
- Tolerant gegenüber Formatänderungen
- Strukturierte Datenextraktion via Prompts

## 📈 Scoring-System

### Basis-Score: 100 Punkte

### Abzüge basierend auf:
- **Fehlende Pflichtfelder**: -20 Punkte
- **Fehlerquoten**: -5 Punkte pro Fehler (max. -30)
- **Datenqualitätsprobleme**: -10 Punkte pro Problem

### Risikobewertung:
- **🟢 Niedrig (86-100)**: Keine kritischen Probleme
- **🟡 Mittel (61-85)**: Kleinere Einschränkungen
- **🔴 Hoch (0-60)**: Signifikante Probleme oder kritische Fehler

### Status-Klassifizierung:
- `ok` - Keine Probleme
- `mit_einschraenkungen` - Kleinere Probleme
- `fehler` - Signifikante Probleme
- `nicht_erfolgreich_analysiert` - Analyse fehlgeschlagen

## 🎮 Verwendung

### Kommandozeile

```bash
# Alle Dateien im Input-Verzeichnis analysieren
python src/main.py

# Spezifische Datei analysieren
python src/main.py --file report.xlsx

# Verfügbare Berichtstypen auflisten
python src/main.py --list-types

# LLM-Verbindung testen
python src/main.py --test-llm

# Cache leeren
python src/main.py --clear-cache

# Hilfe anzeigen
python src/main.py --help
```

### Programmierinterface

```python
from src.utils import ConfigLoader
from src.core import OllamaHandler, ReportDetector, ReportAnalyzer

# Tool initialisieren
config_loader = ConfigLoader()
config = config_loader.load_main_config()

llm_handler = OllamaHandler(
    model="llama3.2",
    base_url="http://localhost:11434"
)

detector = ReportDetector(config_loader, llm_handler)
analyzer = ReportAnalyzer(llm_handler)

# Datei analysieren
detection = detector.detect(Path("report.xlsx"))
if detection:
    result = analyzer.analyze(Path("report.xlsx"), detection)
    print(f"Score: {result.score}, Status: {result.result_status}")
```

## 📋 Ausgabeformat

### JSON-Struktur

```json
{
  "analysis_metadata": {
    "tool_version": "1.0.0",
    "analysis_timestamp": "2024-10-03T14:30:00Z",
    "total_files": 10,
    "successful": 8,
    "failed": 2,
    "success_rate": 80.0,
    "average_score": 82.5
  },
  "reports": [
    {
      "file_info": {
        "name": "backup_report_202409.xlsx",
        "path": "/input/backup_report_202409.xlsx",
        "size_bytes": 45678,
        "format": "xlsx",
        "report_period": "2024-09"
      },
      "report_type": "backup_report",
      "result_status": "ok",
      "risk_level": "niedrig",
      "score": 95,
      "analysis_details": {
        "method": "algorithmic",
        "checks_performed": 5,
        "checks_passed": 5,
        "checks_failed": 0,
        "issues": [],
        "warnings": []
      },
      "extracted_data": {
        "total_jobs": 150,
        "failed_jobs": 2,
        "success_rate": 98.67
      },
      "processing_info": {
        "processing_time_seconds": 2.3,
        "retry_count": 0,
        "parser_used": "ExcelParser"
      },
      "timestamp": "2024-10-03T14:30:15Z"
    }
  ]
}
```

### HTML-Dashboard

Das Tool generiert automatisch ein interaktives HTML-Dashboard mit:
- **Übersichtskarten**: Gesamtstatistiken und KPIs
- **Interaktive Charts**: Risikoverteilung und Berichtstypen
- **Detailansichten**: Einzelne Berichte mit Scoring
- **Filter-/Suchfunktion**: Einfache Navigation
- **Export-Funktionen**: JSON-Download der Ergebnisse

## 🧩 Neue Berichtstypen hinzufügen

### 1. YAML-Konfiguration erstellen

```bash
# Neue Datei erstellen
cp config/report_types/example_report.yaml config/report_types/my_report.yaml
```

### 2. Konfiguration anpassen

```yaml
report_type:
  id: "my_report"
  name: "Mein Spezialbericht"
  description: "Beschreibung des neuen Berichtstyps"
  enabled: true

identification:
  filename_patterns:
    - ".*my_report.*\\.xlsx$"
  
  content_identifiers:
    required_columns:
      - "Spezial-Feld"
    required_keywords:
      - "Spezial-Keyword"
    min_matches: 1

analysis:
  algorithmic_checks:
    - check_id: "special_check"
      name: "Spezial-Prüfung"
      type: "threshold"
      parameters:
        column: "Wert"
        max_count: 10
        severity: "medium"

  extraction_fields:
    - field: "special_metric"
      type: "count"
      source: "all_rows"
      required: true
```

### 3. Tool neu starten

Das neue Berichtsformat wird automatisch erkannt und verwendet.

## 🔧 Erweiterte Konfiguration

### Umgebungsvariablen

```bash
# Ollama-Konfiguration
OLLAMA_MODEL=llama3.2
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_TIMEOUT=60

# Pfad-Konfiguration
INPUT_DIRECTORY=./input
OUTPUT_DIRECTORY=./output
LOGS_DIRECTORY=./logs

# Verarbeitungseinstellungen
MAX_RETRIES=3
FALLBACK_TO_LLM=true
ENABLE_PARALLEL_PROCESSING=false

# Logging-Konfiguration
LOG_LEVEL=INFO
LOG_TO_CONSOLE=true
LOG_TO_FILE=true
```

### Check-Typen

Das Tool unterstützt verschiedene Arten von algorithmischen Checks:

#### `column_validation`
Prüft auf Vorhandensein von Pflichtfeldern
```yaml
parameters:
  required_columns: ["Spalte1", "Spalte2"]
  severity: "high"
```

#### `threshold`
Prüft Schwellenwerte in Daten
```yaml
parameters:
  column: "Status"
  value: "Fehler"
  max_count: 5
  max_percentage: 0.1
  severity: "medium"
```

#### `date_validation`
Validiert Datumsfelder
```yaml
parameters:
  column: "Datum"
  check_continuity: true
  severity: "low"
```

#### `data_quality`
Allgemeine Datenqualitätsprüfung
```yaml
parameters:
  severity: "medium"
```

## 🐛 Troubleshooting

### Häufige Probleme

#### Ollama-Verbindung fehlgeschlagen
```bash
# Prüfen ob Ollama läuft
ollama list

# Service starten
ollama serve

# Modell herunterladen
ollama pull llama3.2
```

#### Parsing-Fehler
```bash
# Log-Level erhöhen
export LOG_LEVEL=DEBUG

# Spezifische Datei testen
python src/main.py --file problematic_file.xlsx --verbose
```

#### Performance-Probleme
```bash
# Cache leeren
python src/main.py --clear-cache

# Parallelverarbeitung aktivieren (experimentell)
# In config/main_config.yaml:
processing:
  parallel_processing: true
```

### Logging

Logs werden sowohl in der Konsole als auch in Dateien ausgegeben:
```
logs/
├── report_analyzer_20241003.log
├── report_analyzer_20241002.log
└── ...
```

Log-Level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

## 🤝 Entwicklung

### Development Setup

```bash
# Development dependencies
pip install -r requirements.txt
pip install black flake8 pytest

# Code formatting
black src/

# Linting
flake8 src/

# Tests ausführen
pytest tests/
```

### Architektur-Prinzipien

1. **Modulare Struktur**: Jede Komponente hat eine klare Verantwortung
2. **Konfigurationsgesteuert**: Keine Hard-coded Logik für Berichtstypen
3. **Fehlertoleranz**: Graceful Handling von Parsing- und Analysefehlern
4. **Erweiterbarkeit**: Einfaches Hinzufügen neuer Parser und Checks
5. **Performance**: Caching und optimierte Verarbeitung

### Contribution Guidelines

1. Fork das Repository
2. Feature Branch erstellen (`git checkout -b feature/amazing-feature`)
3. Changes committen (`git commit -m 'Add amazing feature'`)
4. Branch pushen (`git push origin feature/amazing-feature`)
5. Pull Request erstellen

## 📝 Lizenz

Dieses Projekt steht unter der MIT-Lizenz. Siehe `LICENSE` Datei für Details.

## 🙏 Danksagungen

- **Ollama**: Für die exzellente LLM-Integration
- **pandas**: Für die robuste Datenverarbeitung
- **pdfplumber**: Für die PDF-Extraktion
- **Jinja2**: Für das Template-System
- **Chart.js**: Für die interaktiven Diagramme

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/your-repo/issues)
- **Dokumentation**: [Wiki](https://github.com/your-repo/wiki)
- **Diskussionen**: [GitHub Discussions](https://github.com/your-repo/discussions)

---

**🤖 Powered by Claude Code & Ollama LLM**