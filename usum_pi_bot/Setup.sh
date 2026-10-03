#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ $(id -u) -eq 0 ]]; then
  echo 'Run bash Setup.sh as your normal Pi desktop user; it will request sudo when needed.'
  exit 1
fi
printf 'Installing desktop and capture dependencies...\n'
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-tk libusb-1.0-0 libudev1 \
  libgl1 libxrandr2 libxcursor1 libxi6 libfreetype6 libharfbuzz0b \
  libflac-dev libvorbis0a libvorbisenc2 libogg0 libopenal1 libasound2-dev libgpiod-dev
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python install_capture.py
rules_installer=$(cat capture_rules_installer.txt)
( cd -- "$(dirname -- "$rules_installer")"; sudo sh "./$(basename -- "$rules_installer")" )
sudo udevadm control --reload-rules
chmod +x Launch.sh Launch_capture.sh
printf '\nSetup complete. Unplug/reconnect the 3DS capture USB cable.\n'
printf 'Open the viewer with: bash Launch_capture.sh\n'
printf 'Open the bot with:    bash Launch.sh\n'
printf 'This first build needs the X11 desktop; switch with raspi-config if needed.\n'
