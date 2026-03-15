#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════╗
║             LUCIO AI BRIEFCASE — One-Click Launcher          ║
║                                                              ║
║  Double-click this file (or run: python3 run.py)             ║
║  Opens the dashboard in your browser automatically.          ║
║  Press Ctrl+C in terminal to stop.                           ║
╚═══════════════════════════════════════════════════════════════╝

No installs needed — runs on Python 3.8+ (pre-installed on macOS).
All downloads saved to ~/Desktop/Repositories/
"""
import os, sys, subprocess

# Ensure we're in the project root regardless of how this was launched
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

# Add backend to Python path
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

if __name__ == '__main__':
    print()
    print("═" * 60)
    print("  Lucio AI Briefcase")
    print("  Dashboard: http://localhost:8765")
    print("  Press Ctrl+C to stop")
    print("═" * 60)
    print()

    # Import and run the server
    import server
    server.main()
