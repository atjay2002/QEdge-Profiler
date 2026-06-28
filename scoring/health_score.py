"""
QEdge Profiler Health Score Calculator
Composite metric combining FPS performance + memory stability.
"""

from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class HealthScoreComponents:
    """Components of the health score calculation."""
    health_score: float  # 0-100
    fps_component: float  # 0-1 (normalized)
    leak_component: float  # 0-1 (inverted)
    memory_component: float  # 0-1 (inverted)


class HealthScoreCalculator:
    """Calculate Model Memory Health Score - unique composite metric."""

    # Weights for each component
    FPS_WEIGHT = 0.4
    LEAK_WEIGHT = 0.4
    MEMORY_WEIGHT = 0.2

    # Baselines for normalization
    FPS_BASELINE = 60.0  # Target FPS (60 = 1.0, higher capped at 1.0)
    MEMORY_BASELINE_MB = 2048.0  # 2GB baseline for peak memory

    @classmethod
    def calculate(
        cls,
        fps: float,
        leak_score: float,
        peak_rss_mb: float
    ) -> HealthScoreComponents:
        """
        Calculate Model Memory Health Score.

        Formula:
        Health Score = (normalized_fps * 0.4) + (inverted_leak_score * 0.4) + (inverted_peak_rss * 0.2)

        Args:
            fps: Frames per second (inference throughput)
            leak_score: Leak score 0-100 (higher = worse)
            peak_rss_mb: Peak memory usage in MB

        Returns:
            HealthScoreComponents with all components
        """
        # Normalize FPS (0-1 scale, 60 FPS = 1.0)
        normalized_fps = min(1.0, fps / cls.FPS_BASELINE)

        # Invert leak score (0-100 → 1-0, lower leak score = better)
        inverted_leak_score = 1.0 - (leak_score / 100.0)

        # Invert peak memory (lower usage = better)
        inverted_peak_rss = 1.0 - min(1.0, peak_rss_mb / cls.MEMORY_BASELINE_MB)

        # Calculate weighted health score
        health_score = (
            normalized_fps * cls.FPS_WEIGHT +
            inverted_leak_score * cls.LEAK_WEIGHT +
            inverted_peak_rss * cls.MEMORY_WEIGHT
        ) * 100.0  # Scale to 0-100

        # Clamp to [0, 100]
        health_score = max(0.0, min(100.0, health_score))

        return HealthScoreComponents(
            health_score=round(health_score, 2),
            fps_component=round(normalized_fps, 4),
            leak_component=round(inverted_leak_score, 4),
            memory_component=round(inverted_peak_rss, 4)
        )

    @staticmethod
    def interpret_score(score: float) -> Dict[str, str]:
        """
        Interpret health score and provide recommendations.

        Args:
            score: Health score (0-100)

        Returns:
            Dictionary with grade, status, and recommendation
        """
        if score >= 90:
            return {
                'grade': 'A',
                'status': 'Excellent',
                'color': 'green',
                'description': 'Fast inference with stable memory usage',
                'recommendation': 'Model is production-ready for edge deployment'
            }
        elif score >= 70:
            return {
                'grade': 'B',
                'status': 'Good',
                'color': 'green',
                'description': 'Minor memory growth, acceptable for most use cases',
                'recommendation': 'Monitor memory usage in production'
            }
        elif score >= 50:
            return {
                'grade': 'C',
                'status': 'Warning',
                'color': 'yellow',
                'description': 'Memory instability detected or slow inference',
                'recommendation': 'Investigate memory leaks or optimize model'
            }
        else:
            return {
                'grade': 'D',
                'status': 'Poor',
                'color': 'red',
                'description': 'Significant memory leak or performance issue',
                'recommendation': 'Fix memory leaks before deployment'
            }

    @staticmethod
    def get_score_breakdown(components: HealthScoreComponents) -> Dict[str, str]:
        """
        Get detailed breakdown of score components.

        Args:
            components: HealthScoreComponents from calculate()

        Returns:
            Dictionary with human-readable component breakdown
        """
        return {
            'overall': f"{components.health_score:.1f}/100",
            'fps_contribution': f"{components.fps_component * 100:.1f}% of optimal",
            'leak_contribution': f"{components.leak_component * 100:.1f}% stable",
            'memory_contribution': f"{components.memory_component * 100:.1f}% efficient"
        }


def calculate_and_interpret(fps: float, leak_score: float, peak_rss_mb: float) -> Dict:
    """
    Convenience function to calculate and interpret health score.

    Args:
        fps: Frames per second
        leak_score: Leak score (0-100)
        peak_rss_mb: Peak memory in MB

    Returns:
        Complete health score report
    """
    calc = HealthScoreCalculator()

    components = calc.calculate(fps, leak_score, peak_rss_mb)
    interpretation = calc.interpret_score(components.health_score)
    breakdown = calc.get_score_breakdown(components)

    return {
        'score': components.health_score,
        'components': {
            'fps_component': components.fps_component,
            'leak_component': components.leak_component,
            'memory_component': components.memory_component
        },
        'interpretation': interpretation,
        'breakdown': breakdown
    }
