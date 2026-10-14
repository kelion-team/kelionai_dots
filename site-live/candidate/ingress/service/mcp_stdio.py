"""Local MCP stdio launcher. stdout contains only UTF-8 JSON-RPC messages."""
import argparse
import json
import os
import sys
from pathlib import Path
from mcp_protocol import MCP, MAX_BODY, error
from store import Store


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--runtime',type=Path,default=Path(__file__).with_name('runtime.unverified.json'))
    args=parser.parse_args()
    # Standard stdio uses trusted local process launch, not an auth field in tool arguments.
    # Require securely supplied launcher environment, matching the client principal.
    if len(os.environ.get('KELION_CLIENT_TOKEN','')) < 32:
        parser.error('KELION_CLIENT_TOKEN of at least 32 characters is required in launcher environment')
    protocol=MCP(Store(args.database,json.loads(args.runtime.read_text(encoding='utf-8'))))
    while True:
        line=sys.stdin.buffer.readline(MAX_BODY+1)
        if not line:
            break
        if len(line) > MAX_BODY:
            response=error(None,-32600,'Message exceeds size limit')
            while line and not line.endswith(b'\n'):
                line=sys.stdin.buffer.readline(MAX_BODY+1)
        else:
            try:
                response=protocol.handle(json.loads(line.decode('utf-8')))
            except (ValueError,UnicodeError):
                response=error(None,-32700,'Parse error')
        if response is not None:
            raw=json.dumps(response,ensure_ascii=False,allow_nan=False).encode('utf-8')+b'\n'
            sys.stdout.buffer.write(raw)
            sys.stdout.buffer.flush()


if __name__=='__main__':
    main()
