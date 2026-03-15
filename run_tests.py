#!/usr/bin/env python3
"""
Lucio AI Briefcase — Run Tests
Usage: python3 run_tests.py
"""
import os, sys, subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)

print("Which test to run?")
print("  1) Test new sources only (9 sources, ~3 min)")
print("  2) Test ALL sources (93 sources, ~15 min)")
choice = input("Enter 1 or 2: ").strip()

if choice == '1':
    subprocess.run([sys.executable, os.path.join('tests', 'test_new_sources.py')])
elif choice == '2':
    subprocess.run([sys.executable, os.path.join('tests', 'test_all_sources.py')])
else:
    print("Invalid choice")
