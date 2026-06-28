"""
QEdge Profiler - Enhanced Flask Backend
Updated with ONNX benchmarking and export features.
"""

from flask import Flask, Response, request, jsonify, send_file, render_template
import json
import queue
import time
import os
import sys
from collections import defaultdict
from typing import Dict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import db
from monitor import watcher
from monitor.leak_engine import LeakDetector, analyze_memory_trend
from monitor.alerts import AlertSystem
from scoring.health_score import HealthScoreCalculator, calculate_and_interpret
from benchmark.models import ModelRegistry, BackendDetector, get_system_info
from benchmark.runner import BenchmarkRunner, run_inline_benchmark
from reports.exporter import ReportExporter

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['JSON_SORT_KEYS'] = False

# Global state
snapshot_queues: Dict[int, queue.Queue] = defaultdict(lambda: queue.Queue(maxsize=1000))
active_watchers: Dict[int, watcher.MemoryWatcher] = {}
active_benchmarks: Dict[int, BenchmarkRunner] = {}


# ============================================================================
# Main Routes
# ============================================================================

@app.route('/')
def index():
    """Serve enhanced dashboard."""
    return render_template('index.html')


# ============================================================================
# API Routes - System Info
# ============================================================================

@app.route('/api/system/info', methods=['GET'])
def api_system_info():
    """Get system capabilities."""
    info = get_system_info()
    return jsonify(info)


# ============================================================================
# API Routes - Model & Backend Management
# ============================================================================

@app.route('/api/models/list', methods=['GET'])
def api_list_models():
    """List available models."""
    models = ModelRegistry.list_models()
    availability = ModelRegistry.check_model_availability()

    return jsonify({
        'success': True,
        'models': [
            {
                'name': m.name,
                'description': m.description,
                'input_shape': m.input_shape,
                'precisions': m.precisions,
                'available': availability.get(m.name, False)
            }
            for m in models
        ]
    })


@app.route('/api/backends/detect', methods=['GET'])
def api_detect_backends():
    """Detect available backends."""
    backends = BackendDetector.detect_available_backends()
    providers = BackendDetector.get_available_providers()

    provider_details = [
        BackendDetector.get_provider_info(p) for p in providers
    ]

    return jsonify({
        'success': True,
        'backends': backends,
        'providers': providers,
        'provider_details': provider_details
    })


# ============================================================================
# API Routes - Benchmark Control
# ============================================================================

@app.route('/api/benchmark/run', methods=['POST'])
def api_run_benchmark():
    """Run combined benchmark + memory monitoring."""
    data = request.get_json()

    model_name = data.get('model')
    backend = data.get('backend', 'CPU')
    iterations = data.get('iterations', 100)

    if not model_name:
        return jsonify({'success': False, 'error': 'Model name required'}), 400

    try:
        # Create session
        session_id = db.create_session(
            session_type='combined',
            model_name=model_name,
            backend=backend,
            precision='FP32'
        )

        # Start benchmark runner
        runner = BenchmarkRunner(session_id)
        pid = runner.run_benchmark(model_name, backend, iterations)

        if not pid:
            return jsonify({'success': False, 'error': 'Failed to start benchmark'}), 500

        # Update session with PID
        session = db.get_session(session_id)
        db.update_session_status(session_id, 'running')

        # Start memory watcher
        snapshot_queue = snapshot_queues[session_id]
        memory_watcher = watcher.attach_to_process(pid, session_id, snapshot_queue)

        # Store references
        active_benchmarks[session_id] = runner
        active_watchers[session_id] = memory_watcher

        return jsonify({
            'success': True,
            'session_id': session_id,
            'pid': pid,
            'model': model_name,
            'backend': backend
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/benchmark/inline', methods=['POST'])
def api_inline_benchmark():
    """Run inline benchmark (no subprocess isolation)."""
    data = request.get_json()

    model_name = data.get('model')
    backend = data.get('backend', 'CPU')
    iterations = data.get('iterations', 50)

    try:
        results = run_inline_benchmark(model_name, backend, iterations)
        return jsonify({
            'success': True,
            'results': results
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API Routes - Monitor Control
# ============================================================================

@app.route('/api/monitor/attach', methods=['POST'])
def api_attach_monitor():
    """Attach memory watcher to a process."""
    data = request.get_json()
    pid = data.get('pid')

    if not pid:
        return jsonify({'success': False, 'error': 'PID required'}), 400

    try:
        session_id = db.create_session(session_type='watch', pid=pid)
        snapshot_queue = snapshot_queues[session_id]
        memory_watcher = watcher.attach_to_process(pid, session_id, snapshot_queue)
        active_watchers[session_id] = memory_watcher

        return jsonify({
            'success': True,
            'session_id': session_id,
            'pid': pid
        })

    except ProcessLookupError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/monitor/stop/<int:session_id>', methods=['POST'])
def api_stop_monitor(session_id: int):
    """Stop monitoring and analyze results."""
    if session_id not in active_watchers:
        return jsonify({'success': False, 'error': 'Session not found'}), 404

    try:
        # Stop watcher
        memory_watcher = active_watchers[session_id]
        memory_watcher.stop_monitoring()

        # Get snapshots
        snapshots = db.get_snapshots(session_id)

        results = None

        if len(snapshots) >= LeakDetector.MIN_SNAPSHOTS:
            # Analyze for leaks
            leak_result = analyze_memory_trend(snapshots)

            if leak_result and leak_result.is_valid:
                # Store leak analysis
                db.insert_leak_analysis(
                    session_id=session_id,
                    leak_score=leak_result.leak_score,
                    regression_slope=leak_result.regression_slope,
                    r_squared=leak_result.r_squared,
                    growth_rate_mb_per_min=leak_result.growth_rate_mb_per_min,
                    peak_rss_mb=leak_result.peak_rss_mb
                )

                # Calculate health score if benchmark results exist
                benchmark_results = db.get_benchmark_results(session_id)

                if benchmark_results:
                    health_report = calculate_and_interpret(
                        fps=benchmark_results['fps'],
                        leak_score=leak_result.leak_score,
                        peak_rss_mb=leak_result.peak_rss_mb
                    )

                    # Store health score
                    db.insert_health_score(
                        session_id=session_id,
                        health_score=health_report['score'],
                        fps_component=health_report['components']['fps_component'],
                        leak_component=health_report['components']['leak_component'],
                        memory_component=health_report['components']['memory_component']
                    )

                    results = {
                        'leak_score': leak_result.leak_score,
                        'peak_rss_mb': leak_result.peak_rss_mb,
                        'growth_rate_mb_per_min': leak_result.growth_rate_mb_per_min,
                        'health_score': health_report['score'],
                        'message': leak_result.message
                    }
                else:
                    results = {
                        'leak_score': leak_result.leak_score,
                        'peak_rss_mb': leak_result.peak_rss_mb,
                        'growth_rate_mb_per_min': leak_result.growth_rate_mb_per_min,
                        'message': leak_result.message
                    }

        del active_watchers[session_id]

        return jsonify({
            'success': True,
            'session_id': session_id,
            'snapshot_count': len(snapshots),
            'results': results
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# API Routes - Session Management
# ============================================================================

@app.route('/api/sessions', methods=['GET'])
def api_get_sessions():
    """Get session history."""
    limit = int(request.args.get('limit', 50))
    session_type = request.args.get('type')
    model_name = request.args.get('model')

    sessions = db.get_session_history(
        limit=limit,
        session_type=session_type,
        model_name=model_name
    )

    return jsonify({
        'success': True,
        'sessions': sessions,
        'count': len(sessions)
    })


@app.route('/api/sessions/<int:session_id>', methods=['GET'])
def api_get_session(session_id: int):
    """Get detailed session information."""
    session = db.get_session(session_id)

    if not session:
        return jsonify({'success': False, 'error': 'Session not found'}), 404

    snapshots = db.get_snapshots(session_id)
    leak_analysis = db.get_leak_analysis(session_id)
    benchmark_results = db.get_benchmark_results(session_id)
    health_score = db.get_health_score(session_id)
    alerts = db.get_alerts(session_id)
    tracemalloc = db.get_tracemalloc_snapshots(session_id)

    return jsonify({
        'success': True,
        'session': session,
        'snapshots': snapshots,
        'leak_analysis': leak_analysis,
        'benchmark_results': benchmark_results,
        'health_score': health_score,
        'alerts': alerts,
        'tracemalloc': tracemalloc,
        'snapshot_count': len(snapshots)
    })


# ============================================================================
# API Routes - Export
# ============================================================================

@app.route('/api/export/<int:session_id>/csv', methods=['GET'])
def api_export_csv(session_id: int):
    """Export session as CSV."""
    try:
        exporter = ReportExporter(session_id)
        output_path = exporter.export_csv()

        return send_file(
            output_path,
            mimetype='text/csv',
            as_attachment=True,
            download_name=os.path.basename(output_path)
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/export/<int:session_id>/pdf', methods=['GET'])
def api_export_pdf(session_id: int):
    """Export session as PDF."""
    try:
        exporter = ReportExporter(session_id)
        output_path = exporter.export_pdf()

        return send_file(
            output_path,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=os.path.basename(output_path)
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/export/<int:session_id>/json', methods=['GET'])
def api_export_json(session_id: int):
    """Export session as JSON."""
    try:
        exporter = ReportExporter(session_id)
        data = exporter.export_json()

        return jsonify({
            'success': True,
            'data': data
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# SSE Stream
# ============================================================================

@app.route('/stream/<int:session_id>')
def stream(session_id: int):
    """Server-Sent Events stream for real-time updates."""

    def generate():
        snapshot_queue = snapshot_queues[session_id]
        alert_system = AlertSystem(session_id)

        while True:
            try:
                snapshot = snapshot_queue.get(timeout=25)

                # Periodic leak check
                if snapshot_queue.qsize() == 0:
                    snapshots = db.get_snapshots(session_id)

                    if len(snapshots) >= LeakDetector.MIN_SNAPSHOTS:
                        result = analyze_memory_trend(snapshots)

                        if result and result.is_valid:
                            snapshot['leak_score'] = result.leak_score
                            snapshot['message'] = result.message
                            alert_system.check_leak_score(result.leak_score)

                yield f"data: {json.dumps(snapshot)}\n\n"

            except queue.Empty:
                yield ": keepalive\n\n"

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


# ============================================================================
# Demo Routes
# ============================================================================

@app.route('/api/demo/run_leaky', methods=['POST'])
def api_run_leaky():
    """Run the sample leaky script."""
    import subprocess

    script_path = os.path.join(os.path.dirname(__file__), 'scripts', 'sample_leaky.py')

    try:
        proc = subprocess.Popen(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        return jsonify({
            'success': True,
            'pid': proc.pid,
            'script': script_path
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("="*60)
    print("QEdge Profiler - Starting Enhanced Flask Server")
    print("="*60)
    print(f"Dashboard: http://localhost:5000")
    print("="*60)

    # Print system info
    info = get_system_info()
    print(f"\nONNX Runtime: {'✓' if info['onnxruntime_available'] else '✗'}")
    if info['onnxruntime_version']:
        print(f"Version: {info['onnxruntime_version']}")

    print("\nAvailable Backends:")
    for backend, available in info['available_backends'].items():
        status = '✓' if available else '✗'
        print(f"  {status} {backend}")

    print(f"\nModels: {info['models']['available']}/{info['models']['total']} available")
    print("="*60)

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        threaded=True
    )
