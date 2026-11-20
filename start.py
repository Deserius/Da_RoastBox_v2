#!/usr/bin/env python3
"""Check prepared/missing dependencies, start local servers, open default browser.

On a Windows PC without Python, double-click thelaunch.bat instead. It uses the
packaged interpreter or the verified bootstrap; a .py file cannot execute itself.
"""
from __future__ import annotations
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if "--start" not in args:
        args.insert(0, "--start")
    specification = importlib.util.spec_from_file_location("roastbox_start_installer", ROOT / "install.py")
    installer = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(installer)
    try:
        installer.main(args)
        return 0
    except installer.AlreadyRunning as exc:
        print(str(exc), flush=True)
        return 0
    except KeyboardInterrupt:
        print("\nWeb session stopped. MongoDB and saved data remain intact.", flush=True)
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        if installer.is_space_error(exc) and not isinstance(exc, installer.DiskSpaceError):
            exc = installer.DiskSpaceError(installer.space_message(ROOT, "local startup"))
        print(f"\nStartup stopped: {exc}\nSee START_HERE.txt. No existing configuration or data was deleted.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
