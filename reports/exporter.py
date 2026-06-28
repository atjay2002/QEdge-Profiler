"""
QEdge Profiler Report Exporter
Export session data to CSV and PDF formats.
"""

import os
from typing import Optional, Dict
from datetime import datetime
import io

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("[ReportExporter] Warning: pandas not available")

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    print("[ReportExporter] Warning: reportlab not available")

from database import db


class ReportExporter:
    """Export session reports to various formats."""

    def __init__(self, session_id: int):
        """
        Initialize report exporter.

        Args:
            session_id: Database session ID
        """
        self.session_id = session_id
        self.session = db.get_session(session_id)

        if not self.session:
            raise ValueError(f"Session {session_id} not found")

    def export_csv(self, output_path: Optional[str] = None) -> str:
        """
        Export session data to CSV.

        Args:
            output_path: Optional output path, auto-generated if None

        Returns:
            Path to exported CSV file
        """
        if not PANDAS_AVAILABLE:
            raise RuntimeError("pandas not installed - cannot export CSV")

        # Get all data
        snapshots = db.get_snapshots(self.session_id)
        leak_analysis = db.get_leak_analysis(self.session_id)
        benchmark_results = db.get_benchmark_results(self.session_id)
        health_score = db.get_health_score(self.session_id)

        # Create DataFrame from snapshots
        df = pd.DataFrame(snapshots)

        # Convert timestamp to datetime
        if 'timestamp' in df.columns:
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')

        # Generate filename if not provided
        if not output_path:
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"qedge_session_{self.session_id}_{timestamp_str}.csv"

        # Export
        df.to_csv(output_path, index=False)

        print(f"[ReportExporter] CSV exported: {output_path}")
        return output_path

    def export_pdf(self, output_path: Optional[str] = None) -> str:
        """
        Export session report to PDF.

        Args:
            output_path: Optional output path, auto-generated if None

        Returns:
            Path to exported PDF file
        """
        if not REPORTLAB_AVAILABLE:
            raise RuntimeError("reportlab not installed - cannot export PDF")

        # Generate filename if not provided
        if not output_path:
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = f"qedge_session_{self.session_id}_{timestamp_str}.pdf"

        # Create PDF
        doc = SimpleDocTemplate(output_path, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#7c3aed'),
            spaceAfter=30
        )

        story.append(Paragraph("QEdge Profiler - Session Report", title_style))
        story.append(Spacer(1, 0.2 * inch))

        # Session Info
        story.append(Paragraph("<b>Session Information</b>", styles['Heading2']))

        session_data = [
            ['Session ID', str(self.session_id)],
            ['Type', self.session.get('session_type', 'N/A')],
            ['Model', self.session.get('model_name', 'N/A')],
            ['Backend', self.session.get('backend', 'N/A')],
            ['Precision', self.session.get('precision', 'N/A')],
            ['PID', str(self.session.get('pid', 'N/A'))],
            ['Status', self.session.get('status', 'N/A')],
            ['Start Time', datetime.fromtimestamp(self.session.get('start_time', 0)).strftime('%Y-%m-%d %H:%M:%S')],
        ]

        if self.session.get('end_time'):
            session_data.append([
                'End Time',
                datetime.fromtimestamp(self.session['end_time']).strftime('%Y-%m-%d %H:%M:%S')
            ])

            duration_sec = self.session['end_time'] - self.session['start_time']
            session_data.append(['Duration', f"{duration_sec:.1f}s"])

        session_table = Table(session_data, colWidths=[2*inch, 4*inch])
        session_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))

        story.append(session_table)
        story.append(Spacer(1, 0.3 * inch))

        # Leak Analysis
        leak_analysis = db.get_leak_analysis(self.session_id)

        if leak_analysis:
            story.append(Paragraph("<b>Leak Analysis</b>", styles['Heading2']))

            leak_score = leak_analysis.get('leak_score', 0)
            leak_color = colors.green if leak_score < 50 else (colors.orange if leak_score < 70 else colors.red)

            leak_data = [
                ['Leak Score', f"{leak_score:.1f}/100"],
                ['Regression Slope', f"{leak_analysis.get('regression_slope', 0):.4f} MB/sec"],
                ['R² (Fit Quality)', f"{leak_analysis.get('r_squared', 0):.4f}"],
                ['Growth Rate', f"{leak_analysis.get('growth_rate_mb_per_min', 0):.2f} MB/min"],
                ['Peak RSS', f"{leak_analysis.get('peak_rss_mb', 0):.2f} MB"]
            ]

            leak_table = Table(leak_data, colWidths=[2*inch, 4*inch])
            leak_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('TEXTCOLOR', (1, 0), (1, 0), leak_color),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('FONTSIZE', (1, 0), (1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))

            story.append(leak_table)
            story.append(Spacer(1, 0.3 * inch))

        # Benchmark Results
        benchmark_results = db.get_benchmark_results(self.session_id)

        if benchmark_results:
            story.append(Paragraph("<b>Benchmark Results</b>", styles['Heading2']))

            bench_data = [
                ['FPS', f"{benchmark_results.get('fps', 0):.2f}"],
                ['Latency p50', f"{benchmark_results.get('latency_p50_ms', 0):.2f} ms"],
                ['Latency p95', f"{benchmark_results.get('latency_p95_ms', 0):.2f} ms"],
                ['Latency p99', f"{benchmark_results.get('latency_p99_ms', 0):.2f} ms"],
                ['Iterations', str(benchmark_results.get('iterations', 0))]
            ]

            bench_table = Table(bench_data, colWidths=[2*inch, 4*inch])
            bench_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))

            story.append(bench_table)
            story.append(Spacer(1, 0.3 * inch))

        # Health Score
        health_score = db.get_health_score(self.session_id)

        if health_score:
            story.append(Paragraph("<b>Model Memory Health Score</b>", styles['Heading2']))

            score = health_score.get('health_score', 0)
            score_color = colors.green if score >= 70 else (colors.orange if score >= 50 else colors.red)

            health_data = [
                ['Health Score', f"{score:.1f}/100"],
                ['FPS Component', f"{health_score.get('fps_component', 0):.2%}"],
                ['Leak Component', f"{health_score.get('leak_component', 0):.2%}"],
                ['Memory Component', f"{health_score.get('memory_component', 0):.2%}"]
            ]

            health_table = Table(health_data, colWidths=[2*inch, 4*inch])
            health_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('TEXTCOLOR', (1, 0), (1, 0), score_color),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('FONTSIZE', (1, 0), (1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))

            story.append(health_table)
            story.append(Spacer(1, 0.3 * inch))

        # Memory Snapshots Summary
        snapshots = db.get_snapshots(self.session_id)

        if snapshots:
            story.append(Paragraph("<b>Memory Snapshots Summary</b>", styles['Heading2']))

            rss_values = [s['rss_mb'] for s in snapshots]

            summary_data = [
                ['Total Snapshots', str(len(snapshots))],
                ['Min RSS', f"{min(rss_values):.2f} MB"],
                ['Max RSS', f"{max(rss_values):.2f} MB"],
                ['Avg RSS', f"{sum(rss_values) / len(rss_values):.2f} MB"],
                ['RSS Growth', f"{max(rss_values) - min(rss_values):.2f} MB"]
            ]

            summary_table = Table(summary_data, colWidths=[2*inch, 4*inch])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))

            story.append(summary_table)

        # Footer
        story.append(Spacer(1, 0.5 * inch))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.grey
        )
        story.append(Paragraph(
            f"Generated by QEdge Profiler on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            footer_style
        ))

        # Build PDF
        doc.build(story)

        print(f"[ReportExporter] PDF exported: {output_path}")
        return output_path

    def export_json(self) -> Dict:
        """
        Export session data as JSON-serializable dictionary.

        Returns:
            Complete session data dictionary
        """
        return {
            'session': self.session,
            'snapshots': db.get_snapshots(self.session_id),
            'leak_analysis': db.get_leak_analysis(self.session_id),
            'benchmark_results': db.get_benchmark_results(self.session_id),
            'health_score': db.get_health_score(self.session_id),
            'alerts': db.get_alerts(self.session_id),
            'tracemalloc': db.get_tracemalloc_snapshots(self.session_id)
        }


def export_session(session_id: int, format: str = 'csv', output_path: Optional[str] = None) -> str:
    """
    Convenience function to export a session.

    Args:
        session_id: Session ID to export
        format: 'csv' or 'pdf'
        output_path: Optional output path

    Returns:
        Path to exported file
    """
    exporter = ReportExporter(session_id)

    if format == 'csv':
        return exporter.export_csv(output_path)
    elif format == 'pdf':
        return exporter.export_pdf(output_path)
    else:
        raise ValueError(f"Unsupported format: {format}")
