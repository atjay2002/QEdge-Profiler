// QEdge Profiler - Dashboard JavaScript
// Real-time monitoring with Chart.js

// Global state
let currentSessionId = null;
let eventSource = null;
let snapshotCount = 0;

// Chart instances
let rssChart = null;
let cpuChart = null;
let benchmarkChart = null;

// Chart configuration
const chartColors = {
    primary: '#7c3aed',
    secondary: '#10b981',
    danger: '#ef4444',
    warning: '#f59e0b'
};

const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            labels: {
                color: '#e2e8f0'
            }
        }
    },
    scales: {
        x: {
            ticks: { color: '#94a3b8' },
            grid: { color: '#334155' }
        },
        y: {
            ticks: { color: '#94a3b8' },
            grid: { color: '#334155' }
        }
    },
    animation: {
        duration: 0 // Disable animation for real-time
    }
};

// ============================================================================
// Initialization
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initializeCharts();
    loadSystemInfo();
    loadModels();
    loadHistory();
});

function initializeCharts() {
    // RSS Chart
    const rssCtx = document.getElementById('rss-chart').getContext('2d');
    rssChart = new Chart(rssCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'RSS (MB)',
                data: [],
                borderColor: chartColors.primary,
                backgroundColor: chartColors.primary + '20',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        },
        options: chartOptions
    });

    // CPU Chart
    const cpuCtx = document.getElementById('cpu-chart').getContext('2d');
    cpuChart = new Chart(cpuCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'CPU (%)',
                data: [],
                borderColor: chartColors.secondary,
                backgroundColor: chartColors.secondary + '20',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        },
        options: chartOptions
    });

    // Benchmark Chart
    const benchCtx = document.getElementById('benchmark-chart').getContext('2d');
    benchmarkChart = new Chart(benchCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'FPS',
                data: [],
                backgroundColor: chartColors.primary,
                borderColor: chartColors.primary,
                borderWidth: 1
            }]
        },
        options: {
            ...chartOptions,
            scales: {
                ...chartOptions.scales,
                y: {
                    ...chartOptions.scales.y,
                    beginAtZero: true
                }
            }
        }
    });
}

// ============================================================================
// Tab Navigation
// ============================================================================

function showTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
    });

    // Remove active class from all tabs
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });

    // Show selected tab
    document.getElementById(`tab-${tabName}`).classList.remove('hidden');

    // Add active class to clicked tab
    event.target.classList.add('active');
}

// ============================================================================
// Memory Monitoring
// ============================================================================

async function attachProcess() {
    const pid = document.getElementById('pid-input').value;

    if (!pid) {
        alert('Please enter a PID');
        return;
    }

    try {
        const response = await fetch('/api/monitor/attach', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pid: parseInt(pid)})
        });

        const data = await response.json();

        if (data.success) {
            currentSessionId = data.session_id;
            document.getElementById('metric-session').textContent = data.session_id;

            log(`Started monitoring PID ${pid} (Session ${data.session_id})`, 'success');

            // Reset charts
            resetCharts();
            snapshotCount = 0;

            // Start SSE stream
            startStreaming(data.session_id);
        } else {
            log(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        log(`Error: ${error}`, 'error');
    }
}

async function stopMonitoring() {
    if (!currentSessionId) {
        alert('No active session');
        return;
    }

    try {
        const response = await fetch(`/api/monitor/stop/${currentSessionId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            log(`Stopped monitoring session ${currentSessionId}`, 'success');

            if (eventSource) {
                eventSource.close();
                eventSource = null;
            }

            // Show results
            if (data.results) {
                showAlert(
                    `Session Complete: Leak Score ${data.results.leak_score.toFixed(1)}, Peak RSS ${data.results.peak_rss_mb.toFixed(2)} MB`,
                    data.results.leak_score >= 85 ? 'critical' : (data.results.leak_score >= 70 ? 'warning' : 'info')
                );

                // Offer export options
                setTimeout(() => {
                    if (confirm('Export this session as PDF?')) {
                        exportSession(currentSessionId, 'pdf');
                    }
                }, 1000);
            }

            currentSessionId = null;
        }
    } catch (error) {
        log(`Error: ${error}`, 'error');
    }
}

function startStreaming(sessionId) {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(`/stream/${sessionId}`);

    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateMetrics(data);
        updateCharts(data);
    };

    eventSource.onerror = () => {
        log('SSE connection lost', 'warning');
    };
}

function updateMetrics(data) {
    if (data.rss_mb !== undefined) {
        document.getElementById('metric-rss').textContent = data.rss_mb.toFixed(2);
    }

    if (data.cpu_percent !== undefined) {
        document.getElementById('metric-cpu').textContent = data.cpu_percent.toFixed(1);
    }

    if (data.leak_score !== undefined) {
        const leakElement = document.getElementById('metric-leak');
        leakElement.textContent = data.leak_score.toFixed(1);

        // Color code leak score
        if (data.leak_score >= 85) {
            leakElement.style.color = chartColors.danger;
        } else if (data.leak_score >= 70) {
            leakElement.style.color = chartColors.warning;
        } else {
            leakElement.style.color = chartColors.secondary;
        }

        // Show alert if high
        if (data.leak_score >= 70 && !document.getElementById(`alert-${currentSessionId}`)) {
            showAlert(
                data.message || 'Memory leak detected',
                data.leak_score >= 85 ? 'critical' : 'warning'
            );
        }
    }

    snapshotCount++;
}

function updateCharts(data) {
    const timestamp = new Date(data.timestamp).toLocaleTimeString();

    // RSS Chart
    rssChart.data.labels.push(timestamp);
    rssChart.data.datasets[0].data.push(data.rss_mb);

    // Cap at 500 points
    if (rssChart.data.labels.length > 500) {
        rssChart.data.labels.shift();
        rssChart.data.datasets[0].data.shift();
    }

    rssChart.update('none');

    // CPU Chart
    if (data.cpu_percent !== undefined) {
        cpuChart.data.labels.push(timestamp);
        cpuChart.data.datasets[0].data.push(data.cpu_percent);

        if (cpuChart.data.labels.length > 500) {
            cpuChart.data.labels.shift();
            cpuChart.data.datasets[0].data.shift();
        }

        cpuChart.update('none');
    }
}

function resetCharts() {
    rssChart.data.labels = [];
    rssChart.data.datasets[0].data = [];
    rssChart.update();

    cpuChart.data.labels = [];
    cpuChart.data.datasets[0].data = [];
    cpuChart.update();
}

// ============================================================================
// Benchmarking
// ============================================================================

async function runBenchmark() {
    const model = document.getElementById('model-select').value;
    const backend = document.getElementById('backend-select').value;
    const iterations = parseInt(document.getElementById('iterations-input').value);

    if (!model) {
        alert('Please select a model');
        return;
    }

    log(`Starting benchmark: ${model} on ${backend} (${iterations} iterations)`, 'info');

    try {
        const response = await fetch('/api/benchmark/run', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({model, backend, iterations})
        });

        const data = await response.json();

        if (data.success) {
            currentSessionId = data.session_id;
            document.getElementById('metric-session').textContent = data.session_id;

            log(`Benchmark started: PID ${data.pid}, Session ${data.session_id}`, 'success');

            // Switch to monitor tab and start streaming
            showTab('monitor');
            resetCharts();
            startStreaming(data.session_id);
        } else {
            log(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        log(`Error: ${error}`, 'error');
    }
}

async function runInlineBenchmark() {
    const model = document.getElementById('model-select').value;
    const backend = document.getElementById('backend-select').value;
    const iterations = 50;

    if (!model) {
        alert('Please select a model');
        return;
    }

    log(`Running inline benchmark: ${model} on ${backend}...`, 'info');

    try {
        const response = await fetch('/api/benchmark/inline', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({model, backend, iterations})
        });

        const data = await response.json();

        if (data.success) {
            const results = data.results;

            document.getElementById('benchmark-results').innerHTML = `
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <div class="text-slate-400 text-sm">FPS</div>
                        <div class="text-2xl font-bold text-purple-400">${results.fps.toFixed(2)}</div>
                    </div>
                    <div>
                        <div class="text-slate-400 text-sm">Latency p50</div>
                        <div class="text-2xl font-bold text-green-400">${results.latency_p50_ms.toFixed(2)} ms</div>
                    </div>
                    <div>
                        <div class="text-slate-400 text-sm">Latency p95</div>
                        <div class="text-2xl font-bold">${results.latency_p95_ms.toFixed(2)} ms</div>
                    </div>
                    <div>
                        <div class="text-slate-400 text-sm">Latency p99</div>
                        <div class="text-2xl font-bold">${results.latency_p99_ms.toFixed(2)} ms</div>
                    </div>
                </div>
                <div class="mt-4 p-3 bg-slate-800 rounded">
                    <div class="text-sm text-slate-400">Provider: ${results.providers[0]}</div>
                </div>
            `;

            log(`Benchmark complete: ${results.fps.toFixed(2)} FPS`, 'success');

            // Update benchmark chart
            benchmarkChart.data.labels.push(`${model}\n${backend}`);
            benchmarkChart.data.datasets[0].data.push(results.fps);
            benchmarkChart.update();
        } else {
            log(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        log(`Error: ${error}`, 'error');
    }
}

// ============================================================================
// History
// ============================================================================

async function loadHistory() {
    try {
        const response = await fetch('/api/sessions?limit=20');
        const data = await response.json();

        const tbody = document.getElementById('history-tbody');
        tbody.innerHTML = '';

        if (data.sessions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="p-3 text-center text-slate-400">No sessions yet</td></tr>';
            return;
        }

        data.sessions.forEach(session => {
            const startTime = new Date(session.start_time * 1000).toLocaleString();
            const statusColor = session.status === 'completed' ? 'text-green-400' :
                              (session.status === 'running' ? 'text-yellow-400' : 'text-red-400');

            tbody.innerHTML += `
                <tr class="border-b border-slate-700 hover:bg-slate-800">
                    <td class="p-3">${session.id}</td>
                    <td class="p-3">${session.session_type}</td>
                    <td class="p-3">${session.model_name || '-'}</td>
                    <td class="p-3">${session.backend || '-'}</td>
                    <td class="p-3 ${statusColor}">${session.status}</td>
                    <td class="p-3">${startTime}</td>
                    <td class="p-3">
                        <button onclick="viewSession(${session.id})" class="text-purple-400 hover:text-purple-300 mr-2">View</button>
                        <button onclick="exportSession(${session.id}, 'pdf')" class="text-green-400 hover:text-green-300">PDF</button>
                    </td>
                </tr>
            `;
        });
    } catch (error) {
        log(`Error loading history: ${error}`, 'error');
    }
}

async function viewSession(sessionId) {
    try {
        const response = await fetch(`/api/sessions/${sessionId}`);
        const data = await response.json();

        if (data.success) {
            // Show session details in a modal or new view
            alert(`Session ${sessionId}\nSnapshots: ${data.snapshot_count}\nStatus: ${data.session.status}`);
            // TODO: Implement proper session detail view
        }
    } catch (error) {
        log(`Error viewing session: ${error}`, 'error');
    }
}

async function exportSession(sessionId, format) {
    try {
        window.open(`/api/export/${sessionId}/${format}`, '_blank');
        log(`Exporting session ${sessionId} as ${format.toUpperCase()}...`, 'success');
    } catch (error) {
        log(`Error exporting session: ${error}`, 'error');
    }
}

// ============================================================================
// System Info
// ============================================================================

async function loadSystemInfo() {
    try {
        const response = await fetch('/api/system/info');
        const data = await response.json();

        // ONNX Runtime Info
        const onnxHtml = data.onnxruntime_available ?
            `<div class="text-green-400 text-xl">✓ Available</div>
             <div class="text-slate-400 mt-2">Version: ${data.onnxruntime_version}</div>` :
            `<div class="text-red-400 text-xl">✗ Not Available</div>
             <div class="text-slate-400 mt-2">Install: pip install onnxruntime</div>`;

        document.getElementById('system-onnx').innerHTML = onnxHtml;

        // Backends
        let backendsHtml = '<div class="space-y-3">';
        for (const [backend, available] of Object.entries(data.available_backends)) {
            const icon = available ? '✓' : '✗';
            const color = available ? 'text-green-400' : 'text-slate-500';
            backendsHtml += `<div class="${color} text-lg">${icon} ${backend}</div>`;
        }
        backendsHtml += '</div>';
        document.getElementById('system-backends').innerHTML = backendsHtml;

        // Models
        let modelsHtml = `<div class="text-slate-400 mb-3">${data.models.available}/${data.models.total} available</div>`;
        modelsHtml += '<div class="space-y-2">';
        for (const [model, available] of Object.entries(data.models.availability)) {
            const icon = available ? '✓' : '✗';
            const color = available ? 'text-green-400' : 'text-slate-500';
            modelsHtml += `<div class="${color}">${icon} ${model}</div>`;
        }
        modelsHtml += '</div>';
        document.getElementById('system-models').innerHTML = modelsHtml;

    } catch (error) {
        log(`Error loading system info: ${error}`, 'error');
    }
}

async function loadModels() {
    try {
        const response = await fetch('/api/models/list');
        const data = await response.json();

        const select = document.getElementById('model-select');
        select.innerHTML = '<option value="">Select a model...</option>';

        data.models.forEach(model => {
            if (model.available) {
                select.innerHTML += `<option value="${model.name}">${model.name} - ${model.description}</option>`;
            }
        });
    } catch (error) {
        log(`Error loading models: ${error}`, 'error');
    }
}

// ============================================================================
// Demo
// ============================================================================

async function runLeakyScript() {
    try {
        const response = await fetch('/api/demo/run_leaky', {method: 'POST'});
        const data = await response.json();

        if (data.success) {
            log(`Started leaky script with PID ${data.pid}`, 'success');
            document.getElementById('pid-input').value = data.pid;

            // Auto-attach after 1 second
            setTimeout(() => {
                attachProcess();
            }, 1000);
        }
    } catch (error) {
        log(`Error: ${error}`, 'error');
    }
}

// ============================================================================
// UI Helpers
// ============================================================================

function showAlert(message, severity = 'warning') {
    const container = document.getElementById('alerts-container');
    const alertId = `alert-${currentSessionId}-${Date.now()}`;

    const alertClass = severity === 'critical' ? 'alert-critical' : 'alert-warning';
    const icon = severity === 'critical' ? '🚨' : '⚠️';

    const alertHtml = `
        <div id="${alertId}" class="alert-banner ${alertClass}">
            <div class="flex justify-between items-center">
                <div class="flex items-center">
                    <span class="text-2xl mr-3">${icon}</span>
                    <span>${message}</span>
                </div>
                <button onclick="document.getElementById('${alertId}').remove()" class="text-xl">&times;</button>
            </div>
        </div>
    `;

    container.innerHTML += alertHtml;
}

function log(message, type = 'info') {
    const colors = {
        success: 'text-green-400',
        error: 'text-red-400',
        warning: 'text-yellow-400',
        info: 'text-blue-400'
    };

    const color = colors[type] || colors.info;
    const time = new Date().toLocaleTimeString();

    console.log(`[${time}] ${message}`);
}
