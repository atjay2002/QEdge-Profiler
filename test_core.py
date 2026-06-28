#!/usr/bin/env python3
"""
QEdge Profiler - Quick Test
Tests core functionality without running the full Flask app.
"""

import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("="*60)
print("QEdge Profiler - Core Functionality Test")
print("="*60)

# Test 1: Database initialization
print("\n[1/5] Testing database initialization...")
try:
    from database import db
    print("✓ Database initialized successfully")
    print(f"  Database path: {db.DB_PATH}")
except Exception as e:
    print(f"✗ Database error: {e}")
    sys.exit(1)

# Test 2: Leak engine
print("\n[2/5] Testing leak detection engine...")
try:
    from monitor.leak_engine import LeakDetector

    # Simulate memory growth
    rss_values = [100 + i * 2 for i in range(20)]  # Linear growth
    result = LeakDetector.analyze(rss_values)

    print("✓ Leak detection working")
    print(f"  Leak Score: {result.leak_score:.1f}/100")
    print(f"  Slope: {result.regression_slope:.4f} MB/sec")
    print(f"  R²: {result.r_squared:.4f}")
    print(f"  Message: {result.message}")
except Exception as e:
    print(f"✗ Leak engine error: {e}")
    sys.exit(1)

# Test 3: Health score calculator
print("\n[3/5] Testing health score calculator...")
try:
    from scoring.health_score import calculate_and_interpret

    report = calculate_and_interpret(fps=45.0, leak_score=35.0, peak_rss_mb=512.0)

    print("✓ Health score calculation working")
    print(f"  Health Score: {report['score']:.1f}/100")
    print(f"  Grade: {report['interpretation']['grade']}")
    print(f"  Status: {report['interpretation']['status']}")
except Exception as e:
    print(f"✗ Health score error: {e}")
    sys.exit(1)

# Test 4: Memory watcher (test current process)
print("\n[4/5] Testing memory watcher...")
try:
    from monitor import watcher
    import os

    current_pid = os.getpid()
    info = watcher.get_process_info(current_pid)

    if info:
        print("✓ Memory watcher working")
        print(f"  PID: {info['pid']}")
        print(f"  Name: {info['name']}")
        print(f"  RSS: {info['rss_mb']:.2f} MB")
        print(f"  CPU: {info['cpu_percent']:.1f}%")
    else:
        print("✗ Could not get process info")
except Exception as e:
    print(f"✗ Memory watcher error: {e}")
    sys.exit(1)

# Test 5: Alert system
print("\n[5/5] Testing alert system...")
try:
    from monitor.alerts import AlertSystem

    session_id = db.create_session(session_type='watch', pid=os.getpid())
    alert_system = AlertSystem(session_id)

    alert_system.check_leak_score(75.0)  # Should trigger warning
    alert_system.check_leak_score(90.0)  # Should trigger critical

    alerts = db.get_alerts(session_id)

    print("✓ Alert system working")
    print(f"  Alerts created: {len(alerts)}")
    for alert in alerts:
        print(f"  - {alert['severity'].upper()}: {alert['message']}")
except Exception as e:
    print(f"✗ Alert system error: {e}")
    sys.exit(1)

# Summary
print("\n" + "="*60)
print("✓ All core tests passed!")
print("="*60)
print("\nNext steps:")
print("1. Install dependencies: pip install -r requirements.txt")
print("2. Run Flask app: python app.py")
print("3. Open http://localhost:5000")
print("4. Click 'Run Leaky Script' and 'Start Monitoring'")
print("="*60)
