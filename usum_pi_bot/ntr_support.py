"""Capture source selection and NTR window layout."""
from pathlib import Path
import subprocess

SOURCES = ('Loopy USB', 'NTR wireless')
NTR_PREFIX = 'NTRViewer-HR'


def choose_viewer(windows, source='Loopy USB'):
    prefix = NTR_PREFIX if source == 'NTR wireless' else 'cc3dsfs_bot'
    matches = [item for item in windows if item[1].startswith(prefix)]
    if len(matches) != 1:
        if not matches:
            raise ValueError('Open NTRViewer-HR in Bottom Only view.' if source == 'NTR wireless'
                             else 'Open cc3dsfs with separate screen windows.')
        raise ValueError('Close duplicate viewers. For NTR, use Bottom Only view in one window.')
    return matches[0][0]


def ntr_executable():
    path = Path.home()/'ntr-viewer'/'NTRViewer-HR-Linux-arm64'/'ntrviewer'
    if not path.is_file():
        raise ValueError(f'NTR viewer is missing: {path}')
    return path


def position_ntr():
    """Use the top-right slot without covering the USB bottom viewer."""
    for args in [('wmctrl','-r',NTR_PREFIX,'-b','remove,maximized_vert,maximized_horz'),
                 ('wmctrl','-r',NTR_PREFIX,'-e','0,850,30,320,240')]:
        subprocess.run(args, check=True, timeout=5, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL)
