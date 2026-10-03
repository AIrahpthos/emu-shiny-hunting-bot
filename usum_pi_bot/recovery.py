"""Reacquire a restarted viewer without sending console input."""
import time
from capture_linux import Capture, Desktop, ViewerUnavailable
from core import BOTTOM_WINDOW_PREFIX, Stopped, choose_bottom_window


def wait_for_capture(point, stop, emit, timeout=120, desktop_factory=Desktop,
                     capture_factory=Capture):
    deadline = time.monotonic() + timeout
    candidate = None
    consecutive = 0
    try:
        while time.monotonic() < deadline:
            if stop.is_set():
                raise Stopped()
            desktop = None
            try:
                desktop = desktop_factory()
                windows = desktop.windows()
            finally:
                if desktop:
                    desktop.close()
            matches = [item for item in windows if item[1].startswith(BOTTOM_WINDOW_PREFIX)]
            if len(matches) > 1:
                raise RuntimeError('Multiple bottom-screen viewers appeared during recovery.')
            if not matches:
                if candidate:
                    candidate.close()
                    candidate = None
                consecutive = 0
            else:
                hwnd = choose_bottom_window(matches)
                if candidate is not None and candidate.hwnd != hwnd:
                    candidate.close()
                    candidate = None
                    consecutive = 0
                try:
                    if candidate is None:
                        candidate = capture_factory(hwnd, point)
                    candidate.grab()
                    consecutive += 1
                    if consecutive >= 3:
                        if stop.is_set():
                            raise Stopped()
                        emit('Capture restored. Resuming the active hunt with its existing baseline.')
                        restored = candidate
                        candidate = None
                        return restored
                except ViewerUnavailable:
                    if candidate:
                        candidate.close()
                        candidate = None
                    consecutive = 0
            if stop.wait(.2):
                raise Stopped()
        raise TimeoutError(f'Capture did not recover within {timeout} seconds; hunt stopped.')
    finally:
        if candidate:
            candidate.close()
