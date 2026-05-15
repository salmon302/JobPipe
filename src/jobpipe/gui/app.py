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


def _format_score(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


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


class JobPipeMainWindow(QMainWindow):
    def __init__(self, service: JobPipeGuiService) -> None:
        super().__init__()
        self._service = service
        self._thread_pool = QThreadPool(self)
        self._resume_busy = False
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

        self._ingest_status_value = QLabel("Starting")
        self._ingest_endpoint_value = QLabel("n/a")

        self._settings_env_path_value = QLabel()
        self._settings_notification_threshold_input = QLineEdit()
        self._settings_user_years_input = QLineEdit()
        self._settings_ingest_host_input = QLineEdit()
        self._settings_ingest_port_input = QLineEdit()
        self._settings_ingest_payload_input = QLineEdit()
        self._settings_critical_skills_input = QLineEdit()
        self._settings_reject_terms_input = QLineEdit()
        self._settings_auto_stage_checkbox = QCheckBox("Enable auto-stage job description")
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
            ["Total", "Relevance", "Attainability", "Recency", "Title", "Company", "Platform", "Status", "Posted", "URL"]
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

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._ingest_server is not None:
            self._ingest_server.stop()
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
                    stop:0 #f7f4ee, stop:1 #e6eef1);
                color: #1e2a32;
            }
            #appRoot {
                background: transparent;
            }
            #headerBar {
                background: #ffffff;
                border: 1px solid #e4d8cc;
                border-radius: 12px;
            }
            #pageTitle {
                font-size: 22px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            #pageSubtitle {
                color: #5c6b74;
            }
            QMenuBar {
                background: #f6f0ea;
                border-bottom: 1px solid #e4d8cc;
            }
            QMenuBar::item {
                background: transparent;
                padding: 6px 10px;
                color: #1e2a32;
            }
            QMenuBar::item:selected {
                background: #1f6f8b;
                color: #ffffff;
                border-radius: 6px;
            }
            QMenu {
                background: #ffffff;
                border: 1px solid #e4d8cc;
            }
            QMenu::item {
                padding: 6px 12px;
            }
            QMenu::item:selected {
                background: #1f6f8b;
                color: #ffffff;
            }
            QStatusBar {
                background: #f6f0ea;
                border-top: 1px solid #e4d8cc;
                color: #1e2a32;
            }
            QStatusBar::item {
                border: 0;
            }
            QTabWidget::pane {
                background: #ffffff;
                border: 1px solid #e4d8cc;
                border-radius: 8px;
                padding: 8px;
            }
            QTabBar::tab {
                background: #f2ede7;
                color: #2b3a42;
                border: 1px solid #e4d8cc;
                border-bottom: 0;
                padding: 7px 12px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                color: #ffffff;
                background: #1f6f8b;
                border-color: #1f6f8b;
            }
            QTabBar::tab:!selected {
                margin-top: 2px;
            }
            QTabBar::tab:hover {
                background: #efe6dc;
            }
            QFrame[role="card"],
            QFrame[role="metricCard"] {
                background: #ffffff;
                border: 1px solid #e4d8cc;
                border-radius: 10px;
            }
            QFrame[role="chip"] {
                background: #f6f0ea;
                border: 1px solid #e4d8cc;
                border-radius: 10px;
            }
            QLabel[role="chipLabel"] {
                font-size: 9pt;
                color: #6e7a83;
            }
            QLabel[role="chipValue"] {
                font-weight: 700;
                color: #1e2a32;
            }
            QLabel#cardTitle {
                font-size: 10pt;
                font-weight: 600;
                color: #4b5d6a;
            }
            QLabel#metricTitle {
                font-size: 9pt;
                font-weight: 600;
                color: #6e7a83;
            }
            QLabel[role="metricValue"] {
                font-size: 13pt;
                font-weight: 700;
            }
            QLabel[role="statusBadge"] {
                background: #f6f0ea;
                border: 1px solid #e4d8cc;
                border-radius: 8px;
                padding: 4px 8px;
                font-weight: 600;
                color: #1e2a32;
            }
            QLabel[role="muted"] {
                color: #6e7a83;
            }
            QLineEdit, QPlainTextEdit, QTableWidget {
                background: #ffffff;
                border: 1px solid #d9cfc4;
                border-radius: 8px;
                padding: 6px;
                selection-background-color: #1f6f8b;
                color: #1e2a32;
            }
            QPlainTextEdit#detailsText {
                background: #fbf7f2;
            }
            QHeaderView::section {
                background: #efe8df;
                color: #2b3a42;
                border: 0;
                border-bottom: 1px solid #d9cfc4;
                padding: 6px;
                font-weight: 600;
            }
            QTableWidget {
                gridline-color: #e7ddd3;
                alternate-background-color: #fbf7f2;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cbbfb4;
                border-radius: 8px;
                padding: 6px 12px;
                color: #1e2a32;
            }
            QPushButton:hover {
                background: #f2ece6;
            }
            QPushButton#primaryButton {
                background: #1f6f8b;
                color: #ffffff;
                border-color: #1f6f8b;
            }
            QPushButton#primaryButton:hover {
                background: #1b6078;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #e6ddd3;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #1f6f8b;
                border: 1px solid #1b6078;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            """
        )

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("headerBar")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        title = QLabel("JobPipe Control Center")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Ingest and resume operations")
        subtitle.setObjectName("pageSubtitle")

        left = QVBoxLayout()
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
        layout.setSpacing(12)

        # Counts label
        counts_layout = QHBoxLayout()
        counts_layout.addWidget(self._jobs_count_label)
        counts_layout.addWidget(self._jobs_results_label)
        counts_layout.addStretch(1)
        layout.addLayout(counts_layout)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Search:"))
        controls.addWidget(self._jobs_search_input, 1)
        self._jobs_search_input.returnPressed.connect(self.refresh_views)

        self._jobs_search_button.clicked.connect(self.refresh_views)
        controls.addWidget(self._jobs_search_button)

        self._jobs_clear_search_button.clicked.connect(self._clear_job_search)
        controls.addWidget(self._jobs_clear_search_button)

        controls.addWidget(QLabel("Limit:"))
        controls.addWidget(self._jobs_limit_input)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_views)
        controls.addWidget(refresh_button)

        open_button = QPushButton("Open Selected Job")
        open_button.clicked.connect(self._open_selected_job_url)
        controls.addWidget(open_button)

        clear_button = QPushButton("Clear Jobs")
        clear_button.clicked.connect(self._clear_jobs)
        controls.addWidget(clear_button)

        controls.addStretch(1)
        layout.addLayout(controls)
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._jobs_table)

        # Job details panel
        details_panel = QFrame()
        details_panel.setProperty("role", "card")
        details_layout = QVBoxLayout(details_panel)
        details_layout.setContentsMargins(12, 10, 12, 10)
        details_label = QLabel("Job Details")
        details_label.setObjectName("cardTitle")
        self._job_details_text = QPlainTextEdit()
        self._job_details_text.setObjectName("detailsText")
        self._job_details_text.setReadOnly(True)
        self._job_details_text.setPlaceholderText("Select a job to view details...")
        details_layout.addWidget(details_label)
        details_layout.addWidget(self._job_details_text)

        splitter.addWidget(details_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # Connect selection change to show details
        self._jobs_table.selectionModel().selectionChanged.connect(self._on_job_selection_changed)

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

        self._settings_notification_threshold_input.setPlaceholderText("0.80")
        self._settings_user_years_input.setPlaceholderText("1")
        self._settings_ingest_host_input.setPlaceholderText("127.0.0.1")
        self._settings_ingest_port_input.setPlaceholderText("3838")
        self._settings_ingest_payload_input.setPlaceholderText("1000000")
        self._settings_critical_skills_input.setPlaceholderText("python,fastapi,sql,aws")
        self._settings_reject_terms_input.setPlaceholderText("senior,staff,principal,architect")

        # Weight sliders (Phase 2)
        self._relevance_slider = QSlider(Qt.Orientation.Horizontal)
        self._relevance_slider.setRange(0, 100)
        self._relevance_slider.setValue(50)
        self._relevance_label = QLabel("Relevance: 0.50")
        
        self._attainability_slider = QSlider(Qt.Orientation.Horizontal)
        self._attainability_slider.setRange(0, 100)
        self._attainability_slider.setValue(30)
        self._attainability_label = QLabel("Attainability: 0.30")
        
        self._recency_slider = QSlider(Qt.Orientation.Horizontal)
        self._recency_slider.setRange(0, 100)
        self._recency_slider.setValue(20)
        self._recency_label = QLabel("Recency: 0.20")
        
        # Connect sliders to update labels
        self._relevance_slider.valueChanged.connect(
            lambda v: self._relevance_label.setText(f"Relevance: {v/100:.2f}")
        )
        self._attainability_slider.valueChanged.connect(
            lambda v: self._attainability_label.setText(f"Attainability: {v/100:.2f}")
        )
        self._recency_slider.valueChanged.connect(
            lambda v: self._recency_label.setText(f"Recency: {v/100:.2f}")
        )

        form = QFormLayout()
        form.addRow("Env File", self._settings_env_path_value)
        form.addRow("Notification Threshold", self._settings_notification_threshold_input)
        form.addRow("User Years Experience", self._settings_user_years_input)
        form.addRow("Ingest Host", self._settings_ingest_host_input)
        form.addRow("Ingest Port", self._settings_ingest_port_input)
        form.addRow("Ingest Max Payload Bytes", self._settings_ingest_payload_input)
        form.addRow("Critical Skills (CSV)", self._settings_critical_skills_input)
        form.addRow("Reject Terms (CSV)", self._settings_reject_terms_input)
        form.addRow("Flags", self._settings_auto_stage_checkbox)
        form.addRow("Last Save Status", self._settings_status_value)
        form_card = QFrame()
        form_card.setProperty("role", "card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(12, 10, 12, 10)
        form_layout.addLayout(form)
        layout.addWidget(form_card)
        
        # Scoring Weights Section
        weights_label = QLabel("Scoring Weights (Phase 2):")
        weights_label.setObjectName("cardTitle")
        weights_card = QFrame()
        weights_card.setProperty("role", "card")
        weights_layout = QVBoxLayout(weights_card)
        weights_layout.setContentsMargins(12, 10, 12, 10)
        weights_layout.addWidget(weights_label)
        weights_layout.addWidget(self._relevance_label)
        weights_layout.addWidget(self._relevance_slider)
        weights_layout.addWidget(self._attainability_label)
        weights_layout.addWidget(self._attainability_slider)
        weights_layout.addWidget(self._recency_label)
        weights_layout.addWidget(self._recency_slider)
        layout.addWidget(weights_card)

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

        # Editor and preview split
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
        layout.setSpacing(8)

        self._resume_job_id_input.setPlaceholderText("Optional explicit job id")
        self._resume_min_score_input.setPlaceholderText("Defaults to notification threshold")
        self._resume_min_score_input.setText(f"{self._service.settings.notification_threshold:.2f}")
        self._resume_tex_path_input.setText(str(self._service.default_resume_tex_path()))

        form = QFormLayout()
        form.addRow("Job ID", self._resume_job_id_input)
        form.addRow("Minimum Score", self._resume_min_score_input)
        form.addRow("Staged Markdown Path", self._resume_output_path_value)
        form.addRow("TeX Path", self._resume_tex_path_input)
        form.addRow("Status", self._resume_status_value)
        form_card = QFrame()
        form_card.setProperty("role", "card")
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(12, 8, 12, 8)
        form_layout.addLayout(form)
        layout.addWidget(form_card)

        # Quick AI Generation panel
        ai_card = QFrame()
        ai_card.setProperty("role", "card")
        ai_layout = QVBoxLayout(ai_card)
        ai_layout.setContentsMargins(12, 8, 12, 8)
        ai_title = QLabel("AI Resume Generation (Phase C)")
        ai_title.setObjectName("cardTitle")
        ai_layout.addWidget(ai_title)

        ai_desc = QLabel("Generates a targeted LaTeX resume for the selected job using Gemini API.")
        ai_desc.setProperty("role", "muted")
        ai_layout.addWidget(ai_desc)

        ai_buttons = QHBoxLayout()
        self._resume_gen_1page_button.setObjectName("primaryButton")
        self._resume_gen_1page_button.clicked.connect(lambda: self._resume_generate_ai_clicked("1"))
        ai_buttons.addWidget(self._resume_gen_1page_button)

        self._resume_gen_halfpage_button.clicked.connect(lambda: self._resume_generate_ai_clicked("half"))
        ai_buttons.addWidget(self._resume_gen_halfpage_button)

        ai_buttons.addStretch(1)
        ai_layout.addLayout(ai_buttons)
        layout.addWidget(ai_card)

        controls = QHBoxLayout()
        self._resume_stage_button.clicked.connect(self._resume_stage_clicked)
        self._resume_compile_button.clicked.connect(self._resume_compile_clicked)
        self._resume_open_pdf_button.clicked.connect(self._resume_open_pdf_clicked)
        self._resume_stage_button.setObjectName("primaryButton")
        self._resume_approve_button.setObjectName("primaryButton")
        controls.addWidget(self._resume_stage_button)
        controls.addWidget(self._resume_compile_button)
        controls.addWidget(self._resume_approve_button)  # REQ-3.4
        controls.addWidget(self._resume_open_pdf_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        # Job context info (populated when staging or generating)
        self._resume_context_label = QLabel("No job selected")
        self._resume_context_label.setProperty("role", "muted")
        layout.addWidget(self._resume_context_label)

        # LaTeX editor (REQ-3.3)
        editor_label = QLabel("LaTeX Resume Editor:")
        editor_label.setObjectName("cardTitle")
        layout.addWidget(editor_label)
        layout.addWidget(self._resume_preview)
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

    def refresh_views(self) -> None:
        try:
            snapshot = self._service.dashboard_snapshot()
            search_query = self._jobs_search_input.text().strip() or None
            jobs = self._service.list_jobs(
                limit=self._jobs_limit_input.value(),
                search_query=search_query,
            )
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
            
            values = [
                _format_score(job.match_score),  # Total
                _format_score(job.score_relevance),  # Relevance
                _format_score(job.score_attainability),  # Attainability
                _format_score(job.score_recency),  # Recency
                job.title,
                job.company,
                job.platform,
                job.status,
                posted_display,
                job.url,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                if column == 4:
                    item.setData(Qt.ItemDataRole.UserRole, job.id)
                # Add tooltip with full date if using posted_ago
                if column == 8 and job.posted_ago:  # Posted column
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
        url_item = self._jobs_table.item(row, 9)
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
        title_item = self._jobs_table.item(row, 4)
        if title_item:
            job_id = title_item.data(Qt.ItemDataRole.UserRole)
            if job_id:
                self._start_enrichment_polling(str(job_id), row)

        self._append_log(f"Opened URL: {url}, monitoring enrichment...")

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
        
        # Get basic info from table
        title_item = self._jobs_table.item(row, 4)  # Title column
        company_item = self._jobs_table.item(row, 5)  # Company column
        url_item = self._jobs_table.item(row, 9)  # URL column
        
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
        self._enrichment_poll_timer.start()
        self._append_log(f"Started enrichment polling for job: {job_id}")

    def _check_enrichment_status(self) -> None:
        """Check if the job has been enriched (poll callback)."""
        self._enrichment_poll_count += 1
        if self._enrichment_job_id is None:
            self._enrichment_poll_timer.stop()
            return

        try:
            enriched = self._service.poll_job_enrichment(self._enrichment_job_id)
            if enriched:
                self._on_enrichment_detected()
                return
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
            self._enrichment_job_id = None
            self._enrichment_job_row = None

    def _on_enrichment_detected(self) -> None:
        """Handle successful enrichment detection."""
        self._enrichment_poll_timer.stop()

        # Update the status cell in the jobs table
        if self._enrichment_job_row is not None:
            row = self._enrichment_job_row
            status_item = self._jobs_table.item(row, 7)  # Status column
            if status_item:
                current_status = status_item.text().strip()
                if "Enriched" not in current_status:
                    status_item.setText(f"{current_status} ✓Enriched")

        self._append_log(f"Job {self._enrichment_job_id} enriched successfully!")
        self.statusBar().showMessage("Job data enriched from detail page ✓", 5000)
        self.refresh_views()
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
        title_item = self._jobs_table.item(row, 4)
        company_item = self._jobs_table.item(row, 5)
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
        title_item = self._jobs_table.item(row, 4)
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
                    "Minimum score must be a valid number (for example 0.80).",
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
                self._settings_notification_threshold_input.text().strip()
            ),
            "JOBPIPE_USER_YEARS_EXPERIENCE": (
                self._settings_user_years_input.text().strip()
            ),
            "JOBPIPE_INGEST_HOST": self._settings_ingest_host_input.text().strip(),
            "JOBPIPE_INGEST_PORT": self._settings_ingest_port_input.text().strip(),
            "JOBPIPE_INGEST_MAX_PAYLOAD_BYTES": (
                self._settings_ingest_payload_input.text().strip()
            ),
            "JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION": str(
                self._settings_auto_stage_checkbox.isChecked()
            ).lower(),
            "JOBPIPE_CRITICAL_SKILLS": self._settings_critical_skills_input.text().strip(),
            "JOBPIPE_REJECT_TERMS": self._settings_reject_terms_input.text().strip(),
        }

    def _set_settings_form_values(self, values: dict[str, str]) -> None:
        self._settings_env_path_value.setText(
            str(self._service.editable_env_file_path())
        )
        self._settings_notification_threshold_input.setText(
            values.get("JOBPIPE_NOTIFICATION_THRESHOLD", "")
        )
        self._settings_user_years_input.setText(
            values.get("JOBPIPE_USER_YEARS_EXPERIENCE", "")
        )
        self._settings_ingest_host_input.setText(values.get("JOBPIPE_INGEST_HOST", ""))
        self._settings_ingest_port_input.setText(values.get("JOBPIPE_INGEST_PORT", ""))
        self._settings_ingest_payload_input.setText(
            values.get("JOBPIPE_INGEST_MAX_PAYLOAD_BYTES", "")
        )
        self._settings_critical_skills_input.setText(
            values.get("JOBPIPE_CRITICAL_SKILLS", "")
        )
        self._settings_reject_terms_input.setText(
            values.get("JOBPIPE_REJECT_TERMS", "")
        )

        self._settings_auto_stage_checkbox.setChecked(
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
        filter_layout.addWidget(QLabel("Company:"))
        self._variant_company_filter = QLineEdit()
        self._variant_company_filter.setPlaceholderText("Filter by company...")
        self._variant_company_filter.textChanged.connect(self._refresh_variants_table)
        filter_layout.addWidget(self._variant_company_filter)

        # Job type filter
        filter_layout.addWidget(QLabel("Job Type:"))
        self._variant_job_type_filter = QLineEdit()
        self._variant_job_type_filter.setPlaceholderText("Filter by job type...")
        self._variant_job_type_filter.textChanged.connect(self._refresh_variants_table)
        filter_layout.addWidget(self._variant_job_type_filter)

        # Page length filter
        filter_layout.addWidget(QLabel("Pages:"))
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
