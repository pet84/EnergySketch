# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Internal distribution entry point, with an explicit offline QA command."""
import sys

if __name__ == "__main__":
    if any(flag in sys.argv for flag in ("--archenergy-check", "--archenergy-render")):
        from plugins.archcontrol.diagnostics import main
    else:
        from main import main
    raise SystemExit(main())
