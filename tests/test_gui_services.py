from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from jobpipe.config import InvalidSettingsError, Settings
from jobpipe.gui.services import JobPipeGuiService


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("JOBPIPE_DB_PATH", str(tmp_path / "jobpipe.db"))
    monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(tmp_path / "Master_CV.md"))
    monkeypatch.setenv("JOBPIPE_JOB_DESCRIPTION_PATH", str(tmp_path / "Job_Description.md"))
    monkeypatch.setenv("JOBPIPE_RESUME_OUTPUT_DIR", str(tmp_path / "resume"))
    monkeypatch.setenv(
        "JOBPIPE_HIRINGCAFE_STORAGE_STATE",
        str(tmp_path / "hiringcafe_state.json"),
    )
    monkeypatch.setenv(
        "JOBPIPE_WELLFOUND_STORAGE_STATE",
        str(tmp_path / "wellfound_state.json"),
    )
    monkeypatch.setenv(
        "JOBPIPE_BUILTIN_STORAGE_STATE",
        str(tmp_path / "builtin_state.json"),
    )
    monkeypatch.setenv("JOBPIPE_RUN_LOCK_PATH", str(tmp_path / "aggregator.lock"))
    return Settings.from_env()


def test_scheduler_status_delegates_to_scheduler_module(monkeypatch, tmp_path) -> None:
    expected = SimpleNamespace(task_name="MyTask", exists=True, stdout="ok")
    monkeypatch.setattr("jobpipe.gui.services.get_task_status", lambda task_name: expected)

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    result = service.scheduler_status(task_name="MyTask")

    assert result is expected


def test_install_or_update_scheduler_passes_expected_arguments(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def _fake_create_or_update_hourly_task(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            task_name=kwargs["task_name"],
            interval_hours=kwargs["interval_hours"],
            run_command="cmd /c echo",
            stdout="configured",
        )

    monkeypatch.setattr(
        "jobpipe.gui.services.create_or_update_hourly_task",
        _fake_create_or_update_hourly_task,
    )

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    monkeypatch.setattr(service, "_project_root", lambda: tmp_path)

    env_file = tmp_path / ".env"
    result = service.install_or_update_scheduler(
        task_name="TaskA",
        interval_hours=3,
        max_pages=4,
        start_time="09:30",
        env_file=env_file,
    )

    assert result.task_name == "TaskA"
    assert captured["task_name"] == "TaskA"
    assert captured["interval_hours"] == 3
    assert captured["max_pages"] == 4
    assert captured["start_time"] == "09:30"
    assert captured["project_root"] == tmp_path
    assert captured["env_file"] == env_file
    assert isinstance(captured["python_executable"], Path)


def test_run_scheduler_now_delegates(monkeypatch, tmp_path) -> None:
    expected = SimpleNamespace(task_name="NowTask", stdout="running")
    monkeypatch.setattr("jobpipe.gui.services.run_task_now", lambda task_name: expected)

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    result = service.run_scheduler_now(task_name="NowTask")

    assert result is expected


def test_uninstall_scheduler_delegates(monkeypatch, tmp_path) -> None:
    expected = SimpleNamespace(task_name="GoneTask", deleted=True, stdout="deleted")
    monkeypatch.setattr("jobpipe.gui.services.remove_task", lambda task_name: expected)

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    result = service.uninstall_scheduler(task_name="GoneTask")

    assert result is expected


def test_load_editable_env_values_prefers_env_file(monkeypatch, tmp_path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "JOBPIPE_NOTIFICATION_THRESHOLD=0.92",
                "JOBPIPE_WELLFOUND_ENABLED=true",
                "JOBPIPE_CRITICAL_SKILLS=python,sql,aws",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    monkeypatch.setattr(service, "_project_root", lambda: tmp_path)

    values = service.load_editable_env_values()

    assert values["JOBPIPE_NOTIFICATION_THRESHOLD"] == "0.92"
    assert values["JOBPIPE_WELLFOUND_ENABLED"] == "true"
    assert values["JOBPIPE_CRITICAL_SKILLS"] == "python,sql,aws"


def test_validate_editable_env_values_rejects_invalid_threshold(monkeypatch, tmp_path) -> None:
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    values = service.load_editable_env_values()
    values["JOBPIPE_NOTIFICATION_THRESHOLD"] = "1.7"

    with pytest.raises(InvalidSettingsError):
        service.validate_editable_env_values(values)


def test_save_editable_env_values_persists_and_updates_runtime(monkeypatch, tmp_path) -> None:
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    monkeypatch.setattr(service, "_project_root", lambda: tmp_path)

    values = service.load_editable_env_values()
    values["JOBPIPE_NOTIFICATION_THRESHOLD"] = "0.77"
    values["JOBPIPE_SCHEDULE_INTERVAL_HOURS"] = "4"
    values["JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION"] = "true"

    saved_path = service.save_editable_env_values(values)

    assert saved_path == tmp_path / ".env"
    content = saved_path.read_text(encoding="utf-8")
    assert "JOBPIPE_NOTIFICATION_THRESHOLD=0.77" in content
    assert "JOBPIPE_SCHEDULE_INTERVAL_HOURS=4" in content
    assert "JOBPIPE_AUTO_STAGE_JOB_DESCRIPTION=true" in content
    assert service.settings.notification_threshold == 0.77
    assert service.settings.schedule_interval_hours == 4
    assert service.settings.auto_stage_job_description is True


def test_default_resume_tex_path_uses_configured_basename(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("JOBPIPE_RESUME_TARGET_BASENAME", "FocusedResume")
    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))

    path = service.default_resume_tex_path()

    assert path.name == "FocusedResume.tex"


def test_stage_resume_target_delegates_to_staging_module(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    expected = SimpleNamespace(
        job_id="job-1",
        title="Backend Engineer",
        company="Acme",
        score=0.91,
        output_path=tmp_path / "Job_Description.md",
    )

    def _fake_stage_job_description(repository, output_path, minimum_score, job_id=None):
        captured["repository"] = repository
        captured["output_path"] = output_path
        captured["minimum_score"] = minimum_score
        captured["job_id"] = job_id
        return expected

    monkeypatch.setattr("jobpipe.gui.services.stage_job_description", _fake_stage_job_description)

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    result = service.stage_resume_target(minimum_score=0.88, job_id="job-1")

    assert result is expected
    assert captured["output_path"] == service.settings.job_description_path
    assert captured["minimum_score"] == 0.88
    assert captured["job_id"] == "job-1"


def test_compile_resume_delegates_with_config(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    expected = SimpleNamespace(
        tex_path=tmp_path / "resume" / "FocusedResume.tex",
        pdf_path=tmp_path / "resume" / "FocusedResume.pdf",
        attempts=1,
    )

    def _fake_compile_latex(tex_path, output_pdf_path=None, config=None):
        captured["tex_path"] = tex_path
        captured["output_pdf_path"] = output_pdf_path
        captured["config"] = config
        return expected

    monkeypatch.setenv("JOBPIPE_RESUME_TARGET_BASENAME", "FocusedResume")
    monkeypatch.setattr("jobpipe.gui.services.compile_latex", _fake_compile_latex)

    service = JobPipeGuiService(_settings(tmp_path, monkeypatch))
    result = service.compile_resume()

    assert result is expected
    assert captured["tex_path"].name == "FocusedResume.tex"
    assert captured["output_pdf_path"].name == "FocusedResume.pdf"
    assert captured["config"].pdflatex_command == service.settings.resume_pdflatex_command
