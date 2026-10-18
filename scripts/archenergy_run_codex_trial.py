# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Run authenticated Codex against an already started private demo host.

The user-authorized trial uses the existing ChatGPT login, never reads tokens,
does not alter user config, and enables only this demo's MCP server.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    out = args.directory.resolve()
    ready = json.loads((out / "ready.json").read_text(encoding="utf-8"))
    root = Path(__file__).resolve().parents[1]
    codex = shutil.which("codex")
    if not codex:
        parser.error("Codex CLI was not found")
    env = dict(os.environ)
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(key, None)
    login = subprocess.run([codex, "login", "status"], env=env,
                           capture_output=True, text=True, timeout=30)
    status = (login.stdout+login.stderr).strip()
    if login.returncode or "ChatGPT" not in status:
        parser.error("This trial requires an existing ChatGPT login in Codex")
    # Respect the user's selected model; auth credentials are never opened.
    import tomllib
    home = Path(env.get("CODEX_HOME", str(Path.home()/".codex")))
    config = tomllib.loads((home/"config.toml").read_text(encoding="utf-8"))
    model = config.get("model")
    overrides = {
        "approval_policy": "never",
        "mcp_servers.energysketch.command": sys.executable,
        "mcp_servers.energysketch.args": [str(root/"scripts/ingetrazo_mcp.py")],
        "mcp_servers.energysketch.env.INGETRAZO_AI_PORT": str(ready["port"]),
        "mcp_servers.energysketch.tool_timeout_sec": 120,
        "mcp_servers.energysketch.startup_timeout_sec": 30,
        "mcp_servers.energysketch.default_tools_approval_mode": "approve",
    }
    if model:
        overrides["model"] = model
    prompt = (
        "Jsi připojen přes MCP energysketch k výhradně testovacímu prázdnému "
        "dokumentu EnergySketch. Pracuj jen s jeho MCP nástroji, nepoužívej "
        "shell ani jiné aplikace a nečti soubory. Chci skutečně vyzkoušet "
        "nativní modelovací kuchařku. Postav dům 8 × 6 metrů, výška stěn "
        "3 m, tloušťka 0,25 m, se sedlovou střechou sklonu 30°, hřeben "
        "podél X a přesahem 0,4 m. Vlož dveře na jih a celkem čtyři okna "
        "(dvě na západní straně, po jednom na jih a východ), parapet 0,9 m, "
        "okna 1,2 × 1,3 m, dveře 0,9 × 2,1 m. Jejich vhodné odstupy zvol sám "
        "bez kolize s rohy a s dveřmi. Sever tohoto nového dokumentu je +Y. "
        "Nejprve query_model; podle dodané kuchařky použij nativní house, "
        "nevytvářej vlastní náhradu modelovacího jádra. Dům vytvoř jedním "
        "vratným krokem, skupiny pojmenuj česky, přibliž model a ověř screenshot "
        "i skutečný počet oken a skupin. Nic dalšího nestav. Neukládej soubory "
        "(host to provede po testu). Krátce česky popiš výsledek a omezení. "
        "Čas provedení vezmi z execution_seconds, nevydávej jej za čas celého "
        "uvažování. Pokud se cokoli nepodaří, přiznej to."
    )
    (out/"prompt.txt").write_text(prompt, encoding="utf-8")
    command = [codex, "exec", "--ignore-user-config", "--ignore-rules",
               "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check",
               "--cd", str(root), "--json", "--output-last-message",
               str(out/"codex-final.txt")]
    for key, value in overrides.items():
        command += ["-c", key+"="+json.dumps(value, ensure_ascii=False)]
    command += ["-"]
    started = time.perf_counter()
    report = {"login_status": status, "model": model,
              "mcp_transport": "stdio to private loopback TCP",
              "private_port": ready["port"], "api_key_environment_removed": True}
    try:
        with (out/"codex-events.jsonl").open("w", encoding="utf-8") as stdout, \
                (out/"codex-stderr.txt").open("w", encoding="utf-8") as stderr:
            result = subprocess.run(command, input=prompt, text=True, encoding="utf-8",
                                    env=env, stdout=stdout, stderr=stderr, timeout=600)
        report["codex_exit"] = result.returncode
    except subprocess.TimeoutExpired:
        report["error"] = "Codex exceeded the 600 second trial limit"
    finally:
        report["codex_wall_seconds"] = round(time.perf_counter()-started, 3)
        (out/"trial-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (out/"finish.request").touch()
    print(json.dumps(report, ensure_ascii=False))
    return report.get("codex_exit", 1)


if __name__ == "__main__":
    raise SystemExit(main())
