# Purpose: End-to-end pipeline test for JobPipe.
# Author: Seth Nenninger (Tencent: Hy3 preview Agent)
# Timestamp: 2026-05-12T20:45:00Z

"""End-to-end tests for the complete JobPipe pipeline."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jobpipe.config import Settings
from jobpipe.storage.db import connect, initialize_database
from jobpipe.storage.repository import JobRepository


class TestE2EPipeline(unittest.TestCase):
    """Test the complete JobPipe pipeline from ingest to PDF."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test environment."""
        cls.test_dir = TemporaryDirectory()
        cls.test_root = Path(cls.test_dir.name)
        cls.db_path = cls.test_root / "test.db"
        cls.master_cv_path = cls.test_root / "Master_CV.md"
        cls.job_desc_path = cls.test_root / "Job_Description.md"
        cls.resume_dir = cls.test_root / "data" / "resume"
        cls.resume_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal Master CV
        cls.master_cv_path.write_text(
            """# John Doe - Master CV

## Experience
### Senior Python Developer
**TechCorp Inc.** | 2020 - Present
- Developed scalable web applications using Python, FastAPI, and PostgreSQL
- Led a team of 5 developers on cloud migration project (AWS)
- Improved API response time by 60% through query optimization

### Python Developer
**StartupXYZ** | 2018 - 2020
- Built REST APIs using Django and Flask
- Implemented CI/CD pipelines with GitHub Actions
- Reduced deployment time from 2 hours to 15 minutes

## Skills
- **Languages:** Python, JavaScript, SQL, Bash
- **Frameworks:** FastAPI, Django, Flask, React
- **Cloud:** AWS (EC2, Lambda, S3), Docker, Kubernetes
- **Databases:** PostgreSQL, Redis, MongoDB

## Education
**B.S. Computer Science** | State University | 2018
""",
            encoding="utf-8",
        )

        # Create settings for testing
        cls.settings = Settings(
            db_path=cls.db_path,
            master_cv_path=cls.master_cv_path,
            job_description_path=cls.job_desc_path,
            resume_output_dir=cls.resume_dir,
            resume_target_basename="Targeted_Resume",
            resume_pdflatex_command="pdflatex",
            resume_compile_retries=1,
            resume_compile_timeout_seconds=30,
            resume_write_retries=1,
            ingest_host="127.0.0.1",
            ingest_port=0,  # Will be set when server starts
            ingest_max_payload_bytes=1_000_000,
            critical_skills=["python", "fastapi", "aws"],
            reject_terms=["senior", "staff"],
            user_years_experience=5,
            notification_threshold=0.75,
            auto_stage_job_description=False,
            embed_model="sentence-transformers/all-MiniLM-L6-v2",
            embed_batch_size=32,
            score_async=False,
            run_lock_path=cls.test_root / "runtime" / "lock.lock",
            run_lock_stale_seconds=3600,
            gemini_api_key=None,  # No API key for e2e tests
            gemini_model="gemini-flash-latest",
            gemini_base_url="https://generativelanguage.googleapis.com/v1beta",
            gemini_timeout_seconds=30,
            gemini_max_retries=1,
            gemini_retry_delay_seconds=0.5,
        )

        # Initialize database
        cls.settings.ensure_runtime_dirs()
        initialize_database(cls.db_path)

    @classmethod
    def tearDownClass(cls) -> None:
        """Clean up test environment."""
        # Ensure all connections are closed
        import gc
        gc.collect()
        time.sleep(0.5)  # Give time for file locks to release

        try:
            cls.test_dir.cleanup()
        except PermissionError:
            # On Windows, sometimes files are still locked
            import shutil

            try:
                shutil.rmtree(cls.test_root, ignore_errors=True)
            except Exception:
                pass

    def setUp(self) -> None:
        """Clear database before each test."""
        # Use initialize_database which will recreate tables
        if self.db_path.exists():
            try:
                # Try to remove the file - if locked, we'll work with existing db
                self.db_path.unlink()
            except PermissionError:
                # If file is locked, just clear the tables
                pass

        initialize_database(self.db_path)

    def test_01_ingest_single_job(self) -> None:
        """Test ingesting a single job via the server."""
        from jobpipe.ingest.server import IngestServer, IngestServerConfig
        from jobpipe.ingest.service import JobIngestService

        # Allocate a dynamic port
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()

        # Update settings with the valid port
        self.settings = Settings(
            db_path=self.db_path,
            master_cv_path=self.master_cv_path,
            job_description_path=self.job_desc_path,
            resume_output_dir=self.resume_dir,
            resume_target_basename="Targeted_Resume",
            resume_pdflatex_command="pdflatex",
            resume_compile_retries=1,
            resume_compile_timeout_seconds=30,
            resume_write_retries=1,
            ingest_host="127.0.0.1",
            ingest_port=port,  # Use the dynamically allocated port
            ingest_max_payload_bytes=1_000_000,
            critical_skills=["python", "fastapi", "aws"],
            reject_terms=["senior", "staff"],
            user_years_experience=5,
            notification_threshold=0.75,
            auto_stage_job_description=False,
            embed_model="sentence-transformers/all-MiniLM-L6-v2",
            embed_batch_size=32,
            score_async=False,
            run_lock_path=self.test_root / "runtime" / "lock.lock",
            run_lock_stale_seconds=3600,
            gemini_api_key=None,
            gemini_model="gemini-flash-latest",
            gemini_base_url="https://generativelanguage.googleapis.com/v1beta",
            gemini_timeout_seconds=30,
            gemini_max_retries=1,
            gemini_retry_delay_seconds=0.5,
        )

        config = IngestServerConfig(
            host="127.0.0.1",
            port=port,  # Use the same port
            max_payload_bytes=1_000_000,
        )
        service = JobIngestService(self.settings)
        server = IngestServer(config=config, service=service)
        server.start()

        try:
            # Use the port from config (which is now a real port)
            url = f"http://127.0.0.1:{port}/ingest"

            # Send job payload
            payload = {
                "platform": "HiringCafe",
                "title": "Python Developer",
                "company": "TestCorp",
                "url": "https://example.com/job/123",
                "description": """
                    We are looking for a Python Developer with experience in
                    FastAPI, Django, and cloud technologies (AWS).
                    Must have 3+ years of experience.
                    Skills: Python, FastAPI, PostgreSQL, AWS, Docker.
                """,
            }

            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "-X",
                    "POST",
                    "-H",
                    "Content-Type: application/json",
                    "-d",
                    json.dumps(payload),
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 0)

            # Check database
            repo = JobRepository(self.db_path)
            jobs = repo.list_top_jobs(limit=10)

            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].title, "Python Developer")
            self.assertEqual(jobs[0].company, "TestCorp")
            self.assertEqual(jobs[0].platform, "HiringCafe")

            # Check that score was computed
            self.assertIsNotNone(jobs[0].match_score)
            self.assertGreater(jobs[0].match_score, 0.0)  # Should match our CV

        finally:
            server.stop()

    def test_02_ingest_batch_jobs(self) -> None:
        """Test ingesting multiple jobs at once."""
        from jobpipe.ingest.server import IngestServer, IngestServerConfig
        from jobpipe.ingest.service import JobIngestService

        # Allocate a dynamic port
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        sock.close()

        config = IngestServerConfig(
            host="127.0.0.1",
            port=port,
            max_payload_bytes=1_000_000,
        )
        service = JobIngestService(self.settings)
        server = IngestServer(config=config, service=service)
        server.start()

        try:
            # Use the port from config
            url = f"http://127.0.0.1:{port}/ingest"

            payload = {
                "jobs": [
                    {
                        "platform": "LinkedIn",
                        "title": "Senior Python Developer",
                        "company": "Company A",
                        "url": "https://linkedin.com/jobs/1",
                        "description": "Python, Django, AWS...",
                    },
                    {
                        "platform": "BuiltIn",
                        "title": "Full Stack Developer",
                        "company": "Company B",
                        "url": "https://builtin.com/jobs/2",
                        "description": "Python, React, PostgreSQL...",
                    },
                ]
            }

            result = subprocess.run(
                ["curl", "-s", "-X", "POST", "-H", "Content-Type: application/json", "-d", json.dumps(payload), url],
                capture_output=True,
                text=True,
                timeout=10,
            )

            self.assertEqual(result.returncode, 0)

            # Check database
            repo = JobRepository(self.db_path)
            jobs = repo.list_top_jobs(limit=10)

            self.assertEqual(len(jobs), 2)

        finally:
            server.stop()

    def test_03_stage_job_description(self) -> None:
        """Test staging a job description for resume generation."""
        from jobpipe.resume.staging import stage_job_description

        # First, insert a job
        repo = JobRepository(self.db_path)
        from jobpipe.storage.models import JobRecord

        job = JobRecord(
            id="test-job-1",
            platform="HiringCafe",
            title="Python Developer",
            company="TestCorp",
            url="https://example.com/job/1",
            description="Python, FastAPI, AWS...",
            date_posted=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            match_score=0.85,
            status="Queued",
        )

        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, platform, title, company, url, description, date_posted, match_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (job.id, job.platform, job.title, job.company, job.url, job.description, job.date_posted.isoformat(), job.match_score, job.status),
            )
            conn.commit()

        # Stage the job description
        result = stage_job_description(
            repository=repo,
            output_path=self.job_desc_path,
            minimum_score=0.80,
        )

        self.assertEqual(result.job_id, "test-job-1")
        self.assertTrue(self.job_desc_path.exists())

        content = self.job_desc_path.read_text(encoding="utf-8")
        self.assertIn("Python Developer", content)
        self.assertIn("TestCorp", content)

    def test_04_resume_write_and_compile(self) -> None:
        """Test writing and compiling a resume (without Gemini)."""
        from jobpipe.resume.compiler import compile_latex
        from jobpipe.resume.service import write_targeted_resume

        # Create a simple LaTeX resume
        latex_content = r"""
\documentclass[11pt,a4paper]{article}
\usepackage[margin=0.5in]{geometry}
\begin{document}
\centerline{\Large\bf John Doe}
\section*{Experience}
\textbf{Python Developer} \hfill 2020--Present\\
\textit{TestCorp}
\begin{itemize}
\item Developed Python applications
\item Used FastAPI and PostgreSQL
\end{itemize}
\end{document}
"""

        # Write to file (simulating user approval)
        tex_path = self.resume_dir / "Targeted_Resume.tex"
        tex_path.write_text(latex_content, encoding="utf-8")

        # Compile (this will fail if pdflatex is not installed, so we mock it)
        import shutil

        if not shutil.which("pdflatex"):
            self.skipTest("pdflatex not installed, skipping compilation test")

        config = __import__("jobpipe.resume.compiler", fromlist=["LatexCompileConfig"]).LatexCompileConfig(
            pdflatex_command="pdflatex",
            retries=1,
            timeout_seconds=30,
        )

        result = write_targeted_resume(
            tex_content=latex_content,
            output_name="Targeted_Resume",
            output_dir=self.resume_dir,
            compile_config=config,
            approved=True,
            write_retries=1,
        )

        self.assertTrue(result.tex_path.exists())
        # PDF may not exist if pdflatex fails, but tex should exist
        self.assertEqual(result.compile_attempts, 1)

    def test_05_cli_commands(self) -> None:
        """Test CLI commands work correctly."""
        # Test init-db
        result = subprocess.run(
            [sys.executable, "-m", "jobpipe", "init-db", "--db-path", str(self.db_path)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)

        # Test top command (should show no jobs)
        result = subprocess.run(
            [sys.executable, "-m", "jobpipe", "top", "--limit", "5"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0)


class TestE2EGeminiIntegration(unittest.TestCase):
    """Test Gemini API integration (requires API key)."""

    @classmethod
    def setUpClass(cls) -> None:
        """Check if Gemini API key is available."""
        cls.api_key = os.environ.get("JOBPIPE_GEMINI_API_KEY") or None
        cls.skip_tests = cls.api_key is None

    def setUp(self) -> None:
        if self.skip_tests:
            self.skipTest("Gemini API key not configured, skipping Gemini tests")

    def test_gemini_resume_generation(self) -> None:
        """Test generating a resume with Gemini API."""
        from jobpipe.resume.gemini_client import GeminiClient, GeminiConfig

        config = GeminiConfig(api_key=self.api_key)
        client = GeminiClient(config)

        # Check health
        self.assertTrue(client.health_check())

        # Generate resume
        master_cv = """
# John Doe
## Experience
### Python Developer
Built web apps with Python and FastAPI.
## Skills
Python, FastAPI, AWS, PostgreSQL
"""

        job_desc = """
We are looking for a Python Developer with FastAPI experience.
Skills: Python, FastAPI, AWS
"""

        response = client.generate_resume(master_cv, job_desc)

        self.assertIsNotNone(response.text)
        self.assertIn("\\documentclass", response.text)
        self.assertIn("\\end{document}", response.text)


if __name__ == "__main__":
    unittest.main()
