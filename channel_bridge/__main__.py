"""Offline supervisor. No production adapters are shipped or dynamically loaded."""
import argparse
import json
import signal
import threading
from pathlib import Path
from .bridge import Bridge, Endpoint


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', required=True)
    p.add_argument('--state', required=True)
    p.add_argument('--serve', action='store_true')
    args = p.parse_args()
    cfg = json.loads(Path(args.config).read_text())
    if cfg.get('enabled') is not False:
        p.error('production_adapters_unimplemented: enabled must remain false')
    endpoints = [Endpoint(**e) for e in cfg['endpoints']]
    bridge = Bridge(args.state, endpoints)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        while True:
            report = bridge.health()
            print(json.dumps(report, sort_keys=True), flush=True)
            if not args.serve:
                return 0 if report['readiness'] == 'ready' else 2
            if stop.wait(30):
                return 0
    finally:
        bridge.close()


if __name__ == '__main__':
    raise SystemExit(main())
