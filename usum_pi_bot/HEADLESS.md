# Headless Pi desktop from an iPad

The tested setup uses Raspberry Pi OS/Debian 13, SSH, TigerVNC and Openbox. An X11 virtual desktop keeps both capture windows visible without an HDMI monitor. VNC viewer access from an iPad is sufficient for setup and control; Termius SSH/SFTP handles commands and downloads.

## Desktop installation

```bash
sudo apt-get update
sudo apt-get install -y tigervnc-standalone-server tigervnc-common openbox xterm pcmanfm dbus-x11
tigervncpasswd
```

Create `~/start-shiny-desktop.sh`:

```sh
#!/bin/sh
unset SESSION_MANAGER DBUS_SESSION_BUS_ADDRESS WAYLAND_DISPLAY
export XDG_SESSION_TYPE=x11
xterm &
exec dbus-run-session -- openbox-session
```

```bash
chmod +x ~/start-shiny-desktop.sh
tigervncserver :1 -localhost no -SecurityTypes VncAuth -geometry 1280x800 -depth 24 -xstartup "$HOME/start-shiny-desktop.sh"
```

Connect the iPad VNC viewer to the Pi’s LAN IP, port **5901** (display `:1`), using the VNC password. Keep this service on your local network; do not forward its port through your router.

## Capture and bot startup

From `usum_pi_bot/`, run:

```bash
bash Install_capture_recovery.sh
```

This adds the capture supervisor to `~/.config/openbox/autostart`. Also add one line for the bot, replacing `/absolute/path/usum_pi_bot` with the actual installation directory:

```sh
bash /absolute/path/usum_pi_bot/Launch.sh >> "$HOME/shiny-bot.log" 2>&1 &
```

Keep only one capture-supervisor entry and one bot entry. When migrating from an older installation, update the old paths instead of starting both installations. Restart the desktop to apply autostart changes. The bot GUI launches automatically; hunting still requires its Start button and first-normal confirmation.

## Start the desktop at boot

Create `/etc/systemd/system/shiny-desktop.service` using the following, replacing `USERNAME` and `/home/USERNAME` with your account and home directory:

```ini
[Unit]
Description=Shiny bot remote desktop
After=network.target

[Service]
Type=simple
User=USERNAME
WorkingDirectory=/home/USERNAME
Environment=HOME=/home/USERNAME
ExecStartPre=-/usr/bin/tigervncserver -kill :1
ExecStart=/usr/bin/tigervncserver :1 -fg -localhost no -SecurityTypes VncAuth -geometry 1280x800 -depth 24 -xstartup /home/USERNAME/start-shiny-desktop.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now shiny-desktop.service
```

Stop any manually launched display `:1` before starting the service. To restart later:

```bash
sudo systemctl restart shiny-desktop.service
```

Restarting the desktop stops any active hunt. The capture supervisor restarts the viewer within an existing desktop session; the bot’s optional capture recovery resumes an interrupted active hunt. Neither automatically restarts a crashed 3DS nor enables InputRedirection after a console reboot.

## Layout and logs

Use the 1280×800 desktop. The supervisor places the top viewer at approximately (850,30) and bottom at (850,350), with 1× scaling and separate screens. Keep other windows away from the bottom viewer and disable desktop blanking. The viewer’s audio is disabled to avoid repeated audio-device initialization errors in the virtual desktop.

Persistent diagnostic output is in the installation’s `out/` directory. Viewer incident ZIPs can be downloaded from Termius SFTP. `~/capture-viewer.log` links to the current viewer log, and `~/capture-supervisor.log` records supervisor output.
