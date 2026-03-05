#!/usr/bin/env python3
"""
DHG Hardware Spec Collector — Universal Launcher
Auto-detects OS and runs the appropriate collector.
Output: hw_specs_<hostname>_<timestamp>.csv
"""

import platform
import subprocess
import sys
import os

def main():
    os_type = platform.system()
    script_dir = os.path.dirname(os.path.abspath(__file__))

    script_map = {
        'Linux':   'collect_linux.py',
        'Windows': 'collect_windows.py',
        'Darwin':  'collect_macos.py',
    }

    script = script_map.get(os_type)
    if not script:
        print(f"[ERROR] Unsupported OS: {os_type}")
        sys.exit(1)

    script_path = os.path.join(script_dir, script)
    print(f"[HW-SPEC] Detected OS: {os_type}")
    print(f"[HW-SPEC] Running: {script_path}")

    result = subprocess.run([sys.executable, script_path], check=False)
    sys.exit(result.returncode)

if __name__ == '__main__':
    main()
