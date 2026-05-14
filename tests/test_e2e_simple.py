# Purpose: Simplified end-to-end pipeline test for JobPipe.
# Author: Seth Nenninger (Tencent: Hy3 preview Agent)
# Timestamp: 2026-05-12T21:00:00Z

"""Simplified end-to-end tests for JobPipe pipeline."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import requests

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jobpipe.config import Settings
from jobpipe.ingest.server import IngestServer, IngestServerConfig
from jobpipe.ingest.service import JobIngestService
from jobpipe.storage.db import connect, initialize_database
from jobpipe.storage.repository import JobRepository


class TestSimplifiedE2E(unittest.TestCase):
    """Simplified end-to-end tests."""

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
### Python Developer
**TechCorp Inc.** | 2020 - Present
- Developed web apps with Python, FastAPI, PostgreSQL
- Used AWS cloud services

## Skills
Python, FastAPI, AWS, PostgreSQL
""",
            encoding="utf-8",
        )

    @classmethod
    def tearDownClass(cls) -> None:
        """Clean up."""
        import gc
        gc.collect()
        time.sleep(0.5)
        try:
            cls.test_dir.cleanup()
        except PermissionError:
            try:
                import shutil
                shutil.rmtree(cls.test_root, ignore_errors=True)
            except Exception:
                pass

    def setUp(self) -> None:
        """Set up before each test."""
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except PermissionError:
                pass
        initialize_database(self.db_path)

    def _create_settings(self, port: int) -> Settings:
        """Create settings with the specified port."""
        return Settings(
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
            ingest_port=port,
            ingest_max_payload_bytes=1_000_000,
            critical_skills=["python", "fastapi"],
            reject_terms=["senior"],
            user_years_experience=5,
            notification_threshold=0.75,
            auto_stage_job_description=False,
            embed_model="sentence-transformers/all-MiniLM-L6-v2",
            embed_batch_size=32,
            score_async=False,
            run_lock_path=self.test_root / "runtime" / "lock.lock",
            run_lock_stale_seconds=3600,
            gemini_api_key=None,
        )

    def test_01_ingest_via_server(self) -> None:
        """Test ingesting a job via the server using requests."""
        import socket

        # Allocate a dynamic port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        settings = self._create_settings(port)

        # Start server
        config = IngestServerConfig(
            host="127.0.0.1",
            port=port,
            max_payload_bytes=1_000_000,
        )
        service = JobIngestService(settings)
        server = IngestServer(config=config, service=service)
        server.start()

        try:
            # Send job payload using requests
            url = f"http://127.0.0.1:{port}/ingest"
            payload = {
                "platform": "HiringCafe",
                "title": "Python Developer",
                "company": "TestCorp",
                "url": "https://example.com/job/123",
                "description": "Python, FastAPI, AWS...",
            }

            response = requests.post(url, json=payload, timeout=30)
            self.assertEqual(response.status_code, 200)

            # Check database
            repo = JobRepository(self.db_path)
            jobs = repo.list_top_jobs(limit=10)

            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].title, "Python Developer")
            self.assertEqual(jobs[0].company, "TestCorp")
            self.assertEqual(jobs[0].platform, "HiringCafe")

            # Check that score was computed
            self.assertIsNotNone(jobs[0].match_score)

        finally:
            server.stop()

    def test_02_health_endpoint(self) -> None:
        """Test the health check endpoint."""
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()

        settings = self._create_settings(port)

        config = IngestServerConfig(
            host="127.0.0.1",
            port=port,
            max_payload_bytes=1_000_000,
        )
        service = JobIngestService(settings)
        server = IngestServer(config=config, service=service)
        server.start()

        try:
            url = f"http://127.0.0.1:{port}/health"
            response = requests.get(url, timeout=10)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "ok")
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
