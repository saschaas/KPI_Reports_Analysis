@echo off
echo ================================
echo Report Analysis Tool - Setup
echo ================================
echo.

:: Prüfe Python-Installation
echo [1/6] Prüfe Python-Installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python nicht gefunden!
    echo.
    echo Bitte installieren Sie Python 3.11+ von https://www.python.org/downloads/
    echo WICHTIG: "Add Python to PATH" aktivieren!
    echo.
    echo Alternativ Windows Store Python-Aliases deaktivieren:
    echo Einstellungen → Apps → Erweiterte App-Einstellungen → App-Ausführungsaliase
    echo.
    pause
    exit /b 1
)

python --version
echo ✅ Python gefunden!
echo.

:: Prüfe pip
echo [2/6] Prüfe pip...
pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ pip nicht gefunden!
    pause
    exit /b 1
)
echo ✅ pip verfügbar!
echo.

:: Erstelle virtuelle Umgebung
echo [3/6] Erstelle virtuelle Umgebung...
if exist "venv" (
    echo ⚠️  venv-Ordner existiert bereits. Lösche alten venv...
    rmdir /s /q venv
)

python -m venv venv
if errorlevel 1 (
    echo ❌ Fehler beim Erstellen der virtuellen Umgebung!
    pause
    exit /b 1
)
echo ✅ Virtuelle Umgebung erstellt!
echo.

:: Aktiviere virtuelle Umgebung
echo [4/6] Aktiviere virtuelle Umgebung...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ Fehler beim Aktivieren der virtuellen Umgebung!
    pause
    exit /b 1
)
echo ✅ Virtuelle Umgebung aktiviert!
echo.

:: Aktualisiere pip
echo [5/6] Aktualisiere pip...
python -m pip install --upgrade pip
echo ✅ pip aktualisiert!
echo.

:: Installiere Dependencies
echo [6/6] Installiere Dependencies...
echo Das kann einige Minuten dauern...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Fehler beim Installieren der Dependencies!
    echo.
    echo Versuche einzelne Installation der Kern-Dependencies...
    pip install ollama==0.6.0
    pip install pandas==2.3.3
    pip install pyyaml==6.0.2
    pip install python-dotenv==1.0.1
    echo.
    echo Bitte prüfen Sie die Logs und versuchen Sie:
    echo pip install -r requirements.txt
    pause
    exit /b 1
)
echo ✅ Dependencies installiert!
echo.

:: Erstelle .env-Datei falls nicht vorhanden
if not exist ".env" (
    echo [Bonus] Erstelle .env-Datei...
    copy .env.example .env
    echo ✅ .env-Datei erstellt! Bitte anpassen nach Bedarf.
    echo.
)

:: Teste Installation
echo [Test] Teste Tool-Installation...
python src/main.py --help >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Tool-Test fehlgeschlagen. Prüfen Sie die Installation.
) else (
    echo ✅ Tool erfolgreich installiert!
)
echo.

echo ================================
echo 🎉 Setup abgeschlossen!
echo ================================
echo.
echo Nächste Schritte:
echo 1. Ollama installieren: https://ollama.ai/download
echo 2. Ollama-Service starten: ollama serve
echo 3. Modell herunterladen: ollama pull llama3.2
echo 4. Tool testen: python src/main.py --test-llm
echo.
echo Zum Aktivieren der venv in Zukunft:
echo   venv\Scripts\activate
echo.
echo Zum Starten der Analyse:
echo   python src/main.py
echo.
pause