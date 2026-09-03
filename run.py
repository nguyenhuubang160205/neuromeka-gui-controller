#!/usr/bin/env python3
"""
Launcher script for Neuromeka Indy7 GUI Controller
"""
import os
import sys
import subprocess

if __name__ == "__main__":
    gui_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neuromeka_gui")
    main_py = os.path.join(gui_dir, "main.py")
    sys.exit(subprocess.call([sys.executable, main_py], cwd=gui_dir))
