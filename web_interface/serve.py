#!/usr/bin/env python3
"""
Simple HTTP server for the dashboard.
This serves the web_interface directory and allows CORS for local file access.
"""

import sys
import io
import http.server
import socketserver
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PORT = 8000

class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler with CORS support."""

    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        """Override to use custom logging format."""
        print(f"[{self.log_date_time_string()}] {format % args}")

def serve():
    """Start the HTTP server."""

    # Change to web_interface directory
    web_dir = Path(__file__).parent
    import os
    os.chdir(web_dir)

    print(f"🚀 Starting server in directory: {web_dir}")
    print(f"📡 Server running at: http://localhost:{PORT}")
    print(f"🌐 Open dashboard at: http://localhost:{PORT}/dashboard.html")
    print(f"\nPress Ctrl+C to stop the server\n")

    try:
        with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped")
        sys.exit(0)
    except OSError as e:
        if "address already in use" in str(e).lower():
            print(f"❌ Port {PORT} is already in use. Try closing other servers or use a different port.")
            sys.exit(1)
        else:
            raise

if __name__ == "__main__":
    serve()
