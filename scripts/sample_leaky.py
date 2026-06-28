#!/usr/bin/env python3
"""
QEdge Profiler - Sample Leaky Script
Intentionally leaks memory for testing the leak detection system.
"""

import time
import sys

def main():
    """Leak memory at a steady rate (1MB every 0.5s)."""
    print("="*60)
    print("QEdge Profiler - Sample Leaky Script")
    print("Leaking 1MB every 0.5 seconds...")
    print(f"PID: {sys.argv[0] if len(sys.argv) > 1 else 'unknown'}")
    print("="*60)

    leak_list = []
    iteration = 0

    try:
        while True:
            # Leak 1MB per iteration
            leak_list.append(' ' * 1024 * 1024)
            iteration += 1

            # Print status every 10 iterations (5 seconds)
            if iteration % 10 == 0:
                leaked_mb = len(leak_list)
                print(f"[{iteration:4d}] Leaked: {leaked_mb} MB")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print(f"\n\nStopped. Total leaked: {len(leak_list)} MB")
        print("Cleanup not performed - memory remains allocated.")


if __name__ == '__main__':
    main()
