# QEdge Profiler - Complete Implementation ✅

**On-Device AI Inference Benchmarking & Memory Health Platform**

A full-stack developer tool combining AI model benchmarking with real-time memory leak detection. Features a dark-themed web dashboard with Chart.js visualizations, ONNX Runtime integration, and comprehensive export capabilities.

---

## 🚀 Features Implemented

### Core Memory Monitoring
- ✅ **Real-time Process Monitoring** - Attach to any PID, track RSS/VMS/CPU
- ✅ **Leak Detection Algorithm** - Linear regression with 0-100 confidence score
- ✅ **Smart Alerts** - Warning (70+) and Critical (85+) thresholds
- ✅ **Desktop Notifications** - Cross-platform via plyer
- ✅ **SQLite Session History** - 7-table schema with full audit trail

### ONNX Benchmarking
- ✅ **Model Registry** - Pre-configured models (MobileNetV2, ResNet50, SqueezeNet, EfficientNet-Lite0)
- ✅ **Backend Detection** - Auto-detect CPU/GPU/NPU via ONNX Runtime providers
- ✅ **Subprocess Isolation** - PID-based monitoring during inference
- ✅ **Inline Benchmarking** - Quick test mode without subprocess overhead
- ✅ **Performance Metrics** - Latency (p50/p95/p99), FPS, memory footprint

### Health Scoring
- ✅ **Model Memory Health Score** - Unique composite metric (FPS + memory stability)
- ✅ **Component Breakdown** - FPS (40%), Leak (40%), Memory (20%) weights
- ✅ **Grade System** - A/B/C/D grades with actionable recommendations

### Visualization & Export
- ✅ **Chart.js Dashboards** - Real-time line charts (RSS, CPU), bar charts (benchmark)
- ✅ **Dark Theme UI** - TailwindCSS, purple accent (#7c3aed)
- ✅ **CSV Export** - Pandas-based data export
- ✅ **PDF Reports** - ReportLab with embedded tables and metrics
- ✅ **JSON API** - Complete REST API for all operations

### Advanced Features
- ✅ **Server-Sent Events** - 25s keep-alive, automatic reconnection
- ✅ **Tracemalloc Integration** - Python memory allocation breakdown
- ✅ **Session Comparison** - Side-by-side analysis
- ✅ **Demo Leaky Script** - Built-in test case

---

## 📦 Installation

```bash
# Clone or navigate to project directory
cd memleak_detector

# Install core dependencies
pip install Flask psutil numpy pandas

# Optional: Install ONNX Runtime for benchmarking
pip install onnxruntime

# Optional: Install export dependencies
pip install reportlab pillow

# Optional: Install notification support
pip install plyer
```

---

## 🎯 Quick Start

### 1. Memory Leak Detection (No ONNX Required)

```bash
# Start the server
python app.py

# Open browser
# Navigate to http://localhost:5000

# Click "Run Demo Leaky Script"
# Click "Start Monitoring"
# Watch leak detection in action (~60 seconds for alert)
```

### 2. ONNX Benchmarking (Requires models)

```bash
# Download a model (example: MobileNetV2)
mkdir -p models/onnx
cd models/onnx
wget https://github.com/onnx/models/raw/main/validated/vision/classification/mobilenet/model/mobilenetv2-7.onnx
cd ../..

# Start server
python app.py

# Go to "Benchmark" tab
# Select MobileNetV2, CPU, 100 iterations
# Click "Run Benchmark"
```

---

## 🏗️ Architecture

```
memleak_detector/
├── app.py (23KB)               # Flask backend + REST API
├── database/
│   └── db.py                   # SQLite with 7 tables, thread-safe
├── monitor/
│   ├── watcher.py              # psutil polling daemon (0.5s)
│   ├── leak_engine.py          # Linear regression leak detector
│   └── alerts.py               # Desktop notifications
├── benchmark/
│   ├── models.py               # ONNX model registry
│   ├── runner.py               # Subprocess benchmark runner
│   └── inference_worker.py     # Worker script with tracemalloc
├── scoring/
│   └── health_score.py         # Composite health metric
├── reports/
│   └── exporter.py             # CSV/PDF/JSON export
├── templates/
│   └── index.html              # Dark-themed dashboard
├── static/js/
│   └── dashboard.js            # Chart.js + SSE client
└── scripts/
    └── sample_leaky.py         # Demo leak script (1MB/0.5s)
```

---

## 📊 Dashboard Features

### Tab 1: Memory Monitor
- **Live Metrics**: Session ID, RSS, CPU%, Leak Score
- **RSS Chart**: Real-time line chart with 500-point buffer
- **CPU Chart**: Real-time CPU% tracking
- **Alert Banners**: Visual warnings for leaks
- **Controls**: Attach by PID, Stop monitoring, Run demo

### Tab 2: Benchmark
- **Model Selection**: Dropdown of available ONNX models
- **Backend Choice**: CPU/GPU/NPU selection
- **Iteration Count**: Configurable (default 100)
- **Results Display**: FPS, latency (p50/p95/p99), provider info
- **Comparison Chart**: Bar chart comparing model performance

### Tab 3: History
- **Session Table**: All past runs with filters
- **View Details**: Full session data
- **Export Options**: CSV/PDF download buttons

### Tab 4: System Info
- **ONNX Runtime**: Version and availability
- **Backends**: CPU/GPU/NPU detection status
- **Models**: Available models list

---

## 🔌 REST API

### System
- `GET /api/system/info` - System capabilities
- `GET /api/models/list` - Available ONNX models
- `GET /api/backends/detect` - Backend detection

### Monitoring
- `POST /api/monitor/attach` - Attach to PID
- `POST /api/monitor/stop/<id>` - Stop and analyze

### Benchmarking
- `POST /api/benchmark/run` - Run benchmark + monitoring
- `POST /api/benchmark/inline` - Quick inline test

### Sessions
- `GET /api/sessions` - List history
- `GET /api/sessions/<id>` - Get details

### Export
- `GET /api/export/<id>/csv` - Export as CSV
- `GET /api/export/<id>/pdf` - Export as PDF
- `GET /api/export/<id>/json` - Export as JSON

### Streaming
- `GET /stream/<id>` - SSE real-time updates

---

## 🧪 Testing

```bash
# Test core features
python test_core.py

# Test enhanced features
python test_enhanced.py
```

---

## 📈 Leak Detection Algorithm

**Formula:**
```
Leak Score = min(100, max(0, slope * 10 * R² * 100 + 10))

Where:
- slope = Linear regression slope (MB/sec)
- R² = Regression fit quality (0-1)
- Minimum 10 snapshots required
```

**Interpretation:**
- **0-50**: No significant leak
- **50-70**: Minor memory growth
- **70-85**: WARNING - Possible leak
- **85-100**: CRITICAL - Significant leak

---

## 🏆 Health Score Formula

```
Health Score = (normalized_fps * 0.4) + (inverted_leak * 0.4) + (inverted_memory * 0.2)

Components:
- normalized_fps = min(1.0, fps / 60)
- inverted_leak = 1.0 - (leak_score / 100)
- inverted_memory = 1.0 - min(1.0, peak_rss_mb / 2048)
```

**Grades:**
- **A (90-100)**: Excellent - Production-ready
- **B (70-89)**: Good - Monitor in production
- **C (50-69)**: Warning - Investigate issues
- **D (0-49)**: Poor - Fix before deployment

---

## 📝 Use Cases

1. **Edge AI Development** - Profile models on resource-constrained devices
2. **Memory Leak Detection** - Identify leaks in long-running processes
3. **Model Optimization** - Compare memory footprint across architectures
4. **Performance Benchmarking** - Measure latency/FPS across backends
5. **Production Monitoring** - Track memory health of deployed services

---

## 🛠️ Technology Stack

| Layer | Technologies |
|-------|-------------|
| Backend | Python 3.10, Flask, psutil, numpy |
| Database | SQLite (thread-safe) |
| ML | ONNX Runtime (CPU/GPU/NPU) |
| Algorithms | Linear regression (polyfit), percentiles |
| Frontend | HTML5, TailwindCSS CDN, Chart.js 4.4 |
| Real-time | Server-Sent Events (SSE) |
| Export | Pandas (CSV), ReportLab (PDF) |
| Notifications | plyer (cross-platform) |

---

## 📦 Dependencies

### Required (Core Memory Monitoring)
```
Flask==3.0.0
psutil==6.0.0
numpy==1.24.3
```

### Optional (Benchmarking)
```
onnxruntime==1.18.0
scikit-learn==1.3.0
```

### Optional (Export)
```
pandas==2.0.3
reportlab==4.0.4
Pillow==10.0.0
```

### Optional (Notifications)
```
plyer==2.1.0
```

---

## 🌐 Platform Support

- ✅ **Linux**: Full support (Ubuntu 24.04 tested)
- ✅ **Windows**: Full support (Windows 11 tested)
- ✅ **macOS**: Compatible (plyer supported)

---

## 📄 License

Open source - built for the edge AI community.  

---

**Made with ❤️ for Edge AI Developers**
