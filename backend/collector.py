#!/usr/bin/env python3
"""Bounded, concurrent read-only collection with a private atomic cache."""
from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from providers import SERVICES, collect_provider, diagnose, number, service, stamp, metric, read_json


def paths():
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home()/".cache"))) / "cinnamon-ai-usage"
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "cinnamon-ai-usage/config.json"
    return cache, config


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError, OverflowError):
        return 0


def empty_snapshot(message="Nenhuma leitura disponível; atualize para consultar."):
    return {"schema_version": 1, "generated_at": None,
            "services": [service(k, "unavailable", message) for k in SERVICES]}


def valid_snapshot(data):
    return isinstance(data, dict) and data.get("schema_version") == 1 and isinstance(data.get("services"), list)


def load_snapshot(path):
    data = read_json(path)
    return data if valid_snapshot(data) else empty_snapshot()


def stale_read(snapshot, ttl=120):
    snapshot = copy.deepcopy(snapshot)
    for item in snapshot["services"]:
        if item.get("status") == "ok" and time.time()-timestamp(item.get("read_at")) > ttl:
            item["status"] = "stale"
            item["message"] = "Última leitura disponível; atualização pendente."
    return snapshot


def detected_change(previous, current):
    if previous.get("_identity") != current.get("_identity"):
        return False
    before = {m["id"]: m for m in previous.get("metrics", [])}
    for m in current.get("metrics", []):
        old = before.get(m["id"])
        if not old or (old.get("kind"), old.get("currency"), old.get("window_seconds")) != (
                m.get("kind"), m.get("currency"), m.get("window_seconds")):
            continue
        if m["kind"] == "quota":
            if m.get("reset_at") != old.get("reset_at"):
                continue
            a, b = number(old.get("used_percent")), number(m.get("used_percent"))
            changed = a is not None and b is not None and b > a + 1e-6
        else:
            a, b = number(old.get("value")), number(m.get("value"))
            changed = a is not None and b is not None and (
                b < a - 1e-6 if m["kind"] == "balance" else b > a + 1e-6)
        if changed:
            return True
    return False


def merge_history(current, previous):
    previous = previous or {}
    if current["status"] != "ok":
        if current["status"] != "disabled" and previous.get("metrics"):
            # Preserve data timestamp and source: an error is not a new measurement.
            result = copy.deepcopy(previous)
            result.update(status="stale", message=current["message"])
            return result
        return current
    if previous.get("_identity") == current.get("_identity"):
        current["last_used_at"] = previous.get("last_used_at")
        current["recency_basis"] = previous.get("recency_basis", "unknown")
        if detected_change(previous, current):
            current["last_used_at"] = current["read_at"]
            current["recency_basis"] = "observed_change"
    return current


def save_atomic(path, snapshot):
    fd, name = tempfile.mkstemp(prefix=".snapshot-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(snapshot, f, ensure_ascii=False, allow_nan=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


def collect(force=False, ttl_override=None):
    cache, config_path = paths()
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(cache, 0o700)
    path = cache/"snapshot.json"
    config = read_json(config_path)
    ttl = number(ttl_override) or number(config.get("refresh_seconds")) or 120
    ttl = max(30, min(3600, ttl))
    lock_fd = os.open(cache/"collect.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Outra coleta está em andamento. Isso não é falha: o snapshot sai com um aviso
            # público (``notice``) dizendo que a atualização foi ignorada, e as leituras
            # continuam sendo as últimas conhecidas. Sem o aviso, o applet e a janela não têm
            # como distinguir "pulei" de "falhei" e acabam afirmando falha que não houve.
            adiado = stale_read(load_snapshot(path), ttl)
            adiado["notice"] = ("Atualização ignorada: já há uma coleta em andamento; "
                                "os valores são os últimos lidos.")
            return adiado
        old = load_snapshot(path)
        if not force and 0 <= time.time()-timestamp(old.get("generated_at")) < ttl:
            return stale_read(old, ttl)
        before = {s["id"]: s for s in old["services"]}
        pending, result = {}, {}
        enabled = config.get("enabled", {})
        deadline = time.monotonic()+40
        try:
            for id_ in SERVICES:
                if isinstance(enabled, dict) and enabled.get(id_) is False:
                    result[id_] = service(id_, "disabled", "Desativado na configuração.")
                else:
                    pending[id_] = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "worker", id_],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
            for id_, proc in pending.items():
                try:
                    output, _ = proc.communicate(timeout=max(0.1, deadline-time.monotonic()))
                    item = json.loads(output)
                    if proc.returncode or not isinstance(item, dict) or item.get("id") != id_:
                        raise ValueError()
                    result[id_] = item
                except (subprocess.TimeoutExpired, ValueError):
                    result[id_] = service(id_, "error", "Consulta excedeu o tempo limite ou retornou dados inválidos.")
        finally:
            for proc in pending.values():
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try: proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                if proc.stdout: proc.stdout.close()
        snapshot = {"schema_version": 1, "generated_at": stamp(),
                    "services": [merge_history(result[k], before.get(k)) for k in SERVICES]}
        save_atomic(path, snapshot)
        return snapshot


# Forma de cada conector na demonstração. O demo não pode afirmar o que o serviço não mede:
# o Grok é pré-pago (saldo e créditos usados, sem janela de 5 h) e o OpenCode Go tem três
# janelas. Antes tudo caía no mesmo ramo e a imagem de exemplo do repositório mentia.
DEMO_SHAPES = {
    "codex": [("primary", "Janela de 5 h", "quota", 18000),
              ("secondary", "Semana", "quota", 604800)],
    "claude": [("five_hour", "Janela de 5 h", "quota", 18000),
               ("seven_day", "Semana", "quota", 604800)],
    "meta": [("janela", "Janela de 5 h", "quota", 18000),
             ("semanal", "Semana", "quota", 604800)],
    "opencode": [("rolling", "Janela móvel", "quota", None),
                 ("weekly", "Semana", "quota", 604800),
                 ("monthly", "Mês", "quota", None)],
    "antigravity": [("model:exemplo", "Modelo de exemplo", "quota", None)],
    "grok": [("balance:USD", "Saldo pré-pago da API", "balance", None),
             ("credits_used", "Créditos pré-pagos usados", "quota", None)],
    "nous": [("total_usable_credits", "Saldo total disponível", "balance", None),
             ("subscription_credits_remaining", "Saldo do plano", "balance", None)],
    "deepseek": [("balance:USD", "Saldo disponível", "balance", None)],
    "openrouter": [("usage_monthly", "Gasto no mês", "spend", None)],
}


def demo():
    items = []
    for i, id_ in enumerate(SERVICES):
        metrics = []
        for position, (metric_id, label, kind, window) in enumerate(DEMO_SHAPES.get(id_, [])):
            if kind in ("balance", "spend"):
                metrics.append(metric(metric_id, label, kind, value=4.02 + i + position,
                                      currency="USD"))
                continue
            metrics.append(metric(metric_id, label, "quota",
                                  percent=min(92, 12 + i * 7 + position * 9), window=window,
                                  reset=time.time() + 3600 if window else None))
        item = service(id_, source="Simulação — nenhum dado real", metrics=metrics)
        item.update(last_used_at=stamp(time.time()-i*900), recency_basis="observed_change")
        items.append(item)
    return {"schema_version": 1, "generated_at": stamp(), "demo": True, "services": items}


def public(snapshot):
    snapshot = copy.deepcopy(snapshot)
    for item in snapshot.get("services", []):
        item.pop("_identity", None)
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="collect",
                        choices=["collect", "read", "demo", "worker", "diag"])
    parser.add_argument("provider", nargs="?", choices=list(SERVICES))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ttl", type=int, help="TTL desta consulta, em segundos")
    args = parser.parse_args()
    if args.command == "worker":
        if not args.provider: parser.error("worker exige um provedor")
        def timed_out(*_):
            raise TimeoutError()
        signal.signal(signal.SIGALRM, timed_out)
        signal.signal(signal.SIGTERM, timed_out)
        signal.alarm(30)
        result = collect_provider(args.provider, read_json(paths()[1]))
    elif args.command == "diag":
        if not args.provider: parser.error("diag exige um provedor")
        result = diagnose(args.provider, read_json(paths()[1]))
    elif args.command == "demo":
        result = demo()
    elif args.command == "read":
        result = public(stale_read(load_snapshot(paths()[0]/"snapshot.json")))
    else:
        try:
            signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
            result = public(collect(args.force, args.ttl))
        except (OSError, ValueError, TypeError):
            result = empty_snapshot("Falha ao ler configuração ou gravar o cache local.")
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
