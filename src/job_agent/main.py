'Development entry item; the Mac app starts the same service without a terminal.'
import argparse
import os
from pathlib import Path
import sys


def default_workspace():
    if sys.platform == 'darwin':
        return Path.home()/'Library/Application Support/Candidatures'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'candidatures'


def main():
    parser = argparse.ArgumentParser(description='Open Vitae local app service')
    parser.add_argument('--workspace', type=Path, default=default_workspace())
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    args.workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.environ['JOB_AGENT_ROOT'] = str(args.workspace.resolve())
    import uvicorn
    uvicorn.run('job_agent.app:app', host='127.0.0.1', port=args.port, access_log=False)


if __name__ == '__main__':
    main()
