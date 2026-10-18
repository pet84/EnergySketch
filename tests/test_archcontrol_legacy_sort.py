# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Equal-key order captured from the original installed Ruby 2.2 DLL."""
import json
from pathlib import Path

import pytest

from plugins.archcontrol.legacy_sort import ruby_sort_by

ORACLE = json.loads((Path(__file__).parent / "data" / "archcontrol_ruby_sort.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", ORACLE["cases"], ids=lambda c: f"n{c['count']}-mode{c['mode']}")
def test_ties_match_native_runtime_and_input_is_unchanged(case):
    count, mode = case["count"], case["mode"]
    state, keys = 721, []
    for i in range(count):
        state = (state * 1664525 + 1013904223) & 0xffffffff
        keys.append(("Layer0", 3 if mode == 0 else i // 4 if mode == 1
                     else (count - i) // 4 if mode == 2 else state % 9))
    original = list(range(count))
    calls = []

    def key(i):
        calls.append(i)
        return keys[i]

    result = ruby_sort_by(original, key=key)
    assert result == case["indices"]
    assert original == list(range(count))
    assert calls == original  # evaluate each user key only once, in source order
    assert [keys[i] for i in result] == sorted(keys)
