"""Resolução de credenciais do Cinnamon AI Usage.

Ordem por variável, sempre sem shell e sem servidor de credenciais obrigatório:

1. cofre do sistema (Secret Service / gnome-keyring), onde a janela "Credenciais" grava o que a
   pessoa digita;
2. arquivo NOME=VALOR indicado em ``config.json`` pela chave ``credentials_path`` (qualquer
   caminho: ~/.env, ~/.config/secrets.env, o que a pessoa usar);
3. variáveis de ambiente herdadas do processo.

O arquivo de token OAuth em JSON (``token_files`` em ``config.json``) cobre logins que não são
chave de API, como o token do Nous Portal.

Nenhuma função devolve valor dentro de mensagem de erro, e nada é impresso ou registrado.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

SCHEMA_NAME = "local.claudio.CinnamonAIUsage"
KEYRING_LABEL = "Cinnamon AI Usage"

# Variáveis aceitas por serviço, na ordem de preferência.
SERVICE_KEYS = {
    "openrouter": ("OPENROUTER_API_KEY",),
    "deepseek": ("DEEPSEEK_API_KEY",),
    "opencode": ("OPENCODE_GO_API_KEY", "OPENCODE_API_KEY"),
    "grok": ("XAI_MANAGEMENT_API_KEY", "XAI_MANAGEMENT_KEY"),
    "nous": ("NOUS_PORTAL_TOKEN",),
    "codex": (),
    "antigravity": (),
}

# Dados não secretos que costumam acompanhar a credencial (time, projeto, conta).
SERVICE_SETTINGS = {
    "grok": ("XAI_TEAM_ID",),
}

# Serviços que aceitam token OAuth vindo de arquivo JSON, em vez de chave digitada.
TOKEN_SERVICES = ("nous",)

ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_assignments(text):
    """Extrai NOME=VALOR de um arquivo de credenciais, sem executar shell.

    Aspas simples ou duplas são removidas; um valor com $(...) ou crases permanece literal.
    """
    values = {}
    for line in (text or "").splitlines():
        match = ASSIGNMENT.match(line)
        if not match:
            continue
        name, raw = match.group(1), match.group(2)
        try:
            parts = shlex.split(raw, comments=True, posix=True)
        except ValueError:
            continue
        if len(parts) == 1:
            values[name] = parts[0]
    return values


def read_file(path):
    if not path:
        return {}
    try:
        return parse_assignments(Path(path).expanduser().read_text())
    except OSError:
        return {}


def _secret_module():
    """Importa o vínculo Secret sem exigir que exista na máquina.

    O namespace declara versão "1" (arquivo Secret-1.typelib); pedir "1.0" falha.
    """
    try:
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Secret

        return Secret
    except Exception:
        return None


def _service(Secret):
    """Serviço sem prompt e sem carregar coleções: cofre travado responde "sem valor"."""
    try:
        return Secret.Service.get_sync(Secret.ServiceFlags.NONE, None)
    except Exception:
        return None


def _schema(Secret):
    return Secret.Schema.new(SCHEMA_NAME, Secret.SchemaFlags.NONE,
                             {"nome": Secret.SchemaAttributeType.STRING})


def keyring_available():
    Secret = _secret_module()
    if Secret is None:
        return False
    return _service(Secret) is not None


def keyring_get(name):
    Secret = _secret_module()
    if Secret is None:
        return None
    if _service(Secret) is None:
        return None
    try:
        found = Secret.password_lookup_sync(_schema(Secret), {"nome": name}, None)
    except Exception:
        return None
    return found or None


def keyring_set(name, value, label=""):
    Secret = _secret_module()
    if Secret is None or _service(Secret) is None:
        raise RuntimeError("Cofre do sistema indisponível.")
    Secret.password_store_sync(_schema(Secret), {"nome": name},
                               Secret.COLLECTION_DEFAULT,
                               f"{KEYRING_LABEL} — {label or name}", value, None)


def keyring_delete(name):
    Secret = _secret_module()
    if Secret is None or _service(Secret) is None:
        raise RuntimeError("Cofre do sistema indisponível.")
    try:
        return bool(Secret.password_clear_sync(_schema(Secret), {"nome": name}, None))
    except Exception:
        return False


def keyring_names():
    """Nomes já guardados no cofre (o cofre é a fonte; a leitura por nome é sempre ao vivo)."""
    Secret = _secret_module()
    if Secret is None:
        return set()
    try:
        service = Secret.Service.get_sync(Secret.ServiceFlags.LOAD_COLLECTIONS, None)
    except Exception:
        return set()
    if service is None:
        return set()
    names = set()
    try:
        for item in service.get_collections() or []:
            if item.get_locked():
                continue
            for stored in item.get_items() or []:
                attributes = stored.get_attributes() or {}
                nome = attributes.get("nome")
                if nome:
                    names.add(str(nome))
    except Exception:
        return names
    return names


def token_from_json(path):
    """Primeiro access_token encontrado no JSON, em qualquer nível."""
    try:
        data = json.loads(Path(path).expanduser().read_text())
    except (OSError, ValueError):
        return None
    stack = [data]
    while stack:
        current = stack.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                if key in ("access_token", "accessToken") and isinstance(value, str) and value:
                    return value
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(item for item in current if isinstance(item, (dict, list)))
    return None


def sources(config=None):
    """Fontes não secretas em uso, para mensagem de estado na interface."""
    config = config or {}
    return {"cofre": keyring_available(), "arquivo": bool(config.get("credentials_path")),
            "token": {name: bool((config.get("token_files") or {}).get(name)) for name in TOKEN_SERVICES}}


def resolve(names, config=None):
    """Valores disponíveis para ``names``, seguindo cofre, arquivo e ambiente."""
    config = config or {}
    wanted = list(names)
    found = {}
    for name in wanted:
        value = keyring_get(name)
        if value:
            found[name] = value
    missing = [name for name in wanted if name not in found]
    if missing:
        file_values = read_file(config.get("credentials_path"))
        for name in missing:
            if file_values.get(name):
                found[name] = file_values[name]
    for name in wanted:
        if name not in found and os.environ.get(name):
            found[name] = os.environ[name]
    return found


def service_value(service, config=None):
    """Primeiro valor disponível entre as variáveis do serviço, ou None."""
    names = SERVICE_KEYS.get(service, ())
    if not names:
        return None
    values = resolve(names, config)
    for name in names:
        if values.get(name):
            return values[name]
    return None


def setting_value(service, config=None):
    """Primeiro valor disponível entre as variáveis não secretas do serviço, ou None."""
    names = SERVICE_SETTINGS.get(service, ())
    if not names:
        return None
    values = resolve(names, config)
    for name in names:
        if values.get(name):
            return values[name]
    return None


def oauth_token(service, config=None):
    """Token OAuth de arquivo indicado na configuração, se houver."""
    path = (config or {}).get("token_files", {}).get(service)
    return token_from_json(path) if path else None
