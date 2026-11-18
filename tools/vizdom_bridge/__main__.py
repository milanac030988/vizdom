"""python -m vizdom_bridge --port 0 --token <secret>  (PYTHONPATH=src;tools)"""

import argparse
import os
import socket
import sys


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="VizDOM Studio bridge (local API for the GUI)")
    parser.add_argument("--port", type=int, default=0, help="0 = pick a free port")
    parser.add_argument("--token", default=os.environ.get("VIZDOM_BRIDGE_TOKEN", ""),
                        help="shared secret every request must carry (empty = no check, dev only)")
    parser.add_argument("--config", default=None, help="session config JSON (default: vizdom.config.json if present)")
    args = parser.parse_args()

    import uvicorn
    from .server import create_app

    port = args.port or _free_port()
    app = create_app(token=args.token, config_path=args.config)
    # The GUI waits for this exact line before it talks to the bridge.
    print(f"VIZDOM_BRIDGE_READY port={port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
