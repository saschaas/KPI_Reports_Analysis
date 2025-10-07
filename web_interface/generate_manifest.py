#!/usr/bin/env python3
"""
Generate manifest file for web dashboard.
This script scans the output directory and creates a manifest.json file
listing all available analysis results.
"""

import json
import sys
import io
from pathlib import Path
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def generate_manifest():
    """Generate manifest of all JSON analysis results."""

    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_dir = project_root / "output"

    if not output_dir.exists():
        print(f"Output directory not found: {output_dir}")
        return

    manifest = {
        "generated_at": datetime.now().isoformat(),
        "months": {}
    }

    # Scan all month directories
    for month_dir in sorted(output_dir.glob("*/"), reverse=True):
        if not month_dir.is_dir():
            continue

        month_name = month_dir.name
        json_files = []

        # Find all JSON files in this month
        for json_file in sorted(month_dir.glob("analysis_results_*.json"), reverse=True):
            file_stat = json_file.stat()
            json_files.append({
                "filename": json_file.name,
                "path": f"../output/{month_name}/{json_file.name}",
                "size": file_stat.st_size,
                "modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat()
            })

        if json_files:
            manifest["months"][month_name] = {
                "count": len(json_files),
                "files": json_files,
                "latest": json_files[0]["filename"] if json_files else None
            }

    # Write manifest to web_interface directory
    manifest_path = script_dir / "manifest.json"

    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        print(f"✅ Manifest generated successfully: {manifest_path}")
        print(f"   Found {len(manifest['months'])} months with analysis results")

        for month, data in manifest['months'].items():
            print(f"   - {month}: {data['count']} file(s)")

        return True

    except Exception as e:
        print(f"❌ Failed to write manifest: {e}")
        return False

if __name__ == "__main__":
    success = generate_manifest()
    sys.exit(0 if success else 1)
