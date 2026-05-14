# Purpose: Export GUI launcher entry point.
# Author: Seth Nenninger (GPT-5.2-Codex Agent)
# Timestamp: 2026-05-12T00:00:00Z
# Changelog: Align GUI launch signature with ingest server workflow.

from __future__ import annotations

from jobpipe.config import Settings

__all__ = ["launch_gui"]


def launch_gui(settings: Settings) -> int:
    from jobpipe.gui.app import launch_gui as _launch_gui

    return _launch_gui(settings=settings)