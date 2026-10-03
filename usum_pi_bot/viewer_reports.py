"""Persistent viewer-exit reports and portable diagnostic archives."""
import json
import time
import uuid
import zipfile
from pathlib import Path


def read_reports(folder):
    index = Path(folder)/'incidents.jsonl'
    records = []
    if index.exists():
        with index.open(encoding='utf-8') as file:
            for line in file:
                try:
                    record = json.loads(line)
                    if isinstance(record, dict) and record.get('type') == 'viewer_exit':
                        records.append(record)
                except (ValueError, TypeError):
                    continue
    return records


def log_path(folder, record):
    # Recorded filenames are not permitted to escape the report directory.
    filename = record.get('log_file', '')
    if not isinstance(filename, str) or not filename or Path(filename).name != filename:
        raise ValueError('Invalid viewer report filename')
    return Path(folder)/filename


def record_exit(folder, details):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    record = {'id':uuid.uuid4().hex, 'type':'viewer_exit',
              'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S%z'), **details}
    log_path(folder, record)
    with (folder/'incidents.jsonl').open('a', encoding='utf-8') as file:
        file.write(json.dumps(record)+'\n')
    return record


def export_reports(folder, destination, records, bot_log=None):
    """Archive closed viewer logs; never send anything over the network."""
    destination = Path(destination)
    if not records:
        raise ValueError('No capture interruptions have been recorded yet.')
    missing = []
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('incidents.json', json.dumps(records, indent=2))
        for record in records:
            path = log_path(folder, record)
            if path.exists():
                archive.write(path, 'viewer-logs/'+path.name)
            else:
                missing.append(path.name)
            if record.get('bot_log_file'):
                snapshot = log_path(folder, {'log_file':record['bot_log_file']})
                if snapshot.exists():
                    archive.write(snapshot, 'bot-at-interruption/'+snapshot.name)
                else:
                    missing.append(snapshot.name)
        if bot_log is not None and Path(bot_log).exists():
            # Only a recent tail is included, keeping unrelated hunt history out.
            with Path(bot_log).open('rb') as file:
                file.seek(0, 2)
                length = file.tell()
                file.seek(max(0,length-65536))
                data = file.read()
            archive.writestr('bot-events-tail.log', data)
        archive.writestr('README.txt',
            'Capture interruption report\n'
            'Viewer stdout/stderr, exit code or signal, launch settings and system details.\n'
            'An exit does not by itself prove a crash: disconnects and manual closes\n'
            'also cause the configured supervisor to relaunch the viewer.\n'
            'Intentional desktop/service shutdowns are not counted as interruptions.\n'
            'No automatic upload is performed. No memory/core dump is collected.\n'+
            ('Missing saved logs: '+', '.join(missing)+'\n' if missing else ''))
    return destination
