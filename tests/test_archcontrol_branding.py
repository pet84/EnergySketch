# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Product labels and stable source keys across a deliberate language switch."""
from core import i18n


def test_product_branding_and_reverse_keys_in_all_shipped_languages():
    original = i18n.current_language()
    try:
        for language in i18n.available_languages():
            i18n.set_language(language)
            for source in ('About IngeTrazo','IngeTrazo document (*.igz)','Restart IngeTrazo to apply the new language.'):
                text = i18n.tr(source)
                assert 'EnergySketch' in text and 'IngeTrazo' not in text
                assert i18n.source_of(text)==source
            assert i18n.tr('https://github.com/ingelibre/ingetrazo')=='https://github.com/ingelibre/ingetrazo'
    finally:
        i18n.set_language(original)


def test_frozen_mcp_command_uses_the_distribution_name():
    from plugins.ai_bridge import mcp_command
    assert mcp_command('win32',frozen=True,executable=r'C:\EnergySketch\EnergySketch.exe',env={})==[r'C:\EnergySketch\EnergySketch-mcp.exe']
