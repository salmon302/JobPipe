# Purpose: LaTeX code editor widget with syntax highlighting.
# Author: Seth Nenninger (Tencent: Hy3 preview Agent)
# Timestamp: 2026-05-12T20:15:00Z

from __future__ import annotations

try:
    from PySide6.QtCore import QRegularExpression, Qt
    from PySide6.QtGui import (
        QColor,
        QFont,
        QSyntaxHighlighter,
        QTextCharFormat,
    )
    from PySide6.QtWidgets import QPlainTextEdit
except ImportError as exc:
    raise RuntimeError(
        "GUI dependencies are missing. Install with: pip install -e .[gui]"
    ) from exc


class LatexSyntaxHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for LaTeX code."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._highlighting_rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        # LaTeX command format (e.g., \documentclass, \begin)
        command_format = QTextCharFormat()
        command_format.setForeground(QColor(0, 0, 255))  # Blue
        command_format.setFontWeight(QFont.Weight.Bold)
        self._add_rule(r"\\(?:documentclass|usepackage|begin|end|section|subsection|textbf|textit|texttt|emph|item|label|ref|cite|url|href|includegraphics|input)\b", command_format)

        # Bracket format (for {} and [])
        bracket_format = QTextCharFormat()
        bracket_format.setForeground(QColor(255, 128, 0))  # Orange
        self._add_rule(r"[{}\[\]]", bracket_format)

        # Comment format
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor(0, 128, 0))  # Green
        comment_format.setFontItalic(True)
        self._add_rule(r"%.*$", comment_format)

        # Math mode format
        math_format = QTextCharFormat()
        math_format.setForeground(QColor(128, 0, 128))  # Purple
        self._add_rule(r"\$.*?\$", math_format)

        # Environment name format (inside \begin{} and \end{})
        env_format = QTextCharFormat()
        env_format.setForeground(QColor(0, 128, 128))  # Teal
        env_format.setFontWeight(QFont.Weight.Bold)
        self._add_rule(r"(?<=\\begin{)[^}]+|(?<=\\end{)[^}]+", env_format)

    def _add_rule(self, pattern: str, format: QTextCharFormat) -> None:
        regex = QRegularExpression(pattern)
        regex.setPatternOptions(QRegularExpression.PatternOption.CaseInsensitiveOption)
        self._highlighting_rules.append((regex, format))

    def highlightBlock(self, text: str) -> None:
        for regex, format in self._highlighting_rules:
            iterator = regex.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)


class LatexEditor(QPlainTextEdit):
    """A QPlainTextEdit with LaTeX syntax highlighting."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._highlighter = LatexSyntaxHighlighter(self.document())

        # Set font to monospace
        font = QFont("Cascadia Code", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFixedPitch(True)
        self.setFont(font)

        # Set tab width
        self.setTabStopDistance(40)

        # Line numbers could be added here in the future

    def load_file(self, file_path) -> bool:
        """Load a LaTeX file into the editor.

        Args:
            file_path: Path to the .tex file

        Returns:
            True if file was loaded successfully, False otherwise
        """
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            return False

        try:
            content = path.read_text(encoding="utf-8")
            self.setPlainText(content)
            return True
        except OSError:
            return False

    def save_file(self, file_path) -> bool:
        """Save editor content to a file.

        Args:
            file_path: Path where to save the .tex file

        Returns:
            True if file was saved successfully, False otherwise
        """
        from pathlib import Path

        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            content = self.toPlainText()
            path.write_text(content, encoding="utf-8")
            return True
        except OSError:
            return False

    def get_latex_content(self) -> str:
        """Get the current LaTeX content as string."""
        return self.toPlainText()
