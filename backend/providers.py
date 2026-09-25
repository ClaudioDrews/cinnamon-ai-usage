"""Read-only provider adapters. No inference, token refresh or billing mutations."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shlex
import shutil
import ssl
import subprocess
import time
from datetime import datetime, timezone
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError, URLError

SERVICES = {
    "codex": "Codex", "antigravity": "Antigravity", "grok": "Grok / xAI",
    "nous": "Nous Portal", "opencode": "OpenCode Go", "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
}


class Unavailable(Exception):
    def __init__(self, message, status="unavailable"):
        super().__init__(message)
        self.status = status


def number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def stamp(value=None):
    if value is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    try:
        if isinstance(value, str) and not value.isdigit():
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return None
        else:
            n = float(value)
            if n > 1e12:
                n /= 1000
            dt = datetime.fromtimestamp(n, timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def text(value, default="", limit=100):
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(value or default))[:limit]


def metric(id_, label, kind, *, percent=None, value=None, currency=None, window=None, reset=None):
    p = number(percent)
    return {"id": id_, "label": text(label), "kind": kind,
            "used_percent": max(0, min(100, p)) if p is not None else None,
            "value": number(value), "currency": currency,
            "window_seconds": window, "reset_at": stamp(reset) if reset else None}


def service(id_, status="ok", message="", source="", metrics=None, identity=None):
    result = {"id": id_, "label": SERVICES[id_], "status": status, "message": message,
              "source": source, "read_at": stamp() if status == "ok" else None,
              "last_used_at": None, "recency_basis": "unknown", "metrics": metrics or []}
    if identity:
        # Private cache baseline discriminator; the identifier itself is never persisted.
        result["_identity"] = hashlib.sha256(str(identity).encode()).hexdigest()
    return result


def read_json(path):
    try:
        with Path(path).open() as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def credentials(names):
    result = {k: os.environ[k] for k in names if os.environ.get(k)}
    path = Path.home() / ".config/agentes/credenciais.env"
    try:
        for line in path.read_text().splitlines():
            match = re.match(r"^\s*([A-Z][A-Z0-9_]*)=(.*)$", line)
            if not match or match[1] not in names or match[1] in result:
                continue
            parts = shlex.split(match[2], comments=True, posix=True)
            if len(parts) == 1:
                result[match[1]] = parts[0]
    except (OSError, ValueError):
        pass
    return result


def require_key(name):
    key = credentials([name]).get(name)
    if not key:
        raise Unavailable("Credencial não configurada.", "unconfigured")
    return key


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Unavailable("Redirecionamento inesperado; consulta interrompida.", "error")


def request(url, token=None, data=None, headers=None, local=False, timeout=8):
    # Caller URLs are fixed trusted endpoints; never follow redirects with credentials.
    h = {"Accept": "application/json", "User-Agent": "cinnamon-ai-usage/0.1.0"}
    if token:
        h["Authorization"] = "Bearer " + token
    h.update(headers or {})
    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        h["Content-Type"] = "application/json"
    handlers = [NoRedirect()]
    if local:
        if not re.match(r"^https?://127\.0\.0\.1:[0-9]+/", url):
            raise ValueError("Loopback only")
        handlers += [ProxyHandler({}), HTTPSHandler(context=ssl._create_unverified_context())]
    try:
        with build_opener(*handlers).open(Request(url, data=body, headers=h), timeout=timeout) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise Unavailable("Resposta maior que o limite permitido.", "error")
            return json.loads(raw)
    except HTTPError as e:
        messages = {401: "Login expirado ou credencial recusada.",
                    403: "Acesso à consulta recusado (HTTP 403).",
                    404: "Fonte de uso não encontrada (HTTP 404).",
                    429: "Limite de consultas; aguarde a próxima atualização."}
        raise Unavailable(messages.get(e.code, f"Falha na consulta (HTTP {e.code})."), "error") from None
    except (URLError, TimeoutError, OSError):
        raise Unavailable("Não foi possível consultar o serviço; verifique a conexão.", "error") from None
    except (ValueError, TypeError):
        raise Unavailable("Formato de resposta não reconhecido.", "error") from None


def parse_codex(payload):
    buckets = payload.get("rateLimitsByLimitId")
    if not isinstance(buckets, dict) or not buckets:
        buckets = {"codex": payload.get("rateLimits", {})}
    out = []
    for bucket_id, bucket in buckets.items():
        if not isinstance(bucket, dict):
            continue
        for key in ("primary", "secondary"):
            part = bucket.get(key)
            if not isinstance(part, dict) or number(part.get("usedPercent")) is None:
                continue
            minutes = number(part.get("windowDurationMins"))
            window = int(minutes * 60) if minutes and minutes > 0 else None
            label = f"Janela de {minutes / 60:g} h" if minutes else "Cota"
            if len(buckets) > 1:
                label = f"{text(bucket.get('limitName') or bucket_id)} · {label}"
            out.append(metric(f"{bucket_id}:{key}", label, "quota", percent=part["usedPercent"],
                              window=window, reset=part.get("resetsAt")))
    return out


def codex():
    executable = shutil.which("codex")
    if not executable:
        raise Unavailable("Codex CLI não encontrado.", "unconfigured")
    auth = read_json(Path(os.environ.get("CODEX_HOME", str(Path.home()/'.codex'))) / "auth.json")
    identity = (auth.get("tokens") or {}).get("account_id") or "codex-local"
    p = subprocess.Popen([executable, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL)
    selector = selectors.DefaultSelector()
    selector.register(p.stdout, selectors.EVENT_READ)
    buffer = b""
    deadline = time.monotonic() + 20

    def send(obj):
        p.stdin.write((json.dumps(obj) + "\n").encode()); p.stdin.flush()

    def receive(id_):
        nonlocal buffer
        while time.monotonic() < deadline:
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("id") == id_:
                    if "error" in obj:
                        raise Unavailable("Codex não disponibilizou cotas; confira o login do CLI.", "error")
                    return obj.get("result", {})
            if not selector.select(max(0, deadline-time.monotonic())):
                break
            chunk = os.read(p.stdout.fileno(), 65536)
            if not chunk:
                break
            buffer += chunk
            if len(buffer) > 2_000_000:
                break
        raise Unavailable("Tempo limite na consulta ao Codex.", "error")

    try:
        send({"id": 1, "method": "initialize", "params": {
            "clientInfo": {"name": "cinnamon-ai-usage", "version": "0.1.0"}}})
        receive(1)
        send({"method": "initialized"})
        send({"id": 2, "method": "account/rateLimits/read"})
        metrics = parse_codex(receive(2))
    finally:
        selector.close()
        p.terminate()
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            p.kill(); p.wait()
        p.stdin.close(); p.stdout.close()
    if not metrics:
        raise Unavailable("Login atual não retornou cotas do Codex.")
    return service("codex", source="Codex app-server", metrics=metrics, identity=identity)


def parse_openrouter(payload):
    d = payload.get("data", {})
    out = []
    limit, remaining = number(d.get("limit")), number(d.get("limit_remaining"))
    if limit is not None and limit > 0 and remaining is not None:
        label = "Limite da chave" + (f" ({text(d['limit_reset'])})" if d.get("limit_reset") else "")
        out.append(metric("limit", label, "quota", percent=100*(limit-remaining)/limit))
    for k, label in [("usage_monthly", "Gasto no mês"), ("usage", "Gasto acumulado da chave")]:
        if number(d.get(k)) is not None:
            out.append(metric(k, label, "spend", value=d[k], currency="USD"))
    return out


def openrouter():
    key = require_key("OPENROUTER_API_KEY")
    return service("openrouter", source="OpenRouter · chave", identity=key,
                   metrics=parse_openrouter(request("https://openrouter.ai/api/v1/key", key)))


def parse_deepseek(payload):
    return [metric("balance:"+str(d.get("currency")), "Saldo disponível", "balance",
                   value=d["total_balance"], currency=d.get("currency"))
            for d in payload.get("balance_infos", []) if number(d.get("total_balance")) is not None
            and d.get("currency") in ("USD", "CNY")]


def deepseek():
    key = require_key("DEEPSEEK_API_KEY")
    return service("deepseek", source="DeepSeek · saldo", identity=key,
                   metrics=parse_deepseek(request("https://api.deepseek.com/user/balance", key)))


def parse_nous(payload):
    access = payload.get("paid_service_access") or {}
    out = []
    for key, label in [("total_usable_credits", "Saldo total disponível"),
                       ("subscription_credits_remaining", "Saldo do plano"),
                       ("purchased_credits_remaining", "Saldo de recargas")]:
        if number(access.get(key)) is not None:
            out.append(metric(key, label, "balance", value=access[key], currency="USD"))
    sub = payload.get("subscription") or {}
    if sub.get("current_period_end"):
        for m in out:
            if m["id"] == "subscription_credits_remaining":
                m["reset_at"] = stamp(sub["current_period_end"])
    # Rollover/topups complicate the denominator: don't infer percent from monthly allowance.
    return out


def nous():
    auth = read_json(Path.home()/".hermes/auth.json")
    state = (auth.get("providers") or {}).get("nous") or {}
    token = state.get("access_token")
    if not token:
        raise Unavailable("Login Nous do Hermes não encontrado.", "unconfigured")
    payload = request("https://portal.nousresearch.com/api/oauth/account", token)
    return service("nous", source="Nous Portal · OAuth do Hermes", metrics=parse_nous(payload),
                   identity=(payload.get("organisation") or {}).get("id"))


def parse_go(payload):
    out = []
    # Observed read-only endpoint, 2026-09-25; no undocumented fields guessed as zeros.
    usage = payload.get("usage") or {}
    for key, label, seconds in [("rolling", "Janela móvel", None), ("weekly", "Semana", 604800),
                                ("monthly", "Mês", None)]:
        part = usage.get(key)
        if not isinstance(part, dict):
            continue
        pct = number(part.get("percent"))
        if pct is not None:
            out.append(metric(key, label, "quota", percent=pct, window=seconds, reset=part.get("resetsAt")))
    return out


def opencode():
    key = credentials(["OPENCODE_GO_API_KEY", "OPENCODE_API_KEY"])
    token = key.get("OPENCODE_GO_API_KEY") or key.get("OPENCODE_API_KEY")
    if not token:
        raise Unavailable("Chave OpenCode Go não configurada.", "unconfigured")
    payload = request("https://opencode.ai/zen/go/v1/usage", token)
    metrics = parse_go(payload)
    if not metrics:
        raise Unavailable("Resposta Go sem cotas reconhecidas; conector experimental.")
    return service("opencode", source="OpenCode Go · uso (experimental)", metrics=metrics, identity=token)


def grok(config):
    key = require_key("XAI_MANAGEMENT_API_KEY")
    team = (config.get("grok") or {}).get("team_id", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", str(team)):
        raise Unavailable("Informe grok.team_id na configuração para consultar a API xAI.", "unconfigured")
    payload = request(f"https://management-api.x.ai/v1/billing/teams/{team}/prepaid/balance", key)
    total = number((payload.get("total") or {}).get("val"))
    if total is None:
        raise Unavailable("Saldo xAI não reconhecido.")
    return service("grok", source="xAI Management API · não inclui assinatura Grok", identity=team,
                   metrics=[metric("balance", "Saldo pré-pago da API", "balance", value=total/100, currency="USD")])


def parse_antigravity(payload):
    user = payload.get("userStatus") or payload
    configs = (user.get("cascadeModelConfigData") or {}).get("clientModelConfigs", [])
    out = []
    for i, config in enumerate(configs):
        quota = config.get("quotaInfo") or {}
        fraction = number(quota.get("remainingFraction"))
        if fraction is not None and 0 <= fraction <= 1:
            label = text(config.get("modelLabel"), f"Modelo {i+1}")
            out.append(metric("model:"+label, label, "quota", percent=(1-fraction)*100,
                              reset=quota.get("resetTime")))
    if out:
        return out
    plan = user.get("planStatus") or {}
    info = plan.get("planInfo") or {}
    for key, label in [("Prompt", "Créditos de prompts"), ("Flow", "Créditos de fluxo")]:
        total, remaining = number(info.get(f"monthly{key}Credits")), number(plan.get(f"available{key}Credits"))
        if total and total > 0 and remaining is not None:
            out.append(metric(key, label, "quota", percent=100*(1-remaining/total)))
    return out


def antigravity():
    # Read only this user's process arguments in memory; never print CSRF tokens.
    candidate = None
    for directory in Path("/proc").glob("[0-9]*"):
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            args = directory.joinpath("cmdline").read_bytes().decode(errors="replace").split("\0")
            if not args or "language_server" not in args[0] or "antigravity" not in " ".join(args).lower():
                continue
            opts = {}
            for i, arg in enumerate(args):
                if arg.startswith("--"):
                    k, sep, val = arg.partition("=")
                    opts[k] = val if sep else (args[i+1] if i+1 < len(args) else "")
            if opts.get("--csrf_token"):
                candidate = (directory.name, opts); break
        except OSError:
            continue
    if not candidate:
        raise Unavailable("Abra o Antigravity para consultar as cotas locais.")
    pid, opts = candidate
    ports = set()
    if shutil.which("ss"):
        result = subprocess.run(["ss", "-tlnpH"], capture_output=True, text=True, timeout=3)
        for line in result.stdout.splitlines():
            if re.search(r"pid="+pid+r"\b", line):
                parts = line.split()
                if len(parts)>3:
                    port = parts[3].rsplit(":",1)[-1]
                    if port.isdigit(): ports.add(int(port))
    if opts.get("--extension_server_port", "").isdigit():
        ports.add(int(opts["--extension_server_port"]))
    headers = {"X-Codeium-Csrf-Token": opts["--csrf_token"], "Connect-Protocol-Version": "1"}
    body = {"metadata": {"ideName": "antigravity", "extensionName": "antigravity", "locale": "pt-BR", "ideVersion": "unknown"}}
    deadline = time.monotonic()+18
    for port in sorted(ports)[:6]:
        for scheme in ("https", "http"):
            if time.monotonic() > deadline:
                break
            base = f"{scheme}://127.0.0.1:{port}/exa.language_server_pb.LanguageServerService/"
            try:
                request(base+"GetUnleashData", data={}, headers=headers, local=True, timeout=1)
            except Unavailable:
                continue
            for method in ("GetUserStatus", "GetCommandModelConfigs"):
                try:
                    metrics = parse_antigravity(request(base+method, data=body, headers=headers, local=True, timeout=3))
                    if metrics:
                        return service("antigravity", source="Antigravity · servidor local (experimental)", metrics=metrics,
                                       identity="antigravity:"+pid)
                except Unavailable:
                    continue
    raise Unavailable("Servidor local encontrado, mas não retornou cotas reconhecidas.")


def collect_provider(id_, config):
    try:
        result = grok(config) if id_ == "grok" else globals()[id_]()
        if not result["metrics"]:
            raise Unavailable("Fonte não retornou métricas de uso reconhecidas.")
        return result
    except Unavailable as e:
        return service(id_, e.status, str(e))
    except Exception:
        return service(id_, "error", "Falha ao ler dados do serviço; tente atualizar.")
