# Integrated bot on your existing VNC desktop

Use the existing 1280×800 TigerVNC/Openbox desktop. A physical monitor is not required. Launch the bot from the VNC terminal or use `DISPLAY=:1` from SSH, as shown in [README.md](README.md).

The bot provides its own preview and capture connections. No viewer or capture-supervisor startup is needed. Covering the preview or disconnecting the iPad's VNC client does not interrupt direct capture; keep the desktop session itself running.

When this version has passed a hardware test, remove the old installation's `Capture_supervisor.sh`, `Launch_capture.sh` and `Launch.sh` entries from `~/.config/openbox/autostart`. Run `bash Install_capture_recovery.sh` from this installation to add its one bot startup entry. Reuse your existing desktop boot service.

The bot window opens at desktop startup. Click Connect capture to start the selected feed, then start the hunt and confirm the first normal encounter. Capture reconnects are automatic while the app stays open, but launching the app does not automatically start hunting.

Logs are in `out/`; Recovery reports exports incident ZIPs there. SSH-launched GUI output is in `~/shiny-integrated.log` if you used the command in README. Console crashes still require manual console recovery.
