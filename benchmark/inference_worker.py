#!/usr/bin/env python3
"""
QEdge Profiler - ONNX Inference Worker
Runs in subprocess for PID-based memory monitoring.
"""

import argparse
import sys
import os
import time
import tracemalloc

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import onnxruntime as ort
from database import db


def main():
    parser = argparse.ArgumentParser(description='ONNX Inference Worker')
    parser.add_argument('--model-path', required=True, help='Path to ONNX model')
    parser.add_argument('--session-id', type=int, required=True, help='Database session ID')
    parser.add_argument('--iterations', type=int, default=100, help='Number of iterations')
    parser.add_argument('--warmup', type=int, default=2, help='Warmup iterations')
    parser.add_argument('--providers', required=True, help='Comma-separated provider list')
    parser.add_argument('--input-shape', required=True, help='Comma-separated input shape')
    parser.add_argument('--input-name', required=True, help='Input tensor name')
    parser.add_argument('--output-name', required=True, help='Output tensor name')

    args = parser.parse_args()

    print(f"[Worker] PID: {os.getpid()}")
    print(f"[Worker] Session ID: {args.session_id}")
    print(f"[Worker] Model: {os.path.basename(args.model_path)}")

    # Start tracemalloc if enabled
    if os.environ.get('PYTHONTRACEMALLOC') == '1':
        tracemalloc.start()
        print("[Worker] tracemalloc enabled")

    try:
        # Parse arguments
        providers = args.providers.split(',')
        input_shape = tuple(map(int, args.input_shape.split(',')))

        print(f"[Worker] Providers: {providers}")
        print(f"[Worker] Input shape: {input_shape}")

        # Create ONNX Runtime session
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        session = ort.InferenceSession(
            args.model_path,
            sess_options=sess_options,
            providers=providers
        )

        actual_providers = session.get_providers()
        print(f"[Worker] Active provider: {actual_providers[0]}")

        # Generate random input
        input_data = np.random.randn(*input_shape).astype(np.float32)

        # Warmup
        print(f"[Worker] Warmup: {args.warmup} iterations...")
        for _ in range(args.warmup):
            session.run([args.output_name], {args.input_name: input_data})

        # Timed benchmark
        print(f"[Worker] Benchmark: {args.iterations} iterations...")
        latencies = []

        for i in range(args.iterations):
            start = time.perf_counter()
            session.run([args.output_name], {args.input_name: input_data})
            end = time.perf_counter()

            latency_ms = (end - start) * 1000.0
            latencies.append(latency_ms)

            if (i + 1) % 20 == 0:
                print(f"  Progress: {i + 1}/{args.iterations}")

        # Calculate statistics
        latencies_np = np.array(latencies)

        latency_p50 = float(np.percentile(latencies_np, 50))
        latency_p95 = float(np.percentile(latencies_np, 95))
        latency_p99 = float(np.percentile(latencies_np, 99))
        fps = 1000.0 / np.mean(latencies_np)

        print(f"[Worker] Completed: {fps:.2f} FPS, {latency_p50:.2f}ms p50")

        # Store results in database
        db.insert_benchmark_results(
            session_id=args.session_id,
            latency_p50_ms=latency_p50,
            latency_p95_ms=latency_p95,
            latency_p99_ms=latency_p99,
            fps=fps,
            iterations=args.iterations
        )

        # Get tracemalloc snapshot if enabled
        if tracemalloc.is_tracing():
            snapshot = tracemalloc.take_snapshot()
            top_stats = snapshot.statistics('lineno')[:10]

            print("[Worker] Top 10 memory allocations:")
            for stat in top_stats:
                size_mb = stat.size / (1024 * 1024)
                print(f"  {stat.traceback.format()[0]}: {size_mb:.2f} MB")

                # Store in database
                db.insert_tracemalloc_snapshot(
                    session_id=args.session_id,
                    line_no=stat.traceback[0].lineno,
                    file_path=stat.traceback[0].filename,
                    size_mb=size_mb
                )

        # Update session status
        db.update_session_status(args.session_id, 'completed')

        print("[Worker] Success")
        sys.exit(0)

    except Exception as e:
        print(f"[Worker] Error: {e}")
        import traceback
        traceback.print_exc()

        # Update session status to failed
        db.update_session_status(args.session_id, 'failed')

        sys.exit(1)


if __name__ == '__main__':
    main()
