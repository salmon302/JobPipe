# Purpose: Test Gemini API client functionality.
# Author: Seth Nenninger (Tencent: Hy3 preview Agent)
# Timestamp: 2026-05-12T20:00:00Z

"""Tests for Gemini API client."""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from jobpipe.resume.gemini_client import (
    GeminiAPIError,
    GeminiClient,
    GeminiConfig,
    _build_resume_prompt,
    _extract_latex,
)


class TestBuildResumePrompt(unittest.TestCase):
    """Test prompt building logic."""

    def test_basic_prompt(self):
        """Test basic prompt generation."""
        master_cv = "# My CV\n\nExperience: ..."
        job_desc = "Job: Python Developer"

        prompt = _build_resume_prompt(master_cv, job_desc)

        self.assertIn(master_cv, prompt)
        self.assertIn(job_desc, prompt)
        self.assertIn("LaTeX", prompt)
        self.assertIn("ONE page", prompt)

    def test_prompt_with_template(self):
        """Test prompt with LaTeX template."""
        master_cv = "CV content"
        job_desc = "Job description"
        template = "\\documentclass{article}..."

        prompt = _build_resume_prompt(master_cv, job_desc, template)

        self.assertIn(template, prompt)
        self.assertIn("LaTeX Template Structure", prompt)


class TestExtractLatex(unittest.TestCase):
    """Test LaTeX extraction from API responses."""

    def test_plain_latex(self):
        """Test extraction of plain LaTeX code."""
        latex = "\\documentclass{article}\n\\begin{document}Hello\\end{document}"
        result = _extract_latex(latex)
        self.assertEqual(result, latex)

    def test_latex_with_markdown_fences(self):
        """Test removal of markdown code blocks."""
        latex = "```latex\n\\documentclass{article}\n\\end{document}\n```"
        result = _extract_latex(latex)
        self.assertNotIn("```", result)
        self.assertIn("\\documentclass", result)

    def test_latex_with_documentclass_search(self):
        """Test finding documentclass in response."""
        latex = "Some text before\n\\documentclass{article}\n\\begin{document}Content\\end{document}"
        result = _extract_latex(latex)
        self.assertTrue(result.startswith("\\documentclass"))
        self.assertTrue(result.endswith("\\end{document}"))

    def test_latex_with_end_document_search(self):
        """Test finding end{document} in response."""
        latex = "\\documentclass{article}\n\\begin{document}Content\\end{document}\nSome text after"
        result = _extract_latex(latex)
        self.assertTrue(result.endswith("\\end{document}"))


class TestGeminiConfig(unittest.TestCase):
    """Test GeminiConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = GeminiConfig(api_key="test-key")
        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.model, "gemini-1.5-flash")
        self.assertIn("generativelanguage.googleapis.com", config.base_url)
        self.assertEqual(config.timeout_seconds, 60)
        self.assertEqual(config.max_retries, 3)


class TestGeminiClient(unittest.TestCase):
    """Test GeminiClient class with mocked requests."""

    def setUp(self):
        self.config = GeminiConfig(api_key="test-key")
        self.client = GeminiClient(self.config)

    @mock.patch.object(GeminiClient, "__init__", lambda self, config: None)
    def test_generate_resume_success(self):
        """Test successful resume generation."""
        client = GeminiClient.__new__(GeminiClient)
        client._config = self.config
        client._session = mock.MagicMock()

        # Mock response
        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "\\documentclass{article}\\begin{document}Test\\end{document}"},
                        ],
                    },
                },
            ],
        }
        client._session.post.return_value = mock_response

        result = client.generate_resume("CV", "Job")

        self.assertIn("\\documentclass", result.text)
        self.assertIn("\\end{document}", result.text)

    @mock.patch.object(GeminiClient, "__init__", lambda self, config: None)
    def test_generate_resume_api_error(self):
        """Test handling of API errors."""
        client = GeminiClient.__new__(GeminiClient)
        client._config = self.config
        client._session = mock.MagicMock()

        # Mock timeout
        import requests
        client._session.post.side_effect = requests.exceptions.Timeout("Connection timed out")

        with self.assertRaises(GeminiAPIError):
            client.generate_resume("CV", "Job")

    def test_health_check_success(self):
        """Test successful health check."""
        client = GeminiClient.__new__(GeminiClient)
        client._config = self.config
        client._session = mock.MagicMock()

        mock_response = mock.MagicMock()
        mock_response.status_code = 200
        client._session.get.return_value = mock_response

        self.assertTrue(client.health_check())

    def test_health_check_failure(self):
        """Test failed health check."""
        client = GeminiClient.__new__(GeminiClient)
        client._config = self.config
        client._session = mock.MagicMock()

        mock_response = mock.MagicMock()
        mock_response.status_code = 404
        client._session.get.return_value = mock_response

        self.assertFalse(client.health_check())


if __name__ == "__main__":
    unittest.main()
