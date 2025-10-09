#!/usr/bin/env python3
"""Regenerate HTML from existing JSON files for testing."""
import json
import sys
import io
from pathlib import Path

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.result_handler import ResultHandler

def regenerate_html(json_path: Path):
    """Regenerate HTML from JSON file."""
    print(f"Loading JSON from: {json_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    config = {
        'paths': {'output_directory': 'output'},
        'output': {'generate_html_report': True}
    }

    rh = ResultHandler(config)
    html_path = json_path.with_suffix('.html')

    print(f"Generating HTML to: {html_path}")
    result = rh._generate_html_report(data, html_path)
    print(f"✅ Generated: {result}")

    return result

if __name__ == "__main__":
    # Find most recent JSON file
    output_dir = Path("output")
    json_files = list(output_dir.glob("*/analysis_results_*.json"))

    if not json_files:
        print("❌ No JSON files found")
        sys.exit(1)

    # Sort by modification time
    json_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    latest_json = json_files[0]

    print(f"📄 Using latest JSON: {latest_json}")
    regenerate_html(latest_json)
