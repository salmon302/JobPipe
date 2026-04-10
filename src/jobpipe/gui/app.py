from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
from typing import Callable

from jobpipe.config import Settings
from jobpipe.gui.services import DashboardSnapshot, JobPipeGuiService

try:
    from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
    from PySide6.QtGui import QAction, QDesktopServices
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QApplication,
        QCheckBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QSpinBox,
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


class RunOnceSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    completed = Signal()


class BackgroundActionSignals(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    completed = Signal()


class RunOnceWorker(QRunnable):
    def __init__(self, service: JobPipeGuiService, max_pages: int) -> None:
        super().__init__()
        self._service = service
        self._max_pages = max_pages
        self.signals = RunOnceSignals()

    def run(self) -> None:
        try:
            summary = self._service.run_pipeline_once(max_pages=self._max_pages)
            self.signals.succeeded.emit(summary)
        except Exception as exc:
            self.signals.failed.emit(str(exc))
        finally:
            self.signals.completed.emit()


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
    def __init__(self, service: JobPipeGuiService, default_max_pages: int = 1) -> None:
        super().__init__()
        self._service = service
        self._thread_pool = QThreadPool(self)
        self._run_in_progress = False
        self._scheduler_busy = False
        self._resume_busy = False
        self._current_worker: RunOnceWorker | None = None
        self._current_scheduler_worker: BackgroundActionWorker | None = None
        self._current_resume_worker: BackgroundActionWorker | None = None
        self._default_max_pages = max(1, default_max_pages)

        self._max_pages_spin = QSpinBox()
        self._run_once_button = QPushButton("Run Once")

        self._scheduler_task_name_input = QLineEdit("JobPipeAggregator")
        self._scheduler_interval_spin = QSpinBox()
        self._scheduler_max_pages_spin = QSpinBox()
        self._scheduler_start_time_input = QLineEdit()
        self._scheduler_status_value = QLabel("Unknown")
        self._scheduler_check_button = QPushButton("Check Status")
        self._scheduler_install_button = QPushButton("Install / Update")
        self._scheduler_run_now_button = QPushButton("Run Now")
        self._scheduler_uninstall_button = QPushButton("Uninstall")

        self._settings_env_path_value = QLabel()
        self._settings_notification_threshold_input = QLineEdit()
        self._settings_user_years_input = QLineEdit()
        self._settings_schedule_interval_input = QLineEdit()
        self._settings_critical_skills_input = QLineEdit()
        self._settings_reject_terms_input = QLineEdit()
        self._settings_auto_stage_checkbox = QCheckBox("Enable auto-stage job description")
        self._settings_require_auth_checkbox = QCheckBox("Require usable auth state")
        self._settings_wellfound_enabled_checkbox = QCheckBox("Enable Wellfound scraper")
        self._settings_builtin_enabled_checkbox = QCheckBox("Enable BuiltIn scraper")
        self._settings_reload_button = QPushButton("Reload")
        self._settings_save_button = QPushButton("Validate + Save")
        self._settings_status_value = QLabel("Not loaded")

        self._resume_job_id_input = QLineEdit()
        self._resume_min_score_input = QLineEdit()
        self._resume_stage_button = QPushButton("Stage Job Description")
        self._resume_output_path_value = QLabel("Not staged")
        self._resume_preview = QPlainTextEdit()
        self._resume_preview.setReadOnly(True)
        self._resume_tex_path_input = QLineEdit()
        self._resume_compile_button = QPushButton("Compile Resume")
        self._resume_open_pdf_button = QPushButton("Open Compiled PDF")
        self._resume_status_value = QLabel("Idle")
        self._resume_last_pdf_path: Path | None = None

        self._db_path_value = QLabel()
        self._threshold_value = QLabel()
        self._counts_value = QLabel()
        self._last_run_status_value = QLabel()
        self._last_run_started_value = QLabel()
        self._last_run_finished_value = QLabel()
        self._last_run_summary_value = QLabel()

        self._auth_hiringcafe_value = QLabel()
        self._auth_wellfound_value = QLabel()
        self._auth_builtin_value = QLabel()

        self._jobs_table = self._create_table(
            ["Score", "Title", "Company", "Platform", "Status", "Posted", "URL"]
        )
        self._runs_table = self._create_table(
            [
                "Status",
                "Run ID",
                "Started",
                "Finished",
                "Scraped",
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

        self.setWindowTitle("JobPipe Desktop")
        self.resize(1300, 800)
        self._build_ui()
        self.statusBar().showMessage("Ready")
        self.refresh_views()
        self._load_settings_form_values(silent=True)

    def _build_ui(self) -> None:
        central = QWidget(self)
        root = QVBoxLayout(central)

        title = QLabel("JobPipe Control Center")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        tabs = QTabWidget()
        tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        tabs.addTab(self._build_jobs_tab(), "Jobs")
        tabs.addTab(self._build_runs_tab(), "Runs")
        tabs.addTab(self._build_notifications_tab(), "Notifications")
        tabs.addTab(self._build_scheduler_tab(), "Scheduler")
        tabs.addTab(self._build_resume_tab(), "Resume")
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

        form = QFormLayout()
        form.addRow("Database Path", self._db_path_value)
        form.addRow("Notification Threshold", self._threshold_value)
        form.addRow("Tracked Job Counts", self._counts_value)
        form.addRow("Last Run Status", self._last_run_status_value)
        form.addRow("Last Run Started", self._last_run_started_value)
        form.addRow("Last Run Finished", self._last_run_finished_value)
        form.addRow("Last Run Summary", self._last_run_summary_value)

        form.addRow(QLabel(""))  # Spacer
        form.addRow("HiringCafe Login", self._auth_hiringcafe_value)
        form.addRow("Wellfound Login", self._auth_wellfound_value)
        form.addRow("BuiltIn Login", self._auth_builtin_value)

        layout.addLayout(form)

        controls = QHBoxLayout()
        self._max_pages_spin.setRange(1, 25)
        self._max_pages_spin.setValue(self._default_max_pages)
        controls.addWidget(QLabel("Max Pages"))
        controls.addWidget(self._max_pages_spin)

        self._run_once_button.clicked.connect(self._run_once_clicked)
        controls.addWidget(self._run_once_button)

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

        controls = QHBoxLayout()
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_views)
        controls.addWidget(refresh_button)

        open_button = QPushButton("Open Selected Job")
        open_button.clicked.connect(self._open_selected_job_url)
        controls.addWidget(open_button)

        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(self._jobs_table)
        return widget

    def _build_runs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_views)
        layout.addWidget(refresh_button)
        layout.addWidget(self._runs_table)
        return widget

    def _build_notifications_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh_views)
        layout.addWidget(refresh_button)
        layout.addWidget(self._notifications_table)
        return widget

    def _build_scheduler_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._scheduler_interval_spin.setRange(1, 24)
        self._scheduler_interval_spin.setValue(self._service.settings.schedule_interval_hours)
        self._scheduler_max_pages_spin.setRange(1, 25)
        self._scheduler_max_pages_spin.setValue(self._default_max_pages)
        self._scheduler_start_time_input.setPlaceholderText("Optional HH:MM (24h)")

        form = QFormLayout()
        form.addRow("Task Name", self._scheduler_task_name_input)
        form.addRow("Interval Hours", self._scheduler_interval_spin)
        form.addRow("Max Pages", self._scheduler_max_pages_spin)
        form.addRow("Start Time", self._scheduler_start_time_input)
        form.addRow("Current Status", self._scheduler_status_value)
        layout.addLayout(form)

        controls = QHBoxLayout()
        self._scheduler_check_button.clicked.connect(self._scheduler_check_status_clicked)
        self._scheduler_install_button.clicked.connect(self._scheduler_install_clicked)
        self._scheduler_run_now_button.clicked.connect(self._scheduler_run_now_clicked)
        self._scheduler_uninstall_button.clicked.connect(self._scheduler_uninstall_clicked)

        controls.addWidget(self._scheduler_check_button)
        controls.addWidget(self._scheduler_install_button)
        controls.addWidget(self._scheduler_run_now_button)
        controls.addWidget(self._scheduler_uninstall_button)
        controls.addStretch(1)

        layout.addLayout(controls)
        layout.addStretch(1)
        return widget

    def _build_settings_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self._settings_notification_threshold_input.setPlaceholderText("0.80")
        self._settings_user_years_input.setPlaceholderText("1")
        self._settings_schedule_interval_input.setPlaceholderText("2")
        self._settings_critical_skills_input.setPlaceholderText("python,fastapi,sql,aws")
        self._settings_reject_terms_input.setPlaceholderText("senior,staff,principal,architect")

        form = QFormLayout()
        form.addRow("Env File", self._settings_env_path_value)
        form.addRow("Notification Threshold", self._settings_notification_threshold_input)
        form.addRow("User Years Experience", self._settings_user_years_input)
        form.addRow("Schedule Interval Hours", self._settings_schedule_interval_input)
        form.addRow("Critical Skills (CSV)", self._settings_critical_skills_input)
        form.addRow("Reject Terms (CSV)", self._settings_reject_terms_input)
        form.addRow("Flags", self._settings_auto_stage_checkbox)
        form.addRow("", self._settings_require_auth_checkbox)
        form.addRow("", self._settings_wellfound_enabled_checkbox)
        form.addRow("", self._settings_builtin_enabled_checkbox)
        form.addRow("Last Save Status", self._settings_status_value)
        layout.addLayout(form)

        controls = QHBoxLayout()
        self._settings_reload_button.clicked.connect(self._reload_settings_clicked)
        self._settings_save_button.clicked.connect(self._save_settings_clicked)
        controls.addWidget(self._settings_reload_button)
        controls.addWidget(self._settings_save_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        layout.addStretch(1)
        return widget

    def _build_resume_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

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
        layout.addLayout(form)

        controls = QHBoxLayout()
        self._resume_stage_button.clicked.connect(self._resume_stage_clicked)
        self._resume_compile_button.clicked.connect(self._resume_compile_clicked)
        self._resume_open_pdf_button.clicked.connect(self._resume_open_pdf_clicked)
        controls.addWidget(self._resume_stage_button)
        controls.addWidget(self._resume_compile_button)
        controls.addWidget(self._resume_open_pdf_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        layout.addWidget(self._resume_preview)
        return widget

    def _build_logs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        controls = QHBoxLayout()
        clear_button = QPushButton("Clear Log")
        clear_button.clicked.connect(self._log_output.clear)
        controls.addWidget(clear_button)
        controls.addStretch(1)

        layout.addLayout(controls)
        layout.addWidget(self._log_output)
        return widget

    def _create_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(False)
        return table

    def refresh_views(self) -> None:
        try:
            snapshot = self._service.dashboard_snapshot()
            jobs = self._service.list_top_jobs(limit=200)
            runs = self._service.list_recent_runs(limit=200)
            notifications = self._service.list_recent_notifications(limit=200)
        except Exception as exc:
            self._append_log(f"Refresh failed: {exc}")
            QMessageBox.critical(self, "Refresh Failed", str(exc))
            return

        self._populate_dashboard(snapshot)
        self._populate_jobs(jobs)
        self._populate_runs(runs)
        self._populate_notifications(notifications)
        self._refresh_scheduler_status(silent=True)

        self.statusBar().showMessage("Data refreshed", 3000)
        self._append_log("UI data refreshed")

    def _refresh_scheduler_status(self, silent: bool) -> None:
        try:
            result = self._service.scheduler_status(task_name=self._scheduler_task_name())
        except Exception as exc:
            self._scheduler_status_value.setText("Unavailable")
            self._append_log(f"Scheduler status check failed: {exc}")
            if not silent:
                QMessageBox.warning(self, "Scheduler Status", str(exc))
            return

        self._scheduler_status_value.setText("Installed" if result.exists else "Missing")

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
                f"scraped={last_run.scraped}, inserted={last_run.inserted}, "
                f"updated={last_run.updated}, scored={last_run.scored}, "
                f"above={last_run.above_threshold}, notified={last_run.notified}"
            )
        )

        self._update_auth_status(self._auth_hiringcafe_value, snapshot.auth_states.get("HiringCafe"))
        self._update_auth_status(self._auth_wellfound_value, snapshot.auth_states.get("Wellfound"))
        self._update_auth_status(self._auth_builtin_value, snapshot.auth_states.get("BuiltIn"))

    def _update_auth_status(self, label: QLabel, status: StorageStateStatus | None) -> None:
        if status is None:
            label.setText("Unknown")
            label.setStyleSheet("")
            return

        if not status.exists:
            label.setText("Missing (Storage state file not found)")
            label.setStyleSheet("color: orange;")
            return

        if not status.valid_json:
            label.setText("Error (Invalid JSON)")
            label.setStyleSheet("color: red;")
            return

        if status.usable:
            label.setText(f"OK ({status.cookie_count} cookies, {status.unexpired_cookie_count} unexpired)")
            label.setStyleSheet("color: darkgreen;")
        else:
            errors = ", ".join(status.errors) if status.errors else "Unusable"
            label.setText(f"Expired/Invalid ({errors})")
            label.setStyleSheet("color: red;")

    def _populate_jobs(self, jobs: list) -> None:
        self._jobs_table.setSortingEnabled(False)
        self._jobs_table.setRowCount(len(jobs))

        for row, job in enumerate(jobs):
            values = [
                _format_score(job.match_score),
                job.title,
                job.company,
                job.platform,
                job.status,
                _format_datetime(job.date_posted),
                job.url,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                self._jobs_table.setItem(row, column, item)

        self._jobs_table.resizeColumnsToContents()
        self._jobs_table.setSortingEnabled(True)

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
        url_item = self._jobs_table.item(row, 6)
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

        self._append_log(f"Opened URL: {url}")

    def _run_once_clicked(self) -> None:
        if self._run_in_progress:
            return

        max_pages = self._max_pages_spin.value()
        self._run_in_progress = True
        self._run_once_button.setEnabled(False)
        self.statusBar().showMessage("Running pipeline...")
        self._append_log(f"Starting run-once with max-pages={max_pages}")

        worker = RunOnceWorker(service=self._service, max_pages=max_pages)
        worker.signals.succeeded.connect(self._run_once_succeeded)
        worker.signals.failed.connect(self._run_once_failed)
        worker.signals.completed.connect(self._run_once_completed)
        self._current_worker = worker
        self._thread_pool.start(worker)

    def _run_once_succeeded(self, summary: object) -> None:
        self._append_log(
            (
                "Run completed successfully: "
                f"scraped={summary.scraped}, inserted={summary.inserted}, "
                f"updated={summary.updated}, scored={summary.scored}, "
                f"above={summary.above_threshold}, notified={summary.notified}"
            )
        )
        self.statusBar().showMessage("Run completed", 5000)

    def _run_once_failed(self, message: str) -> None:
        self._append_log(f"Run failed: {message}")
        QMessageBox.critical(self, "Run Failed", message)
        self.statusBar().showMessage("Run failed", 5000)

    def _run_once_completed(self) -> None:
        self._run_in_progress = False
        self._run_once_button.setEnabled(True)
        self._current_worker = None
        self.refresh_views()

    def _scheduler_task_name(self) -> str:
        candidate = self._scheduler_task_name_input.text().strip()
        return candidate or "JobPipeAggregator"

    def _set_scheduler_controls_enabled(self, enabled: bool) -> None:
        self._scheduler_task_name_input.setEnabled(enabled)
        self._scheduler_interval_spin.setEnabled(enabled)
        self._scheduler_max_pages_spin.setEnabled(enabled)
        self._scheduler_start_time_input.setEnabled(enabled)
        self._scheduler_check_button.setEnabled(enabled)
        self._scheduler_install_button.setEnabled(enabled)
        self._scheduler_run_now_button.setEnabled(enabled)
        self._scheduler_uninstall_button.setEnabled(enabled)

    def _start_scheduler_action(
        self,
        action_name: str,
        fn: Callable[[], object],
        success_handler: Callable[[object], None],
    ) -> None:
        if self._scheduler_busy:
            return

        self._scheduler_busy = True
        self._set_scheduler_controls_enabled(False)
        self.statusBar().showMessage(f"Scheduler action running: {action_name}")
        self._append_log(f"Scheduler action started: {action_name}")

        worker = BackgroundActionWorker(fn=fn)
        worker.signals.succeeded.connect(success_handler)
        worker.signals.failed.connect(self._scheduler_action_failed)
        worker.signals.completed.connect(self._scheduler_action_completed)
        self._current_scheduler_worker = worker
        self._thread_pool.start(worker)

    def _scheduler_check_status_clicked(self) -> None:
        self._start_scheduler_action(
            action_name="Check Status",
            fn=lambda: self._service.scheduler_status(task_name=self._scheduler_task_name()),
            success_handler=self._scheduler_status_succeeded,
        )

    def _scheduler_install_clicked(self) -> None:
        task_name = self._scheduler_task_name()
        interval_hours = self._scheduler_interval_spin.value()
        max_pages = self._scheduler_max_pages_spin.value()
        start_time = self._scheduler_start_time_input.text().strip() or None

        self._start_scheduler_action(
            action_name="Install / Update",
            fn=lambda: self._service.install_or_update_scheduler(
                task_name=task_name,
                interval_hours=interval_hours,
                max_pages=max_pages,
                start_time=start_time,
            ),
            success_handler=self._scheduler_install_succeeded,
        )

    def _scheduler_run_now_clicked(self) -> None:
        self._start_scheduler_action(
            action_name="Run Now",
            fn=lambda: self._service.run_scheduler_now(task_name=self._scheduler_task_name()),
            success_handler=self._scheduler_run_now_succeeded,
        )

    def _scheduler_uninstall_clicked(self) -> None:
        self._start_scheduler_action(
            action_name="Uninstall",
            fn=lambda: self._service.uninstall_scheduler(task_name=self._scheduler_task_name()),
            success_handler=self._scheduler_uninstall_succeeded,
        )

    def _scheduler_status_succeeded(self, result: object) -> None:
        exists = bool(getattr(result, "exists", False))
        self._scheduler_status_value.setText("Installed" if exists else "Missing")
        self._append_log(f"Scheduler status checked | exists={exists}")
        stdout = getattr(result, "stdout", "")
        if stdout:
            self._append_log(stdout)

    def _scheduler_install_succeeded(self, result: object) -> None:
        task_name = getattr(result, "task_name", self._scheduler_task_name())
        interval = getattr(result, "interval_hours", self._scheduler_interval_spin.value())
        self._scheduler_status_value.setText("Installed")
        self._append_log(f"Scheduler installed/updated | task={task_name} interval_hours={interval}")
        run_command = getattr(result, "run_command", "")
        if run_command:
            self._append_log(f"Task run command: {run_command}")

    def _scheduler_run_now_succeeded(self, result: object) -> None:
        task_name = getattr(result, "task_name", self._scheduler_task_name())
        self._append_log(f"Scheduler triggered immediately | task={task_name}")
        stdout = getattr(result, "stdout", "")
        if stdout:
            self._append_log(stdout)

    def _scheduler_uninstall_succeeded(self, result: object) -> None:
        task_name = getattr(result, "task_name", self._scheduler_task_name())
        deleted = bool(getattr(result, "deleted", False))
        self._scheduler_status_value.setText("Missing")
        action = "deleted" if deleted else "already absent"
        self._append_log(f"Scheduler uninstall complete | task={task_name} state={action}")
        stdout = getattr(result, "stdout", "")
        if stdout:
            self._append_log(stdout)

    def _scheduler_action_failed(self, message: str) -> None:
        self._append_log(f"Scheduler action failed: {message}")
        QMessageBox.critical(self, "Scheduler Action Failed", message)

    def _scheduler_action_completed(self) -> None:
        self._scheduler_busy = False
        self._set_scheduler_controls_enabled(True)
        self._current_scheduler_worker = None
        self.statusBar().showMessage("Scheduler action complete", 5000)

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
        self._resume_output_path_value.setText(str(output_path))

        preview = ""
        if output_path.exists():
            preview = output_path.read_text(encoding="utf-8")
        self._resume_preview.setPlainText(preview)

        score = getattr(result, "score", None)
        score_text = "n/a" if score is None else f"{score:.3f}"
        title = getattr(result, "title", "unknown")
        company = getattr(result, "company", "unknown")
        self._resume_status_value.setText("Staged")
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
            "JOBPIPE_NOTIFICATION_THRESHOLD": self._settings_notification_threshold_input.text().strip(),
            "JOBPIPE_USER_YEARS_EXPERIENCE": self._settings_user_years_input.text().strip(),
            "JOBPIPE_SCHEDULE_INTERVAL_HOURS": self._settings_schedule_interval_input.text().strip(),
            "JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION": str(
                self._settings_auto_stage_checkbox.isChecked()
            ).lower(),
            "JOBPIPE_REQUIRE_USABLE_AUTH_STATE": str(
                self._settings_require_auth_checkbox.isChecked()
            ).lower(),
            "JOBPIPE_WELLFOUND_ENABLED": str(
                self._settings_wellfound_enabled_checkbox.isChecked()
            ).lower(),
            "JOBPIPE_BUILTIN_ENABLED": str(self._settings_builtin_enabled_checkbox.isChecked()).lower(),
            "JOBPIPE_CRITICAL_SKILLS": self._settings_critical_skills_input.text().strip(),
            "JOBPIPE_REJECT_TERMS": self._settings_reject_terms_input.text().strip(),
        }

    def _set_settings_form_values(self, values: dict[str, str]) -> None:
        self._settings_env_path_value.setText(str(self._service.editable_env_file_path()))
        self._settings_notification_threshold_input.setText(
            values.get("JOBPIPE_NOTIFICATION_THRESHOLD", "")
        )
        self._settings_user_years_input.setText(values.get("JOBPIPE_USER_YEARS_EXPERIENCE", ""))
        self._settings_schedule_interval_input.setText(
            values.get("JOBPIPE_SCHEDULE_INTERVAL_HOURS", "")
        )
        self._settings_critical_skills_input.setText(values.get("JOBPIPE_CRITICAL_SKILLS", ""))
        self._settings_reject_terms_input.setText(values.get("JOBPIPE_REJECT_TERMS", ""))

        self._settings_auto_stage_checkbox.setChecked(
            _is_truthy_env_value(values.get("JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION", "false"))
        )
        self._settings_require_auth_checkbox.setChecked(
            _is_truthy_env_value(values.get("JOBPIPE_REQUIRE_USABLE_AUTH_STATE", "false"))
        )
        self._settings_wellfound_enabled_checkbox.setChecked(
            _is_truthy_env_value(values.get("JOBPIPE_WELLFOUND_ENABLED", "false"))
        )
        self._settings_builtin_enabled_checkbox.setChecked(
            _is_truthy_env_value(values.get("JOBPIPE_BUILTIN_ENABLED", "false"))
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

        try:
            schedule_interval = int(values.get("JOBPIPE_SCHEDULE_INTERVAL_HOURS", ""))
            if 1 <= schedule_interval <= 24:
                self._scheduler_interval_spin.setValue(schedule_interval)
        except ValueError:
            pass

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

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_output.appendPlainText(f"[{timestamp}] {message}")


def launch_gui(settings: Settings, default_max_pages: int = 1) -> int:
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)

    window = JobPipeMainWindow(
        service=JobPipeGuiService(settings),
        default_max_pages=default_max_pages,
    )
    window.show()

    if owns_app:
        return int(app.exec())
    return 0