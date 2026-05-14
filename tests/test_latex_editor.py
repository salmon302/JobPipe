# Purpose: Test LaTeX editor widget.
# Author: Seth Nenninger (Tencent: Hy3 preview Agent)
# Timestamp: 2026-05-12T20:30:00Z

"""Tests for LaTeX editor widget."""

from __future__ import annotations

import sys
from pathlib import Path
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from PySide6.QtWidgets import QApplication
    from jobpipe.gui.latex_editor import LatexEditor, LatexSyntaxHighlighter
except ImportError:
    # Skip tests if PySide6 not installed
    import pytest
    pytest.skip("PySide6 not installed", allow_module_level=True)


class TestLatexEditor(unittest.TestCase):
    """Test LatexEditor widget."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance()
        if cls.app is None:
            cls.app = QApplication([])

    def setUp(self) -> None:
        self.editor = LatexEditor()

    def test_load_file_success(self) -> None:
        """Test loading a valid LaTeX file."""
        from tempfile import NamedTemporaryFile

        content = "\\documentclass{article}\n\\begin{document}Test\\end{document}"
        with NamedTemporaryFile(mode="w", suffix=".tex", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            result = self.editor.load_file(temp_path)
            self.assertTrue(result)
            self.assertEqual(self.editor.get_latex_content(), content)
        finally:
            Path(temp_path).unlink()

    def test_load_file_not_exists(self) -> None:
        """Test loading a non-existent file."""
        result = self.editor.load_file("/non/existent/file.tex")
        self.assertFalse(result)

    def test_save_file_success(self) -> None:
        """Test saving editor content to file."""
        from tempfile import NamedTemporaryFile

        content = "\\documentclass{article}\n\\begin{document}Hello\\end{document}"
        self.editor.setPlainText(content)

        with NamedTemporaryFile(mode="w", suffix=".tex", delete=False) as f:
            temp_path = f.name

        try:
            result = self.editor.save_file(temp_path)
            self.assertTrue(result)
            saved_content = Path(temp_path).read_text(encoding="utf-8")
            self.assertEqual(saved_content, content)
        finally:
            Path(temp_path).unlink()

    def test_get_latex_content(self) -> None:
        """Test getting LaTeX content from editor."""
        content = "\\textbf{Hello World}"
        self.editor.setPlainText(content)
        self.assertEqual(self.editor.get_latex_content(), content)

    def test_empty_content(self) -> None:
        """Test handling of empty content."""
        self.editor.setPlainText("")
        self.assertEqual(self.editor.get_latex_content(), "")

    def test_latex_syntax_highlighting(self) -> None:
        """Test that syntax highlighter is attached."""
        self.assertIsInstance(self.editor._highlighter, LatexSyntaxHighlighter)


class TestLatexSyntaxHighlighter(unittest.TestCase):
    """Test LaTeX syntax highlighter."""

    def test_highlighter_creation(self) -> None:
        """Test creating a syntax highlighter."""
        highlighter = LatexSyntaxHighlighter()
        self.assertIsNotNone(highlighter)

    def test_highlighting_rules_exist(self) -> None:
        """Test that highlighting rules are defined."""
        highlighter = LatexSyntaxHighlighter()
        self.assertTrue(len(highlighter._highlighting_rules) > 0)


if __name__ == "__main__":
    unittest.main()
