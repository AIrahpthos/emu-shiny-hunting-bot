import json
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from app import App
from viewer_reports import export_reports, read_reports, record_exit
from viewer_supervisor import run_viewer_once


class ViewerReportTests(unittest.TestCase):
    def test_signal_exit_retains_stdout_stderr_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            code=('import os,signal,sys,resource; '
                  'resource.setrlimit(resource.RLIMIT_CORE,(0,0)); '
                  'print("last video message",flush=True); '
                  'print("last error message",file=sys.stderr,flush=True); '
                  'os.kill(os.getpid(),signal.SIGSEGV)')
            record=run_viewer_once(Path(sys.executable),folder,threading.Event(),[None],
                                   command=[sys.executable,'-c',code],current_log=False)
            self.assertEqual(record['reason'],'SIGSEGV')
            self.assertEqual(record['returncode'],-11)
            saved=(folder/record['log_file']).read_text()
            self.assertIn('last video message',saved)
            self.assertIn('last error message',saved)
            self.assertEqual(read_reports(folder),[record])
            bot_log=folder/'bot.log'; bot_log.write_text('capture restored; hunt resumed\n')
            export_reports(folder,folder/'diagnostics.zip',[record],bot_log)
            with zipfile.ZipFile(folder/'diagnostics.zip') as archive:
                self.assertIn('viewer-logs/'+record['log_file'],archive.namelist())
                self.assertEqual(json.loads(archive.read('incidents.json')),[record])
                self.assertIn(b'hunt resumed',archive.read('bot-events-tail.log'))

    def test_closed_viewer_is_reported_without_claiming_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            record=run_viewer_once(Path(sys.executable),Path(tmp),threading.Event(),[None],
                                   command=[sys.executable,'-c','print("closed normally")'],current_log=False)
            self.assertEqual(record['returncode'],0)
            self.assertIn('closed or disconnected',record['reason'])

    def test_intentional_shutdown_is_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop=threading.Event()
            process=Mock(); process.wait.side_effect=lambda:stop.set() or -15
            with patch('viewer_supervisor.subprocess.Popen',return_value=process):
                record=run_viewer_once(Path(sys.executable),Path(tmp),stop,[None],current_log=False)
            self.assertIsNone(record)
            self.assertEqual(read_reports(Path(tmp)),[])

    def test_report_files_are_distinct_and_persistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            records=[run_viewer_once(Path(sys.executable),Path(tmp),threading.Event(),[None],
                      command=[sys.executable,'-c',f'print("run {i}");raise SystemExit(1)'],current_log=False)
                     for i in range(2)]
            self.assertNotEqual(records[0]['log_file'],records[1]['log_file'])
            self.assertEqual(read_reports(tmp),records)
            self.assertIn('run 0',(Path(tmp)/records[0]['log_file']).read_text())
            self.assertNotIn('run 1',(Path(tmp)/records[0]['log_file']).read_text())

    def test_archive_cannot_read_paths_outside_report_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                export_reports(tmp,Path(tmp)/'report.zip',[{'log_file':'../secret'}])

    def test_persistent_badge_and_acknowledgement(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp); folder=out/'capture-incidents'
            record_exit(folder,{'log_file':'one.log','returncode':1,'reason':'exit 1'})
            app=App.__new__(App)
            app.capture_reports=[]; app.report_signature=None; app.report_ack_count=0
            app.report_tree=Mock(); app.report_tree.get_children.return_value=[]
            app.report_summary=Mock()
            with patch('app.OUT',out):
                app.refresh_reports()
                self.assertIn('Unreviewed: 1',app.report_summary.set.call_args.args[0])
                app.acknowledge_reports()
                self.assertIn('Unreviewed: 0',app.report_summary.set.call_args.args[0])
            self.assertEqual(json.loads((out/'capture-report-ack.json').read_text())['count'],1)
            self.assertEqual(len(read_reports(folder)),1)
