"""Read-only provider adapters. No inference, token refresh or billing mutations."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import ssl
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler
from urllib.error import HTTPError, URLError

import credentials

SERVICES = {
    "codex": "Codex", "claude": "Claude Code", "antigravity": "Antigravity",
    "grok": "Grok / xAI", "nous": "Nous Portal", "opencode": "OpenCode Go",
    "deepseek": "DeepSeek", "openrouter": "OpenRouter", "meta": "Meta AI (Muse Code)",
}

# A assinatura do Claude Code é lida por uma rota de leitura (GET /api/oauth/usage), a mesma
# que a própria CLI usa no comando /usage. Nada aqui é inferência: o rascunho que pedia uma
# resposta em /v1/messages apenas para raspar cabeçalhos de limite consumiria a cota que o
# applet exibe, e por isso foi recusado. A rota não é documentada pela Anthropic, então o
# conector impõe intervalo mínimo próprio e degrada em vez de adivinhar.
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_BETA = "oauth-2025-04-20"
CLAUDE_MIN_INTERVAL = 300

# A assinatura da Meta só é legível pela chamada que emite credencial do Muse Code; ela é
# idempotente (verificado em 26/09/2026: mesma api_key devolvida e auth.json intacto), mas
# não há documentação de limite de uso, então o conector impõe intervalo mínimo próprio.
META_KEY_URL = "https://api.meta.ai/muse-code/key"
META_MIN_INTERVAL = 900


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
                # Antes a data sem fuso era descartada em silêncio e o campo desaparecia sem
                # rastro. A convenção do projeto é UTC em tudo que sai daqui, então a data sem
                # fuso é lida como UTC — regra declarada no contrato, não adivinhação.
                dt = dt.replace(tzinfo=timezone.utc)
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


def require_key(name, config=None):
    """Valor da variável pelo cofre, arquivo indicado ou ambiente."""
    value = credentials.resolve([name], config).get(name)
    if not value:
        raise Unavailable("Credencial não configurada.", "unconfigured")
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Unavailable("Redirecionamento inesperado; consulta interrompida.", "error")


VERSION = "0.2.0"  # mesma versão de applet/metadata.json (o teste confere)


def request(url, token=None, data=None, headers=None, local=False, timeout=8):
    # Caller URLs are fixed trusted endpoints; never follow redirects with credentials.
    h = {"Accept": "application/json", "User-Agent": f"cinnamon-ai-usage/{VERSION}"}
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


def codex(config=None):
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
            "clientInfo": {"name": "cinnamon-ai-usage", "version": VERSION}}})
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


def openrouter(config=None):
    key = require_key("OPENROUTER_API_KEY", config)
    return service("openrouter", source="OpenRouter · chave", identity=key,
                   metrics=parse_openrouter(request("https://openrouter.ai/api/v1/key", key)))


def parse_deepseek(payload):
    return [metric("balance:"+str(d.get("currency")), "Saldo disponível", "balance",
                   value=d["total_balance"], currency=d.get("currency"))
            for d in payload.get("balance_infos", []) if number(d.get("total_balance")) is not None
            and d.get("currency") in ("USD", "CNY")]


def deepseek(config=None):
    key = require_key("DEEPSEEK_API_KEY", config)
    return service("deepseek", source="DeepSeek · saldo", identity=key,
                   metrics=parse_deepseek(request("https://api.deepseek.com/user/balance", key)))


def parse_nous(payload):
    """Saldos do Nous. Rollover e recarga impedem inferir percentual mensal."""
    access = payload.get("paid_service_access") or {}
    total = number(access.get("total_usable_credits"))
    plan_balance = number(access.get("subscription_credits_remaining"))
    purchased = number(access.get("purchased_credits_remaining"))
    out = []
    if total is not None:
        out.append(metric("total_usable_credits", "Saldo total disponível", "balance",
                          value=total, currency="USD"))
    # Saldo do plano igual ao total é a mesma informação: uma linha só.
    if plan_balance is not None and (total is None or plan_balance != total):
        out.append(metric("subscription_credits_remaining", "Saldo do plano", "balance",
                          value=plan_balance, currency="USD"))
    if purchased:
        out.append(metric("purchased_credits_remaining", "Saldo de recargas", "balance",
                          value=purchased, currency="USD"))
    period_end = (payload.get("subscription") or {}).get("current_period_end")
    if period_end:
        for item in out:
            if item["id"] in ("total_usable_credits", "subscription_credits_remaining"):
                item["reset_at"] = stamp(period_end)
    return out


def nous(config=None):
    token = credentials.service_value("nous", config) or credentials.oauth_token("nous", config)
    if not token:
        raise Unavailable("Token do Nous Portal não configurado.", "unconfigured")
    payload = request("https://portal.nousresearch.com/api/oauth/account", token)
    return service("nous", source="Nous Portal · token OAuth", metrics=parse_nous(payload),
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


def opencode(config=None):
    token = credentials.service_value("opencode", config)
    if not token:
        raise Unavailable("Chave OpenCode Go não configurada.", "unconfigured")
    payload = request("https://opencode.ai/zen/go/v1/usage", token)
    metrics = parse_go(payload)
    if not metrics:
        raise Unavailable("Resposta Go sem cotas reconhecidas; conector experimental.")
    return service("opencode", source="OpenCode Go · uso (experimental)", metrics=metrics, identity=token)


def parse_grok(payload):
    """Saldo pré-pago e, quando já houve consumo, quanto do crédito foi usado.

    ``total.val`` vem com o sinal invertido: recarga entra como valor negativo no razão e o total
    é a soma das mudanças, de modo que o crédito disponível é o módulo desse total (conferido em
    resposta real: recarga negativa, total negativo, mesmo valor absoluto). O denominador do percentual
    são os créditos concedidos — a soma das recargas — porque a chave não traz teto próprio; a
    métrica só aparece quando existe consumo, para não encher o menu de barra em zero.
    """
    total = number((payload.get("total") or {}).get("val"))
    if total is None:
        raise Unavailable("Saldo xAI não reconhecido.")
    concedidos = usados = 0.0
    for mudanca in payload.get("changes") or []:
        valor = number((mudanca.get("amount") or {}).get("val"))
        if valor is None:
            continue
        concedidos += -valor if valor < 0 else 0.0
        usados += valor if valor > 0 else 0.0
    metrics = [metric("balance", "Saldo pré-pago da API", "balance",
                      value=-total / 100, currency="USD")]
    if concedidos > 0 and usados > 0:
        metrics.append(metric("credits_used", "Créditos pré-pagos usados", "quota",
                              percent=100 * usados / concedidos,
                              value=usados / 100, currency="USD"))
    return metrics


def grok(config):
    key = credentials.service_value("grok", config)
    if not key:
        raise Unavailable("Chave de gerenciamento da xAI não configurada.", "unconfigured")
    team = (config.get("grok") or {}).get("team_id") or credentials.setting_value("grok", config) or ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", str(team)):
        raise Unavailable("Informe grok.team_id na configuração ou XAI_TEAM_ID junto das "
                          "credenciais para consultar a API xAI.", "unconfigured")
    payload = request(f"https://management-api.x.ai/v1/billing/teams/{team}/prepaid/balance", key)
    return service("grok", source="xAI Management API · não inclui assinatura Grok",
                   message="A xAI registra recargas como valor negativo em total.val; o saldo "
                           "exibido é o crédito disponível.",
                   identity=team, metrics=parse_grok(payload))


def parse_antigravity(payload):
    """Cotas do Antigravity: créditos do plano primeiro, depois fração por modelo.

    Os modelos vêm em ``clientModelConfigs`` com o nome em ``label``; só entram os que
    informam ``remainingFraction`` (a família Gemini do plano Pro informa apenas resetTime,
    e ausência de fração não vira zero).
    """
    user = payload.get("userStatus") or payload
    out = []
    plan = user.get("planStatus") or {}
    info = plan.get("planInfo") or {}
    for key, label in (("Prompt", "Créditos de prompts"), ("Flow", "Créditos de fluxo")):
        total = number(info.get(f"monthly{key}Credits"))
        remaining = number(plan.get(f"available{key}Credits"))
        if total and total > 0 and remaining is not None:
            out.append(metric(key.lower(), label, "quota", percent=100 * (1 - remaining / total)))
    configs = (user.get("cascadeModelConfigData") or {}).get("clientModelConfigs") or []
    for index, config in enumerate(configs):
        quota = config.get("quotaInfo") or {}
        fraction = number(quota.get("remainingFraction"))
        if fraction is None or not 0 <= fraction <= 1:
            continue
        name = (config.get("label") or config.get("modelLabel")
                or (config.get("modelOrAlias") or {}).get("model"))
        label = text(name, f"Modelo {index + 1}")
        out.append(metric("model:" + label, label, "quota", percent=(1 - fraction) * 100,
                          reset=quota.get("resetTime")))
    return out


def antigravity(config=None):
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


def meta_login_path(config=None):
    """Arquivo de login do Muse Code, na mesma ordem que o próprio cliente usa.

    O cliente resolve ``$MUSE_AUTH_PATH`` e, sem ele, ``$XDG_CONFIG_HOME/muse/auth.json`` ou
    ``$HOME/.config/muse/auth.json`` (regra lida no script do launcher dentro do binário).
    ``token_files.meta`` na configuração tem precedência sobre tudo.
    """
    declared = ((config or {}).get("token_files") or {}).get("meta")
    if declared:
        return Path(os.path.expanduser(str(declared)))
    if os.environ.get("MUSE_AUTH_PATH"):
        return Path(os.path.expanduser(os.environ["MUSE_AUTH_PATH"]))
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home()/".config")
    return Path(base)/"muse"/"auth.json"


def meta_interval(config=None):
    """Intervalo mínimo entre chamadas de assinatura, em segundos (300 s a 24 h)."""
    value = number(((config or {}).get("meta") or {}).get("min_interval_seconds"))
    return max(300, min(86400, value)) if value else META_MIN_INTERVAL


def quota_cache_path(name):
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home()/".cache")
    return Path(cache)/"cinnamon-ai-usage"/f"{name}.json"


def quota_read_cache(name, interval, identity):
    """Leitura anterior do serviço, se for da mesma conta e ainda válida."""
    data = read_json(quota_cache_path(name))
    if not isinstance(data, dict) or data.get("identity") != identity:
        return None
    metrics, read_at = data.get("metrics"), data.get("read_at")
    if not isinstance(metrics, list) or not metrics or not isinstance(read_at, str):
        return None
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(read_at.replace("Z", "+00:00")))
    except ValueError:
        return None
    if age.total_seconds() < interval:
        return read_at, metrics
    return None


def quota_write_cache(name, identity, read_at, metrics):
    """Guarda a última leitura em arquivo privado; só o digest da conta, nunca o token."""
    path = quota_cache_path(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        fd, temp = tempfile.mkstemp(prefix=f".{name}-", dir=path.parent)
        with os.fdopen(fd, "w") as f:
            json.dump({"read_at": read_at, "identity": identity, "metrics": metrics}, f)
            f.flush(); os.fsync(f.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    except OSError:
        pass


def meta_cache_path():
    return quota_cache_path("meta")


def meta_read_cache(config, identity):
    return quota_read_cache("meta", meta_interval(config), identity)


def meta_write_cache(identity, read_at, metrics):
    quota_write_cache("meta", identity, read_at, metrics)


def parse_meta(payload):
    """As duas janelas da assinatura Muse Code.

    ``subs_usage.window`` traz ``used_percent`` inteiro, ``window_duration_mins`` e
    ``resets_at`` em epoch; ``weekly`` traz ``used_percent`` e ``resets_at``. A Meta avisa que
    o percentual pode passar de 100: a barra vai até 100 e a nota do serviço informa o valor
    relatado. Percentual ausente não vira zero, e nada aqui é teto de cobrança por uso — é a
    assinatura do aplicativo.
    """
    usage = payload.get("subs_usage") or {}
    out = []
    window = usage.get("window") or {}
    percent = number(window.get("used_percent"))
    if percent is not None:
        minutes = number(window.get("window_duration_mins"))
        out.append(metric("janela", f"Janela de {minutes/60:g} h" if minutes else "Janela atual",
                          "quota", percent=percent,
                          window=int(minutes*60) if minutes and minutes > 0 else None,
                          reset=window.get("resets_at")))
    weekly = usage.get("weekly") or {}
    percent = number(weekly.get("used_percent"))
    if percent is not None:
        out.append(metric("semanal", "Semana", "quota", percent=percent, window=604800,
                          reset=weekly.get("resets_at")))
    return out


def meta_message(payload):
    """Nota pública do serviço: plano, aviso de percentual acima de 100% e origem do dado."""
    usage = payload.get("subs_usage") or {}
    partes = ["Assinatura do aplicativo; não é a cobrança por uso da API."]
    plano = text(payload.get("subs_tier_name"), "")
    if plano:
        partes.append(f"Plano: {plano}.")
    relatado = [number((usage.get(k) or {}).get("used_percent")) for k in ("window", "weekly")]
    acima = [p for p in relatado if p is not None and p > 100]
    if acima:
        partes.append(f"A Meta relatou {max(acima):g}% de uso; a barra do applet vai até 100%.")
    return " ".join(partes)


def meta(config=None):
    config = config or {}
    path = meta_login_path(config)
    token = credentials.oauth_token("meta", {"token_files": {"meta": str(path)}})
    if not token:
        raise Unavailable("Login do Muse Code não encontrado; rode `muse login` para ler a "
                          "assinatura da Meta.", "unconfigured")
    identity = hashlib.sha256(token.encode()).hexdigest()
    source = "Muse Code · assinatura da Meta"
    cached = meta_read_cache(config, identity)
    if cached:
        read_at, metrics = cached
        result = service("meta", source=source, metrics=metrics, identity=identity,
                         message="Leitura reaproveitada; a assinatura é consultada respeitando um "
                                 "intervalo mínimo entre chamadas.")
        # Não inventar frescor: o applet passa a mostrar a leitura como antiga pelo horário real.
        result["read_at"] = read_at
        return result
    payload = request(META_KEY_URL, token, data={}, headers={"x-client-id": "tbh:tui"})
    read_at = stamp()
    metrics = parse_meta(payload)
    if metrics:
        meta_write_cache(identity, read_at, metrics)
    return service("meta", source=source, metrics=metrics, identity=identity,
                   message=meta_message(payload))


def claude_login_path(config=None):
    """Arquivo de credenciais do Claude Code, na ordem publicada pela Anthropic.

    ``token_files.claude`` na configuração tem precedência; depois ``$CLAUDE_CONFIG_DIR`` +
    ``/.credentials.json`` (usado por quem roda mais de uma conta) e por fim
    ``~/.claude/.credentials.json``. No macOS o login vive no Keychain e não é lido aqui.
    """
    declared = ((config or {}).get("token_files") or {}).get("claude")
    if declared:
        return Path(os.path.expanduser(str(declared)))
    base = os.environ.get("CLAUDE_CONFIG_DIR")
    if base:
        return Path(os.path.expanduser(base))/".credentials.json"
    return Path.home()/".claude"/".credentials.json"


def claude_interval(config=None):
    """Intervalo mínimo entre consultas de assinatura, em segundos (120 s a 24 h)."""
    value = number(((config or {}).get("claude") or {}).get("min_interval_seconds"))
    return max(120, min(86400, value)) if value else CLAUDE_MIN_INTERVAL


CLAUDE_WINDOWS = {"session": ("janela", "Janela de 5 h", 18000),
                  "weekly_all": ("semanal", "Semana", 604800),
                  "weekly_scoped": ("semanal:", "Semana: ", 604800)}


def parse_claude(payload):
    """As janelas da assinatura do Claude Code, em duas formas conhecidas.

    A resposta traz os objetos planos ``five_hour`` e ``seven_day`` (que passaram a vir nulos)
    e a lista ``limits``, em que cada entrada se descreve com ``kind``, ``percent`` e
    ``resets_at`` — a forma viva segundo os projetos que acompanham a CLI. Só entra o que vem
    com percentual numérico: entrada desconhecida é ignorada, nunca convertida em zero. O
    percentual é usado como veio, na escala 0–100 relatada pela Anthropic; a escala observada
    aparece no diagnóstico, e um valor fracionário seria sub-relatado, não inflado.
    """
    found = {}
    for key, id_, label, window in (("five_hour", "janela", "Janela de 5 h", 18000),
                                    ("seven_day", "semanal", "Semana", 604800)):
        part = payload.get(key)
        if isinstance(part, dict) and number(part.get("utilization")) is not None:
            found[id_] = metric(id_, label, "quota", percent=part["utilization"], window=window,
                                reset=part.get("resets_at"))
    for entry in payload.get("limits") or []:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "").lower()
        percent = number(entry.get("percent") if number(entry.get("percent")) is not None
                         else entry.get("utilization"))
        if not kind or percent is None or kind not in CLAUDE_WINDOWS:
            continue
        id_, label, window = CLAUDE_WINDOWS[kind]
        if kind == "weekly_scoped":
            model = text(((entry.get("scope") or {}).get("model") or {}).get("display_name"), "")
            if not model:
                continue  # janela por modelo sem nome: não inventar rótulo
            id_, label, window = f"semanal:{model}", f"Semana · {model}", 604800
        found[id_] = metric(id_, label, "quota", percent=percent, window=window,
                            reset=entry.get("resets_at"))
    return list(found.values())


def claude_message(payload, oauth):
    """Nota pública do serviço: o que é a assinatura, plano e origem não verificada."""
    partes = ["Assinatura do Claude Code; não é a cobrança por uso da API.",
              "Conector não verificado em conta real."]
    plano = text(oauth.get("subscriptionType"), "") if isinstance(oauth, dict) else ""
    tier = text(oauth.get("rateLimitTier"), "") if isinstance(oauth, dict) else ""
    if plano or tier:
        partes.append("Plano: " + " · ".join(p for p in (plano, tier) if p) + ".")
    return " ".join(partes)


def claude(config=None):
    config = config or {}
    path = claude_login_path(config)
    oauth = read_json(path).get("claudeAiOauth")
    oauth = oauth if isinstance(oauth, dict) else {}
    token = credentials.oauth_token("claude", {"token_files": {"claude": str(path)}})
    if not token:
        raise Unavailable("Login do Claude Code não encontrado; rode `claude` e faça /login.",
                          "unconfigured")
    # O token vale cerca de uma hora e é a própria CLI que o renova; o applet nunca renova
    # credencial, então um token vencido vira aviso, e não uma consulta condenada a falhar.
    expires = number(oauth.get("expiresAt"))
    if expires:
        segundos = expires/1000 if expires > 1e11 else expires
        if segundos < time.time():
            raise Unavailable("Token do Claude Code expirado; rode `claude` para renovar a "
                              "sessão (o applet não renova credenciais).", "unconfigured")
    identity = hashlib.sha256(token.encode()).hexdigest()
    source = "Claude Code · assinatura (não verificado)"
    cached = quota_read_cache("claude", claude_interval(config), identity)
    if cached:
        read_at, metrics = cached
        result = service("claude", source=source, metrics=metrics, identity=identity,
                         message="Leitura reaproveitada; a rota é consultada respeitando um "
                                 "intervalo mínimo entre chamadas.")
        result["read_at"] = read_at  # horário real: frescor não se inventa
        return result
    payload = request(CLAUDE_USAGE_URL, token, headers={"anthropic-beta": CLAUDE_BETA})
    read_at = stamp()
    metrics = parse_claude(payload)
    if not metrics:
        raise Unavailable("Resposta sem as janelas esperadas; rode `diag claude` e relate o "
                          "resultado no GitHub para ajustar o conector.")
    quota_write_cache("claude", identity, read_at, metrics)
    return service("claude", source=source, metrics=metrics, identity=identity,
                   message=claude_message(payload, oauth))


def describe(payload, depth=0):
    """Estrutura da resposta para diagnóstico: nomes de campos, tipos e faixa dos números.

    Nenhum valor sai daqui. O que interessa relatar é o nome do campo e se o número vem em
    0–1 ou em 0–100, a única ambiguidade capaz de estragar o percentual; texto e data são
    classificados sem reproduzir conteúdo.
    """
    if depth > 3:
        return "…"
    if isinstance(payload, dict):
        return {str(k): describe(v, depth + 1) for k, v in list(payload.items())[:40]}
    if isinstance(payload, list):
        return [describe(payload[0], depth + 1)] if payload else []
    if isinstance(payload, bool) or payload is None:
        return type(payload).__name__
    if isinstance(payload, (int, float)):
        value = float(payload)
        if value < 0:
            return "número negativo"
        if value <= 1:
            return "número entre 0 e 1"
        return "número entre 1 e 100" if value <= 100 else "número acima de 100"
    if isinstance(payload, str) and re.match(r"^\d{4}-\d{2}-\d{2}T", payload):
        return "texto (data e hora)"
    return "texto"


def claude_diag(config=None):
    """Diagnóstico do conector Claude Code, para relatar em issue sem vazar nada."""
    config = config or {}
    declared = ((config or {}).get("token_files") or {}).get("claude")
    origem = ("configuração" if declared else
              "CLAUDE_CONFIG_DIR" if os.environ.get("CLAUDE_CONFIG_DIR") else "padrão")
    path = claude_login_path(config)
    report = {"origem_do_caminho": origem, "arquivo_existe": path.exists()}
    token = credentials.oauth_token("claude", {"token_files": {"claude": str(path)}})
    if not token:
        report["credencial"] = "não encontrada"
        return report
    report["credencial"] = "encontrada"
    oauth = read_json(path).get("claudeAiOauth")
    report["campos_do_login"] = sorted(oauth.keys()) if isinstance(oauth, dict) else []
    try:
        payload = request(CLAUDE_USAGE_URL, token, headers={"anthropic-beta": CLAUDE_BETA})
    except Unavailable as e:
        report["consulta"] = str(e)
        return report
    report["consulta"] = "ok"
    report["estrutura"] = describe(payload)
    report["janelas_reconhecidas"] = [m["id"] for m in parse_claude(payload)]
    return report


DIAGNOSTICS = {"claude": claude_diag}


def diagnose(id_, config=None):
    """Diagnóstico sanitizado de um serviço; há relatório apenas para quem declara um."""
    fn = DIAGNOSTICS.get(id_)
    if fn is None:
        return {"diagnostico": "não há diagnóstico para este serviço"}
    try:
        return fn(config)
    except Unavailable as e:
        return {"erro": str(e)}
    except Exception:
        return {"erro": "falha inesperada no diagnóstico"}


def collect_provider(id_, config=None):
    config = config or {}
    try:
        result = globals()[id_](config)
        if not result["metrics"]:
            raise Unavailable("Fonte não retornou métricas de uso reconhecidas.")
        return result
    except Unavailable as e:
        return service(id_, e.status, str(e))
    except Exception:
        return service(id_, "error", "Falha ao ler dados do serviço; tente atualizar.")
