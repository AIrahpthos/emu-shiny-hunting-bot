"""Download a pinned official cc3dsfs desktop release and verify its hash."""
import hashlib
import platform
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

ASSETS={
    'aarch64':('cc3dsfs_linux_arm64.zip','98f499c36e7a802e13c5649b664f480b6701ba21aef99e84d286f0453fb921a7'),
    'armv7l':('cc3dsfs_linux_arm32.zip','381758a29d554d1056eaad259560dda8930b22469f37dd3d51367b605d08e7eb'),
}


def safe_extract(archive,destination):
    root=destination.resolve()
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            if not (root/ item.filename).resolve().is_relative_to(root):
                raise ValueError('Unexpected archive path')
            if stat.S_ISLNK(item.external_attr>>16):
                raise ValueError('Unexpected archive symlink')
        z.extractall(root)


def main():
    arch=platform.machine()
    if arch not in ASSETS:
        raise ValueError(f'This package targets Raspberry Pi ARM Linux, not {arch}.')
    filename,expected=ASSETS[arch]
    root=Path(__file__).resolve().parent
    url='https://github.com/Lorenzooone/cc3dsfs/releases/download/1.3.0.1/'+filename
    archive=root/filename
    print('Downloading official cc3dsfs 1.3.0.1 desktop build...',flush=True)
    urllib.request.urlretrieve(url,archive)
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest!=expected:
        archive.unlink(missing_ok=True)
        raise ValueError('cc3dsfs checksum mismatch. Nothing was installed.')
    destination=root/'capture_viewer'
    destination.mkdir(exist_ok=True)
    safe_extract(archive,destination)
    executables=[p for p in destination.rglob('cc3dsfs') if p.is_file()]
    if len(executables)!=1:
        raise ValueError('Could not identify the capture executable in the official archive.')
    executables[0].chmod(0o755)
    (root/'capture_executable.txt').write_text(str(executables[0].resolve()))
    scripts=list(destination.rglob('install_usb_rules.sh'))
    if len(scripts)!=1:
        raise ValueError('Could not identify the bundled USB permissions installer.')
    (root/'capture_rules_installer.txt').write_text(str(scripts[0].resolve()))
    print('Official release downloaded and verified.',flush=True)


if __name__=='__main__':
    try: main()
    except Exception as e:
        print(f'Capture setup stopped: {e}',file=sys.stderr)
        raise SystemExit(1)
