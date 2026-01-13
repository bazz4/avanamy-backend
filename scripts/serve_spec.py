#!/usr/bin/env python3
"""
Simple HTTP server to serve the modified Open-Meteo spec
Run with: python serve_spec.py
Then use: http://localhost:5001/openmeteo.yml
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import sys

class SpecHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/openmeteo.yml' or self.path == '/':
            # Serve the v2 modified spec (with /v1/forecast removed)
            self.path = '/openmeteo-modified-v2.yml'
        return super().do_GET()
    
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'text/yaml')
        super().end_headers()

if __name__ == '__main__':
    port = 5001
    server = HTTPServer(('0.0.0.0', port), SpecHandler)
    print(f"\n[*] Serving modified spec at http://localhost:{port}/openmeteo.yml")
    print(f"    Modified spec: openmeteo-modified-v2.yml")
    print(f"    Breaking change: /v1/forecast endpoint REMOVED")
    print(f"    Press Ctrl+C to stop\n")
    server.serve_forever()
