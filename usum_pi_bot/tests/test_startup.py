from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from startup import migrate, install
from app import App


class StartupTests(unittest.TestCase):
    def test_replaces_old_entries_preserves_unrelated_and_is_idempotent(self):
        home=Path('/home/jack');bot=home/'shiny-integrated/usum_pi_bot'
        text='''xterm &
bash /home/jack/usum_pi_bot/Capture_supervisor.sh >> "$HOME/capture-supervisor.log" 2>&1 &
bash /home/jack/usum_pi_bot/Launch.sh &
bash /home/jack/other/Launch.sh &
# Previous setup: /home/jack/usum_pi_bot/Launch.sh
'''
        result=migrate(text,bot,home)
        self.assertNotIn('bash /home/jack/usum_pi_bot/',result)
        self.assertIn('bash /home/jack/other/Launch.sh &',result)
        self.assertIn('xterm &',result)
        self.assertEqual(result.count('bash /home/jack/shiny-integrated/usum_pi_bot/Launch.sh'),1)
        self.assertEqual(migrate(result,bot,home),result)

    def test_home_and_quoted_paths_migrate_without_matching_neighbour(self):
        home=Path('/home/jack');bot=home/'shiny-integrated/usum_pi_bot'
        text='''bash "$HOME/usum_pi_bot/Launch.sh" &
bash '${HOME}/usum_pi_bot/Capture_supervisor.sh' &
bash ~/usum_pi_bot/Launch_capture.sh &
bash /home/jack/usum_pi_bot-other/Launch.sh &
'''
        result=migrate(text,bot,home)
        self.assertNotIn('Capture_supervisor.sh',result)
        self.assertNotIn('Launch_capture.sh',result)
        self.assertIn('usum_pi_bot-other/Launch.sh',result)

    def test_original_startup_is_backed_up_and_repeat_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);bot=home/'shiny-integrated/usum_pi_bot'
            path=home/'.config/openbox/autostart';path.parent.mkdir(parents=True)
            original=f'xterm &\nbash {home}/usum_pi_bot/Launch.sh &\n'
            path.write_text(original)
            backup=install(bot,home)
            self.assertEqual(backup.read_text(),original)
            self.assertIsNone(install(bot,home))
            self.assertIn(str(bot/'Launch.sh'),path.read_text())

    def test_saved_capture_connects_on_open_without_starting_hunt(self):
        app=object.__new__(App)
        app.stop=Mock();app.stop.is_set.return_value=False
        app.auto_connect_capture=Mock();app.auto_connect_capture.get.return_value=True
        app.source=Mock(return_value='NTR wireless');app.ip=Mock();app.ip.get.return_value='10.0.0.106'
        app.connect_capture=Mock();app.start=Mock();app.emit=Mock()
        app.connect_saved_capture()
        app.connect_capture.assert_called_once();app.start.assert_not_called()
        app.connect_capture.reset_mock();app.auto_connect_capture.get.return_value=False
        app.connect_saved_capture();app.connect_capture.assert_not_called()

    def test_missing_ntr_ip_waits_for_user_entry(self):
        app=object.__new__(App)
        app.stop=Mock();app.stop.is_set.return_value=False
        app.auto_connect_capture=Mock();app.auto_connect_capture.get.return_value=True
        app.source=Mock(return_value='NTR wireless');app.ip=Mock();app.ip.get.return_value=''
        app.connect_capture=Mock();app.emit=Mock()
        app.connect_saved_capture();app.connect_capture.assert_not_called();app.emit.assert_called_once()
