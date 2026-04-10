from pathlib import Path

import pytest

from jobpipe.resume.compiler import LatexCompileConfig, LatexCompileResult
from jobpipe.resume.service import ApprovalRequiredError, write_targeted_resume


def _fake_compile(
    tex_path: Path,
    output_pdf_path: Path | None,
    config: LatexCompileConfig | None,
) -> LatexCompileResult:
    _ = config
    pdf_path = output_pdf_path or tex_path.with_suffix(".pdf")
    pdf_path.write_text("%PDF-1.4\n", encoding="utf-8")
    return LatexCompileResult(
        tex_path=tex_path,
        pdf_path=pdf_path,
        attempts=1,
        command=["pdflatex"],
        stdout="",
        stderr="",
    )


def test_write_targeted_resume_requires_approval(tmp_path) -> None:
    with pytest.raises(ApprovalRequiredError):
        write_targeted_resume(
            tex_content="\\documentclass{article}",
            output_name="targeted_resume",
            output_dir=tmp_path,
            compile_config=LatexCompileConfig(),
            approved=False,
        )


def test_write_targeted_resume_writes_tex_and_compiles(tmp_path) -> None:
    result = write_targeted_resume(
        tex_content="\\documentclass{article}\\begin{document}Hi\\end{document}",
        output_name="backend_focus",
        output_dir=tmp_path,
        compile_config=LatexCompileConfig(),
        approved=True,
        compile_func=_fake_compile,
    )

    assert result.tex_path.exists() is True
    assert result.pdf_path.exists() is True
    assert result.compile_attempts == 1
    assert result.tex_path.read_text(encoding="utf-8").startswith("\\documentclass")
