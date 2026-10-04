#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
[[ $(id -u) -ne 0 ]] || { echo "Run Setup_integrated.sh from your desktop account."; exit 1; }
sudo apt-get update
sudo apt-get install -y git cmake build-essential pkg-config python3-venv python3-tk \
  libxrandr-dev libxcursor-dev libxi-dev libudev-dev libfreetype-dev libharfbuzz-dev libflac-dev \
  libvorbis-dev libogg-dev libopenal-dev libgl1-mesa-dev libusb-1.0-0-dev
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
bash native/Build_loopy.sh
sed "s/__UID__/$(id -u)/g" native/51-shiny-loopy.rules > native/51-shiny-loopy.installed.rules
sudo install -m 0644 native/51-shiny-loopy.installed.rules /etc/udev/rules.d/51-shiny-loopy.rules
sudo udevadm control --reload-rules
bash Install_capture_recovery.sh
printf '\nSetup finished. Reconnect the USB cable if using Loopy, then restart the desktop after stopping the old hunt.\n'
