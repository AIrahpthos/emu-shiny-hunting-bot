# Integrated bot on your existing VNC desktop

Use the existing 1280×800 TigerVNC/Openbox desktop and its existing boot service. A physical monitor is not required.

Setup backs up `~/.config/openbox/autostart` and replaces the known old bot/viewer startup entries with one entry for this installation. Other startup commands are preserved. Existing processes are not killed by setup; stop the active hunt and restart the desktop to apply the change.

The new bot opens and automatically connects the saved capture source. NTR uses the saved 3DS IP, JPEG quality and bandwidth. Loopy connects directly over USB. No separate viewer or capture supervisor needs to start. The Screen setup checkbox can disable automatic capture connection.

Starting the hunt and confirming the first normal encounter remain manual. Covering the preview or disconnecting the iPad VNC client does not interrupt direct capture; keep the desktop session itself running.

To apply the migration again, run `bash Install_capture_recovery.sh` from this installation. It is safe to repeat and avoids duplicate bot entries. The previous startup file is saved beside it as `autostart.before-integrated-<timestamp>`; restore that backup to return to the former boot setup.

Logs are in `out/`; Recovery reports exports incident ZIPs there. GUI output is in `~/shiny-integrated.log`. Console crashes still require manual console recovery.
