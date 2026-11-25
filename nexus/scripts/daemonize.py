"""Daemonize a command: double-fork + setsid + redirect to a log file.

Usage: python scripts/daemonize.py <logfile> <pidfile> -- <command...>

The grandchild is reparented away from the launching shell and survives after
the shell command returns.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    try:
        sep = sys.argv.index("--")
    except ValueError:
        print("usage: daemonize.py <logfile> <pidfile> -- <command...>", file=sys.stderr)
        return 2
    logfile, pidfile = sys.argv[1], sys.argv[2]
    command = sys.argv[sep + 1 :]
    if not command:
        print("no command given", file=sys.stderr)
        return 2

    first = os.fork()
    if first > 0:
        print(f"spawned pid {first}")
        return 0

    os.setsid()

    second = os.fork()
    if second > 0:
        os._exit(0)

    os.chdir(os.environ.get("NEXUS_WORKDIR", os.getcwd()))
    log = open(logfile, "ab", buffering=0)
    devnull = open(os.devnull, "rb")
    os.dup2(devnull.fileno(), 0)
    os.dup2(log.fileno(), 1)
    os.dup2(log.fileno(), 2)

    if pidfile:
        with open(pidfile, "w") as fh:
            fh.write(str(os.getpid()))

    os.execvp(command[0], command)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
