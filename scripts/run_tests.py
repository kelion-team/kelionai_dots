#!/usr/bin/env python3
"""Run pytest unchanged, reaping adopted processes in cloud containers on Linux."""
import ctypes
import os
import subprocess
import sys
import time


def main():
    if sys.platform == 'linux':
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), 'Could not enable child subreaping')
    child = subprocess.Popen(sys.argv[1:])
    if sys.platform != 'linux':
        return child.wait()
    while True:
        pid, status = os.waitpid(-1, os.WNOHANG)
        if pid == child.pid:
            child.returncode = os.waitstatus_to_exitcode(status)
            return child.returncode
        time.sleep(0.02)


if __name__ == '__main__':
    raise SystemExit(main())
