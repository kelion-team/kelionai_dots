"""TEST ONLY: temporary real HTTP/SQLite Store, synthetic inputs over stdin."""
import json
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from store import Store
from server import handler_for, ThreadingHTTPServer


def main():
    config = json.loads(sys.stdin.readline())
    if not config['runtime']['runtime_id'].startswith('SYNTHETIC-'):
        raise ValueError('synthetic_fixture_only')
    with tempfile.TemporaryDirectory(prefix='siwc-http-synthetic-') as directory:
        store = Store(Path(directory) / 'fixture.sqlite3', config['runtime'])
        for raw in config['raw_tasks']:
            if not raw['task_id'].startswith('SYNTHETIC-'):
                raise ValueError('synthetic_fixture_only')
            store.intake(raw)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(store, config['client_token'], config['worker_token']))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(json.dumps({'port': server.server_port, 'synthetic': True}), flush=True)
        try:
            sys.stdin.readline()
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    main()
