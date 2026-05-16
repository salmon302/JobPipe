# Purpose: Render the JobPipe desktop GUI for ingest monitoring and resume actions.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Remove scraping scheduler UI and add ingest server status display.

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Callable

from jobpipe.config import Settings
from jobpipe.gui.latex_editor import LatexEditor
from jobpipe.gui.services import DashboardSnapshot, JobPipeGuiService
from jobpipe.ingest.server import IngestServer
from jobpipe.scoring.attainability import _infer_seniority_hint

try:
    from PySide6.QtCore import (
        QEasingCurve,
        QFileSystemWatcher,
        QObject,
        QPropertyAnimation,
        QRunnable,
        Qt,
        QThreadPool,
        QTimer,
        QUrl,
        Signal,
    )
    from PySide6.QtGui import QAction, QDesktopServices, QFont, QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QFrame,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QSlider,
        QSpinBox,
        QSplitter,
        QMenu,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:
    raise RuntimeError(
        "GUI dependencies are missing. Install with: pip install -e .[gui]"
    ) from exc


def _format_datetime(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_score(value: float | str | None) -> str:
    if value is None:
        return "n/a"
    # Handle case where value is already a string
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return value  # Return as-is if not a valid float
    try:
        return f"{value:.3f}"
    except (ValueError, TypeError):
        return str(value)


def _is_truthy_env_value(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


class BackgroundActionSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    completed = Signal()


class BackgroundActionWorker(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = BackgroundActionSignals()

    def run(self) -> None:
        try:
            result = self._fn()
            self.signals.succeeded.emit(result)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.completed.emit()


class RecommendSignals(QObject):
    """Signals for the AI recommendation worker."""
    succeeded = Signal(str)  # recommendation text
    failed = Signal(str)  # error message
    completed = Signal()


class RecommendWorker(QRunnable):
    """Worker for generating AI recommendations in background thread."""

    def __init__(self, service: JobPipeGuiService, top_jobs: list) -> None:
        super().__init__()
        self._service = service
        self._top_jobs = top_jobs
        self.signals = RecommendSignals()

    def run(self) -> None:
        try:
            recommendation = self._service.generate_ai_recommendations(self._top_jobs)
            self.signals.succeeded.emit(recommendation)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.completed.emit()


class AIRecommendPanel(QWidget):
    """Collapsible right sidebar panel for AI recommendations (Copilot style)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._job_ids: list[str] = []  # Track which jobs were recommended
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header with title and collapse button
        header_layout = QHBoxLayout()
        title = QLabel("✨ AI Recommendations")
        title.setObjectName("cardTitle")
        title.setStyleSheet("color: #e94560; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        self._collapse_btn = QPushButton("◀")
        self._collapse_btn.setMaximumWidth(30)
        self._collapse_btn.setToolTip("Collapse panel")
        self._collapse_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self._collapse_btn)
        layout.addLayout(header_layout)

        # Recommendation text display
        self._text_display = QPlainTextEdit()
        self._text_display.setReadOnly(True)
        self._text_display.setPlaceholderText("Click 'AI Recommend' to generate recommendations...")
        self._text_display.setMaximumHeight(300)
        layout.addWidget(self._text_display)

        # AI Picks section
        picks_label = QLabel("AI Picks:")
        picks_label.setObjectName("cardTitle")
        picks_label.setStyleSheet("color: #a0a0a0; font-size: 9pt;")
        layout.addWidget(picks_label)

        self._picks_list = QPlainTextEdit()
        self._picks_list.setReadOnly(True)
        self._picks_list.setMaximumHeight(150)
        self._picks_list.setPlaceholderText("Top picks will appear here...")
        layout.addWidget(self._picks_list)

        self.setStyleSheet("""
            AIRecommendPanel {
                background: #1a1a2e;
                border-left: 2px solid #533483;
            }
        """)

    def _toggle_collapse(self) -> None:
        """Toggle panel visibility."""
        is_visible = self._text_display.isVisible()
        self._text_display.setVisible(not is_visible)
        self._picks_list.setVisible(not is_visible)
        self._collapse_btn.setText("▶" if is_visible else "◀")
        self._collapse_btn.setToolTip("Expand panel" if is_visible else "Collapse panel")

    def update_recommendations(self, text: str, job_ids: list[str]) -> None:
        """Update the panel with new recommendations."""
        self._job_ids = job_ids
        self._text_display.setPlainText(text)
        
        # Ensure widgets are visible (they might be hidden by collapse toggle)
        self._text_display.setVisible(True)
        self._picks_list.setVisible(True)
        
        # Also ensure the collapse button shows "◀" (expanded state)
        if hasattr(self, '_collapse_btn'):
            self._collapse_btn.setText("◀")  # Set to expanded state
            self._collapse_btn.setToolTip("Collapse panel")

        # Extract job titles from recommendations for the picks list
        picks = []
        for i, job_id in enumerate(job_ids[:5], 1):  # Top 5
            picks.append(f"{i}. Job ID: {job_id}")
        self._picks_list.setPlainText("\n".join(picks))

    def get_job_ids(self) -> list[str]:
        """Return the list of AI-picked job IDs."""
        return self._job_ids


class JobPipeMainWindow(QMainWindow):
    def __init__(self, service: JobPipeGuiService) -> None:
        super().__init__()
        self._service = service
        self._thread_pool = QThreadPool(self)
        self._resume_busy = False
        self._recommend_busy = False  # Separate flag for AI recommendations
        self._current_resume_worker: BackgroundActionWorker | None = None
        self._ingest_server: IngestServer | None = None
        self._intro_animation: QPropertyAnimation | None = None

        # Enrichment polling state
        self._enrichment_poll_timer = QTimer(self)
        self._enrichment_poll_timer.setInterval(2000)  # Poll every 2s
        self._enrichment_poll_timer.timeout.connect(self._check_enrichment_status)
        self._enrichment_poll_count = 0
        self._enrichment_poll_max = 15  # ~30 seconds max
        self._enrichment_job_id: str | None = None
        self._enrichment_job_row: int | None = None
        self._enrichment_initial_desc_length: int = 0
        self._pending_stage_after_enrichment: bool = False  # Flag for double-click staging

        # Auto-refresh timer for database updates
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(30000)  # Refresh every 30 seconds
        self._auto_refresh_timer.timeout.connect(self.refresh_views)

        self._ingest_status_value = QLabel("Starting")
        self._ingest_endpoint_value = QLabel("n/a")

        self._settings_env_path_value = QLabel()
        self._settings_ingest_host_input = QLineEdit()
        self._settings_ingest_port_input = QLineEdit()
        self._settings_ingest_payload_input = QLineEdit()
        self._settings_reload_button = QPushButton("Reload")
        self._settings_save_button = QPushButton("Validate + Save")
        self._settings_status_value = QLabel("Not loaded")
        self._settings_status_value.setProperty("role", "statusBadge")

        self._resume_job_id_input = QLineEdit()
        self._resume_min_score_input = QLineEdit()
        self._resume_stage_button = QPushButton("Stage Job Description")
        self._resume_output_path_value = QLabel("Not staged")
        # LaTeX editor for resume review (REQ-3.3)
        self._resume_preview = LatexEditor()
        self._resume_tex_path_input = QLineEdit()
        self._resume_compile_button = QPushButton("Compile Resume")
        self._resume_approve_button = QPushButton("Approve & Compile")  # REQ-3.4
        self._resume_open_pdf_button = QPushButton("Open Compiled PDF")
        self._resume_status_value = QLabel("Idle")
        self._resume_status_value.setProperty("role", "statusBadge")
        self._resume_last_pdf_path: Path | None = None
        self._resume_context_label = QLabel("No job selected")
        self._resume_context_label.setProperty("role", "muted")
        self._resume_gen_1page_button = QPushButton("Generate 1-Page Resume")
        self._resume_gen_halfpage_button = QPushButton("Generate 1/2-Page Resume")

        self._db_path_value = QLabel("n/a")
        self._threshold_value = QLabel("n/a")
        self._counts_value = QLabel("n/a")
        self._last_run_status_value = QLabel("n/a")
        self._last_run_started_value = QLabel("n/a")
        self._last_run_finished_value = QLabel("n/a")
        self._last_run_summary_value = QLabel("n/a")

        self._jobs_table = self._create_table(
            ["Total", "Relevance", "Attainability", "Recency", "Seniority", "Title", "Company", "Platform", "Status", "Posted", "URL"]
        )
        self._jobs_search_input = QLineEdit()
        self._jobs_search_input.setPlaceholderText("Search title, company, description, location...")
        self._jobs_search_button = QPushButton("Search")
        self._jobs_clear_search_button = QPushButton("Clear")
        self._jobs_limit_input = QSpinBox()
        self._jobs_limit_input.setRange(50, 5000)
        self._jobs_limit_input.setSingleStep(100)
        self._jobs_limit_input.setValue(500)
        self._jobs_results_label = QLabel("Showing: 0")
        self._jobs_results_label.setProperty("role", "muted")
        self._jobs_count_label = QLabel("Jobs: 0 | Companies: 0")
        self._jobs_count_label.setProperty("role", "muted")

        # --- Jobs tab sidebar filter controls ---
        # Seniority filter checkboxes (all checked = show all)
        self._filter_seniority_entry = QCheckBox("Entry / Junior")
        self._filter_seniority_entry.setChecked(True)
        self._filter_seniority_mid = QCheckBox("Mid-Level")
        self._filter_seniority_mid.setChecked(True)
        self._filter_seniority_senior = QCheckBox("Senior / Lead")
        self._filter_seniority_senior.setChecked(True)
        self._filter_seniority_manager = QCheckBox("Manager")
        self._filter_seniority_manager.setChecked(True)

        # --- Job Preferences (moved from Settings tab) ---
        self._filter_notification_threshold = QLineEdit()
        self._filter_notification_threshold.setPlaceholderText("0.00")
        self._filter_notification_threshold.setText("0.00")  # No minimum by default
        self._filter_user_years = QLineEdit()
        self._filter_user_years.setPlaceholderText("1")
        self._filter_user_years.setText("1")  # Minimal default
        self._filter_critical_skills = QLineEdit()
        self._filter_critical_skills.setPlaceholderText("python,fastapi,sql,aws")
        self._filter_critical_skills.setText("")  # Empty by default
        self._filter_reject_terms = QLineEdit()
        self._filter_reject_terms.setPlaceholderText("senior,staff,principal,architect")
        self._filter_reject_terms.setText("")  # Empty by default
        self._filter_auto_stage = QCheckBox("Enable auto-stage job description")
        self._filter_auto_stage.setChecked(False)  # Disabled by default

        # --- Scoring Weights (moved from Settings tab) ---
        self._filter_relevance_slider = QSlider(Qt.Orientation.Horizontal)
        self._filter_relevance_slider.setRange(0, 100)
        self._filter_relevance_slider.setValue(50)
        self._filter_relevance_label = QLabel("Relevance: 0.50")
        
        self._filter_attainability_slider = QSlider(Qt.Orientation.Horizontal)
        self._filter_attainability_slider.setRange(0, 100)
        self._filter_attainability_slider.setValue(30)
        self._filter_attainability_label = QLabel("Attainability: 0.30")
        
        self._filter_recency_slider = QSlider(Qt.Orientation.Horizontal)
        self._filter_recency_slider.setRange(0, 100)
        self._filter_recency_slider.setValue(20)
        self._filter_recency_label = QLabel("Recency: 0.20")

        # --- Age Filter ---
        self._filter_reject_old_jobs = QCheckBox("Reject jobs that are too old")
        self._filter_reject_old_jobs.setChecked(False)  # Disabled by default
        self._filter_max_job_age = QSpinBox()
        self._filter_max_job_age.setRange(1, 365)
        self._filter_max_job_age.setValue(30)
        self._filter_max_job_age.setSuffix(" days")

        # --- Job Preferences (moved from Settings tab) ---
        self._filter_notification_threshold = QLineEdit()
        self._filter_notification_threshold.setPlaceholderText("0.00")
        self._filter_user_years = QLineEdit()
        self._filter_user_years.setPlaceholderText("1")
        self._filter_critical_skills = QLineEdit()
        self._filter_critical_skills.setPlaceholderText("python,fastapi,sql,aws")
        self._filter_reject_terms = QLineEdit()
        self._filter_reject_terms.setPlaceholderText("senior,staff,principal,architect")
        self._filter_auto_stage = QCheckBox("Enable auto-stage job description")
        self._filter_auto_stage.setChecked(True)

        # --- Scoring Weights (moved from Settings tab) ---
        self._filter_relevance_slider = QSlider(Qt.Orientation.Horizontal)
        self._filter_relevance_slider.setRange(0, 100)
        self._filter_relevance_slider.setValue(50)
        self._filter_relevance_label = QLabel("Relevance: 0.50")
        
        self._filter_attainability_slider = QSlider(Qt.Orientation.Horizontal)
        self._filter_attainability_slider.setRange(0, 100)
        self._filter_attainability_slider.setValue(30)
        self._filter_attainability_label = QLabel("Attainability: 0.30")
        
        self._filter_recency_slider = QSlider(Qt.Orientation.Horizontal)
        self._filter_recency_slider.setRange(0, 100)
        self._filter_recency_slider.setValue(20)
        self._filter_recency_label = QLabel("Recency: 0.20")

        # --- Age Filter ---
        self._filter_reject_old_jobs = QCheckBox("Reject jobs that are too old")
        self._filter_reject_old_jobs.setChecked(True)
        self._filter_max_job_age = QSpinBox()
        self._filter_max_job_age.setRange(1, 365)
        self._filter_max_job_age.setValue(30)
        self._filter_max_job_age.setSuffix(" days")

        # Score minimum sliders (0 = no filter)
        self._filter_min_total = QSlider(Qt.Orientation.Horizontal)
        self._filter_min_total.setRange(0, 100)
        self._filter_min_total.setValue(0)
        self._filter_min_total_label = QLabel("Min Total: 0.00")

        self._filter_min_relevance = QSlider(Qt.Orientation.Horizontal)
        self._filter_min_relevance.setRange(0, 100)
        self._filter_min_relevance.setValue(0)
        self._filter_min_relevance_label = QLabel("Min Relevance: 0.00")

        self._filter_min_attainability = QSlider(Qt.Orientation.Horizontal)
        self._filter_min_attainability.setRange(0, 100)
        self._filter_min_attainability.setValue(0)
        self._filter_min_attainability_label = QLabel("Min Attainability: 0.00")
        
        self._runs_table = self._create_table(
            [
                "Status",
                "Run ID",
                "Started",
                "Finished",
                "Ingested",
                "Inserted",
                "Updated",
                "Scored",
                "Above",
                "Notified",
                "Error",
            ]
        )
        self._notifications_table = self._create_table(
            ["When", "Delivery", "Score", "Title", "Company", "URL", "Error"]
        )

        self._log_output = QPlainTextEdit()
        self._log_output.setReadOnly(True)
        self._log_output.setObjectName("logOutput")

        self.setWindowTitle("JobPipe Desktop")
        self.resize(1300, 800)
        self._apply_theme()
        self._build_ui()
        self.statusBar().showMessage("Ready")
        self._start_ingest_server()
        self.refresh_views()
        self._load_settings_form_values(silent=True)
        self._auto_refresh_timer.start()  # Start auto-refresh

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._ingest_server is not None:
            self._ingest_server.stop()
        if hasattr(self, '_auto_refresh_timer') and self._auto_refresh_timer.isActive():
            self._auto_refresh_timer.stop()
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if self._intro_animation is not None:
            return
        self.setWindowOpacity(0.0)
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(360)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start()
        self._intro_animation = animation

    def _apply_theme(self) -> None:
        app_font = QFont("Bahnschrift", 10)
        QApplication.setFont(app_font)

        self.setStyleSheet(
            """
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1a1a2e, stop:1 #16213e);
                color: #e0e0e0;
            }
            #appRoot {
                background: transparent;
            }
            #headerBar {
                background: #0f3460;
                border: 1px solid #1a1a2e;
                border-radius: 12px;
            }
            #pageTitle {
                font-size: 22px;
                font-weight: 700;
                letter-spacing: 0.5px;
                color: #ffffff;
            }
            #pageSubtitle {
                color: #a0a0a0;
            }
            QMenuBar {
                background: #0f3460;
                border-bottom: 1px solid #1a1a2e;
            }
            QMenuBar::item {
                background: transparent;
                padding: 6px 10px;
                color: #e0e0e0;
            }
            QMenuBar::item:selected {
                background: #533483;
                color: #ffffff;
                border-radius: 6px;
            }
            QMenu {
                background: #1a1a2e;
                border: 1px solid #0f3460;
            }
            QMenu::item {
                padding: 6px 12px;
                color: #e0e0e0;
            }
            QMenu::item:selected {
                background: #533483;
                color: #ffffff;
            }
            QStatusBar {
                background: #0f3460;
                border-top: 1px solid #1a1a2e;
                color: #e0e0e0;
            }
            QStatusBar::item {
                border: 0;
            }
            QTabWidget::pane {
                background: #1a1a2e;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 8px;
            }
            QTabBar::tab {
                background: #16213e;
                color: #a0a0a0;
                border: 1px solid #0f3460;
                border-bottom: 0;
                padding: 7px 12px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                color: #ffffff;
                background: #533483;
                border-color: #533483;
            }
            QTabBar::tab:!selected {
                margin-top: 2px;
            }
            QTabBar::tab:hover {
                background: #1a1a2e;
            }
            QFrame[role="card"],
            QFrame[role="metricCard"] {
                background: #16213e;
                border: 1px solid #0f3460;
                border-radius: 10px;
            }
            QFrame[role="chip"] {
                background: #0f3460;
                border: 0;
                border-radius: 10px;
            }
            QLabel[role="chipLabel"] {
                font-size: 9pt;
                color: #a0a0a0;
            }
            QLabel[role="chipValue"] {
                font-weight: 700;
                color: #e0e0e0;
            }
            QLabel#cardTitle {
                font-size: 10pt;
                font-weight: 600;
                color: #e94560;
            }
            QLabel#metricTitle {
                font-size: 9pt;
                font-weight: 600;
                color: #a0a0a0;
            }
            QLabel[role="metricValue"] {
                font-size: 13pt;
                font-weight: 700;
                color: #e0e0e0;
            }
            QLabel[role="statusBadge"] {
                background: #0f3460;
                border: 1px solid #533483;
                border-radius: 8px;
                padding: 4px 8px;
                font-weight: 600;
                color: #e0e0e0;
            }
            QLabel[role="muted"] {
                color: #a0a0a0;
            }
            QLabel[role="formLabel"] {
                color: #e0e0e0;
                font-weight: 600;
            }
            QLineEdit, QPlainTextEdit, QTableWidget {
                background: #16213e;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 6px;
                selection-background-color: #533483;
                color: #e0e0e0;
            }
            QPlainTextEdit#detailsText {
                background: #1a1a2e;
            }
            QHeaderView::section {
                background: #0f3460;
                color: #e0e0e0;
                border: 0;
                border-bottom: 1px solid #533483;
                padding: 6px;
                font-weight: 600;
            }
            QTableWidget {
                gridline-color: #0f3460;
                alternate-background-color: #1a1a2e;
            }
            QPushButton {
                background: #16213e;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 6px 12px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background: #1a1a2e;
            }
            QPushButton#primaryButton {
                background: #533483;
                color: #ffffff;
                border-color: #533483;
            }
            QPushButton#primaryButton:hover {
                background: #e94560;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #0f3460;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #e94560;
                border: 1px solid #533483;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QCheckBox {
                color: #e0e0e0;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #0f3460;
                border-radius: 3px;
                background: #16213e;
            }
            QCheckBox::indicator:checked {
                background: #533483;
                border-color: #533483;
            }
            QGroupBox {
                color: #e0e0e0;
                border: 1px solid #0f3460;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                color: #e94560;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QSpinBox {
                background: #16213e;
                border: 1px solid #0f3460;
                border-radius: 8px;
                padding: 4px;
                color: #e0e0e0;
            }
            """
        )

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("headerBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        title = QLabel("JobPipe Control Center")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Ingest and resume operations")
        subtitle.setObjectName("pageSubtitle")

        left = QVBoxLayout()
        left.setSpacing(1)
        left.addWidget(title)
        left.addWidget(subtitle)
        layout.addLayout(left)

        layout.addStretch(1)

        status_wrap = QWidget()
        status_layout = QHBoxLayout(status_wrap)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        status_layout.addWidget(self._build_stat_chip("Ingest", self._ingest_status_value))
        status_layout.addWidget(self._build_stat_chip("Endpoint", self._ingest_endpoint_value))
        layout.addWidget(status_wrap)

        return header

    def _build_stat_chip(self, label_text: str, value_label: QLabel) -> QWidget:
        chip = QFrame()
        chip.setProperty("role", "chip")
        chip_layout = QVBoxLayout(chip)
        chip_layout.setContentsMargins(14, 10, 14, 10)
        chip_layout.setSpacing(4)

        label = QLabel(label_text)
        label.setProperty("role", "chipLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        value_label.setProperty("role", "chipValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        value_label.setMinimumHeight(20)

        chip_layout.addWidget(label)
        chip_layout.addWidget(value_label)
        return chip

    def _build_metric_card(self, title: str, value_label: QLabel) -> QWidget:
        card = QFrame()
        card.setProperty("role", "metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        value_label.setProperty("role", "metricValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        value_label.setMinimumHeight(24)
        value_label.setMinimumHeight(24)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return card

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("appRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(12)

        root.addWidget(self._build_header())

        tabs = QTabWidget()
        tabs.setObjectName("mainTabs")
        tabs.setDocumentMode(True)
        tabs.setUsesScrollButtons(True)
        tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        tabs.addTab(self._build_jobs_tab(), "Jobs")
        tabs.addTab(self._build_runs_tab(), "Runs")
        tabs.addTab(self._build_notifications_tab(), "Notifications")
        tabs.addTab(self._build_resume_tab(), "Resume")
        tabs.addTab(self._build_resume_variants_tab(), "Resume Variants")
        tabs.addTab(self._build_cv_editor_tab(), "Master CV")
        tabs.addTab(self._build_settings_tab(), "Settings")
        tabs.addTab(self._build_logs_tab(), "Logs")
        root.addWidget(tabs)

        self.setCentralWidget(central)
        self._build_menu()

    def _build_menu(self) -> None:
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.refresh_views)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(refresh_action)
        file_menu.addAction(exit_action)

    def _build_dashboard_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(12)
        metrics.addWidget(
            self._build_metric_card("Notification Threshold", self._threshold_value), 0, 0
        )
        metrics.addWidget(
            self._build_metric_card("Tracked Jobs", self._counts_value), 0, 1
        )
        metrics.addWidget(
            self._build_metric_card("Last Run Status", self._last_run_status_value), 1, 0
        )
        metrics.addWidget(
            self._build_metric_card("Last Run Finished", self._last_run_finished_value), 1, 1
        )
        layout.addLayout(metrics)

        form = QFormLayout()
        form.addRow("Database Path", self._db_path_value)
        form.addRow("Last Run Started", self._last_run_started_value)
        form.addRow("Last Run Summary", self._last_run_summary_value)
        details_card = QFrame()
        details_card.setProperty("role", "card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(12, 10, 12, 10)
        details_title = QLabel("System Details")
        details_title.setObjectName("cardTitle")
        details_layout.addWidget(details_title)
        details_layout.addLayout(form)
        layout.addWidget(details_card)

        controls = QHBoxLayout()
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_views)
        controls.addWidget(refresh_button)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addStretch(1)
        return widget

    def _build_jobs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)

        # ---- Top bar: counts + search + actions ----
        counts_layout = QHBoxLayout()
        counts_layout.setContentsMargins(0, 0, 0, 0)
        counts_layout.setSpacing(6)
        self._jobs_count_label.setMaximumHeight(20)
        self._jobs_results_label.setMaximumHeight(20)
        counts_layout.addWidget(self._jobs_count_label)
        counts_layout.addWidget(self._jobs_results_label)
        counts_layout.addStretch(1)
        layout.addLayout(counts_layout)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(4)
        search_label = QLabel("Search:")
        search_label.setProperty("role", "formLabel")
        controls.addWidget(search_label)
        controls.addWidget(self._jobs_search_input, 1)
        self._jobs_search_input.returnPressed.connect(self._apply_job_filters)

        self._jobs_search_button.clicked.connect(self._apply_job_filters)
        controls.addWidget(self._jobs_search_button)

        self._jobs_clear_search_button.clicked.connect(self._clear_job_search)
        controls.addWidget(self._jobs_clear_search_button)

        limit_label = QLabel("Limit:")
        limit_label.setProperty("role", "formLabel")
        controls.addWidget(limit_label)
        controls.addWidget(self._jobs_limit_input)
        
        recalc_button = QPushButton("Recalculate Scores")
        recalc_button.setObjectName("primaryButton")
        recalc_button.clicked.connect(self._recalculate_scores_clicked)
        controls.addWidget(recalc_button)

        open_button = QPushButton("Open Selected Job")
        open_button.clicked.connect(self._open_selected_job_url)
        controls.addWidget(open_button)

        clear_button = QPushButton("Clear Jobs")
        clear_button.clicked.connect(self._clear_jobs)
        controls.addWidget(clear_button)

        # AI Recommend button
        self._recommend_button = QPushButton("AI Recommend")
        self._recommend_button.setObjectName("primaryButton")
        self._recommend_button.clicked.connect(self._get_ai_recommendations)
        controls.addWidget(self._recommend_button)

        controls.addStretch(1)
        layout.addLayout(controls)

        # ---- Body: sidebar | table+details ----
        body_splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- Sidebar filters --
        sidebar = QFrame()
        sidebar.setProperty("role", "card")
        sidebar.setMinimumWidth(180)  # Reduced from 200
        sidebar.setMaximumWidth(240)  # Reduced from 280
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(6, 6, 6, 6)  # Tighter margins
        sidebar_layout.setSpacing(4)  # Reduced spacing

        # Filters header
        filters_header = QLabel("Filters")
        filters_header.setObjectName("cardTitle")
        filters_header.setMaximumHeight(20)  # Smaller header
        sidebar_layout.addWidget(filters_header)

        # Seniority group - compact
        seniority_group = QGroupBox("Seniority")
        seniority_group_layout = QVBoxLayout(seniority_group)
        seniority_group_layout.setSpacing(1)  # Tighter spacing
        seniority_group_layout.setContentsMargins(6, 4, 6, 4)  # Tighter margins
        seniority_group_layout.addWidget(self._filter_seniority_entry)
        seniority_group_layout.addWidget(self._filter_seniority_mid)
        seniority_group_layout.addWidget(self._filter_seniority_senior)
        seniority_group_layout.addWidget(self._filter_seniority_manager)
        sidebar_layout.addWidget(seniority_group)

        # Score sliders group with explicit labels - compact
        score_group = QGroupBox("Minimum Scores")
        score_group_layout = QVBoxLayout(score_group)
        score_group_layout.setSpacing(2)  # Tighter spacing
        score_group_layout.setContentsMargins(6, 4, 6, 4)  # Tighter margins

        self._filter_min_total_label = QLabel("Min Total: 0.00")
        self._filter_min_total.valueChanged.connect(
            lambda v: self._filter_min_total_label.setText(f"Min Total: {v/100:.2f}")
        )
        score_group_layout.addWidget(self._filter_min_total_label)
        score_group_layout.addWidget(self._filter_min_total)

        self._filter_min_relevance_label = QLabel("Min Relevance: 0.00")
        self._filter_min_relevance.valueChanged.connect(
            lambda v: self._filter_min_relevance_label.setText(f"Min Relevance: {v/100:.2f}")
        )
        score_group_layout.addWidget(self._filter_min_relevance_label)
        score_group_layout.addWidget(self._filter_min_relevance)

        self._filter_min_attainability_label = QLabel("Min Attainability: 0.00")
        self._filter_min_attainability.valueChanged.connect(
            lambda v: self._filter_min_attainability_label.setText(f"Min Attainability: {v/100:.2f}")
        )
        score_group_layout.addWidget(self._filter_min_attainability_label)
        score_group_layout.addWidget(self._filter_min_attainability)

        sidebar_layout.addWidget(score_group)

        # ---- Job Preferences Group ---- compact
        prefs_group = QGroupBox("Job Preferences")
        prefs_layout = QFormLayout(prefs_group)
        prefs_layout.setSpacing(2)  # Tighter spacing
        prefs_layout.setContentsMargins(6, 4, 6, 4)  # Tighter margins
        prefs_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)  # Smaller fields
        prefs_layout.addRow("Notification Threshold", self._filter_notification_threshold)
        prefs_layout.addRow("User Years Exp.", self._filter_user_years)
        prefs_layout.addRow("Critical Skills (CSV)", self._filter_critical_skills)
        prefs_layout.addRow("Reject Terms (CSV)", self._filter_reject_terms)
        prefs_layout.addRow(self._filter_auto_stage)
        sidebar_layout.addWidget(prefs_group)

        # ---- Scoring Weights Group ---- compact
        weights_group = QGroupBox("Scoring Weights")
        weights_layout = QVBoxLayout(weights_group)
        weights_layout.setSpacing(2)  # Tighter spacing
        weights_layout.setContentsMargins(6, 4, 6, 4)  # Tighter margins
        
        # Connect sliders to update labels
        self._filter_relevance_slider.valueChanged.connect(
            lambda v: self._filter_relevance_label.setText(f"Relevance: {v/100:.2f}")
        )
        self._filter_attainability_slider.valueChanged.connect(
            lambda v: self._filter_attainability_label.setText(f"Attainability: {v/100:.2f}")
        )
        self._filter_recency_slider.valueChanged.connect(
            lambda v: self._filter_recency_label.setText(f"Recency: {v/100:.2f}")
        )
        
        weights_layout.addWidget(self._filter_relevance_label)
        weights_layout.addWidget(self._filter_relevance_slider)
        weights_layout.addWidget(self._filter_attainability_label)
        weights_layout.addWidget(self._filter_attainability_slider)
        weights_layout.addWidget(self._filter_recency_label)
        weights_layout.addWidget(self._filter_recency_slider)
        sidebar_layout.addWidget(weights_group)

        # ---- Age Filter Group ---- compact
        age_group = QGroupBox("Age Filter")
        age_layout = QVBoxLayout(age_group)
        age_layout.setSpacing(2)  # Tighter spacing
        age_layout.setContentsMargins(6, 4, 6, 4)  # Tighter margins
        age_layout.addWidget(self._filter_reject_old_jobs)
        age_layout.addWidget(QLabel("Max Job Age:"))
        age_layout.addWidget(self._filter_max_job_age)
        sidebar_layout.addWidget(age_group)

        # Apply filters button
        apply_filters_btn = QPushButton("Apply Filters")
        apply_filters_btn.setObjectName("primaryButton")
        apply_filters_btn.clicked.connect(self._apply_job_filters)
        sidebar_layout.addWidget(apply_filters_btn)

        # Reset filters button
        reset_filters_btn = QPushButton("Reset Filters")
        reset_filters_btn.clicked.connect(self._reset_job_filters)
        sidebar_layout.addWidget(reset_filters_btn)

        sidebar_layout.addStretch(1)
        body_splitter.addWidget(sidebar)

        # -- Middle panel: table + details --
        middle_panel = QWidget()
        middle_layout = QVBoxLayout(middle_panel)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(6)

        vert_splitter = QSplitter(Qt.Orientation.Vertical)
        vert_splitter.addWidget(self._jobs_table)

        # Job details panel
        details_panel = QFrame()
        details_panel.setProperty("role", "card")
        details_layout = QVBoxLayout(details_panel)
        details_layout.setContentsMargins(8, 6, 8, 6)
        details_label = QLabel("Job Details")
        details_label.setObjectName("cardTitle")
        self._job_details_text = QPlainTextEdit()
        self._job_details_text.setObjectName("detailsText")
        self._job_details_text.setReadOnly(True)
        self._job_details_text.setPlaceholderText("Select a job to view details...")
        details_layout.addWidget(details_label)
        details_layout.addWidget(self._job_details_text)
        vert_splitter.addWidget(details_panel)
        vert_splitter.setStretchFactor(0, 3)
        vert_splitter.setStretchFactor(1, 1)

        middle_layout.addWidget(vert_splitter)
        body_splitter.addWidget(middle_panel)

        # -- Right panel: AI Recommendations (collapsible) --
        self._ai_panel = AIRecommendPanel()
        self._ai_panel.setVisible(False)  # Hidden by default
        body_splitter.addWidget(self._ai_panel)

        # Connect panel visibility changes to adjust splitter
        self._ai_panel._collapse_btn.clicked.connect(
            lambda: self._adjust_splitter_after_ai_panel_toggle()
        )

        body_splitter.setStretchFactor(0, 0)  # Sidebar fixed width
        body_splitter.setStretchFactor(1, 1)  # Middle panel expands
        body_splitter.setStretchFactor(2, 0)  # AI panel hidden by default
        layout.addWidget(body_splitter)

        # Connect selection change to show details
        self._jobs_table.selectionModel().selectionChanged.connect(self._on_job_selection_changed)

        # Connect double-click to open job URL and auto-stage for resume
        self._jobs_table.itemDoubleClicked.connect(self._on_job_double_clicked)

        # Add context menu for copy
        self._jobs_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._jobs_table.customContextMenuRequested.connect(self._show_jobs_context_menu)

        # Add Ctrl+C shortcut for copy
        copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self._jobs_table)
        copy_shortcut.activated.connect(self._copy_selected_jobs)

        return widget

    def _clear_job_search(self) -> None:
        self._jobs_search_input.clear()
        self.refresh_views()

    def _build_runs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_views)
        controls = QHBoxLayout()
        controls.addWidget(refresh_button)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(self._runs_table)
        return widget

    def _build_notifications_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_views)
        controls = QHBoxLayout()
        controls.addWidget(refresh_button)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(self._notifications_table)
        return widget

    def _build_settings_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        self._settings_ingest_host_input.setPlaceholderText("127.0.0.1")
        self._settings_ingest_port_input.setPlaceholderText("3838")
        self._settings_ingest_payload_input.setPlaceholderText("1000000")

        # Network Configuration Card
        network_card = QFrame()
        network_card.setProperty("role", "card")
        network_layout = QVBoxLayout(network_card)
        network_layout.setContentsMargins(12, 10, 12, 10)
        network_title = QLabel("Network Configuration")
        network_title.setObjectName("cardTitle")
        network_layout.addWidget(network_title)
        network_form = QFormLayout()
        network_form.addRow("Env File", self._settings_env_path_value)
        network_form.addRow("Ingest Host", self._settings_ingest_host_input)
        network_form.addRow("Ingest Port", self._settings_ingest_port_input)
        network_form.addRow("Ingest Max Payload", self._settings_ingest_payload_input)
        network_layout.addLayout(network_form)
        layout.addWidget(network_card)

        # Status Card
        status_card = QFrame()
        status_card.setProperty("role", "card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_title = QLabel("Status")
        status_title.setObjectName("cardTitle")
        status_layout.addWidget(status_title)
        status_form = QFormLayout()
        status_form.addRow("Last Save Status", self._settings_status_value)
        status_layout.addLayout(status_form)
        layout.addWidget(status_card)

        controls = QHBoxLayout()
        self._settings_reload_button.clicked.connect(self._reload_settings_clicked)
        self._settings_save_button.clicked.connect(self._save_settings_clicked)
        self._settings_save_button.setObjectName("primaryButton")
        controls.addWidget(self._settings_reload_button)
        controls.addWidget(self._settings_save_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        layout.addStretch(1)
        return widget

    def _build_cv_editor_tab(self) -> QWidget:
        """Master CV editor with live preview (Phase 1 improvement)."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # CV path display
        self._cv_path_label = QLabel(f"CV Path: {self._service.settings.master_cv_path}")
        layout.addWidget(self._cv_path_label)

        # Editor and preview split (horizontal for side-by-side view)
        split_view = QSplitter(Qt.Orientation.Horizontal)

        # Editor
        editor_panel = QFrame()
        editor_panel.setProperty("role", "card")
        editor_layout = QVBoxLayout(editor_panel)
        editor_layout.setContentsMargins(12, 10, 12, 10)
        editor_label = QLabel("Editor")
        editor_label.setObjectName("cardTitle")
        self._cv_editor = QPlainTextEdit()
        self._cv_editor.setPlainText(
            self._service.settings.master_cv_path.read_text(encoding="utf-8")
            if self._service.settings.master_cv_path.exists()
            else ""
        )
        self._cv_editor.setPlaceholderText("Edit your Master CV here...")
        editor_layout.addWidget(editor_label)
        editor_layout.addWidget(self._cv_editor)

        # Preview (read-only)
        preview_panel = QFrame()
        preview_panel.setProperty("role", "card")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(12, 10, 12, 10)
        preview_label = QLabel("Preview")
        preview_label.setObjectName("cardTitle")
        self._cv_preview = QPlainTextEdit()
        self._cv_preview.setReadOnly(True)
        self._cv_preview.setPlaceholderText("Preview will appear here...")
        preview_layout.addWidget(preview_label)
        preview_layout.addWidget(self._cv_preview)

        split_view.addWidget(editor_panel)
        split_view.addWidget(preview_panel)
        split_view.setStretchFactor(0, 1)
        split_view.setStretchFactor(1, 1)

        layout.addWidget(split_view)

        # Controls
        controls = QHBoxLayout()
        self._cv_save_button = QPushButton("Save CV")
        self._cv_save_button.clicked.connect(self._save_cv_clicked)
        self._cv_save_button.setObjectName("primaryButton")
        self._cv_reload_button = QPushButton("Reload from File")
        self._cv_reload_button.clicked.connect(self._reload_cv_clicked)
        self._cv_watch_checkbox = QCheckBox("Watch for changes")
        self._cv_watch_checkbox.setChecked(True)
        self._cv_watch_checkbox.stateChanged.connect(self._toggle_cv_watcher)
        
        # File watcher for CV changes
        self._cv_watcher = QFileSystemWatcher()
        self._cv_watcher.fileChanged.connect(self._on_cv_file_changed)
        self._watcher_enabled = True
        if self._service.settings.master_cv_path.exists():
            self._cv_watcher.addPath(str(self._service.settings.master_cv_path))
        controls.addWidget(self._cv_save_button)
        controls.addWidget(self._cv_reload_button)
        controls.addWidget(self._cv_watch_checkbox)
        controls.addStretch(1)
        layout.addLayout(controls)

        self._cv_status_label = QLabel("Ready")
        self._cv_status_label.setProperty("role", "statusBadge")
        layout.addWidget(self._cv_status_label)

        return widget

    def _save_cv_clicked(self) -> None:
        """Save CV editor content to file."""
        try:
            cv_path = self._service.settings.master_cv_path
            # Temporarily disable watcher to avoid trigger on save
            if self._watcher_enabled:
                self._cv_watcher.removePath(str(cv_path))
            cv_path.write_text(self._cv_editor.toPlainText(), encoding="utf-8")
            self._cv_status_label.setText(f"Saved at {datetime.now().strftime('%H:%M:%S')}")
            self._append_log(f"Master CV saved to {cv_path}")
            if self._watcher_enabled:
                self._cv_watcher.addPath(str(cv_path))
        except Exception as exc:
            self._cv_status_label.setText(f"Error: {exc}")
            QMessageBox.warning(self, "Save CV", str(exc))

    def _toggle_cv_watcher(self, state: int) -> None:
        """Toggle file watcher on/off."""
        self._watcher_enabled = (state == Qt.CheckState.Checked.value)
        cv_path = str(self._service.settings.master_cv_path)
        if self._watcher_enabled:
            if self._service.settings.master_cv_path.exists():
                self._cv_watcher.addPath(cv_path)
            self._append_log("CV file watcher enabled")
        else:
            self._cv_watcher.removePath(cv_path)
            self._append_log("CV file watcher disabled")

    def _on_cv_file_changed(self, path: str) -> None:
        """Handle CV file change - reload editor and trigger re-scoring."""
        self._append_log(f"CV file changed: {path}")
        # Reload editor content
        try:
            cv_path = Path(path)
            if cv_path.exists():
                self._cv_editor.setPlainText(cv_path.read_text(encoding="utf-8"))
                self._cv_status_label.setText("Reloaded from file change")
        except Exception as exc:
            self._append_log(f"Error reloading CV: {exc}")
        
        # Trigger re-scoring in background
        self._rescore_jobs_async()
    
    def _rescore_jobs_async(self) -> None:
        """Re-score all jobs with current CV in background thread."""
        def do_rescore():
            return self._service.rescore_all_jobs()
        
        worker = BackgroundActionWorker(do_rescore)
        worker.signals.succeeded.connect(lambda count: self._on_rescore_complete(count))
        worker.signals.failed.connect(lambda err: self._append_log(f"Re-scoring failed: {err}"))
        self._thread_pool.start(worker)
    
    def _on_rescore_complete(self, count: int) -> None:
        """Handle re-scoring completion."""
        self._append_log(f"Re-scored {count} jobs")
        self._cv_status_label.setText(f"Re-scored {count} jobs")
        self.refresh_views()

    def _reload_cv_clicked(self) -> None:
        """Reload CV from file."""
        try:
            cv_path = self._service.settings.master_cv_path
            if cv_path.exists():
                self._cv_editor.setPlainText(cv_path.read_text(encoding="utf-8"))
                self._cv_status_label.setText("Reloaded")
            else:
                self._cv_status_label.setText("File not found")
        except Exception as exc:
            self._cv_status_label.setText(f"Error: {exc}")

    def _build_resume_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)

        self._resume_job_id_input.setPlaceholderText("Optional explicit job id")
        self._resume_tex_path_input.setText(str(self._service.default_resume_tex_path()))

        # Use horizontal splitter for side-by-side layout
        horiz_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: form and workflow
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        form = QFormLayout()
        form.addRow("Job ID", self._resume_job_id_input)
        form.addRow("Staged Markdown Path", self._resume_output_path_value)
        form.addRow("TeX Path", self._resume_tex_path_input)
        form.addRow("Status", self._resume_status_value)
        form_card = QFrame()
        form_card.setProperty("role", "card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(8, 6, 8, 6)
        form_layout.addLayout(form)
        left_layout.addWidget(form_card)

        # Quick AI Generation panel
        ai_card = QFrame()
        ai_card.setProperty("role", "card")
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(8, 6, 8, 6)
        ai_layout.setSpacing(4)
        ai_title = QLabel("AI Resume Generation (Phase C)")
        ai_title.setObjectName("cardTitle")
        ai_layout.addWidget(ai_title)

        ai_desc = QLabel("Generates a targeted LaTeX resume for the selected job using Gemini API.")
        ai_desc.setProperty("role", "muted")
        ai_layout.addWidget(ai_desc)

        ai_buttons = QHBoxLayout()
        ai_buttons.setSpacing(4)
        self._resume_gen_1page_button.setObjectName("primaryButton")
        self._resume_gen_1page_button.clicked.connect(lambda: self._resume_generate_ai_clicked("1"))
        ai_buttons.addWidget(self._resume_gen_1page_button)

        self._resume_gen_halfpage_button.clicked.connect(lambda: self._resume_generate_ai_clicked("half"))
        ai_buttons.addWidget(self._resume_gen_halfpage_button)

        ai_buttons.addStretch(1)
        ai_layout.addLayout(ai_buttons)
        left_layout.addWidget(ai_card)

        # Workflow section with step labels
        workflow_label = QLabel("Resume Workflow:")
        workflow_label.setObjectName("cardTitle")
        left_layout.addWidget(workflow_label)
        
        # Step 1: Stage
        step1_layout = QHBoxLayout()
        step1_layout.setSpacing(4)
        step1_label = QLabel("1. Stage Job Description")
        step1_label.setProperty("role", "formLabel")
        step1_layout.addWidget(step1_label)
        step1_layout.addStretch(1)
        self._resume_stage_button.setObjectName("primaryButton")
        self._resume_stage_button.clicked.connect(self._resume_stage_clicked)
        step1_layout.addWidget(self._resume_stage_button)
        left_layout.addLayout(step1_layout)

        # Step 2: Review & Compile
        step2_layout = QHBoxLayout()
        step2_layout.setSpacing(4)
        step2_label = QLabel("2. Review LaTeX & Compile")
        step2_label.setProperty("role", "formLabel")
        step2_layout.addWidget(step2_label)
        step2_layout.addStretch(1)
        self._resume_compile_button.clicked.connect(self._resume_compile_clicked)
        step2_layout.addWidget(self._resume_compile_button)
        self._resume_approve_button.setObjectName("primaryButton")
        self._resume_approve_button.clicked.connect(self._resume_approve_clicked)
        step2_layout.addWidget(self._resume_approve_button)
        left_layout.addLayout(step2_layout)

        # Step 3: View Result
        step3_layout = QHBoxLayout()
        step3_layout.setSpacing(4)
        step3_label = QLabel("3. View Result")
        step3_label.setProperty("role", "formLabel")
        step3_layout.addWidget(step3_label)
        step3_layout.addStretch(1)
        self._resume_open_pdf_button.clicked.connect(self._resume_open_pdf_clicked)
        step3_layout.addWidget(self._resume_open_pdf_button)
        left_layout.addLayout(step3_layout)

        # Job details section (scrollable, shows what will be fed to AI)
        job_details_group = QGroupBox("Job Details for AI")
        job_details_layout = QVBoxLayout(job_details_group)
        job_details_layout.setContentsMargins(8, 6, 8, 6)
        
        # Enrichment progress row
        enrichment_row = QHBoxLayout()
        enrichment_row.setSpacing(6)
        self._resume_enrichment_label = QLabel("⏳ Enrichment: Waiting for extension...")
        self._resume_enrichment_label.setProperty("role", "statusBadge")
        self._resume_enrichment_label.setVisible(False)  # Hidden until a job is double-clicked
        enrichment_row.addWidget(self._resume_enrichment_label)
        enrichment_row.addStretch(1)
        job_details_layout.addLayout(enrichment_row)
        
        self._resume_job_details_text = QPlainTextEdit()
        self._resume_job_details_text.setReadOnly(True)
        self._resume_job_details_text.setPlaceholderText("Job details will appear here when a job is staged or selected...")
        self._resume_job_details_text.setMaximumHeight(300)
        job_details_layout.addWidget(self._resume_job_details_text)
        left_layout.addWidget(job_details_group)

        # Job context info (populated when staging or generating)
        self._resume_context_label = QLabel("No job selected")
        self._resume_context_label.setProperty("role", "muted")
        left_layout.addWidget(self._resume_context_label)
        left_layout.addStretch(1)

        horiz_splitter.addWidget(left_panel)

        # Right panel: LaTeX editor (REQ-3.3)
        editor_label = QLabel("LaTeX Resume Editor:")
        editor_label.setObjectName("cardTitle")
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(editor_label)
        right_layout.addWidget(self._resume_preview)
        horiz_splitter.addWidget(right_panel)
        
        horiz_splitter.setStretchFactor(0, 1)
        horiz_splitter.setStretchFactor(1, 1)
        
        layout.addWidget(horiz_splitter)
        return widget

    def _build_logs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        controls = QHBoxLayout()
        clear_button = QPushButton("Clear Log")
        clear_button.clicked.connect(self._log_output.clear)
        controls.addWidget(clear_button)
        controls.addStretch(1)

        layout.addLayout(controls)
        log_card = QFrame()
        log_card.setProperty("role", "card")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(12, 10, 12, 10)
        log_layout.addWidget(self._log_output)
        layout.addWidget(log_card)
        return widget

    def _create_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(28)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(False)
        return table

    def _start_ingest_server(self) -> None:
        try:
            self._ingest_server = self._service.create_ingest_server()
            self._ingest_server.start()
            self._ingest_status_value.setText("Running")
            self._ingest_endpoint_value.setText(self._ingest_server.endpoint())
            self._append_log("Ingest server started")
        except Exception as exc:
            self._ingest_status_value.setText("Failed")
            self._ingest_endpoint_value.setText(self._service.ingest_endpoint())
            self._append_log(f"Ingest server failed to start: {exc}")
            QMessageBox.warning(self, "Ingest Server", str(exc))

    def _filter_jobs_list(self, jobs: list) -> list:
        """Apply sidebar filters to the jobs list (client-side)."""
        filtered = []
        # Build set of allowed seniority levels
        allowed = set()
        if self._filter_seniority_entry.isChecked():
            allowed.update({"entry", "junior"})
        if self._filter_seniority_mid.isChecked():
            allowed.add("mid")
        if self._filter_seniority_senior.isChecked():
            allowed.update({"senior", "staff", "principal", "lead", "architect"})
        if self._filter_seniority_manager.isChecked():
            allowed.add("manager")

        min_total = self._filter_min_total.value() / 100.0
        min_relevance = self._filter_min_relevance.value() / 100.0
        min_attainability = self._filter_min_attainability.value() / 100.0
        
        # Age filter
        reject_old = self._filter_reject_old_jobs.isChecked()
        max_age_days = self._filter_max_job_age.value()
        from datetime import datetime, timedelta, timezone
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        for job in jobs:
            # Seniority filter
            seniority = _infer_seniority_hint(job.title, job.description or "")
            if seniority not in allowed:
                continue
            
            # Age filter (only apply if reject_old is enabled)
            if reject_old and job.date_posted:
                job_date = job.date_posted
                # Ensure both datetimes are offset-aware (UTC)
                if job_date.tzinfo is None:
                    job_date = job_date.replace(tzinfo=timezone.utc)
                if job_date < cutoff_date:
                    continue  # Skip old jobs
            
            # Score filters (0 = no filter) — safely convert to float
            def _safe_float(val):
                if val is None:
                    return None
                if isinstance(val, float):
                    return val
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None
            
            job_total = _safe_float(job.match_score)
            job_rel = _safe_float(job.score_relevance)
            job_attain = _safe_float(job.score_attainability)
            
            if min_total > 0 and (job_total is None or job_total < min_total):
                continue
            if min_relevance > 0 and (job_rel is None or job_rel < min_relevance):
                continue
            if min_attainability > 0 and (job_attain is None or job_attain < min_attainability):
                continue
            filtered.append(job)
        return filtered

    def refresh_views(self) -> None:
        try:
            snapshot = self._service.dashboard_snapshot()
            search_query = self._jobs_search_input.text().strip() or None
            jobs = self._service.list_jobs(
                limit=self._jobs_limit_input.value(),
                search_query=search_query,
            )
            # Apply sidebar filters (client-side, opt-in)
            jobs = self._filter_jobs_list(jobs)

            runs = self._service.list_recent_runs(limit=200)
            notifications = self._service.list_recent_notifications(limit=200)
            job_count, company_count = self._service.get_jobs_and_companies_count()
        except Exception as exc:
            self._append_log(f"Refresh failed: {exc}")
            QMessageBox.critical(self, "Refresh Failed", str(exc))
            return

        self._populate_dashboard(snapshot)
        self._populate_jobs(jobs)
        self._populate_runs(runs)
        self._populate_notifications(notifications)
        self._jobs_count_label.setText(f"Jobs: {job_count} | Companies: {company_count}")
        search_text = search_query or "all jobs"
        self._jobs_results_label.setText(
            f"Showing {len(jobs)} of up to {self._jobs_limit_input.value()} for {search_text}"
        )

        self.statusBar().showMessage("Data refreshed", 3000)
        self._append_log("UI data refreshed")

    def _populate_dashboard(self, snapshot: DashboardSnapshot) -> None:
        self._db_path_value.setText(str(self._service.settings.db_path))
        self._threshold_value.setText(f"{self._service.settings.notification_threshold:.2f}")
        self._counts_value.setText(
            (
                f"total={snapshot.total_jobs} | queued={snapshot.queued_jobs} "
                f"| notified={snapshot.notified_jobs} "
                f"| above-threshold={snapshot.above_threshold_jobs}"
            )
        )

        if self._ingest_server is None:
            self._ingest_status_value.setText("Stopped")
            self._ingest_endpoint_value.setText(self._service.ingest_endpoint())
        else:
            status = "Running" if self._ingest_server.is_running() else "Stopped"
            self._ingest_status_value.setText(status)
            self._ingest_endpoint_value.setText(self._ingest_server.endpoint())

        if snapshot.last_run is None:
            self._last_run_status_value.setText("No runs yet")
            self._last_run_started_value.setText("n/a")
            self._last_run_finished_value.setText("n/a")
            self._last_run_summary_value.setText("n/a")
            return

        last_run = snapshot.last_run
        self._last_run_status_value.setText(last_run.status)
        self._last_run_started_value.setText(_format_datetime(last_run.started_at))
        self._last_run_finished_value.setText(_format_datetime(last_run.finished_at))
        self._last_run_summary_value.setText(
            (
                f"ingested={last_run.scraped}, inserted={last_run.inserted}, "
                f"updated={last_run.updated}, scored={last_run.scored}, "
                f"above={last_run.above_threshold}, notified={last_run.notified}"
            )
        )

    def _populate_jobs(self, jobs: list) -> None:
        self._jobs_table.setSortingEnabled(False)
        self._jobs_table.setRowCount(len(jobs))

        for row, job in enumerate(jobs):
            # Build posted display: prefer posted_ago (e.g., "2 hours ago") with date_posted as tooltip
            posted_display = job.posted_ago or _format_datetime(job.date_posted)
            # Infer seniority from title+description
            seniority = _infer_seniority_hint(job.title, job.description or "")
            
            values = [
                _format_score(job.match_score),  # Total (col 0)
                _format_score(job.score_relevance),  # Relevance (col 1)
                _format_score(job.score_attainability),  # Attainability (col 2)
                _format_score(job.score_recency),  # Recency (col 3)
                seniority.capitalize(),  # Seniority (col 4)
                job.title,  # Title (col 5)
                job.company,  # Company (col 6)
                job.platform,  # Platform (col 7)
                job.status,  # Status (col 8)
                posted_display,  # Posted (col 9)
                job.url,  # URL (col 10)
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if column == 5:  # Title column stores job.id
                    item.setData(Qt.ItemDataRole.UserRole, job.id)
                # Add tooltip with full date if using posted_ago
                if column == 9 and job.posted_ago:  # Posted column
                    item.setToolTip(_format_datetime(job.date_posted))
                # Add tooltip for score columns showing "Why this score?"
                if column in [0, 1, 2, 3] and text != "n/a":
                    score_type = ["Total", "Relevance", "Attainability", "Recency"][column]
                    item.setToolTip(f"{score_type}: {text}\nClick for details")
                self._jobs_table.setItem(row, column, item)

        self._jobs_table.resizeColumnsToContents()
        self._jobs_table.setSortingEnabled(True)
        # Sort by Total score (column 0) descending by default
        self._jobs_table.sortItems(0, Qt.SortOrder.DescendingOrder)

    def _apply_job_filters(self) -> None:
        """Apply search + sidebar filters and refresh the jobs view."""
        # Update settings with sidebar values for scoring weights and preferences
        # This ensures the service uses these values when scoring
        try:
            # Update scoring weights in settings
            self._service.settings.notification_threshold = float(self._filter_notification_threshold.text() or "0.0")
            self._service.settings.user_years_experience = int(self._filter_user_years.text() or "1")
            self._service.settings.critical_skills = self._filter_critical_skills.text() or "python,fastapi,sql,aws"
            self._service.settings.reject_terms = self._filter_reject_terms.text() or "senior,staff,principal,architect"
            self._service.settings.auto_stage_job_description = self._filter_auto_stage.isChecked()
            
            # Note: Scoring weights would need to be passed to the scoring function
            # For now, they're used in the filter display only
        except (ValueError, TypeError) as exc:
            self._append_log(f"Filter validation error: {exc}")
        
        self.refresh_views()

    def _reset_job_filters(self) -> None:
        """Reset all sidebar filters to defaults (show all)."""
        self._filter_seniority_entry.setChecked(True)
        self._filter_seniority_mid.setChecked(True)
        self._filter_seniority_senior.setChecked(True)
        self._filter_seniority_manager.setChecked(True)
        self._filter_min_total.setValue(0)
        self._filter_min_relevance.setValue(0)
        self._filter_min_attainability.setValue(0)
        
        # Reset job preferences to minimal defaults
        self._filter_notification_threshold.setText("0.00")
        self._filter_user_years.setText("1")
        self._filter_critical_skills.clear()
        self._filter_reject_terms.clear()
        self._filter_auto_stage.setChecked(False)
        
        # Reset scoring weights
        self._filter_relevance_slider.setValue(50)
        self._filter_attainability_slider.setValue(30)
        self._filter_recency_slider.setValue(20)
        
        # Reset age filter to minimal (disabled)
        self._filter_reject_old_jobs.setChecked(False)
        self._filter_max_job_age.setValue(30)
        
        self._jobs_search_input.clear()
        self.refresh_views()

    def _recalculate_scores_clicked(self) -> None:
        """Recalculate all job scores using current Master CV."""
        reply = QMessageBox.question(
            self,
            "Recalculate Scores",
            "Recalculate scores for ALL jobs using the current Master CV?\n\nThis will reset and recompute relevance, attainability, and recency scores.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def do_rescore() -> int:
            return self._service.rescore_all_jobs()

        self._resume_busy = True  # reuse resume busy flag for UI disable
        self.statusBar().showMessage("Recalculating scores...")
        self._append_log("Recalculating all job scores...")

        worker = BackgroundActionWorker(fn=do_rescore)
        worker.signals.succeeded.connect(self._on_rescore_complete)
        worker.signals.failed.connect(lambda err: self._append_log(f"Rescore failed: {err}"))
        worker.signals.completed.connect(lambda: setattr(self, '_resume_busy', False))
        self._thread_pool.start(worker)

    def _get_ai_recommendations(self) -> None:
        """Generate AI recommendations for top jobs."""
        # Check both flags - if resume operation is running, warn but allow recommend
        if self._recommend_busy:
            QMessageBox.information(self, "Busy", "AI recommendation is already in progress.")
            return
        if self._resume_busy:
            reply = QMessageBox.question(
                self, "Operation in Progress",
                "A resume operation is in progress.\n\nDo you want to proceed with AI recommendation anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Get top 20% of jobs by match score
        try:
            limit = self._jobs_limit_input.value()
            all_jobs = self._service.list_jobs(limit=limit)
            
            if not all_jobs:
                QMessageBox.information(self, "No Jobs", "No jobs available to analyze.")
                return
            
            # Sort by match_score descending and take top 20%
            sorted_jobs = sorted(
                [j for j in all_jobs if j.match_score is not None],
                key=lambda j: j.match_score if j.match_score is not None else 0.0,
                reverse=True
            )
            
            top_count = max(1, int(len(sorted_jobs) * 0.20))  # At least 1 job
            top_jobs = sorted_jobs[:top_count]
            
            if not top_jobs:
                QMessageBox.information(self, "No Qualified Jobs", "No jobs with scores found.")
                return
            
            self._recommend_busy = True
            self._recommend_button.setEnabled(False)
            self.statusBar().showMessage(f"Generating AI recommendations for top {len(top_jobs)} jobs...")
            self._append_log(f"Requesting AI recommendations for top {len(top_jobs)} jobs (out of {len(all_jobs)} total)...")
            
            # Store job IDs for highlighting/sorting later
            self._last_recommend_job_ids = [job.id for job in top_jobs]
            
            worker = RecommendWorker(self._service, top_jobs)
            worker.signals.succeeded.connect(self._on_recommend_finished)
            worker.signals.failed.connect(self._on_recommend_error)
            worker.signals.completed.connect(self._on_recommend_completed)
            self._thread_pool.start(worker)
            
            # Safety timeout: auto-reset flag after 2 minutes (in case worker hangs)
            QTimer.singleShot(120000, lambda: self._reset_recommend_flag_if_stuck())
            
        except Exception as exc:
            self._append_log(f"Error preparing recommendations: {exc}")
            QMessageBox.warning(self, "Error", f"Failed to prepare recommendations: {exc}")
            self._recommend_busy = False

    def _reset_recommend_flag_if_stuck(self) -> None:
        """Safety method to reset recommend_busy flag if worker gets stuck."""
        if self._recommend_busy:
            self._append_log("Warning: Auto-resetting stuck recommend flag")
            self._recommend_busy = False
            self._recommend_button.setEnabled(True)
            self.statusBar().showMessage("Recommendation timed out")

    def _on_recommend_finished(self, recommendation: str) -> None:
        """Handle successful AI recommendation generation."""
        self._append_log("AI recommendations received successfully")
        
        # Extract job IDs from the top_jobs that were sent to AI
        # (We need to store these during the request)
        top_job_ids = getattr(self, '_last_recommend_job_ids', [])
        
        # Update the AI Recommendation panel (right sidebar)
        if hasattr(self, '_ai_panel'):
            self._ai_panel.update_recommendations(recommendation, top_job_ids)
            self._ai_panel.setVisible(True)
            self._ai_panel.raise_()  # Bring panel to front
            self._ai_panel.update()  # Force UI update
            self._ai_panel.repaint()  # Force repaint
            self._append_log(f"AI panel visible: {self._ai_panel.isVisible()}")
            self._append_log(f"AI panel size: {self._ai_panel.size().width()}x{self._ai_panel.size().height()}")
            self._append_log(f"AI panel isHidden: {self._ai_panel.isHidden()}")
            
            # Force splitter to allocate space for the panel
            self._force_splitter_show_panel()
            
            # Additional check: ensure panel is not collapsed
            if hasattr(self._ai_panel, '_collapse_btn'):
                if self._ai_panel._collapse_btn.text() == "▶":  # If collapsed
                    self._ai_panel._collapse_btn.click()  # Expand it
                    self._append_log("Auto-expanded AI panel")
        
        # Highlight AI picks in the table
        self._highlight_ai_picks(top_job_ids)
        
        # Auto-sort table to bring AI picks to top
        self._resort_by_ai_picks(top_job_ids)
        
        self.statusBar().showMessage("AI recommendations ready - check right panel")

    def _on_recommend_error(self, error: str) -> None:
        """Handle AI recommendation error."""
        self._append_log(f"AI recommendation failed: {error}")
        QMessageBox.warning(self, "AI Recommendation Failed", f"Failed to generate recommendations:\n{error}")
        self.statusBar().showMessage("AI recommendation failed")

    def _on_recommend_completed(self) -> None:
        """Handle recommendation worker completion."""
        self._recommend_busy = False
        self._recommend_button.setEnabled(True)

    def _highlight_ai_picks(self, job_ids: list[str]) -> None:
        """Highlight the AI-picked rows with purple tint and badge."""
        # Clear previous highlights
        for row in range(self._jobs_table.rowCount()):
            for col in range(self._jobs_table.columnCount()):
                item = self._jobs_table.item(row, col)
                if item:
                    item.setBackground(Qt.GlobalColor.white)  # Reset
                    if col == 5:  # Title column
                        text = item.text()
                        # Remove old badge if present
                        if "✨ AI Pick" in text:
                            item.setText(text.replace(" ✨ AI Pick", ""))

        # Apply new highlights
        ai_color = Qt.GlobalColor.cyan  # Light purple-ish tint
        for row in range(self._jobs_table.rowCount()):
            item = self._jobs_table.item(row, 5)  # Title column has job ID
            if item:
                job_id = item.data(Qt.ItemDataRole.UserRole)
                if job_id in job_ids[:5]:  # Top 5 picks
                    # Add purple tint to entire row
                    for col in range(self._jobs_table.columnCount()):
                        row_item = self._jobs_table.item(row, col)
                        if row_item:
                            row_item.setBackground(ai_color)
                    # Add badge to title
                    current_text = item.text()
                    if "✨ AI Pick" not in current_text:
                        item.setText(f"{current_text} ✨ AI Pick")

    def _resort_by_ai_picks(self, job_ids: list[str]) -> None:
        """Auto-sort table to bring AI picks to the top."""
        if not job_ids:
            return

        # Temporarily disable sorting
        self._jobs_table.setSortingEnabled(False)

        # We need to re-populate the table with AI picks first
        # For now, just ensure the table is sorted by the first column (Total score) descending
        # The AI picks are already the top 20% by score, so they should be at top
        self._jobs_table.setSortingEnabled(True)
        self._jobs_table.sortItems(0, Qt.SortOrder.DescendingOrder)  # Sort by Total score

    def _adjust_splitter_after_ai_panel_toggle(self) -> None:
        """Adjust splitter sizes when AI panel is shown/hidden."""
        if not hasattr(self, '_ai_panel'):
            return

        # Get the splitter (body_splitter)
        splitter = self._ai_panel.parent()
        while splitter and not isinstance(splitter, QSplitter):
            splitter = splitter.parent() if hasattr(splitter, 'parent') else None

        if splitter:
            if self._ai_panel.isVisible():
                # Panel is now visible - set stretch factors to show it
                splitter.setStretchFactor(0, 0)  # Sidebar fixed
                splitter.setStretchFactor(1, 1)  # Middle expands
                splitter.setStretchFactor(2, 0)  # AI panel fixed width
            else:
                # Panel is hidden - remove it from stretch calculation
                splitter.setStretchFactor(0, 0)  # Sidebar fixed
                splitter.setStretchFactor(1, 1)  # Middle expands
                splitter.setStretchFactor(2, 0)  # AI panel hidden

    def _force_splitter_show_panel(self) -> None:
        """Force the splitter to allocate space for the AI panel."""
        if not hasattr(self, '_ai_panel'):
            self._append_log("No _ai_panel found")
            return

        # Get the splitter
        splitter = self._ai_panel.parent()
        while splitter and not isinstance(splitter, QSplitter):
            splitter = splitter.parent() if hasattr(splitter, 'parent') else None

        if splitter:
            # Get current sizes
            sizes = splitter.sizes()
            self._append_log(f"Splitter sizes before: {sizes}")
            self._append_log(f"Splitter widget count: {splitter.count()}")

            # Ensure we have 3 widgets
            if splitter.count() >= 3:
                total = sum(sizes)
                # Allocate space: sidebar=200, middle=remaining, panel=300
                new_sizes = [200, max(100, total - 500), 300]
                splitter.setSizes(new_sizes)
                splitter.refresh()  # Force refresh
                self._append_log(f"Splitter sizes after: {splitter.sizes()}")
            else:
                self._append_log(f"Warning: Splitter has {splitter.count()} widgets, expected 3")
        else:
            self._append_log("Warning: Could not find splitter parent")

    def _populate_runs(self, runs: list) -> None:
        self._runs_table.setSortingEnabled(False)
        self._runs_table.setRowCount(len(runs))

        for row, run in enumerate(runs):
            values = [
                run.status,
                run.run_id,
                _format_datetime(run.started_at),
                _format_datetime(run.finished_at),
                str(run.scraped),
                str(run.inserted),
                str(run.updated),
                str(run.scored),
                str(run.above_threshold),
                str(run.notified),
                run.error_message or "",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._runs_table.setItem(row, column, item)

        self._runs_table.resizeColumnsToContents()
        self._runs_table.setSortingEnabled(True)

    def _populate_notifications(self, notifications: list) -> None:
        self._notifications_table.setSortingEnabled(False)
        self._notifications_table.setRowCount(len(notifications))

        for row, event in enumerate(notifications):
            values = [
                _format_datetime(event.notified_at),
                event.delivery_status,
                _format_score(event.score),
                event.title,
                event.company,
                event.url,
                event.error_message or "",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._notifications_table.setItem(row, column, item)

        self._notifications_table.resizeColumnsToContents()
        self._notifications_table.setSortingEnabled(True)

    def _open_selected_job_url(self) -> None:
        selected = self._jobs_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "No Job Selected", "Select a row in Jobs first.")
            return

        row = selected[0].row()
        url_item = self._jobs_table.item(row, 10)  # URL column
        if url_item is None:
            QMessageBox.warning(self, "Missing URL", "Selected row has no URL.")
            return

        url = url_item.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Selected row has no URL.")
            return

        opened = QDesktopServices.openUrl(QUrl(url))
        if not opened:
            QMessageBox.warning(self, "Open Failed", f"Could not open URL: {url}")
            return

        # Start enrichment polling for this job
        title_item = self._jobs_table.item(row, 5)  # Title column
        if title_item:
            job_id = title_item.data(Qt.ItemDataRole.UserRole)
            if job_id:
                self._start_enrichment_polling(str(job_id), row)

        self._append_log(f"Opened URL: {url}, monitoring enrichment...")

    def _on_job_double_clicked(self, item: QTableWidgetItem) -> None:
        """Handle double-click on job table: open URL, start enrichment polling, and auto-stage for resume."""
        row = item.row()
        
        # Get job details from table
        url_item = self._jobs_table.item(row, 10)  # URL column
        title_item = self._jobs_table.item(row, 5)  # Title column
        company_item = self._jobs_table.item(row, 6)  # Company column
        
        if not url_item or not title_item:
            self._append_log("Double-click: Missing URL or title item")
            return
        
        url = url_item.text().strip()
        title = title_item.text().strip()
        company = company_item.text().strip() if company_item else "Unknown"
        
        # Get job_id from the title item's UserRole data
        job_id = title_item.data(Qt.ItemDataRole.UserRole)
        if not job_id:
            self._append_log("Double-click: No job_id found for job")
            # Try to get job_id from the service using title+company
            try:
                jobs = self._service.list_jobs(limit=5000)
                for job in jobs:
                    if job.title == title and job.company == company:
                        job_id = job.id
                        self._append_log(f"Double-click: Found job_id by title+company: {job_id}")
                        break
            except Exception as exc:
                self._append_log(f"Double-click: Error finding job_id: {exc}")
            
        if not job_id:
            self._append_log("Double-click: Could not determine job_id")
            return
        
        self._append_log(f"Double-click: job_id={job_id}, title={title}, company={company}")
        
        # Open URL if available
        if url:
            opened = QDesktopServices.openUrl(QUrl(url))
            if opened:
                self._append_log(f"Double-click opened URL: {url}")
                # Start enrichment polling to monitor auto-scrape from the job page
                self._start_enrichment_polling(str(job_id), row)
            else:
                self._append_log(f"Double-click: Failed to open URL: {url}")
        
        # Switch to Resume tab
        tabs = self.findChild(QTabWidget, "mainTabs")
        if tabs:
            for i in range(tabs.count()):
                if "Resume" in tabs.tabText(i) and "Variant" not in tabs.tabText(i):
                    tabs.setCurrentIndex(i)
                    break
        
        # Pre-populate the job ID field
        self._resume_job_id_input.setText(str(job_id))
        
        # Populate the job details section immediately so user sees info on Resume tab
        self._update_resume_job_details(str(job_id))
        
        # Set flag so that when enrichment polling detects the enriched data,
        # it auto-stages the resume (see _on_enrichment_detected)
        self._pending_stage_after_enrichment = True
        
        # DON'T stage immediately - wait for enrichment to complete
        # The staging will happen in _on_enrichment_detected() if flag is set
        self._append_log(f"Waiting for enrichment before staging resume for: {title} at {company}")

    def _copy_selected_jobs(self) -> None:
        """Copy selected jobs to clipboard as tab-separated values."""
        selected_rows = self._jobs_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        rows_data = []
        headers = []
        for col in range(self._jobs_table.columnCount()):
            header = self._jobs_table.horizontalHeaderItem(col)
            headers.append(header.text() if header else f"Column {col}")

        rows_data.append("\t".join(headers))

        for row_index in sorted([r.row() for r in selected_rows]):
            row_data = []
            for col in range(self._jobs_table.columnCount()):
                item = self._jobs_table.item(row_index, col)
                row_data.append(item.text() if item else "")
            rows_data.append("\t".join(row_data))

        clipboard_text = "\n".join(rows_data)
        QApplication.clipboard().setText(clipboard_text)
        self._append_log(f"Copied {len(selected_rows)} job(s) to clipboard")

    def _on_job_selection_changed(self) -> None:
        selected = self._jobs_table.selectionModel().selectedRows()
        if not selected:
            self._job_details_text.clear()
            return

        row = selected[0].row()
        details = []
        
        # Get basic info from table (Title=5, Company=6, URL=10)
        title_item = self._jobs_table.item(row, 5)  # Title column
        company_item = self._jobs_table.item(row, 6)  # Company column
        url_item = self._jobs_table.item(row, 10)  # URL column
        
        if title_item:
            details.append(f"Title: {title_item.text()}")
        if company_item:
            details.append(f"Company: {company_item.text()}")
        if url_item:
            details.append(f"URL: {url_item.text()}")
        
        # Get the full job record to show all details
        job_id = title_item.data(Qt.ItemDataRole.UserRole) if title_item else None
        if job_id:
            job = self._service.get_job_by_id(str(job_id))
            if job is not None:
                # Show description first (most important)
                if job.description and len(job.description.strip()) > 0:
                    desc = job.description.strip()
                    details.append(f"\n--- Description ({len(desc)} chars) ---")
                    if len(desc) > 1000:
                        details.append(desc[:1000] + "...\n(truncated, full text in DB)")
                    else:
                        details.append(desc)
                else:
                    details.append("\n--- Description: (empty) ---")
                if job.summary:
                    details.append(
                        f"\nSummary: {job.summary[:200]}..." if len(job.summary) > 200 else f"\nSummary: {job.summary}"
                    )
                if job.requirements:
                    details.append(
                        f"\nRequirements: {job.requirements[:200]}..." if len(job.requirements) > 200 else f"\nRequirements: {job.requirements}"
                    )
                if job.location:
                    details.append(f"Location: {job.location}")
                if job.county:
                    details.append(f"County: {job.county}")
                if job.workplace_type:
                    details.append(f"Workplace: {job.workplace_type}")
                if job.employment_type:
                    details.append(f"Employment: {job.employment_type}")
                if job.department:
                    details.append(f"Department: {job.department}")
                if job.team:
                    details.append(f"Team: {job.team}")
                if job.compensation:
                    details.append(f"Compensation: {job.compensation}")
                if job.posted_at:
                    details.append(f"Posted At: {job.posted_at}")
                if job.posted_ago:
                    details.append(f"Posted: {job.posted_ago}")
                if job.views is not None:
                    details.append(f"Views: {job.views}")
                if job.saves is not None:
                    details.append(f"Saves: {job.saves}")
                if job.applications is not None:
                    details.append(f"Applications: {job.applications}")
        
        self._job_details_text.setPlainText("\n".join(details))

    # ==================== ENRICHMENT POLLING ====================

    def _start_enrichment_polling(self, job_id: str, row: int) -> None:
        """Start polling the database for job enrichment status."""
        self._enrichment_job_id = job_id
        self._enrichment_job_row = row
        self._enrichment_poll_count = 0
        # Capture the description length right now so we can detect real growth
        self._enrichment_initial_desc_length = self._get_job_description_length(job_id)
        self._enrichment_poll_timer.start()
        self._append_log(
            f"Started enrichment polling for job: {job_id} "
            f"(initial desc length={self._enrichment_initial_desc_length})"
        )
        # Show enrichment status on the Resume tab
        self._resume_enrichment_label.setText(
            f"⏳ Enrichment: Waiting for extension on the job page..."
        )
        self._resume_enrichment_label.setVisible(True)
        self._resume_enrichment_label.setProperty("role", "statusBadge")
        self._resume_enrichment_label.style().unpolish(self._resume_enrichment_label)
        self._resume_enrichment_label.style().polish(self._resume_enrichment_label)

    def _get_job_description_length(self, job_id: str) -> int:
        """Get the current description length for a job."""
        try:
            job = self._service.get_job_by_id(job_id)
            if job and job.description:
                return len(job.description.strip())
        except Exception:
            pass
        return 0

    def _check_enrichment_status(self) -> None:
        """Check if the job has been enriched (poll callback)."""
        self._enrichment_poll_count += 1
        if self._enrichment_job_id is None:
            self._enrichment_poll_timer.stop()
            return

        try:
            enriched = self._service.poll_job_enrichment(
                self._enrichment_job_id,
                initial_desc_length=self._enrichment_initial_desc_length,
            )
            if enriched:
                self._append_log(f"Enrichment detected for job {self._enrichment_job_id}")
                self._on_enrichment_detected()
                return
            else:
                # Log progress for debugging
                if self._enrichment_poll_count % 5 == 0:  # Every 10 seconds
                    self._append_log(f"Still waiting for enrichment... (poll {self._enrichment_poll_count}/{self._enrichment_poll_max})")
                    # Update the Resume tab enrichment indicator so user knows it's still working
                    elapsed = self._enrichment_poll_count * 2  # 2s interval
                    self._resume_enrichment_label.setText(
                        f"⏳ Enrichment: Still waiting on job page... ({elapsed}s elapsed)"
                    )
        except Exception as exc:
            self._append_log(f"Enrichment poll error: {exc}")

        # Check timeout
        if self._enrichment_poll_count >= self._enrichment_poll_max:
            self._enrichment_poll_timer.stop()
            self._append_log(
                f"Enrichment polling timed out for job {self._enrichment_job_id}. "
                "The extension may not have auto-scraped. Try the popup 'Capture' button."
            )
            self.statusBar().showMessage(
                "Enrichment check timed out — extension may not be active on that page", 5000
            )
            self._resume_enrichment_label.setText(
                f"⚠️ Enrichment: Timed out — try the browser extension popup Capture button"
            )
            self._resume_enrichment_label.setProperty("role", "statusBadge")
            self._resume_enrichment_label.style().unpolish(self._resume_enrichment_label)
            self._resume_enrichment_label.style().polish(self._resume_enrichment_label)
            self._enrichment_job_id = None
            self._enrichment_job_row = None

    def _on_enrichment_detected(self) -> None:
        """Handle successful enrichment detection."""
        self._enrichment_poll_timer.stop()

        # Show success on the Resume tab enrichment indicator
        self._resume_enrichment_label.setText("✅ Enrichment: Complete! Full description loaded.")
        self._resume_enrichment_label.setProperty("role", "statusBadge")
        self._resume_enrichment_label.style().unpolish(self._resume_enrichment_label)
        self._resume_enrichment_label.style().polish(self._resume_enrichment_label)

        # Update the status cell in the jobs table
        if self._enrichment_job_row is not None:
            row = self._enrichment_job_row
            status_item = self._jobs_table.item(row, 7)  # Status column
            if status_item:
                current_status = status_item.text().strip()
                if "Enriched" not in current_status:
                    status_item.setText(f"{current_status} ✓Enriched")

        # Immediately refresh the "Job Details for AI" field on the Resume tab
        # so the user sees the enriched description right away, even before
        # the auto-stage background action completes.
        if self._enrichment_job_id is not None:
            self._update_resume_job_details(self._enrichment_job_id)

        self._append_log(f"Job {self._enrichment_job_id} enriched successfully!")
        self.statusBar().showMessage("Job data enriched from detail page ✓", 5000)
        self.refresh_views()
        
        # Auto-stage resume if flag is set (from double-click)
        if self._pending_stage_after_enrichment:
            self._pending_stage_after_enrichment = False
            self._append_log("Auto-staging resume after enrichment...")
            self._resume_stage_clicked()
        
        self._enrichment_job_id = None
        self._enrichment_job_row = None

    # ==================== RESUME GENERATION ====================

    def _generate_resume_for_selected_job(self) -> None:
        """Right-click handler: generate a resume for the selected job."""
        selected = self._jobs_table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "No Job Selected", "Select a job row first.")
            return

        row = selected[0].row()
        title_item = self._jobs_table.item(row, 5)  # Title column
        company_item = self._jobs_table.item(row, 6)  # Company column
        if not title_item:
            QMessageBox.warning(self, "Missing Data", "Selected row has no job data.")
            return

        job_id = title_item.data(Qt.ItemDataRole.UserRole)
        if not job_id:
            QMessageBox.warning(self, "Missing Job ID", "Selected row has no job ID.")
            return

        company = company_item.text().strip() if company_item else "Unknown"
        title = title_item.text().strip()

        # Switch to Resume tab and pre-populate
        tabs = self.findChild(QTabWidget, "mainTabs")
        if tabs:
            # Find the Resume tab index (usually 4)
            for i in range(tabs.count()):
                if "Resume" in tabs.tabText(i) and "Variant" not in tabs.tabText(i):
                    tabs.setCurrentIndex(i)
                    break

        # Pre-populate the job ID field
        self._resume_job_id_input.setText(str(job_id))
        
        # Update job details section
        self._update_resume_job_details(str(job_id))

        # Auto-stage the job description
        self._append_log(f"Generating resume for: {title} at {company} (job_id={job_id})")
        self._resume_stage_clicked()

    def _resume_generate_ai_clicked(self, max_pages: str = "1") -> None:
        """Generate a resume via AI for the currently staged job."""
        latex_content = self._resume_preview.get_latex_content()
        if latex_content.strip() and latex_content.strip().startswith("\\documentclass"):
            reply = QMessageBox.question(
                self,
                "Overwrite Resume?",
                "There's already a resume in the editor. Generate a new one and overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        job_id = self._resume_job_id_input.text().strip()
        if not job_id:
            QMessageBox.warning(self, "No Job", "Enter or select a Job ID first.")
            return

        page_label = "1/2-page" if max_pages == "half" else "1-page"

        def do_generate() -> dict:
            return self._service.generate_resume_content(
                job_id=job_id, max_pages=max_pages,
            )

        self._start_resume_action(
            action_name=f"AI Generate ({page_label})",
            fn=do_generate,
            success_handler=lambda result: self._resume_ai_generate_succeeded(result, page_label),
        )

    def _resume_ai_generate_succeeded(self, result: object, page_label: str) -> None:
        """Handle successful AI resume generation."""
        result_dict = dict(result)  # Convert from dict-like to dict
        tex_path = result_dict.get("tex_path", "")
        title = result_dict.get("title", "Unknown")
        company = result_dict.get("company", "Unknown")

        # Load the generated LaTeX into the editor
        if tex_path:
            tex_path_obj = Path(tex_path)
            if tex_path_obj.exists():
                self._resume_preview.load_file(tex_path_obj)
                self._resume_tex_path_input.setText(str(tex_path_obj))

        self._resume_status_value.setText(f"AI Generated ({page_label})")
        self._append_log(
            f"AI resume generated for {title} at {company} | tex={tex_path}"
        )
        self.statusBar().showMessage(f"AI {page_label} resume generated ✓", 5000)

    def _show_jobs_context_menu(self, position) -> None:
        """Show context menu for jobs table."""
        selected = self._jobs_table.selectionModel().selectedRows()
        if not selected:
            return

        menu = QMenu(self)
        copy_action = QAction("Copy Selected Rows", self)
        copy_action.triggered.connect(self._copy_selected_jobs)
        menu.addAction(copy_action)

        menu.addSeparator()

        resume_action = QAction("Generate Resume for Selected Job", self)
        resume_action.triggered.connect(self._generate_resume_for_selected_job)
        menu.addAction(resume_action)

        resume_half_action = QAction("Generate 1/2-Page Resume (AI)", self)
        resume_half_action.triggered.connect(
            lambda: self._generate_resume_ai_for_job_from_context_menu("half")
        )
        menu.addAction(resume_half_action)

        menu.exec(self._jobs_table.viewport().mapToGlobal(position))

    def _generate_resume_ai_for_job_from_context_menu(self, max_pages: str) -> None:
        """Generate an AI resume directly from context menu."""
        selected = self._jobs_table.selectionModel().selectedRows()
        if not selected:
            return

        row = selected[0].row()
        title_item = self._jobs_table.item(row, 5)  # Title column
        if not title_item:
            return

        job_id = title_item.data(Qt.ItemDataRole.UserRole)
        if not job_id:
            return

        # Pre-populate and trigger AI generation
        self._resume_job_id_input.setText(str(job_id))

        tabs = self.findChild(QTabWidget, "mainTabs")
        if tabs:
            for i in range(tabs.count()):
                if "Resume" in tabs.tabText(i) and "Variant" not in tabs.tabText(i):
                    tabs.setCurrentIndex(i)
                    break

        self._resume_generate_ai_clicked(max_pages=max_pages)

    def _clear_jobs(self) -> None:
        """Clear all jobs from the database after user confirmation."""
        reply = QMessageBox.question(
            self,
            "Confirm Clear Jobs",
            "Are you sure you want to delete ALL jobs from the database?\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                deleted_count = self._service.clear_jobs()
                self.refresh_views()
                QMessageBox.information(
                    self,
                    "Jobs Cleared",
                    f"Successfully deleted {deleted_count} jobs from the database.",
                )
                self._append_log(f"Cleared {deleted_count} jobs from database")
            except Exception as exc:
                QMessageBox.critical(
                    self,
                    "Clear Failed",
                    f"Failed to clear jobs: {exc}",
                )
                self._append_log(f"Failed to clear jobs: {exc}")

    def _set_resume_controls_enabled(self, enabled: bool) -> None:
        self._resume_job_id_input.setEnabled(enabled)
        self._resume_min_score_input.setEnabled(enabled)
        self._resume_tex_path_input.setEnabled(enabled)
        self._resume_stage_button.setEnabled(enabled)
        self._resume_compile_button.setEnabled(enabled)
        self._resume_open_pdf_button.setEnabled(enabled)

    def _start_resume_action(
        self,
        action_name: str,
        fn: Callable[[], object],
        success_handler: Callable[[object], None],
    ) -> None:
        if self._resume_busy:
            return

        self._resume_busy = True
        self._set_resume_controls_enabled(False)
        self.statusBar().showMessage(f"Resume action running: {action_name}")
        self._append_log(f"Resume action started: {action_name}")

        worker = BackgroundActionWorker(fn=fn)
        worker.signals.succeeded.connect(success_handler)
        worker.signals.failed.connect(self._resume_action_failed)
        worker.signals.completed.connect(self._resume_action_completed)
        self._current_resume_worker = worker
        self._thread_pool.start(worker)

    def _resume_stage_clicked(self) -> None:
        min_score_text = self._resume_min_score_input.text().strip()
        minimum_score: float | None = None
        if min_score_text:
            try:
                minimum_score = float(min_score_text)
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid Minimum Score",
                    "Minimum score must be a valid number (for example 0.00).",
                )
                return

        job_id = self._resume_job_id_input.text().strip() or None
        self._start_resume_action(
            action_name="Stage Job Description",
            fn=lambda: self._service.stage_resume_target(
                minimum_score=minimum_score,
                job_id=job_id,
            ),
            success_handler=self._resume_stage_succeeded,
        )

    def _update_resume_job_details(self, job_id: str) -> None:
        """Update the scrollable job details section with job information."""
        try:
            job = self._service.get_job_by_id(job_id)
            if job:
                details = []
                details.append(f"Job ID: {job.id}")
                details.append(f"Title: {job.title}")
                details.append(f"Company: {job.company}")
                details.append(f"Location: {job.location or 'N/A'}")
                details.append(f"Platform: {job.platform}")
                details.append(f"URL: {job.url}")
                details.append(f"Match Score: {f'{job.match_score:.3f}' if job.match_score is not None else 'N/A'}")
                details.append("")
                details.append("Description:")
                details.append(job.description or 'No description available')
                self._resume_job_details_text.setPlainText('\n'.join(details))
            else:
                self._resume_job_details_text.setPlainText(f"Job {job_id} not found")
        except Exception as exc:
            self._resume_job_details_text.setPlainText(f"Error loading job details: {exc}")

    def _resume_approve_clicked(self) -> None:
        """Handle Approve & Compile button click (REQ-3.4).

        This reads the current LaTeX content from the editor, saves it to the
        TeX path, and compiles it with the approved flag set to True.
        """
        # Get LaTeX content from editor
        latex_content = self._resume_preview.get_latex_content()
        if not latex_content.strip():
            QMessageBox.warning(
                self,
                "Empty Resume",
                "The LaTeX editor is empty. Nothing to approve and compile.",
            )
            return

        # Get output path
        tex_path_text = self._resume_tex_path_input.text().strip()
        if not tex_path_text:
            tex_path_text = str(self._service.default_resume_tex_path())
        from pathlib import Path

        tex_path = Path(tex_path_text)
        if not tex_path_text.lower().endswith(".tex"):
            tex_path = tex_path.with_suffix(".tex")

        # Save the editor content to file
        try:
            tex_path.parent.mkdir(parents=True, exist_ok=True)
            tex_path.write_text(latex_content, encoding="utf-8")
            self._append_log(f"Saved approved LaTeX to: {tex_path}")
        except OSError as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not save LaTeX file:\n{exc}",
            )
            return

        # Now compile with approved=True
        self._start_resume_action(
            action_name="Approve & Compile",
            fn=lambda: self._service.approve_and_compile_resume(tex_path=tex_path),
            success_handler=self._resume_compile_succeeded,
        )

    def _resume_compile_clicked(self) -> None:
        tex_path_text = self._resume_tex_path_input.text().strip()
        tex_path = Path(tex_path_text) if tex_path_text else None
        self._start_resume_action(
            action_name="Compile Resume",
            fn=lambda: self._service.compile_resume(tex_path=tex_path),
            success_handler=self._resume_compile_succeeded,
        )

    def _resume_open_pdf_clicked(self) -> None:
        candidate = self._resume_last_pdf_path
        if candidate is None:
            tex_candidate = self._resume_tex_path_input.text().strip()
            if tex_candidate:
                candidate = Path(tex_candidate).with_suffix(".pdf")

        if candidate is None or not candidate.exists():
            QMessageBox.information(
                self,
                "No Compiled PDF",
                "Compile a resume first before opening the PDF.",
            )
            return

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(candidate)))
        if not opened:
            QMessageBox.warning(self, "Open Failed", f"Could not open file: {candidate}")
            return

        self._append_log(f"Opened compiled PDF: {candidate}")

    def _resume_stage_succeeded(self, result: object) -> None:
        output_path = Path(str(getattr(result, "output_path")))

        # Load the staged content into the LaTeX editor
        preview = ""
        if output_path.exists():
            preview = output_path.read_text(encoding="utf-8")

            # If it's a .tex file, load into editor
            if output_path.suffix.lower() == ".tex":
                self._resume_preview.load_file(output_path)
                self._resume_tex_path_input.setText(str(output_path))
            else:
                # It's markdown, show in editor for reference
                self._resume_preview.setPlainText(preview)

        self._resume_output_path_value.setText(str(output_path))

        score = getattr(result, "score", None)
        score_text = "n/a" if score is None else f"{score:.3f}"
        title = getattr(result, "title", "unknown")
        company = getattr(result, "company", "unknown")
        job_id = getattr(result, "job_id", None)
        
        # Update job details section
        if job_id:
            self._update_resume_job_details(job_id)
        
        self._resume_status_value.setText("Staged")
        self._resume_context_label.setText(f"Job: {title} at {company} | Score: {score_text}")
        self._append_log(
            f"Resume target staged | title={title} company={company} score={score_text}"
        )

    def _resume_compile_succeeded(self, result: object) -> None:
        tex_path = Path(str(getattr(result, "tex_path")))
        pdf_path = Path(str(getattr(result, "pdf_path")))
        attempts = getattr(result, "attempts", "n/a")

        self._resume_tex_path_input.setText(str(tex_path))
        self._resume_last_pdf_path = pdf_path
        self._resume_status_value.setText("Compiled")
        self._append_log(
            f"Resume compiled | tex={tex_path} pdf={pdf_path} attempts={attempts}"
        )

    def _resume_action_failed(self, message: str) -> None:
        self._resume_status_value.setText("Failed")
        self._append_log(f"Resume action failed: {message}")
        QMessageBox.critical(self, "Resume Action Failed", message)

    def _resume_action_completed(self) -> None:
        self._resume_busy = False
        self._set_resume_controls_enabled(True)
        self._current_resume_worker = None
        self.statusBar().showMessage("Resume action complete", 5000)

    def _collect_settings_form_values(self) -> dict[str, str]:
        return {
            "JOBPIPE_NOTIFICATION_THRESHOLD": (
                self._filter_notification_threshold.text().strip()
            ),
            "JOBPIPE_USER_YEARS_EXPERIENCE": (
                self._filter_user_years.text().strip()
            ),
            "JOBPIPE_INGEST_HOST": self._settings_ingest_host_input.text().strip(),
            "JOBPIPE_INGEST_PORT": self._settings_ingest_port_input.text().strip(),
            "JOBPIPE_INGEST_MAX_PAYLOAD_BYTES": (
                self._settings_ingest_payload_input.text().strip()
            ),
            "JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION": str(
                self._filter_auto_stage.isChecked()
            ).lower(),
            "JOBPIPE_CRITICAL_SKILLS": self._filter_critical_skills.text().strip(),
            "JOBPIPE_REJECT_TERMS": self._filter_reject_terms.text().strip(),
        }

    def _set_settings_form_values(self, values: dict[str, str]) -> None:
        self._settings_env_path_value.setText(
            str(self._service.editable_env_file_path())
        )
        self._filter_notification_threshold.setText(
            values.get("JOBPIPE_NOTIFICATION_THRESHOLD", "")
        )
        self._filter_user_years.setText(
            values.get("JOBPIPE_USER_YEARS_EXPERIENCE", "")
        )
        self._settings_ingest_host_input.setText(values.get("JOBPIPE_INGEST_HOST", ""))
        self._settings_ingest_port_input.setText(values.get("JOBPIPE_INGEST_PORT", ""))
        self._settings_ingest_payload_input.setText(
            values.get("JOBPIPE_INGEST_MAX_PAYLOAD_BYTES", "")
        )
        self._filter_critical_skills.setText(
            values.get("JOBPIPE_CRITICAL_SKILLS", "")
        )
        self._filter_reject_terms.setText(
            values.get("JOBPIPE_REJECT_TERMS", "")
        )

        self._filter_auto_stage.setChecked(
            _is_truthy_env_value(values.get("JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION", "false"))
        )

    def _load_settings_form_values(self, silent: bool) -> None:
        try:
            values = self._service.load_editable_env_values()
        except Exception as exc:
            self._settings_status_value.setText("Load failed")
            self._append_log(f"Settings load failed: {exc}")
            if not silent:
                QMessageBox.warning(self, "Settings Load Failed", str(exc))
            return

        self._set_settings_form_values(values)
        self._settings_status_value.setText("Loaded")

        self._append_log("Settings form loaded from .env")
        if not silent:
            self.statusBar().showMessage("Settings loaded", 3000)

    def _reload_settings_clicked(self) -> None:
        self._load_settings_form_values(silent=False)

    def _save_settings_clicked(self) -> None:
        values = self._collect_settings_form_values()

        try:
            saved_path = self._service.save_editable_env_values(values)
        except Exception as exc:
            self._settings_status_value.setText("Save failed")
            self._append_log(f"Settings save failed: {exc}")
            QMessageBox.critical(self, "Settings Save Failed", str(exc))
            return

        self._settings_env_path_value.setText(str(saved_path))
        self._settings_status_value.setText("Saved")
        self._append_log(f"Settings saved to {saved_path}")
        self.statusBar().showMessage("Settings saved", 4000)
        self.refresh_views()

    def _build_resume_variants_tab(self) -> QWidget:
        """Build the Resume Variants tab with filtering and ATS optimization."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        # Filter controls
        filter_layout = QHBoxLayout()

        # Company filter
        company_label = QLabel("Company:")
        company_label.setProperty("role", "formLabel")
        filter_layout.addWidget(company_label)
        self._variant_company_filter = QLineEdit()
        self._variant_company_filter.setPlaceholderText("Filter by company...")
        self._variant_company_filter.textChanged.connect(self._refresh_variants_table)
        filter_layout.addWidget(self._variant_company_filter)

        # Job type filter
        jobtype_label = QLabel("Job Type:")
        jobtype_label.setProperty("role", "formLabel")
        filter_layout.addWidget(jobtype_label)
        self._variant_job_type_filter = QLineEdit()
        self._variant_job_type_filter.setPlaceholderText("Filter by job type...")
        self._variant_job_type_filter.textChanged.connect(self._refresh_variants_table)
        filter_layout.addWidget(self._variant_job_type_filter)

        # Page length filter
        pages_label = QLabel("Pages:")
        pages_label.setProperty("role", "formLabel")
        filter_layout.addWidget(pages_label)
        self._variant_page_length_filter = QLineEdit()
        self._variant_page_length_filter.setPlaceholderText("1 or 2")
        self._variant_page_length_filter.textChanged.connect(self._refresh_variants_table)
        filter_layout.addWidget(self._variant_page_length_filter)

        # ATS optimized filter
        self._variant_ats_filter = QCheckBox("ATS Optimized Only")
        self._variant_ats_filter.stateChanged.connect(self._refresh_variants_table)
        filter_layout.addWidget(self._variant_ats_filter)

        filter_layout.addStretch(1)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_variants_table)
        filter_layout.addWidget(refresh_btn)

        layout.addLayout(filter_layout)

        # Variants table
        self._variants_table = QTableWidget()
        self._variants_table.setColumnCount(9)
        self._variants_table.setHorizontalHeaderLabels([
            "ID", "Variant Name", "Company", "Job Type", "Pages",
            "Generation", "CV Hash", "ATS Score", "Created"
        ])
        self._variants_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._variants_table.setAlternatingRowColors(True)
        self._variants_table.setSortingEnabled(True)
        layout.addWidget(self._variants_table)

        # Action buttons
        button_layout = QHBoxLayout()

        view_lineage_btn = QPushButton("View Lineage")
        view_lineage_btn.clicked.connect(self._view_variant_lineage)
        button_layout.addWidget(view_lineage_btn)

        ats_optimize_btn = QPushButton("ATS Optimize Selected")
        ats_optimize_btn.clicked.connect(self._ats_optimize_selected_variant)
        button_layout.addWidget(ats_optimize_btn)

        ats_optimize_all_btn = QPushButton("ATS Optimize All for Job")
        ats_optimize_all_btn.clicked.connect(self._ats_optimize_all_for_selected_job)
        button_layout.addWidget(ats_optimize_all_btn)

        open_tex_btn = QPushButton("Open TeX")
        open_tex_btn.clicked.connect(self._open_selected_variant_tex)
        button_layout.addWidget(open_tex_btn)

        open_pdf_btn = QPushButton("Open PDF")
        open_pdf_btn.clicked.connect(self._open_selected_variant_pdf)
        button_layout.addWidget(open_pdf_btn)

        button_layout.addStretch(1)
        layout.addLayout(button_layout)

        # Status label
        self._variants_status_label = QLabel("Ready")
        self._variants_status_label.setProperty("role", "statusBadge")
        layout.addWidget(self._variants_status_label)

        return widget

    def _refresh_variants_table(self) -> None:
        """Refresh the variants table with current filters."""
        try:
            # Get filter values
            company = self._variant_company_filter.text().strip() or None
            job_type = self._variant_job_type_filter.text().strip() or None
            page_length_str = self._variant_page_length_filter.text().strip()
            page_length = None
            if page_length_str in ("1", "2"):
                page_length = int(page_length_str)
            ats_only = self._variant_ats_filter.isChecked()

            # Get variants from service
            variants = self._service.list_resume_variants(
                target_company=company,
                job_type=job_type,
                page_length=page_length,
                ats_optimized=True if ats_only else None,
                limit=500,
            )

            # Populate table
            self._variants_table.setSortingEnabled(False)
            self._variants_table.setRowCount(len(variants))

            for row, variant in enumerate(variants):
                values = [
                    str(variant.id),
                    variant.variant_name,
                    variant.target_company or "N/A",
                    variant.job_type or "N/A",
                    str(variant.page_length),
                    str(variant.generation_number),
                    variant.master_cv_hash[:8] + "..." if len(variant.master_cv_hash) > 8 else variant.master_cv_hash,
                    f"{variant.ats_score:.2f}" if variant.ats_score else "N/A",
                    variant.created_at.strftime("%Y-%m-%d %H:%M") if variant.created_at else "N/A",
                ]
                for col, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                    self._variants_table.setItem(row, col, item)

            self._variants_table.resizeColumnsToContents()
            self._variants_table.setSortingEnabled(True)
            self._variants_status_label.setText(f"Loaded {len(variants)} variants")

        except Exception as exc:
            self._variants_status_label.setText(f"Error: {exc}")
            QMessageBox.warning(self, "Refresh Variants", str(exc))

    def _get_selected_variant_id(self) -> int | None:
        """Get the selected variant ID from the table."""
        selection = self._variants_table.selectionModel().selectedRows()
        if not selection:
            return None
        id_item = self._variants_table.item(selection[0].row(), 0)
        if id_item:
            return int(id_item.text())
        return None

    def _view_variant_lineage(self) -> None:
        """View the generational lineage of the selected variant."""
        variant_id = self._get_selected_variant_id()
        if variant_id is None:
            QMessageBox.information(self, "View Lineage", "Please select a variant first.")
            return

        try:
            lineage = self._service.get_variant_lineage(variant_id)
            if not lineage:
                QMessageBox.information(self, "View Lineage", "No lineage data found.")
                return

            # Build lineage text
            text = "Resume Variant Lineage:\n\n"
            for i, variant in enumerate(lineage):
                text += f"Generation {variant.generation_number}:\n"
                text += f"  ID: {variant.id}\n"
                text += f"  Name: {variant.variant_name}\n"
                text += f"  Company: {variant.target_company or 'N/A'}\n"
                text += f"  CV Hash: {variant.master_cv_hash[:16] if variant.master_cv_hash else 'N/A'}...\n"
                text += f"  Created: {variant.created_at}\n"
                if i < len(lineage) - 1:
                    text += "\n"

            QMessageBox.information(self, "Variant Lineage", text)

        except Exception as exc:
            QMessageBox.critical(self, "View Lineage", str(exc))

    def _ats_optimize_selected_variant(self) -> None:
        """Run ATS optimization on the selected variant."""
        variant_id = self._get_selected_variant_id()
        if variant_id is None:
            QMessageBox.information(self, "ATS Optimize", "Please select a variant first.")
            return

        reply = QMessageBox.question(
            self, "ATS Optimize",
            "Run ATS optimization on the selected variant?\nThis will use the Gemini API.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._variants_status_label.setText("Running ATS optimization...")
        QApplication.processEvents()

        try:
            result = self._service.ats_optimize_variant(variant_id)
            score = result.get("ats_score", 0)
            recs = result.get("recommendations", [])

            msg = f"ATS Optimization Complete!\n\nATS Score: {score:.2f}\n\n"
            if recs:
                msg += "Recommendations:\n"
                for i, rec in enumerate(recs[:5], 1):
                    msg += f"{i}. {rec}\n"

            QMessageBox.information(self, "ATS Optimization Complete", msg)
            self._refresh_variants_table()

        except Exception as exc:
            QMessageBox.critical(self, "ATS Optimization Failed", str(exc))
            self._variants_status_label.setText(f"Error: {exc}")

    def _ats_optimize_all_for_selected_job(self) -> None:
        """Run ATS optimization on all variants for the selected job."""
        variant_id = self._get_selected_variant_id()
        if variant_id is None:
            QMessageBox.information(self, "ATS Optimize All", "Please select a variant first.")
            return

        try:
            variant = self._service.get_variant_by_id(variant_id)
            if not variant or not variant.job_id:
                QMessageBox.information(self, "ATS Optimize All", "Selected variant has no associated job.")
                return

            reply = QMessageBox.question(
                self, "ATS Optimize All",
                f"Run ATS optimization on ALL variants for job {variant.job_id}?\n"
                "This will use the Gemini API for each variant.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            self._variants_status_label.setText("Running ATS optimization on all variants...")
            QApplication.processEvents()

            result = self._service.ats_optimize_all_for_role(job_id=variant.job_id)

            msg = f"ATS Optimization Complete!\n\n"
            msg += f"Total variants: {result['total']}\n"
            msg += f"Optimized: {result['optimized']}\n"
            msg += f"Failed: {result['failed']}\n"

            QMessageBox.information(self, "ATS Optimization Complete", msg)
            self._refresh_variants_table()

        except Exception as exc:
            QMessageBox.critical(self, "ATS Optimization Failed", str(exc))
            self._variants_status_label.setText(f"Error: {exc}")

    def _open_selected_variant_tex(self) -> None:
        """Open the TeX file of the selected variant."""
        variant_id = self._get_selected_variant_id()
        if variant_id is None:
            QMessageBox.information(self, "Open TeX", "Please select a variant first.")
            return

        try:
            variant = self._service.get_variant_by_id(variant_id)
            if variant and variant.tex_path:
                tex_path = Path(variant.tex_path)
                if tex_path.exists():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(tex_path)))
                else:
                    QMessageBox.warning(self, "Open TeX", f"File not found: {tex_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Open TeX", str(exc))

    def _open_selected_variant_pdf(self) -> None:
        """Open the PDF file of the selected variant."""
        variant_id = self._get_selected_variant_id()
        if variant_id is None:
            QMessageBox.information(self, "Open PDF", "Please select a variant first.")
            return

        try:
            variant = self._service.get_variant_by_id(variant_id)
            if variant and variant.pdf_path:
                pdf_path = Path(variant.pdf_path)
                if pdf_path.exists():
                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))
                else:
                    QMessageBox.warning(self, "Open PDF", f"File not found: {pdf_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Open PDF", str(exc))

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_output.appendPlainText(f"[{timestamp}] {message}")


def launch_gui(settings: Settings) -> int:
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)

    window = JobPipeMainWindow(
        service=JobPipeGuiService(settings),
    )
    window.show()

    if owns_app:
        return int(app.exec())
    return 0
