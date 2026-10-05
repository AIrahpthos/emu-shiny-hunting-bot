# Remote desktop and automatic startup

The bot needs a graphical desktop. A TigerVNC virtual desktop allows a Linux computer or Pi to run without a monitor and be controlled from another computer, tablet or phone.

## Create a VNC desktop

Install TigerVNC and Openbox, then choose a VNC password:

```bash
sudo apt-get update
sudo apt-get install -y tigervnc-standalone-server tigervnc-common openbox xterm dbus-x11
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

Make it executable and start a 1280×800 desktop:

```bash
chmod +x ~/start-shiny-desktop.sh
tigervncserver :1 -localhost no -SecurityTypes VncAuth \
  -geometry 1280x800 -depth 24 -xstartup "$HOME/start-shiny-desktop.sh"
```

Connect a VNC client to the computer’s LAN address on port **5901**, using the password chosen above. Keep this service on your local network; do not expose it through router port forwarding.

Install the bot using [README.md](README.md). Setup creates its Openbox startup entry. If setup was run before Openbox was installed, run `bash Install_capture_recovery.sh` from the bot directory. Restart the desktop to apply startup changes; stop an active hunt before doing so.

## Launch from SSH

With the VNC desktop already running, use this from the installation’s `usum_pi_bot` directory:

```bash
nohup env DISPLAY=:1 bash Launch.sh > ~/shiny-integrated.log 2>&1 < /dev/null &
```

`:1` matches the desktop created above. If you use another display, substitute its value. You can check it with `echo "$DISPLAY"` in a terminal inside that desktop.

## Start the desktop at boot

Create `/etc/systemd/system/shiny-desktop.service` using the following. Replace `USERNAME` and `/home/USERNAME` with the account and home directory used to install the bot:

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

Stop the manually started display before enabling the service:

```bash
tigervncserver -kill :1
sudo systemctl daemon-reload
sudo systemctl enable --now shiny-desktop.service
```

The desktop starts at boot, Openbox launches the bot, and the bot connects its saved capture source. NTR must be running on the console for wireless capture. Starting a hunt and confirming its first normal encounter remain manual.

**Connect saved capture automatically when the bot opens** can be disabled on Screen setup. No separate viewer or capture supervisor needs to start.

For a local desktop other than Openbox, configure its startup mechanism to run the absolute path to `Launch.sh` instead. A TigerVNC desktop and boot service are optional when a local desktop is available.

## Existing installations

Setup backs up `~/.config/openbox/autostart` and replaces recognised old bot/viewer entries with one entry for the new installation. If an old installation uses another path or startup mechanism, remove its entries manually to prevent competing capture processes.

You can rerun `bash Install_capture_recovery.sh` without creating duplicate entries. Startup backups are saved as `autostart.before-integrated-<timestamp>` beside the startup file.

Disconnecting the VNC client does not stop capture; closing or restarting the desktop does. Logs and incident reports are in the installation’s `out/` directory. SSH-launched GUI output goes to `~/shiny-integrated.log` when using the command above.
