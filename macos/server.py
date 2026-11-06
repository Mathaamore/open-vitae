"""Packaged local service. The workspace stays outside the app bundle."""
import json
import os
from pathlib import Path
import socket
import sys

if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Choose a workspace to continue.')
    Path(sys.argv[1]).mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.getpgrp() != os.getpid():
        os.setsid()
    os.environ['JOB_AGENT_ROOT'] = str(Path(sys.argv[1]).resolve())
    import uvicorn
    try:
        from job_agent.app import app, assistant
    except ValueError as error:
        print(json.dumps({'error': str(error)}), flush=True)
        raise SystemExit(1) from None
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen(128)
        print(json.dumps({'port': listener.getsockname()[1]}), flush=True)
        try:
            uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', access_log=False, log_level='warning',
                                         loop='asyncio', http='h11', ws='none', timeout_graceful_shutdown=2)).run(sockets=[listener])
        finally:
            assistant.close()
