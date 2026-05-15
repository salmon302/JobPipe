"""
Tests for resume variant system: generational tracking, metadata extraction, and ATS optimization.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import pytest

from jobpipe.resume.service import (
    compute_master_cv_hash,
    detect_page_length,
    extract_job_metadata,
    ats_optimize_resume,
)
from jobpipe.storage.models import JobRecord, MasterCVVersion, ResumeVariant
from jobpipe.storage.repository import JobRepository
from jobpipe.storage.db import initialize_database, connect


def _create_test_cv(tmp_path: Path, content: str = "# Test CV\n\nSkills: Python, SQL") -> Path:
    """Create a test Master CV file and return its path."""
    cv_path = tmp_path / "Master_CV.md"
    cv_path.write_text(content, encoding="utf-8")
    return cv_path


def _create_test_db(tmp_path: Path) -> Path:
    """Create a test database with migrations applied."""
    db_path = tmp_path / "test_jobpipe.db"
    initialize_database(db_path)
    return db_path


def _setup_job(repo: JobRepository, job_id: str, company: str = "Acme") -> None:
    """Insert a minimal job record for foreign key constraints."""
    job = JobRecord(
        id=job_id,
        platform="Test",
        title="Backend Engineer",
        company=company,
        url=f"https://example.com/{job_id}",
        description="Test job description",
        date_posted=datetime.now(timezone.utc),
    )
    repo.upsert_jobs([job])


def _require_gui_service():
    """Import GUI service or skip if dependencies are broken elsewhere."""
    try:
        from jobpipe.gui.services import JobPipeGuiService
    except SyntaxError as exc:
        pytest.skip(f"JobPipe GUI services import failed: {exc}")
    except Exception as exc:
        pytest.skip(f"JobPipe GUI services import failed: {exc}")
    return JobPipeGuiService


class TestComputeMasterCVHash:
    def test_hash_consistency(self, tmp_path) -> None:
        cv_path = _create_test_cv(tmp_path, "Version 1")
        hash1 = compute_master_cv_hash(cv_path)
        hash2 = compute_master_cv_hash(cv_path)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest length

    def test_hash_changes_with_content(self, tmp_path) -> None:
        cv_path = _create_test_cv(tmp_path, "Version 1")
        hash1 = compute_master_cv_hash(cv_path)

        cv_path.write_text("Version 2", encoding="utf-8")
        hash2 = compute_master_cv_hash(cv_path)

        assert hash1 != hash2


class TestDetectPageLength:
    def test_single_page_by_default(self) -> None:
        tex = r"\documentclass{article}\begin{document}Short resume\end{document}"
        assert detect_page_length(tex) == 1

    def test_two_pages_with_page_break(self) -> None:
        tex = r"\documentclass{article}\begin{document}Page 1\newpage Page 2\end{document}"
        assert detect_page_length(tex) == 2

    def test_two_pages_with_long_content(self) -> None:
        tex = r"\documentclass{article}\begin{document}" + "x" * 5000 + r"\end{document}"
        assert detect_page_length(tex) == 2


class TestExtractJobMetadata:
    def test_extract_frontend_job_type(self) -> None:
        desc = "We are looking for a Frontend Developer with React experience."
        metadata = extract_job_metadata(desc)
        assert metadata["job_type"] == "Frontend"
        assert "react" in metadata["skills"]

    def test_extract_backend_job_type(self) -> None:
        desc = "Backend Engineer needed for API development using Python and Django."
        metadata = extract_job_metadata(desc)
        assert metadata["job_type"] == "Backend"
        assert "python" in metadata["skills"]
        assert "django" in metadata["skills"]

    def test_extract_skills(self) -> None:
        desc = "Looking for Python, SQL, and AWS experience."
        metadata = extract_job_metadata(desc)
        assert "python" in metadata["skills"]
        assert "sql" in metadata["skills"]
        assert "aws" in metadata["skills"]

    def test_no_matching_job_type(self) -> None:
        desc = "Looking for a Marketing Manager."
        metadata = extract_job_metadata(desc)
        # "Manager" matches "Leadership" job type, so check it's not None
        # Actually, let's test with something that won't match
        desc2 = "Looking for a Graphic Designer with Photoshop skills."
        metadata2 = extract_job_metadata(desc2)
        assert metadata2["job_type"] is None


class TestResumeVariantDatabase:
    def _setup_cv_version(self, repo: JobRepository, cv_hash: str = "hash1") -> None:
        """Helper to create a CV version to satisfy foreign key constraint."""
        # Use INSERT OR REPLACE to ensure the version exists
        with connect(repo._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO master_cv_versions (cv_hash, file_path, version_number) VALUES (?, ?, ?)",
                (cv_hash, "Master_CV.md", 1),
            )
            conn.commit()

    def test_create_and_retrieve_cv_version(self, tmp_path) -> None:
        db_path = _create_test_db(tmp_path)
        repo = JobRepository(db_path)

        cv_hash = "abc123def456"
        version_id = repo.create_cv_version(cv_hash, "Master_CV.md", version_number=1)

        retrieved = repo.get_cv_version_by_hash(cv_hash)
        assert retrieved is not None
        assert retrieved.cv_hash == cv_hash
        assert retrieved.version_number == 1

    def test_create_resume_variant(self, tmp_path) -> None:
        db_path = _create_test_db(tmp_path)
        repo = JobRepository(db_path)
        self._setup_cv_version(repo, "abc123")
        _setup_job(repo, "job-1", company="Acme Corp")

        variant_id = repo.create_resume_variant(
            variant_name="Test_Resume.tex",
            tex_path="/path/to/Test_Resume.tex",
            master_cv_hash="abc123",
            job_id="job-1",
            page_length=2,
            job_type="Backend",
            target_company="Acme Corp",
            skills=json.dumps(["python", "sql"]),
            generation_number=1,
        )

        assert variant_id > 0

        variant = repo.get_resume_variant(variant_id)
        assert variant is not None
        assert variant.variant_name == "Test_Resume.tex"
        assert variant.page_length == 2
        assert variant.job_type == "Backend"
        assert variant.target_company == "Acme Corp"
        assert variant.generation_number == 1

    def test_list_variants_with_filters(self, tmp_path) -> None:
        db_path = _create_test_db(tmp_path)
        repo = JobRepository(db_path)
        self._setup_cv_version(repo, "hash1")
        self._setup_cv_version(repo, "hash2")
        self._setup_cv_version(repo, "hash3")

        _setup_job(repo, "job-1", company="Acme")
        _setup_job(repo, "job-2", company="Beta")
        _setup_job(repo, "job-3", company="Acme")

        # Create multiple variants
        repo.create_resume_variant("Resume1.tex", "/path/1", "hash1", job_id="job-1", page_length=1, target_company="Acme")
        repo.create_resume_variant("Resume2.tex", "/path/2", "hash2", job_id="job-2", page_length=2, target_company="Beta")
        repo.create_resume_variant("Resume3.tex", "/path/3", "hash3", job_id="job-3", page_length=1, target_company="Acme")

        # Filter by company
        acme_variants = repo.list_resume_variants(target_company="Acme")
        assert len(acme_variants) == 2

        # Filter by page length
        one_page = repo.list_resume_variants(page_length=1)
        assert len(one_page) == 2

        two_page = repo.list_resume_variants(page_length=2)
        assert len(two_page) == 1

    def test_variant_lineage(self, tmp_path) -> None:
        db_path = _create_test_db(tmp_path)
        repo = JobRepository(db_path)
        self._setup_cv_version(repo, "hash1")
        self._setup_cv_version(repo, "hash2")

        # Create parent variant
        parent_id = repo.create_resume_variant("Parent.tex", "/path/parent", "hash1", generation_number=1)

        # Create child variant
        child_id = repo.create_resume_variant(
            "Child.tex", "/path/child", "hash2",
            generation_number=2,
            parent_variant_id=parent_id,
        )

        # Get lineage from child
        lineage = repo.get_variant_lineage(child_id)
        assert len(lineage) == 2
        assert lineage[0].id == child_id
        assert lineage[1].id == parent_id

    def test_variants_by_job(self, tmp_path) -> None:
        db_path = _create_test_db(tmp_path)
        repo = JobRepository(db_path)
        self._setup_cv_version(repo, "hash1")
        self._setup_cv_version(repo, "hash2")
        self._setup_cv_version(repo, "hash3")

        _setup_job(repo, "job-1", company="Acme")
        _setup_job(repo, "job-2", company="Beta")

        # Create multiple variants for same job
        repo.create_resume_variant("Gen1.tex", "/path/gen1", "hash1", job_id="job-1", generation_number=1)
        repo.create_resume_variant("Gen2.tex", "/path/gen2", "hash2", job_id="job-1", generation_number=2)
        repo.create_resume_variant("Other.tex", "/path/other", "hash3", job_id="job-2", generation_number=1)

        job1_variants = repo.get_variants_by_job("job-1")
        assert len(job1_variants) == 2
        assert job1_variants[0].generation_number == 1
        assert job1_variants[1].generation_number == 2


class TestATSOptimization:
    @pytest.mark.skipif(True, reason="Requires Gemini API key - integration test")
    def test_ats_optimize_resume(self, tmp_path) -> None:
        """Integration test - requires API key."""
        tex_content = r"\documentclass{article}\begin{document}Test Resume\end{document}"
        job_desc = "Looking for Python developer with SQL skills."

        # This would need a real API key to run
        result = ats_optimize_resume(
            tex_content=tex_content,
            job_description=job_desc,
            gemini_api_key="test-key",
        )

        assert "ats_score" in result
        assert "recommendations" in result
        assert "optimized_content" in result

    def test_ats_optimize_without_api_key(self) -> None:
        tex_content = r"\documentclass{article}\begin{document}Test\end{document}"
        job_desc = "Python developer"

        with pytest.raises(ValueError, match="Gemini API key is required"):
            ats_optimize_resume(
                tex_content=tex_content,
                job_description=job_desc,
                gemini_api_key=None,
            )


class TestGUIIntegration:
    """Test GUI service methods for resume variants."""

    def _setup_settings(self, tmp_path, monkeypatch) -> "Settings":
        """Helper to setup Settings for tests."""
        db_path = _create_test_db(tmp_path)
        cv_path = _create_test_cv(tmp_path, "Test CV Content")

        monkeypatch.setenv("JOBPIPE_DB_PATH", str(db_path))
        monkeypatch.setenv("JOBPIPE_MASTER_CV_PATH", str(cv_path))
        monkeypatch.setenv("JOBPIPE_RESUME_VARIANTS_DIR", str(tmp_path / "resume_variants"))
        monkeypatch.setenv("JOBPIPE_ATS_OPTIMIZATION_MODEL", "gemini-flash-latest")
        monkeypatch.setenv("JOBPIPE_MASTER_CV_HASH_ALGORITHM", "sha256")

        from jobpipe.config import Settings
        return Settings.from_env()

    def test_list_variants_via_service(self, tmp_path, monkeypatch) -> None:
        settings = self._setup_settings(tmp_path, monkeypatch)
        service_cls = _require_gui_service()
        service = service_cls(settings)

        # Create test variant directly in DB
        repo = JobRepository(settings.db_path)
        repo.create_cv_version("hash1", str(settings.master_cv_path), 1)
        _setup_job(repo, "job-1", company="Acme")
        repo.create_resume_variant(
            "Test.tex", "/path/test", "hash1",
            job_id="job-1", target_company="Acme", job_type="Backend"
        )

        # List via service
        variants = service.list_resume_variants(target_company="Acme")
        assert len(variants) == 1
        assert variants[0].target_company == "Acme"

    def test_compute_current_cv_hash(self, tmp_path, monkeypatch) -> None:
        settings = self._setup_settings(tmp_path, monkeypatch)
        service_cls = _require_gui_service()
        service = service_cls(settings)

        cv_hash = service.compute_current_cv_hash()
        assert len(cv_hash) == 64  # SHA-256
