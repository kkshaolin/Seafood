"""Return success when the requested ARQ worker process is running."""

import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        return 2

    worker_settings = sys.argv[1].encode()
    current_pid = os.getpid()
    for command_line in Path("/proc").glob("[0-9]*/cmdline"):
        if int(command_line.parent.name) == current_pid:
            continue
        try:
            command = command_line.read_bytes()
        except OSError:
            continue
        if b"arq" in command and worker_settings in command:
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
