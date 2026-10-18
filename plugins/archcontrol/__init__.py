# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Native ArchControl for EnergySketch; see ARCHENERGY.md for verified scope."""


def setup(app):
    from .adapter import setup_extension
    setup_extension(app)
