# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Pure ASTRA LIVE protocol/state machine; no Qt, files or network access."""
from __future__ import annotations
import copy
from dataclasses import dataclass, field
import json
import math
import re
import time
from urllib.parse import urlsplit
import uuid

MAX_BATCH = 6 * 1024 * 1024
MAX_ELEMENTS = 50000
REF = re.compile(r"[a-zA-Z0-9_-]{1,80}\Z")


def validate_url(value):
    value = value.strip()
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Adresa APP nesmí obsahovat mezery ani řídicí znaky.")
    try:
        uri = urlsplit(value)
        port = uri.port
    except ValueError as exc:
        raise ValueError("Neplatná adresa APP.") from exc
    if not uri.hostname or not (uri.scheme == "https" or uri.scheme == "http" and uri.hostname in ("localhost", "127.0.0.1", "::1")):
        raise ValueError("Použijte HTTPS adresu APP; HTTP je povoleno pouze na localhostu.")
    if uri.username is not None or uri.password is not None or uri.query or uri.fragment or uri.path not in ("", "/"):
        raise ValueError("Adresa musí být bez přihlášení, cesty, parametrů a fragmentu.")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Neplatný port APP.")
    return value.rstrip("/")


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def delta(previous, current):
    return {"upserts": [copy.deepcopy(v) for k,v in current.items() if previous.get(k) != v],
            "removed": [k for k in previous if k not in current]}


@dataclass(frozen=True, repr=False)
class Request:
    epoch: int
    serial: int
    url: str
    route: str
    body: bytes = field(repr=False)
    token: str | None = field(default=None, repr=False)

    def __repr__(self):
        return f"LiveRequest(epoch={self.epoch}, serial={self.serial}, route={self.route!r}, bytes={len(self.body)})"


class LiveSession:
    """One explicit connection. Credentials never enter public status or documents."""
    def __init__(self, clock=time.monotonic, uuid_factory=lambda: str(uuid.uuid4())):
        self.clock, self.uuid = clock, uuid_factory
        self.epoch = self.serial = 0
        self.disconnect()

    def disconnect(self):
        self.epoch += 1
        self._token = None
        self.base = self.model_id = self.project_id = self.connection_id = None
        self.inflight = self.pending = self.pair_payload = None
        self.incoming = self.command_result = self.command_poll_at = None
        self.command_cache = {}
        self.demo_enabled = self.model_enabled = False
        self.acked = {}
        self.generation, self.sent_generation, self.revision = 1, -1, 0
        self.initial, self.paused, self.auth_invalid, self.connecting = True, False, False, False
        self.last_response = self.heartbeat_at = self.retry_at = None
        self.connection_error = False
        self.status = "Odpojeno"
        self.stats = {"batches": 0, "bytes": 0}

    def connect(self, url, code, title, capabilities=("presence-v1",)):
        base = validate_url(url)
        if not isinstance(code, str) or not code.strip() or len(code) > 30:
            raise ValueError("Zadejte platný párovací kód z APP.")
        self.disconnect()
        self.base, self.model_id = base, self.uuid()
        self.pair_payload = {"code": code.strip(), "modelId": self.model_id,
                             "title": str(title)[:240], "capabilities": list(capabilities)}
        self.status, self.connecting = "Páruji s APP…", True

    def dirty(self):
        self.generation += 1

    def toggle_pause(self):
        self.paused = not self.paused
        self.status = "Pozastaveno" if self.paused else "Pokračuji…"
        self.heartbeat_at = None
        self.dirty()

    def presence(self, editing=False):
        if self.paused:
            return "paused"
        if editing:
            return "editing"
        return "syncing" if self.pending or self.initial or self.generation != self.sent_generation else "ready"

    def public_status(self, editing=False):
        age = None if self.last_response is None else max(0, self.clock()-self.last_response)
        online = bool(self._token and not self.auth_invalid and not self.connection_error and age is not None and age < 8)
        return {"status": self.status, "paused": self.paused, "connected": bool(self._token),
                "revision": self.revision, "stats": dict(self.stats),
                "connectionStatus": "online" if online else "connecting" if self.connecting else "offline",
                "responseAgeMs": None if age is None else round(age*1000),
                "offlineAfterMs": 8000, "presence": self.presence(editing),
                "needsPairing": self.auth_invalid}

    def _request(self, route, payload):
        body = encode(payload)
        if len(body) > MAX_BATCH:
            raise ValueError("Dávka přesahuje 6 MB. Zmenšete model pro tento přenos.")
        self.serial += 1
        self.inflight = Request(self.epoch, self.serial, self.base + "/api/penb" + route,
                                route, body, self._token)
        return self.inflight

    def next_request(self, snapshot, editing=False, execute_command=None):
        if self.inflight:
            return None
        if self.pair_payload is not None:
            payload, self.pair_payload = self.pair_payload, None
            return self._request("/live/device/pair", payload)
        if not self._token or self.auth_invalid or self.retry_at is not None and self.clock() < self.retry_at:
            return None
        if (not self.initial or self.paused or editing) and (self.heartbeat_at is None or self.clock()-self.heartbeat_at >= 2):
            return self._request(f"/live/device/{self.project_id}/heartbeat", {"presence": self.presence(editing)})
        if self.paused or editing:
            return None
        if self.command_result is not None and (self.command_result["outcome"] == "rejected" or "resultRevision" in self.command_result):
            return self._request(f"/live/device/{self.project_id}/commands/ack",self.command_result)
        if self.pending is None and self.generation != self.sent_generation:
            generation = self.generation
            current = copy.deepcopy(snapshot())
            if len(current) > MAX_ELEMENTS:
                raise ValueError("LIVE podporuje nejvýše 50 000 prvků.")
            change = delta(self.acked, current)
            if self.initial or change["upserts"] or change["removed"]:
                payload = {**change, "protocol": 1, "modelId": self.model_id,
                           "changeId": self.uuid(), "baseRevision": self.revision, "reset": self.initial}
                body = encode(payload)
                if len(body) > MAX_BATCH:
                    raise ValueError("Dávka přesahuje 6 MB. Zmenšete model pro tento přenos.")
                self.pending = {"payload": payload, "snapshot": current, "generation": generation, "bytes": len(body)}
            else:
                self.sent_generation = generation
        if self.pending is not None:
            self.status = "Synchronizuji…"
            return self._request(f"/live/device/{self.project_id}/batch", self.pending["payload"])
        if self.incoming is not None and execute_command is not None:
            self.execute_incoming(snapshot,execute_command)
        elif execute_command is not None and (self.demo_enabled or self.model_enabled) and (self.command_poll_at is None or self.clock()-self.command_poll_at>1):
            return self._request(f"/live/device/{self.project_id}/commands/next",
                                 {"modelId":self.model_id,"revision":self.revision,"presence":self.presence(editing)})
        return None

    def execute_incoming(self,snapshot,execute_command):
        from .live_commands import signature, validate_command
        command,self.incoming = self.incoming,None
        if not isinstance(command,dict) or not isinstance(command.get("id"),str):
            raise ValueError("APP doručila neplatný příkaz.")
        signed = signature(command)
        cached = self.command_cache.get(command["id"])
        if cached:
            if cached["signature"] != signed:
                raise ValueError("Opakovaný příkaz má jiný obsah. Přenos pozastaven.")
            self.command_result = copy.deepcopy(cached["result"])
            return
        result = {"commandId":command["id"],"modelId":self.model_id}
        try:
            validate_command(command,self.model_id,self.connection_id,self.revision)
            if command["action"] in ("import_model","sync_model") and not self.model_enabled:
                raise ValueError("Přenos modelu není v tomto propojení povolen.")
            if snapshot() != self.acked:
                self.dirty()
                raise ValueError("Model se změnil. Nejdříve odešlu aktuální stav; potom příkaz zopakujte.")
            captured = execute_command(copy.deepcopy(command))
            payload = {**delta(self.acked,captured),"protocol":1,"modelId":self.model_id,
                       "changeId":self.uuid(),"baseRevision":self.revision,"reset":False,"commandId":command["id"]}
            size = len(encode(payload))
            if size>MAX_BATCH:
                raise ValueError("Výsledek příkazu přesahuje 6 MB.")
            self.pending = {"payload":payload,"snapshot":copy.deepcopy(captured),
                            "generation":self.generation,"bytes":size}
            result.update(outcome="executed",message="Příkaz proveden; server ověří vrácenou geometrii.")
            self.dirty()
        except Exception as exc:
            result.update(outcome="rejected",message=str(exc)[:400])
        self.command_result = result
        self.command_cache[command["id"]] = {"signature":signed,"result":copy.deepcopy(result)}
        while len(self.command_cache)>100:
            self.command_cache.pop(next(iter(self.command_cache)))
        self.status = "Příkaz proveden; odesílám výsledek do APP." if result["outcome"] == "executed" else result["message"]

    def complete(self, request, status, body):
        if request.epoch != self.epoch or self.inflight is not request:
            return False
        self.inflight = None
        if not isinstance(body, dict):
            body = {"error": "APP nevrátila platnou odpověď JSON."}
            status = 0
        if status == 200:
            if request.route.endswith("/pair"):
                if not isinstance(body.get("token"), str) or not re.fullmatch(r"[a-f0-9]{64}", body["token"]) or not all(isinstance(body.get(k), str) and REF.fullmatch(body[k]) for k in ("projectId", "connectionId")):
                    status, body = 0, {"error": "APP nevrátila platné údaje propojení. Vytvořte nový kód."}
                else:
                    self._token, self.project_id, self.connection_id = body["token"], body["projectId"], body["connectionId"]
                    self.connecting = False
                    self.demo_enabled = body.get("demoCommands") is True
                    self.model_enabled = body.get("modelCommands") is True
                    self.status = "Připojeno. Připravuji první snímek."
            elif request.route.endswith("/batch"):
                revision = body.get("revision")
                if type(revision) is not int or revision != self.revision+1 or body.get("connectionId") != self.connection_id:
                    status, body = 409, {"error": "APP nepotvrdila očekávanou revizi a propojení. Přenos pozastaven."}
                else:
                    self.revision = revision
                    self.acked, self.sent_generation = self.pending["snapshot"], self.pending["generation"]
                    self.stats["batches"] += 1
                    self.stats["bytes"] += self.pending["bytes"]
                    if self.command_result is not None and self.pending["payload"].get("commandId") == self.command_result["commandId"]:
                        self.command_result["resultRevision"] = revision
                        self.command_cache[self.command_result["commandId"]]["result"] = copy.deepcopy(self.command_result)
                    self.pending, self.initial = None, False
                    self.heartbeat_at = self.clock()
                    self.status = f"Synchronizováno · revize {revision}"
            elif request.route.endswith("/commands/next"):
                self.command_poll_at = self.clock()
                if body.get("revision") != self.revision:
                    status = 409
                else:
                    self.incoming = copy.deepcopy(body.get("command"))
                    self.heartbeat_at = self.clock()
            elif request.route.endswith("/commands/ack"):
                self.command_result = None
                self.status = f"Synchronizováno · revize {self.revision}"
            elif body.get("connectionId") != self.connection_id or body.get("revision") != self.revision:
                status, body = 409, {"error": "Revize nebo propojení APP se změnilo. Připojte model znovu."}
            else:
                self.heartbeat_at = self.clock()
        if status == 200:
            self.last_response = self.clock()
            self.connection_error, self.retry_at = False, None
            return True
        self.connection_error = status == 0 or status >= 500 or status in (301,302,303,307,308,401,403,404)
        self.auth_invalid = status in (401,403,404)
        self.paused = self.paused or status in (301,302,303,307,308,400,401,403,404,409,413,422) or self._token is None
        self.connecting = False
        self.retry_at = self.clock()+3
        # Do not show arbitrary server messages: they may echo credentials.
        self.status = ({401:"Propojení vypršelo; vytvořte v APP nový kód.",
                        403:"APP odmítla přístup; vytvořte nové propojení.",
                        409:"Revize APP je v konfliktu. Přenos je pozastaven.",
                        413:"APP odmítla příliš velkou dávku."}.get(status,
                       "Spojení není dostupné. Čekám na obnovu." if self._token else "Párování se nezdařilo. V APP vytvořte nový kód."))
        return False
