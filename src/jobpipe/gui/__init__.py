from __future__ import annotations

from jobpipe.config import Settings

__all__ = ["launch_gui"]


def launch_gui(settings: Settings, default_max_pages: int = 1) -> int:
	from jobpipe.gui.app import launch_gui as _launch_gui

	return _launch_gui(settings=settings, default_max_pages=default_max_pages)