"""Tests for the MCP-based resume generation server.

Covers resource endpoints, tool endpoints, and error handling
for the MCP server defined in jobpipe.resume.mcp_server.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from jobpipe.config import Settings
from jobpipe.resume.gemini_client import GeminiAPIError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mcps_settings(tmp_path: Path) -> Settings:
    """Minimal Settings for MCP server tests."""
    db_path = tmp_path / "data" / "jobpipe.db"
    cv_path = tmp_path / "Master_CV.md"
    jd_path = tmp_path / "Job_Description.md"
    resume_dir = tmp_path / "data" / "resume"
    lock_path = tmp_path / "data" / "runtime" / "aggregator.lock"

    cv_path.parent.mkdir(parents=True, exist_ok=True)
    cv_path.write_text(
        "# Seth Nenninger\n## Skills\n- **Languages:** Python, C++\n",
        encoding="utf-8",
    )

    return Settings(
        db_path=db_path,
        master_cv_path=cv_path,
        job_description_path=jd_path,
        resume_output_dir=resume_dir,
        resume_target_basename="Targeted_Resume",
        resume_pdflatex_command="pdflatex",
        resume_compile_retries=1,
        resume_compile_timeout_seconds=30,
        resume_write_retries=1,
        ingest_host="127.0.0.1",
        ingest_port=0,
        ingest_max_payload_bytes=1_000_000,
        critical_skills=["python"],
        reject_terms=["senior"],
        user_years_experience=2,
        notification_threshold=0.80,
        auto_stage_job_description=False,
        embed_model="sentence-transformers/all-MiniLM-L6-v2",
        embed_batch_size=32,
        score_async=False,
        run_lock_path=lock_path,
        run_lock_stale_seconds=3600,
        gemini_api_key="test-api-key",
    )


# ---------------------------------------------------------------------------
# create_resume_mcp_server
# ---------------------------------------------------------------------------

def test_create_server_raises_without_mcp(mcps_settings: Settings) -> None:
    """When mcp package is missing, create_resume_mcp_server raises RuntimeError."""
    with patch("jobpipe.resume.mcp_server.FastMCP", None):
        from jobpipe.resume.mcp_server import create_resume_mcp_server

        with pytest.raises(RuntimeError, match="MCP server dependency is missing"):
            create_resume_mcp_server(mcps_settings)


def test_create_server_sets_up_resources_and_tools(mcps_settings: Settings) -> None:
    """Happy path: server object has expected resources and tools."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    mock_fastmcp_class = MagicMock()
    mock_instance = MagicMock()
    mock_fastmcp_class.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp_class):
        server = create_resume_mcp_server(mcps_settings)

    assert server is mock_instance
    mock_fastmcp_class.assert_called_once_with("JobPipe Resume Generator")


# ---------------------------------------------------------------------------
# Resource: jobpipe://master-cv
# ---------------------------------------------------------------------------

def test_master_cv_resource_returns_content(mcps_settings: Settings) -> None:
    """resource_fn reads the Master CV file from settings."""
    # Build server, capture the resource callable
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    captured_resources: dict[str, object] = {}

    def capturing_decorator(uri: str):
        def inner(fn):
            captured_resources[uri] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = capturing_decorator
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured_resources.get("jobpipe://master-cv")
    assert fn is not None, "Expected master-cv resource to be registered"
    result = fn()
    assert "Seth Nenninger" in result
    assert "Python" in result


def test_master_cv_resource_returns_missing_message(tmp_path: Path) -> None:
    """When Master CV file does not exist, resource returns a helpful message."""
    from jobpipe.config import Settings

    settings = Settings(
        db_path=tmp_path / "data" / "jobpipe.db",
        master_cv_path=tmp_path / "Master_CV.md",  # does not exist
        job_description_path=tmp_path / "Job_Description.md",
        resume_output_dir=tmp_path / "data" / "resume",
        resume_target_basename="Targeted_Resume",
        resume_pdflatex_command="pdflatex",
        resume_compile_retries=1,
        resume_compile_timeout_seconds=30,
        resume_write_retries=1,
        ingest_host="127.0.0.1",
        ingest_port=0,
        ingest_max_payload_bytes=1_000_000,
        critical_skills=[],
        reject_terms=[],
        user_years_experience=1,
        notification_threshold=0.80,
        auto_stage_job_description=False,
        embed_model="all-MiniLM-L6-v2",
        embed_batch_size=32,
        score_async=False,
        run_lock_path=tmp_path / "lock.lock",
        run_lock_stale_seconds=3600,
    )

    from jobpipe.resume.mcp_server import create_resume_mcp_server
    captured: dict[str, object] = {}

    def capturing(uri: str):
        def inner(fn):
            captured[uri] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = capturing
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(settings)

    fn = captured.get("jobpipe://master-cv")
    assert fn is not None
    result = fn()
    assert "missing" in result.lower()


# ---------------------------------------------------------------------------
# Resource: jobpipe://resume-skill
# ---------------------------------------------------------------------------

def test_resume_skill_resource_returns_template(mcps_settings: Settings) -> None:
    """resume-skill resource returns the RESUME_SKILL_TEMPLATE constant."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    captured: dict[str, object] = {}

    def capturing(uri: str):
        def inner(fn):
            captured[uri] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = capturing
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured.get("jobpipe://resume-skill")
    assert fn is not None
    result = fn()
    assert "JobPipe Resume Skill Template" in result
    assert "write_targeted_resume" in result


# ---------------------------------------------------------------------------
# Tool: healthcheck
# ---------------------------------------------------------------------------

def test_healthcheck_tool_returns_settings_info(mcps_settings: Settings) -> None:
    """healthcheck() returns a dict with configured paths and threshold."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    captured_tools: dict[str, object] = {}

    def capturing_tool(**kwargs):
        def inner(fn):
            name = kwargs.get("name") or fn.__name__
            captured_tools[name] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = lambda uri: lambda f: f
    mock_instance.tool = capturing_tool
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured_tools.get("healthcheck")
    assert fn is not None
    result = fn()
    assert "db_path" in result
    assert "master_cv_path" in result
    assert str(mcps_settings.db_path) in result["db_path"]
    assert str(mcps_settings.master_cv_path) in result["master_cv_path"]


# ---------------------------------------------------------------------------
# Tool: generate_resume_with_gemini — error paths
# ---------------------------------------------------------------------------

def test_generate_resume_with_gemini_requires_api_key(mcps_settings: Settings) -> None:
    """When gemini_api_key is not set, tool raises RuntimeError."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    no_key_settings = Settings(
        **{**{f.name: getattr(mcps_settings, f.name) for f in mcps_settings.__dataclass_fields__.values()},
            "gemini_api_key": None}
    )
    # Rebuild properly
    no_key_settings = mcps_settings  # fallback, we'll patch instead

    captured_tools: dict[str, object] = {}

    def capturing_tool(**kwargs):
        def inner(fn):
            captured_tools[fn.__name__] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = lambda uri: lambda f: f
    mock_instance.tool = capturing_tool
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured_tools.get("generate_resume_with_gemini")
    assert fn is not None

    # Force gemini_api_key to None for this test
    with patch.object(type(mcps_settings), "gemini_api_key", new_callable=PropertyMock, return_value=None):
        with pytest.raises(RuntimeError, match="Gemini API key not configured"):
            fn()


def test_generate_resume_with_gemini_requires_cv(mcps_settings: Settings, tmp_path: Path) -> None:
    """When Master CV file is missing, tool raises RuntimeError."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    captured_tools: dict[str, object] = {}

    def capturing_tool(**kwargs):
        def inner(fn):
            captured_tools[fn.__name__] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = lambda uri: lambda f: f
    mock_instance.tool = capturing_tool
    mock_fastmcp.return_value = mock_instance

    # Delete the Master CV file
    mcps_settings.master_cv_path.unlink()

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured_tools.get("generate_resume_with_gemini")
    assert fn is not None
    with pytest.raises(RuntimeError, match="Master CV not found"):
        fn()


def test_generate_resume_with_gemini_requires_job_description(mcps_settings: Settings) -> None:
    """When job description file is missing, tool raises RuntimeError."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    captured_tools: dict[str, object] = {}

    def capturing_tool(**kwargs):
        def inner(fn):
            captured_tools[fn.__name__] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = lambda uri: lambda f: f
    mock_instance.tool = capturing_tool
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured_tools.get("generate_resume_with_gemini")
    assert fn is not None

    # Job_Description.md doesn't exist yet
    with pytest.raises(RuntimeError, match="Job description not found"):
        fn()


def test_generate_resume_with_gemini_wraps_gemini_error(mcps_settings: Settings) -> None:
    """When Gemini API call fails, RuntimeError wraps GeminiAPIError."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    # Create the job description file so the tool proceeds past file checks
    mcps_settings.job_description_path.parent.mkdir(parents=True, exist_ok=True)
    mcps_settings.job_description_path.write_text(
        "Backend Python developer role\n",
        encoding="utf-8",
    )

    captured_tools: dict[str, object] = {}
    captured_resources: dict[str, object] = {}

    def capturing_tool(**kwargs):
        def inner(fn):
            captured_tools[fn.__name__] = fn
            return fn
        return inner

    def capturing_resource(uri: str):
        def inner(fn):
            captured_resources[uri] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.tool = capturing_tool
    mock_instance.resource = capturing_resource
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured_tools.get("generate_resume_with_gemini")
    assert fn is not None

    with patch(
        "jobpipe.resume.mcp_server.create_gemini_client_from_settings",
        side_effect=GeminiAPIError("API quota exceeded"),
    ):
        with pytest.raises(RuntimeError, match="Gemini API error"):
            fn()


# ---------------------------------------------------------------------------
# Tool: stage_job_description_for_resume
# ---------------------------------------------------------------------------

def test_stage_job_description_tool_calls_staging(mcps_settings: Settings) -> None:
    """stage_job_description_for_resume delegates to stage_job_description."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    captured_tools: dict[str, object] = {}

    def capturing_tool(**kwargs):
        def inner(fn):
            captured_tools[fn.__name__] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = lambda uri: lambda f: f
    mock_instance.tool = capturing_tool
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured_tools.get("stage_job_description_for_resume")
    assert fn is not None

    mock_staged = MagicMock()
    mock_staged.job_id = "job-123"
    mock_staged.title = "Backend Engineer"
    mock_staged.company = "Acme"
    mock_staged.score = 0.85
    mock_staged.output_path = Path("/tmp/jd.md")

    with patch("jobpipe.resume.mcp_server.stage_job_description", return_value=mock_staged):
        result = fn(job_id="job-123", minimum_score=0.5)

    assert result["job_id"] == "job-123"
    assert result["title"] == "Backend Engineer"
    assert result["company"] == "Acme"
    assert result["score"] == "0.850"


# ---------------------------------------------------------------------------
# Tool: write_targeted_resume
# ---------------------------------------------------------------------------

def test_write_targeted_resume_tool_delegates(mcps_settings: Settings) -> None:
    """write_targeted_resume tool delegates to resume.service.write_targeted_resume."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    captured_tools: dict[str, object] = {}

    def capturing_tool(**kwargs):
        def inner(fn):
            captured_tools[fn.__name__] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = lambda uri: lambda f: f
    mock_instance.tool = capturing_tool
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured_tools.get("write_targeted_resume")
    assert fn is not None

    mock_result = MagicMock()
    mock_result.tex_path = Path("/tmp/resume.tex")
    mock_result.pdf_path = Path("/tmp/resume.pdf")
    mock_result.compile_attempts = 1

    with patch(
        "jobpipe.resume.mcp_server.write_targeted_resume_document",
        return_value=mock_result,
    ):
        result = fn(tex_content="\\documentclass{article}", approved=True)

    assert "tex_path" in result
    assert "pdf_path" in result
    assert result["compile_attempts"] == "1"


# ---------------------------------------------------------------------------
# Tool: compile_existing_resume
# ---------------------------------------------------------------------------

def test_compile_existing_resume_tool_delegates(mcps_settings: Settings) -> None:
    """compile_existing_resume tool delegates to compile_latex."""
    from jobpipe.resume.mcp_server import create_resume_mcp_server

    captured_tools: dict[str, object] = {}

    def capturing_tool(**kwargs):
        def inner(fn):
            captured_tools[fn.__name__] = fn
            return fn
        return inner

    mock_fastmcp = MagicMock()
    mock_instance = MagicMock()
    mock_instance.resource = lambda uri: lambda f: f
    mock_instance.tool = capturing_tool
    mock_fastmcp.return_value = mock_instance

    with patch("jobpipe.resume.mcp_server.FastMCP", mock_fastmcp):
        create_resume_mcp_server(mcps_settings)

    fn = captured_tools.get("compile_existing_resume")
    assert fn is not None

    mock_compile_result = MagicMock()
    mock_compile_result.tex_path = Path("/tmp/resume.tex")
    mock_compile_result.pdf_path = Path("/tmp/resume.pdf")
    mock_compile_result.attempts = 1

    with patch("jobpipe.resume.mcp_server.compile_latex", return_value=mock_compile_result):
        result = fn(output_name="TestResume")

    assert "tex_path" in result
    assert "pdf_path" in result
    assert result["attempts"] == "1"
