# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Capture qs6 ordering from the installed original Ruby DLL, without a GUI.

Development oracle only. Calls the standalone ruby_qsort C entry point on
private integer pairs (same 2*VALUE element size as enum.c sort_by). Does not
initialize Ruby, open a model, load a plugin or write to the installation.
"""
import argparse
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plugins.archcontrol.legacy_sort import ruby_sort_by


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dll_path = args.dll.resolve(strict=True)
    cookie = os.add_dll_directory(str(dll_path.parent))
    library = ct.CDLL(str(dll_path))
    comparator_type = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_void_p)

    class Pair(ct.Structure):
        _fields_ = [("key", ct.c_uint64), ("index", ct.c_uint64)]

    @comparator_type
    def compare(a, b, _):
        left = ct.cast(a, ct.POINTER(Pair)).contents.key
        right = ct.cast(b, ct.POINTER(Pair)).contents.key
        return (left > right) - (left < right)

    native_sort = library.ruby_qsort
    native_sort.argtypes = [ct.c_void_p, ct.c_size_t, ct.c_size_t, comparator_type, ct.c_void_p]
    native_sort.restype = None

    def oracle(keys):
        pairs = (Pair * len(keys))(*(Pair(key, i) for i, key in enumerate(keys)))
        native_sort(pairs, len(keys), ct.sizeof(Pair), compare, None)
        return [item.index for item in pairs]

    cases = []
    lengths = [0, 1, 2, 3, 4, 10, 25, 48, 59, 60, 63, 64, 100, 199, 200, 300, 1000]
    for count in lengths:
        for mode in range(4):
            state = 721
            keys = []
            for i in range(count):
                state = (state * 1664525 + 1013904223) & 0xffffffff
                keys.append(3 if mode == 0 else i // 4 if mode == 1
                            else (count - i) // 4 if mode == 2 else state % 9)
            expected = oracle(keys)
            actual = ruby_sort_by(range(count), key=lambda i: ("Layer0", keys[i]))
            assert actual == expected, (count, mode, "native ordering mismatch")
            cases.append({"count": count, "mode": mode, "indices": expected})
    generator = random.Random(721)
    for count in lengths:
        for _ in range(50):
            keys = [generator.randrange(9) for _ in range(count)]
            assert ruby_sort_by(range(count), key=lambda i: keys[i]) == oracle(keys), count
    result = {"status": "pass", "source": str(dll_path),
              "source_sha256": hashlib.sha256(dll_path.read_bytes()).hexdigest(),
              "entry_point": "ruby_qsort", "pair_bytes": ct.sizeof(Pair),
              "cases": cases, "additional_random_cases": len(lengths) * 50}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    cookie.close()
    print(f"PASS: {len(cases)} native order fixtures and {len(lengths) * 50} random cases")


if __name__ == "__main__":
    main()
