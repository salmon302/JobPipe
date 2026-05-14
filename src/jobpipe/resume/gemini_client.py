# Purpose: Client for Google Gemini API to generate targeted resumes.
# Author: Seth Nenninger (Tencent: Hy3 preview Agent)
# Timestamp: 2026-05-12T19:30:00Z

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import time
from typing import Any

import requests
from requests.exceptions import RequestException, Timeout

from jobpipe.config import Settings


@dataclass(frozen=True)
class GeminiConfig:
    """Configuration for Gemini API client."""

    api_key: str
    model: str = "gemini-1.5-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    timeout_seconds: int = 60
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


@dataclass(frozen=True)
class GeminiResponse:
    """Response from Gemini API."""

    text: str
    usage_metadata: dict[str, Any] | None = None
    raw_response: dict[str, Any] | None = None


class GeminiAPIError(RuntimeError):
    """Error communicating with Gemini API."""

    pass


def _build_resume_prompt(
    master_cv: str,
    job_description: str,
    latex_template: str | None = None,
) -> str:
    """Build the prompt for resume generation."""

    template_section = ""
    if latex_template:
        template_section = f"""
## LaTeX Template Structure (follow this format):
{latex_template}

"""

    return f"""You are an expert resume writer specializing in creating targeted, one-page LaTeX resumes.

## Task
Generate a tailored LaTeX resume based on the provided Master CV and Job Description. The resume must be factual, concise, and optimized for the specific job.

## Constraints
- Use ONLY information from the Master CV (do not invent projects, metrics, or experience)
- Keep the resume to ONE page maximum
- Use standard LaTeX article class with geometry package for margins
- Emphasize skills and experience relevant to the job description
- Use bullet points for achievements with quantifiable results where available
- Maintain a clean, professional layout

{template_section}
## Master CV:
{master_cv}

## Job Description:
{job_description}

## Output
Output ONLY the complete LaTeX code for the resume. Start with \\documentclass and end with \\end{{document}}.
Do not include any explanations or markdown formatting - just the raw LaTeX code."""


def _extract_latex(response_text: str) -> str:
    """Extract LaTeX code from Gemini response."""
    text = response_text.strip()

    # Remove markdown code blocks if present
    text = re.sub(r"^```latex\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^```\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)

    # Ensure it starts with documentclass
    if not text.startswith("\\documentclass"):
        # Try to find the documentclass line
        match = re.search(r"\\documentclass.*", text)
        if match:
            text = text[match.start() :]

    # Ensure it ends with end{document}
    if not text.endswith("\\end{document}"):
        match = re.search(r"\\end{document}", text)
        if match:
            text = text[: match.end()]

    return text.strip()


class GeminiClient:
    """Client for Google Gemini API."""

    def __init__(self, config: GeminiConfig) -> None:
        self._config = config
        self._session = requests.Session()

    def generate_resume(
        self,
        master_cv: str,
        job_description: str,
        latex_template: str | None = None,
    ) -> GeminiResponse:
        """Generate a targeted LaTeX resume using Gemini API."""
        prompt = _build_resume_prompt(master_cv, job_description, latex_template)

        url = f"{self._config.base_url}/models/{self._config.model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "X-goog-api-key": self._config.api_key,
        }
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                    ],
                },
            ],
            "generationConfig": {
                "temperature": 0.3,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 8192,
            },
        }

        last_error = None
        for attempt in range(1, self._config.max_retries + 1):
            try:
                response = self._session.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self._config.timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()

                # Extract text from response
                candidates = data.get("candidates", [])
                if not candidates:
                    raise GeminiAPIError("No candidates in API response")

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    raise GeminiAPIError("No content parts in API response")

                generated_text = parts[0].get("text", "")
                if not generated_text:
                    raise GeminiAPIError("Empty text in API response")

                # Extract LaTeX code
                latex_code = _extract_latex(generated_text)

                return GeminiResponse(
                    text=latex_code,
                    usage_metadata=data.get("usageMetadata"),
                    raw_response=data,
                )

            except Timeout as exc:
                last_error = GeminiAPIError(f"Request timeout: {exc}")
            except RequestException as exc:
                last_error = GeminiAPIError(f"Request failed: {exc}")
            except (KeyError, IndexError) as exc:
                last_error = GeminiAPIError(f"Unexpected API response format: {exc}")

            if attempt < self._config.max_retries:
                time.sleep(self._config.retry_delay_seconds * attempt)

        raise last_error or GeminiAPIError("Failed to generate resume after retries")

    def health_check(self) -> bool:
        """Check if Gemini API is accessible."""
        try:
            url = f"{self._config.base_url}/models/{self._config.model}"
            headers = {"X-goog-api-key": self._config.api_key}
            response = self._session.get(
                url,
                headers=headers,
                timeout=10,
            )
            return response.status_code == 200
        except Exception:
            return False


def create_gemini_client_from_settings(settings: Settings) -> GeminiClient:
    """Create a Gemini client from application settings."""
    api_key = getattr(settings, "gemini_api_key", None)
    if not api_key:
        raise GeminiAPIError(
            "Gemini API key not configured. Set JOBPIPE_GEMINI_API_KEY in .env file."
        )

    config = GeminiConfig(
        api_key=api_key,
        model=getattr(settings, "gemini_model", "gemini-1.5-flash"),
        base_url=getattr(
            settings, "gemini_base_url", "https://generativelanguage.googleapis.com/v1beta"
        ),
        timeout_seconds=getattr(settings, "gemini_timeout_seconds", 60),
        max_retries=getattr(settings, "gemini_max_retries", 3),
        retry_delay_seconds=getattr(settings, "gemini_retry_delay_seconds", 1.0),
    )

    return GeminiClient(config)
