# Keepit Backup Report

## Übersicht

Der Keepit Backup Report Analyzer verarbeitet Sicherungsberichte für Microsoft 365 Dienste, die von Keepit erstellt wurden.

## Unterstützte Services

1. **OneDrive** - Persönliche Cloud-Speicher
2. **SharePoint** - Team-Sites und Dokumentenbibliotheken
3. **Exchange** - E-Mail-Sicherungen
4. **User Teams Chats** - Microsoft Teams Chat-Verläufe

## Eingabeformat

### CSV-Datei (Standardformat)

Der Bericht sollte folgende Spalten enthalten (Groß-/Kleinschreibung wird ignoriert):

**Erforderliche Felder:**
- `Connector` - Der Service-Typ (OneDrive, SharePoint, Exchange, Teams)
- `Status` - Ergebnis des Backups (Success, Failed, etc.)

**Optionale Felder:**
- `Initiated by` - Wer den Backup initiiert hat
- `Type` - Backup-Typ oder Operation
- `Description` - Detaillierte Beschreibung/Fehlermeldung
- `Start time` - Startzeit des Backups
- `End time` - Endzeit des Backups

### Dateiidentifikation

Der Report wird automatisch erkannt durch:

1. **Dateinamen-Muster:**
   - `*keepit*backup*.csv`
   - `*donner*reuschel*microsoft*365*.csv`
   - `*microsoft*365*backup*.csv`

2. **Inhaltserkennung:**
   - Muss "Connector" und "Status" Spalten enthalten
   - Sollte Keywords wie "keepit", "backup", "microsoft 365" enthalten

3. **Spezielle Zeilen:**
   - Zeilen die mit "Donner-Reuschel_Microsoft 365" beginnen werden speziell behandelt

## Analyse-Features

### 1. Erfolgsrate-Berechnung

```
Erfolgsrate = (Erfolgreiche Backups / Gesamte Backups) × 100%
```

### 2. Status-Normalisierung

Das Tool normalisiert verschiedene Status-Schreibweisen:
- **Success:** "Success", "Successful", "Succeeded", "Completed", "OK", "Passed"
- **Failed:** "Failed", "Failure", "Error", "Fail", "Unsuccessful"
- **Warning:** "Warning", "Warn", "Attention", "Partial"

### 3. Datums-Format-Erkennung

Automatische Erkennung von verschiedenen Datumsformaten:
- `YYYY-MM-DD`
- `YYYY-DD-MM`
- `DD-MM-YYYY`
- `MM-DD-YYYY`

### 4. Fehlende Backup-Tage

Das Tool identifiziert Tage im Berichtsmonat, an denen **keine** Backups durchgeführt wurden.

**Algorithmus:**
1. Erkenne den Berichtsmonat aus den Start Time Werten
2. Generiere alle Tage des Monats
3. Finde Tage ohne Backup-Einträge

## Scoring-System

### Basis-Score: 100 Punkte

**Abzüge:**
- **-10 Punkte** pro fehlgeschlagenem Backup (max. 50 Punkte)
- **-2 Punkte** pro Warnung (max. 10 Punkte)
- **-5 Punkte** pro Tag ohne Backup (max. 20 Punkte)
- **-15 Punkte** wenn Erfolgsrate < 95%
- **-25 Punkte** wenn Erfolgsrate < 90%

### Risiko-Levels

- **Niedrig (86-100):** Alles in Ordnung
- **Mittel (61-85):** Einige Probleme gefunden
- **Hoch (0-60):** Kritische Probleme

## Ausgabe

### JSON-Ausgabe

```json
{
  "report_type": "keepit_backup",
  "score": 95,
  "risk_level": "niedrig",
  "extracted_data": {
    "total_backups": 120,
    "successful_backups": 118,
    "failed_backups": 2,
    "warning_backups": 0,
    "success_rate": 98.33,
    "failure_rate": 1.67,
    "unique_connectors": 4,
    "connector_breakdown": {
      "OneDrive": 40,
      "SharePoint": 35,
      "Exchange": 30,
      "Teams": 15
    },
    "failed_backup_details": [...],
    "missing_backup_days": ["2025-10-15", "2025-10-16"]
  }
}
```

### HTML-Report

Der HTML-Bericht enthält:

1. **Report-Informationen**
   - Berichtszeitraum
   - Gesamtanzahl Backups
   - Erfolgreiche/Fehlgeschlagene Backups
   - Erfolgsrate
   - Anzahl Services

2. **Service-Breakdown**
   - Backup-Anzahl pro Service (OneDrive, SharePoint, etc.)
   - Backup-Typen Übersicht

3. **Fehlgeschlagene Backups**
   - Tabelle mit allen fehlgeschlagenen Backups
   - Service, Typ, Startzeit, Beschreibung

4. **Tage ohne Backups**
   - Liste der Tage im Berichtsmonat ohne Backups

## Beispiel CSV-Struktur

```csv
Connector,Initiated by,Type,Status,Description,Start time,End time
Donner-Reuschel_Microsoft 365 OneDrive,System,Full,Success,Completed successfully,2025-10-01 02:00:00,2025-10-01 02:15:00
Donner-Reuschel_Microsoft 365 SharePoint,System,Incremental,Success,Completed successfully,2025-10-01 02:20:00,2025-10-01 02:45:00
Donner-Reuschel_Microsoft 365 Exchange,System,Full,Failed,Connection timeout,2025-10-01 03:00:00,2025-10-01 03:05:00
Donner-Reuschel_Microsoft 365 Teams,System,Incremental,Success,Completed successfully,2025-10-01 03:10:00,2025-10-01 03:25:00
```

## Fuzzy Matching

Das Tool verwendet fuzzy matching für Spaltennamen, um verschiedene Schreibweisen zu unterstützen:

- **Threshold:** 0.85 (konfigurierbar)
- **Normalisierung:** Leerzeichen entfernen, Kleinbuchstaben, Unicode-Normalisierung, Diakritika entfernen

**Beispiele:**
- "Connector" = "connector" = "CONNECTOR" = "Service Type"
- "Start time" = "start_time" = "StartTime" = "Begin Time"

## Verwendung

```bash
# Automatische Erkennung
python src/main.py

# Spezifische Datei
python src/main.py --file "input/keepit_backup_october.csv"

# Report-Typen auflisten
python src/main.py --list-types
```

## Konfiguration

Die Keepit-Konfiguration befindet sich in:
```
config/report_types/keepit_backup.yaml
```

Hier können Sie anpassen:
- Identifikationskriterien
- Fuzzy matching Schwellenwerte
- Scoring-Regeln
- Ausgabe-Formate
