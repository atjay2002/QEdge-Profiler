"""
QEdge Profiler Leak Detection Engine
Linear regression-based memory leak detection with confidence scoring.
"""

import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class LeakAnalysisResult:
    """Result of leak analysis."""
    leak_score: float  # 0-100 scale
    regression_slope: float  # MB/sec
    r_squared: float  # Regression fit quality (0-1)
    growth_rate_mb_per_min: float  # MB/min
    peak_rss_mb: float  # Maximum RSS observed
    is_valid: bool  # Whether analysis is valid (min snapshots requirement)
    message: str  # Human-readable status


class LeakDetector:
    """Memory leak detector using linear regression analysis."""

    MIN_SNAPSHOTS = 10  # Minimum snapshots required for valid analysis

    @classmethod
    def analyze(cls, rss_snapshots: List[float], timestamps: Optional[List[int]] = None) -> LeakAnalysisResult:
        """
        Analyze RSS snapshots for memory leaks.

        Args:
            rss_snapshots: List of RSS values in MB
            timestamps: Optional list of timestamps (milliseconds). If None, uses indices.

        Returns:
            LeakAnalysisResult with leak score and analysis details
        """
        # Check minimum snapshots requirement
        if len(rss_snapshots) < cls.MIN_SNAPSHOTS:
            return LeakAnalysisResult(
                leak_score=0.0,
                regression_slope=0.0,
                r_squared=0.0,
                growth_rate_mb_per_min=0.0,
                peak_rss_mb=max(rss_snapshots) if rss_snapshots else 0.0,
                is_valid=False,
                message=f"Insufficient data: {len(rss_snapshots)} snapshots (minimum {cls.MIN_SNAPSHOTS} required)"
            )

        try:
            # Convert to numpy arrays
            rss_array = np.array(rss_snapshots)
            peak_rss = float(np.max(rss_array))

            # Use timestamps if provided, otherwise use indices
            if timestamps is not None and len(timestamps) == len(rss_snapshots):
                # Convert timestamps to seconds from first snapshot
                x_values = np.array([(t - timestamps[0]) / 1000.0 for t in timestamps])
            else:
                # Use snapshot indices as x-values (assuming 0.5s interval)
                x_values = np.arange(len(rss_snapshots)) * 0.5

            # Perform linear regression using numpy.polyfit
            # Returns coefficients [slope, intercept] for degree 1 polynomial
            coefficients = np.polyfit(x_values, rss_array, deg=1)
            slope = float(coefficients[0])  # MB/sec
            intercept = float(coefficients[1])

            # Calculate R² (coefficient of determination)
            # R² = 1 - (SS_res / SS_tot)
            y_pred = slope * x_values + intercept
            ss_res = np.sum((rss_array - y_pred) ** 2)
            ss_tot = np.sum((rss_array - np.mean(rss_array)) ** 2)

            if ss_tot == 0:
                # Constant values - no variation
                r_squared = 1.0 if ss_res == 0 else 0.0
            else:
                r_squared = float(1.0 - (ss_res / ss_tot))
                # Clamp R² to [0, 1] range
                r_squared = max(0.0, min(1.0, r_squared))

            # Calculate growth rate in MB/min
            growth_rate_mb_per_min = slope * 60.0

            # Calculate leak score
            leak_score = cls._calculate_leak_score(slope, r_squared)

            # Determine message
            if leak_score >= 85:
                message = "CRITICAL: Significant memory leak detected"
            elif leak_score >= 70:
                message = "WARNING: Possible memory leak detected"
            elif leak_score >= 40:
                message = "NOTICE: Minor memory growth observed"
            else:
                message = "OK: No significant memory leak detected"

            return LeakAnalysisResult(
                leak_score=leak_score,
                regression_slope=slope,
                r_squared=r_squared,
                growth_rate_mb_per_min=growth_rate_mb_per_min,
                peak_rss_mb=peak_rss,
                is_valid=True,
                message=message
            )

        except Exception as e:
            return LeakAnalysisResult(
                leak_score=0.0,
                regression_slope=0.0,
                r_squared=0.0,
                growth_rate_mb_per_min=0.0,
                peak_rss_mb=max(rss_snapshots) if rss_snapshots else 0.0,
                is_valid=False,
                message=f"Analysis error: {str(e)}"
            )

    @staticmethod
    def _calculate_leak_score(slope: float, r_squared: float) -> float:
        """
        Calculate leak score (0-100) based on regression slope and R² fit quality.

        Formula: min(100, max(0, slope_factor * R² * 100 + 10))
        - slope_factor = slope * 10 (amplifies MB/sec growth)
        - R² weights confidence (R² → 1 means consistent growth = leak)
        - Base score of 10 to avoid zero for minimal growth
        - Clamp to [0, 100] range

        Args:
            slope: Regression slope in MB/sec
            r_squared: R² fit quality (0-1)

        Returns:
            Leak score (0-100)
        """
        # Only positive slopes indicate memory growth
        if slope <= 0:
            return 0.0

        # Amplify slope (MB/sec → leak factor)
        slope_factor = slope * 10.0

        # Calculate score: confidence (R²) weighted growth factor
        score = slope_factor * r_squared * 100.0 + 10.0

        # Clamp to [0, 100]
        return float(min(100.0, max(0.0, score)))

    @staticmethod
    def get_regression_line(
        timestamps: List[int],
        slope: float,
        intercept: float
    ) -> List[Tuple[int, float]]:
        """
        Calculate regression line points for visualization.

        Args:
            timestamps: List of timestamps (milliseconds)
            slope: Regression slope
            intercept: Regression intercept

        Returns:
            List of (timestamp, rss_prediction) tuples
        """
        if not timestamps:
            return []

        # Convert timestamps to seconds from first snapshot
        first_ts = timestamps[0]
        x_values = [(t - first_ts) / 1000.0 for t in timestamps]

        # Calculate predicted RSS values
        regression_points = []
        for ts, x in zip(timestamps, x_values):
            y_pred = slope * x + intercept
            regression_points.append((ts, float(y_pred)))

        return regression_points

    @staticmethod
    def detect_spikes(rss_snapshots: List[float], threshold_factor: float = 2.0) -> List[int]:
        """
        Detect sudden memory spikes (anomalies).

        Args:
            rss_snapshots: List of RSS values in MB
            threshold_factor: Multiplier for std deviation threshold

        Returns:
            List of indices where spikes occur
        """
        if len(rss_snapshots) < 3:
            return []

        rss_array = np.array(rss_snapshots)

        # Calculate differences between consecutive snapshots
        diffs = np.diff(rss_array)

        # Calculate mean and std of differences
        mean_diff = np.mean(diffs)
        std_diff = np.std(diffs)

        if std_diff == 0:
            return []

        # Find spikes: differences exceeding threshold
        threshold = mean_diff + threshold_factor * std_diff
        spike_indices = np.where(diffs > threshold)[0] + 1  # +1 because diff shifts indices

        return spike_indices.tolist()


def analyze_memory_trend(snapshots: List[Dict[str, any]]) -> Optional[LeakAnalysisResult]:
    """
    Convenience function to analyze memory trend from snapshot dictionaries.

    Args:
        snapshots: List of snapshot dicts with 'rss_mb' and 'timestamp' keys

    Returns:
        LeakAnalysisResult or None if no snapshots provided
    """
    if not snapshots:
        return None

    rss_values = [s['rss_mb'] for s in snapshots]
    timestamps = [s['timestamp'] for s in snapshots]

    detector = LeakDetector()
    return detector.analyze(rss_values, timestamps)
