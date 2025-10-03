# 🚀 Setup-Anleitung: Report Analysis Tool

## Problem: Python-Installation

Es wurde festgestellt, dass keine vollständige Python-Installation vorhanden ist. Die Windows Store Python-Aliases sind aktiv, aber keine echte Python-Installation wurde gefunden.

## 1. Python 3.11+ installieren

### Option A: Von python.org (Empfohlen)
1. Besuchen Sie: https://www.python.org/downloads/
2. Laden Sie Python 3.11 oder neuer herunter
3. **WICHTIG**: Bei der Installation "Add Python to PATH" aktivieren
4. Wählen Sie "Install for all users" für eine vollständige Installation

### Option B: Mit Chocolatey
```powershell
# Chocolatey installieren (falls nicht vorhanden)
Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))

# Python installieren
choco install python --version=3.11.9
```

### Option C: Mit winget
```cmd
winget install Python.Python.3.11
```

## 2. Windows Store Python-Aliases deaktivieren

1. Öffnen Sie Windows-Einstellungen
2. Gehen Sie zu "Apps" → "Erweiterte App-Einstellungen" → "App-Ausführungsaliase"
3. Deaktivieren Sie die Einträge für:
   - "App Installer python.exe"
   - "App Installer python3.exe"

## 3. Installation überprüfen

Öffnen Sie eine **neue** Eingabeaufforderung und testen Sie:

```cmd
python --version
pip --version
```

Erwartete Ausgabe:
```
Python 3.11.x
pip 23.x.x from ...
```

## 4. Virtuelle Umgebung einrichten

Nach erfolgreicher Python-Installation:

```cmd
# Zum Projektverzeichnis wechseln
cd "C:\Users\sseidel\Coding\ClaudeCode\KPI-Analyse Tool\report_analysis_tool"

# Virtuelle Umgebung erstellen
python -m venv venv

# Virtuelle Umgebung aktivieren (Windows)
venv\Scripts\activate

# Dependencies installieren
pip install -r requirements.txt
```

## 5. Ollama einrichten

```cmd
# Ollama installieren (falls noch nicht vorhanden)
# Besuchen Sie: https://ollama.ai/download

# Ollama-Service starten
ollama serve

# Empfohlenes Modell herunterladen (in neuer Eingabeaufforderung)
ollama pull llama3.2
```

## 6. Tool testen

```cmd
# Virtuelles Environment aktivieren (falls nicht aktiv)
venv\Scripts\activate

# Tool-Hilfe anzeigen
python src/main.py --help

# LLM-Verbindung testen
python src/main.py --test-llm

# Verfügbare Berichtstypen anzeigen
python src/main.py --list-types
```

## 7. Erste Analyse durchführen

```cmd
# Beispieldateien ins Input-Verzeichnis kopieren
# (Excel-, PDF-, CSV- oder HTML-Dateien)

# Analyse starten
python src/main.py

# Ergebnisse ansehen
# Öffnen Sie das generierte HTML-Dashboard im output-Ordner
```

## Problembehandlung

### "Python wurde nicht gefunden"
- Stellen Sie sicher, dass Python korrekt installiert ist
- Öffnen Sie eine **neue** Eingabeaufforderung nach der Installation
- Überprüfen Sie, ob Python zum PATH hinzugefügt wurde

### "Ollama-Verbindung fehlgeschlagen"
```cmd
# Ollama-Status prüfen
ollama list

# Service neu starten
ollama serve

# Modell erneut herunterladen
ollama pull llama3.2
```

### Dependency-Installationsfehler
```cmd
# Pip aktualisieren
python -m pip install --upgrade pip

# Dependencies einzeln installieren
pip install ollama==0.6.0
pip install pandas==2.3.3
# etc.
```

## Alternative: Conda verwenden

Falls Sie Anaconda/Miniconda bevorzugen:

```cmd
# Environment erstellen
conda create -n report-analysis python=3.11

# Environment aktivieren
conda activate report-analysis

# Ins Projektverzeichnis wechseln
cd "C:\Users\sseidel\Coding\ClaudeCode\KPI-Analyse Tool\report_analysis_tool"

# Dependencies installieren
pip install -r requirements.txt
```

## Nächste Schritte

Nach erfolgreicher Einrichtung:

1. **Konfiguration anpassen**: Editieren Sie `.env` und `config/main_config.yaml`
2. **Berichtstypen definieren**: Erstellen Sie neue YAML-Dateien in `config/report_types/`
3. **Test-Berichte analysieren**: Kopieren Sie Beispieldateien ins `input/`-Verzeichnis
4. **Dashboard öffnen**: Nutzen Sie die generierten HTML-Berichte für eine moderne Übersicht

## Support

Bei Problemen:
- Überprüfen Sie die Logs im `logs/`-Verzeichnis
- Nutzen Sie `--verbose` für detaillierte Ausgaben
- Stellen Sie sicher, dass alle Dependencies installiert sind