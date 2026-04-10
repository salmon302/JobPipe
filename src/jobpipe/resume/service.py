from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import time
from typing import Callable

from jobpipe.resume.compiler import LatexCompileConfig, LatexCompileResult, compile_latex


_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class ApprovalRequiredError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResumeWriteResult:
    tex_path: Path
    pdf_path: Path
    compile_attempts: int


def _normalize_output_name(output_name: str, default_base_name: str) -> str:
    candidate = output_name.strip() if output_name else ""
    if not candidate:
        candidate = default_base_name

    candidate = _SAFE_FILENAME_RE.sub("_", candidate.strip().replace(" ", "_"))
    candidate = candidate.strip("._")

    if not candidate:
        candidate = default_base_name

    if not candidate.lower().endswith(".tex"):
        candidate = f"{candidate}.tex"

    return candidate


def _write_text_with_retries(path: Path, content: str, retries: int, backoff_seconds: float = 0.5) -> None:
    max_attempts = max(1, retries + 1)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    last_error: OSError | None = None

    path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_attempts + 1):
        try:
            temp_path.write_text(content, encoding="utf-8")
            temp_path.replace(path)
            return
        except OSError as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(backoff_seconds * attempt)
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    raise RuntimeError(f"Unable to write TeX file at {path}: {last_error}") from last_error


def write_targeted_resume(
    tex_content: str,
    output_name: str,
    output_dir: Path,
    compile_config: LatexCompileConfig,
    approved: bool,
    write_retries: int = 2,
    default_base_name: str = "Targeted_Resume",
    compile_func: Callable[[Path, Path | None, LatexCompileConfig | None], LatexCompileResult] = compile_latex,
) -> ResumeWriteResult:
    if not approved:
        raise ApprovalRequiredError(
            "Write was blocked because approved=False. Review the diff in Claude and retry with approval."
        )

    normalized_name = _normalize_output_name(output_name, default_base_name)
    tex_path = output_dir / normalized_name

    _write_text_with_retries(tex_path, tex_content, retries=write_retries)

    compile_result = compile_func(
        tex_path,
        output_pdf_path=tex_path.with_suffix(".pdf"),
        config=compile_config,
    )

    return ResumeWriteResult(
        tex_path=tex_path,
        pdf_path=compile_result.pdf_path,
        compile_attempts=compile_result.attempts,
    )
