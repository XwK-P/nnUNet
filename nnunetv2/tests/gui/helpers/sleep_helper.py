"""Test-only helper: sleep for N seconds, exit with given code.

Usage:  python -m nnunetv2.tests.gui.helpers.sleep_helper 0.5 0
"""
import sys
import time

if __name__ == "__main__":
    secs = float(sys.argv[1])
    code = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    time.sleep(secs)
    sys.exit(code)
