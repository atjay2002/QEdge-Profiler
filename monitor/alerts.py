"""
QEdge Profiler Alert System
Threshold-based alerts with desktop notifications.
"""

import threading
from typing import Optional, Callable
from database import db

# Try to import plyer for desktop notifications
try:
    from plyer import notification as plyer_notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    print("[AlertSystem] Warning: plyer not available - desktop notifications disabled")


class AlertSystem:
    """Manages leak detection alerts and notifications."""

    # Alert thresholds
    WARNING_THRESHOLD = 70.0  # Leak score
    CRITICAL_THRESHOLD = 85.0  # Leak score

    def __init__(self, session_id: int):
        """
        Initialize alert system.

        Args:
            session_id: Database session ID
        """
        self.session_id = session_id
        self._alert_sent = {
            'warning': False,
            'critical': False
        }

    def check_leak_score(self, leak_score: float, model_name: Optional[str] = None):
        """
        Check leak score and send alerts if thresholds exceeded.

        Args:
            leak_score: Current leak score (0-100)
            model_name: Optional model name for notification context
        """
        severity = None
        message = None

        # Check critical threshold first
        if leak_score >= self.CRITICAL_THRESHOLD and not self._alert_sent['critical']:
            severity = 'critical'
            message = f"CRITICAL: Significant memory leak detected (score: {leak_score:.1f})"
            self._alert_sent['critical'] = True
            self._alert_sent['warning'] = True  # Implied

        # Check warning threshold
        elif leak_score >= self.WARNING_THRESHOLD and not self._alert_sent['warning']:
            severity = 'warning'
            message = f"WARNING: Possible memory leak detected (score: {leak_score:.1f})"
            self._alert_sent['warning'] = True

        # Send alert if triggered
        if severity and message:
            self._send_alert(severity, message, model_name)

    def _send_alert(self, severity: str, message: str, model_name: Optional[str] = None):
        """
        Send alert via database storage and desktop notification.

        Args:
            severity: 'warning' or 'critical'
            message: Alert message
            model_name: Optional model name
        """
        # Store in database
        db.insert_alert(self.session_id, severity, message)

        # Send desktop notification in background thread (non-blocking)
        if PLYER_AVAILABLE:
            threading.Thread(
                target=self._send_desktop_notification,
                args=(severity, message, model_name),
                daemon=True
            ).start()

        # Log to console
        prefix = "🚨 CRITICAL" if severity == 'critical' else "⚠️  WARNING"
        print(f"[AlertSystem] {prefix}: {message}")

    @staticmethod
    def _send_desktop_notification(severity: str, message: str, model_name: Optional[str] = None):
        """
        Send desktop notification (runs in background thread).

        Args:
            severity: Alert severity
            message: Alert message
            model_name: Optional model name
        """
        if not PLYER_AVAILABLE:
            return

        try:
            title = "QEdge Profiler - Memory Leak Alert"
            if model_name:
                title += f" ({model_name})"

            # Icon based on severity (platform-specific)
            icon = "dialog-warning" if severity == 'warning' else "dialog-error"

            plyer_notification.notify(
                title=title,
                message=message,
                app_name="QEdge Profiler",
                timeout=10  # seconds
            )

        except Exception as e:
            print(f"[AlertSystem] Failed to send desktop notification: {e}")

    def reset_alerts(self):
        """Reset alert sent flags (for new monitoring session)."""
        self._alert_sent = {
            'warning': False,
            'critical': False
        }

    def get_alert_status(self) -> dict:
        """Get current alert status."""
        return {
            'warning_sent': self._alert_sent['warning'],
            'critical_sent': self._alert_sent['critical']
        }


def check_and_alert(session_id: int, leak_score: float, model_name: Optional[str] = None) -> bool:
    """
    Convenience function to check leak score and send alert if needed.

    Args:
        session_id: Database session ID
        leak_score: Current leak score
        model_name: Optional model name

    Returns:
        True if alert was triggered, False otherwise
    """
    alert_system = AlertSystem(session_id)
    initial_status = alert_system.get_alert_status()

    alert_system.check_leak_score(leak_score, model_name)

    final_status = alert_system.get_alert_status()

    # Check if any new alert was sent
    return (
        (final_status['warning_sent'] and not initial_status['warning_sent']) or
        (final_status['critical_sent'] and not initial_status['critical_sent'])
    )
