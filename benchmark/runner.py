"""
QEdge Profiler Benchmark Runner
Spawns ONNX inference as subprocess for memory monitoring.
"""

import subprocess
import sys
import os
import time
import json
from typing import Optional, Dict, List
import numpy as np

from database import db
from benchmark.models import ModelRegistry, BackendDetector

try:
    import onnxruntime as ort
    ONNXRUNTIME_AVAILABLE = True
except ImportError:
    ONNXRUNTIME_AVAILABLE = False


class BenchmarkRunner:
    """Manages ONNX model benchmarking with subprocess isolation."""

    def __init__(self, session_id: int):
        """
        Initialize benchmark runner.

        Args:
            session_id: Database session ID
        """
        self.session_id = session_id
        self.process: Optional[subprocess.Popen] = None

    def run_benchmark(
        self,
        model_name: str,
        backend: str,
        iterations: int = 100,
        warmup_iterations: int = 2
    ) -> Optional[int]:
        """
        Run benchmark in subprocess and return PID.

        Args:
            model_name: Model name from registry
            backend: 'CPU', 'GPU', or 'NPU'
            iterations: Number of timed inference runs
            warmup_iterations: Number of warmup runs (not timed)

        Returns:
            Process PID or None if failed
        """
        if not ONNXRUNTIME_AVAILABLE:
            raise RuntimeError("onnxruntime not installed")

        # Get model info
        model_info = ModelRegistry.get_model(model_name)
        if not model_info:
            raise ValueError(f"Model '{model_name}' not found in registry")

        model_path = ModelRegistry.get_model_path(model_name)
        if not model_path:
            raise FileNotFoundError(f"Model file not found for '{model_name}'")

        # Get providers for backend
        providers = BackendDetector.get_providers_for_backend(backend)

        # Create worker script arguments
        worker_script = os.path.join(
            os.path.dirname(__file__),
            'inference_worker.py'
        )

        # Launch subprocess
        env = os.environ.copy()
        env['PYTHONTRACEMALLOC'] = '1'  # Enable tracemalloc in child

        cmd = [
            sys.executable,
            worker_script,
            '--model-path', model_path,
            '--session-id', str(self.session_id),
            '--iterations', str(iterations),
            '--warmup', str(warmup_iterations),
            '--providers', ','.join(providers),
            '--input-shape', ','.join(map(str, model_info.input_shape)),
            '--input-name', model_info.input_name,
            '--output-name', model_info.output_name
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            return self.process.pid

        except Exception as e:
            print(f"[BenchmarkRunner] Failed to start subprocess: {e}")
            return None

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for benchmark to complete.

        Args:
            timeout: Optional timeout in seconds

        Returns:
            True if completed successfully, False if timeout/error
        """
        if not self.process:
            return False

        try:
            self.process.wait(timeout=timeout)
            return self.process.returncode == 0
        except subprocess.TimeoutExpired:
            return False

    def stop_benchmark(self):
        """Terminate the benchmark process."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)


class InferenceEngine:
    """
    Direct inference engine for in-process benchmarking.
    Used when subprocess isolation is not needed.
    """

    def __init__(self, model_path: str, providers: List[str]):
        """
        Initialize inference session.

        Args:
            model_path: Path to ONNX model
            providers: List of execution providers
        """
        # Session options for optimal performance
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        # Create inference session
        self.session = ort.InferenceSession(
            model_path,
            sess_options=sess_options,
            providers=providers
        )

        # Get input/output metadata
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.input_shape = self.session.get_inputs()[0].shape

        print(f"[InferenceEngine] Loaded model: {os.path.basename(model_path)}")
        print(f"[InferenceEngine] Providers: {self.session.get_providers()}")

    def run_inference(self, input_data: np.ndarray) -> np.ndarray:
        """
        Run single inference.

        Args:
            input_data: Input tensor

        Returns:
            Output tensor
        """
        return self.session.run(
            [self.output_name],
            {self.input_name: input_data}
        )[0]

    def benchmark(
        self,
        iterations: int = 100,
        warmup_iterations: int = 2
    ) -> Dict:
        """
        Run benchmark and return performance metrics.

        Args:
            iterations: Number of timed runs
            warmup_iterations: Number of warmup runs

        Returns:
            Dictionary with latency, FPS, and timing statistics
        """
        # Generate random input
        input_shape = tuple(
            dim if isinstance(dim, int) else 1
            for dim in self.input_shape
        )
        input_data = np.random.randn(*input_shape).astype(np.float32)

        print(f"[InferenceEngine] Warmup: {warmup_iterations} iterations...")

        # Warmup runs
        for _ in range(warmup_iterations):
            self.run_inference(input_data)

        print(f"[InferenceEngine] Benchmark: {iterations} iterations...")

        # Timed runs
        latencies = []

        for i in range(iterations):
            start = time.perf_counter()
            self.run_inference(input_data)
            end = time.perf_counter()

            latency_ms = (end - start) * 1000.0
            latencies.append(latency_ms)

            if (i + 1) % 10 == 0:
                print(f"  Progress: {i + 1}/{iterations}")

        # Calculate statistics
        latencies_np = np.array(latencies)

        results = {
            'iterations': iterations,
            'latency_mean_ms': float(np.mean(latencies_np)),
            'latency_p50_ms': float(np.percentile(latencies_np, 50)),
            'latency_p95_ms': float(np.percentile(latencies_np, 95)),
            'latency_p99_ms': float(np.percentile(latencies_np, 99)),
            'latency_min_ms': float(np.min(latencies_np)),
            'latency_max_ms': float(np.max(latencies_np)),
            'fps': 1000.0 / np.mean(latencies_np)
        }

        print(f"[InferenceEngine] Completed: {results['fps']:.2f} FPS, {results['latency_p50_ms']:.2f}ms p50")

        return results


def run_inline_benchmark(
    model_name: str,
    backend: str,
    iterations: int = 100
) -> Dict:
    """
    Run benchmark inline (not subprocess) for quick testing.

    Args:
        model_name: Model name from registry
        backend: Backend name
        iterations: Number of iterations

    Returns:
        Benchmark results dictionary
    """
    if not ONNXRUNTIME_AVAILABLE:
        raise RuntimeError("onnxruntime not installed")

    # Get model path
    model_path = ModelRegistry.get_model_path(model_name)
    if not model_path:
        raise FileNotFoundError(f"Model not found: {model_name}")

    # Get providers
    providers = BackendDetector.get_providers_for_backend(backend)

    # Create engine and run
    engine = InferenceEngine(model_path, providers)
    results = engine.benchmark(iterations=iterations)

    results['model'] = model_name
    results['backend'] = backend
    results['providers'] = engine.session.get_providers()

    return results


# Test function
if __name__ == '__main__':
    print("="*60)
    print("QEdge Profiler - Benchmark Runner Test")
    print("="*60)

    from benchmark.models import get_system_info

    # Check system
    info = get_system_info()

    if not info['onnxruntime_available']:
        print("\n✗ ONNX Runtime not installed")
        print("Install: pip install onnxruntime")
        sys.exit(1)

    print(f"\n✓ ONNX Runtime {info['onnxruntime_version']} available")

    available_models = info['models']['list']

    if not available_models:
        print("\n✗ No ONNX models found")
        print(f"Place .onnx files in: {ModelRegistry.MODEL_DIR}")
        sys.exit(1)

    print(f"\n✓ {len(available_models)} model(s) available: {', '.join(available_models)}")

    # Run quick test with first available model
    test_model = available_models[0]
    print(f"\nRunning quick benchmark: {test_model} on CPU (10 iterations)")

    try:
        results = run_inline_benchmark(test_model, 'CPU', iterations=10)

        print("\n✓ Benchmark completed:")
        print(f"  FPS: {results['fps']:.2f}")
        print(f"  Latency p50: {results['latency_p50_ms']:.2f}ms")
        print(f"  Latency p95: {results['latency_p95_ms']:.2f}ms")
        print(f"  Provider: {results['providers'][0]}")

    except Exception as e:
        print(f"\n✗ Benchmark failed: {e}")
        sys.exit(1)
