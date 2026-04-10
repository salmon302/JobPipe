from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


_RETRYABLE_MARKERS = (
    "permission denied",
    "resource busy",
    "file is being used by another process",
    "i can't write on file",
)


@dataclass(frozen=True)
class LatexCompileConfig:
    pdflatex_command: str = "pdflatex"
    retries: int = 2
    retry_backoff_seconds: float = 1.0
    timeout_seconds: int = 120


@dataclass(frozen=True)
class LatexCompileResult:
    tex_path: Path
    pdf_path: Path
    attempts: int
    command: list[str]
    stdout: str
    stderr: str


class LatexCompilationError(RuntimeError):
    pass


def _should_retry(stdout: str, stderr: str) -> bool:
    combined = f"{stdout}\n{stderr}".lower()
    return any(marker in combined for marker in _RETRYABLE_MARKERS)


def _copy_pdf_with_retries(
    source_pdf: Path,
    target_pdf: Path,
    retries: int,
    backoff_seconds: float,
) -> None:
    max_attempts = max(1, retries + 1)
    last_error: OSError | None = None

    target_pdf.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, max_attempts + 1):
        try:
            if target_pdf.exists():
                target_pdf.unlink()
            shutil.copy2(source_pdf, target_pdf)
            return
        except OSError as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(backoff_seconds * attempt)

    raise LatexCompilationError(
        f"Unable to write compiled PDF at {target_pdf}: {last_error}"
    ) from last_error


def compile_latex(
    tex_path: Path,
    output_pdf_path: Path | None = None,
    config: LatexCompileConfig | None = None,
) -> LatexCompileResult:
    if not tex_path.exists():
        raise LatexCompilationError(f"TeX source file does not exist: {tex_path}")

    cfg = config or LatexCompileConfig()
    output_pdf = output_pdf_path or tex_path.with_suffix(".pdf")
    max_attempts = max(1, cfg.retries + 1)

    last_stdout = ""
    last_stderr = ""
    command: list[str] = []

    for attempt in range(1, max_attempts + 1):
        with tempfile.TemporaryDirectory(prefix="jobpipe-tex-") as build_dir_str:
            build_dir = Path(build_dir_str)
            command = [
                cfg.pdflatex_command,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                "-output-directory",
                str(build_dir),
                str(tex_path),
            ]

            try:
                proc = subprocess.run(
                    command,
                    cwd=str(tex_path.parent),
                    capture_output=True,
                    text=True,
                    timeout=max(1, cfg.timeout_seconds),
                    check=False,
                )
                last_stdout = proc.stdout or ""
                last_stderr = proc.stderr or ""
            except FileNotFoundError as exc:
                raise LatexCompilationError(
                    "pdflatex executable was not found. "
                    f"Configure JOBPIPE_PDFLATEX_COMMAND (current: {cfg.pdflatex_command})."
                ) from exc
            except subprocess.TimeoutExpired as exc:
                last_stdout = exc.stdout or ""
                last_stderr = (exc.stderr or "") + "\nCompilation timed out."
                proc = None

            compiled_pdf = build_dir / f"{tex_path.stem}.pdf"
            if proc is not None and proc.returncode == 0 and compiled_pdf.exists():
                _copy_pdf_with_retries(
                    source_pdf=compiled_pdf,
                    target_pdf=output_pdf,
                    retries=cfg.retries,
                    backoff_seconds=cfg.retry_backoff_seconds,
                )
                return LatexCompileResult(
                    tex_path=tex_path,
                    pdf_path=output_pdf,
                    attempts=attempt,
                    command=command,
                    stdout=last_stdout,
                    stderr=last_stderr,
                )

        if attempt == max_attempts:
            break

        if not _should_retry(last_stdout, last_stderr):
            break

        time.sleep(cfg.retry_backoff_seconds * attempt)

    raise LatexCompilationError(
        "LaTeX compilation failed "
        f"after {max_attempts} attempt(s) for {tex_path}.\n"
        f"Command: {' '.join(command)}\n"
        f"stderr:\n{last_stderr.strip()}"
    )
