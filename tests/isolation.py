#!/usr/bin/env python3
"""Isolated environment for the evidence harnesses in this directory.

`dump_visible_text.py` and `smoke_gtk_credentials.py` write files into `docs/evidence/` and,
next to them, the claim that the run reads no credential of this machine, queries no service
and runs no local binary. The first version of both pointed `XDG_CONFIG_HOME` and
`XDG_CACHE_HOME` at a temporary directory and claimed exactly that — while the system
keyring, the environment variables, the login files under `$HOME` and the `codex` binary
installed on the machine were all still reachable. The versioned dump was the proof: it
recorded Codex as `ok` in the section that says "no configuration".

The claim has to be built, not written down. `Isolation` does that:

1. points every path the product resolves at an exclusive temporary directory (`HOME`,
   `XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, `XDG_DATA_HOME`, `XDG_STATE_HOME`) and takes the
   credential variables out of the environment, recording which ones it removed;
2. substitutes every external dependency — system keyring, credential file, network, local
   binary, process table, and the worker process of the collection — by a fixture;
3. counts what was substituted and records what tried to escape, so a run that stops going
   through a fixture, or that reaches for the network, the real keyring, a local binary or a
   process of the machine, **fails** instead of filing evidence that claims an isolation it
   does not have.

The sandbox is created under `/tmp` on purpose: the captures and the dumps go into the
repository, and `TMPDIR` points inside a personal directory on some setups — the evidence
cannot carry a path of the machine that produced it. The directory is unique per run and
removed on the way out.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

# Raiz do sandbox: caminho neutro, ver o docstring.
SANDBOX_ROOT = "/tmp"
PREFIX = "ai-usage-evidence-"

# Variáveis de ambiente que o produto lê para decidir de onde vem uma credencial ou um login.
# Saem do ambiente da rodada (e a ausência delas é conferida no fim): a evidência tem de sair
# igual em qualquer máquina, e uma chave exportada no shell não pode virar "configurado".
EXTRA_VARIABLES = ("CLAUDE_CONFIG_DIR", "MUSE_AUTH_PATH", "CODEX_HOME")

_MISSING = object()


class Module:
    """Módulo real com atributos trocados, para a substituição ficar confinada a um módulo.

    `providers` importa `shutil` e `subprocess` e é por esses nomes que ele os alcança: trocar
    o atributo **no módulo do produto** corta o acesso do produto sem mexer no processo inteiro
    (o harness continua com o `subprocess` de verdade, e o `shutil` compartilhado fica intacto).
    """

    def __init__(self, real, **overrides):
        self._real = real
        self._overrides = overrides

    def __getattr__(self, name):
        if name in self._overrides:
            return self._overrides[name]
        return getattr(self._real, name)


class WorkerProcess:
    """Processo falso do worker: roda o corpo da consulta no processo do harness.

    Interface imitada — é a que `collector.collect` usa: ``communicate()``, ``returncode``,
    ``poll()``, ``stdout``, ``pid`` e ``wait()``. ``poll()`` nunca devolve ``None``, e é o que
    mantém o caminho de limpeza da coleta (``killpg``) longe de um pid que não é de um filho.
    """

    def __init__(self, id_, runner):
        self.id = id_
        self.returncode = None
        self.stdout = None
        self.pid = 0
        self._runner = runner

    def communicate(self, timeout=None):
        payload = self._runner(self.id)
        self.returncode = 0
        return json.dumps(payload, ensure_ascii=False, allow_nan=False), ""

    def poll(self):
        return self.returncode if self.returncode is not None else 0

    def wait(self, timeout=None):
        return self.poll()


def add_tree(tree):
    """Coloca o `backend` de uma árvore no caminho de importação do processo."""
    path = str(Path(tree).resolve() / "backend")
    if path not in sys.path:
        sys.path.insert(0, path)
    return path


class Isolation:
    """Substituições e guardas de uma rodada de evidência. Use como gerenciador de contexto.

    ``keyring`` é a fixture do cofre (nome → valor; vazio é "cofre sem nada"), ``binaries`` a
    dos executáveis locais (nome → caminho; por omissão nenhum existe) e ``processes`` a da
    tabela de processos (pares pid → opções que o conector do Antigravity aceita). ``responses``
    permite servir uma resposta de rede para uma URL exata, para uma rodada que precise
    exercitar um conector sem tocar a rede; qualquer outra URL é violação.
    """

    def __init__(self, tree=None, *, keyring=None, binaries=None, responses=None,
                 processes=(), keyring_available=True):
        self.tree = Path(tree).resolve() if tree else Path(__file__).resolve().parents[1]
        add_tree(self.tree)
        self.keyring = dict(keyring or {})
        self.binaries = dict(binaries or {})
        self.responses = dict(responses or {})
        self.processes = list(processes)
        self.keyring_available = bool(keyring_available)
        self.base = None
        self.calls = Counter()
        self.violations = []
        self.removed_from_environment = []
        self.absent_seams = []
        self._patched = []
        self._environment = {}

    # -- entradas e guardas --------------------------------------------------------------

    def variable_names(self):
        """Nomes de variável que o produto usa para credencial ou para caminho de login."""
        credentials = self.credentials
        names = {name for group in credentials.SERVICE_KEYS.values() for name in group}
        names |= {name for group in credentials.SERVICE_SETTINGS.values() for name in group}
        return sorted(names | set(EXTRA_VARIABLES))

    def violate(self, what):
        """Registra um acesso ao mundo real; a rodada falha em `assert_clean`."""
        if what not in self.violations:
            self.violations.append(what)

    def inside(self, path):
        """O caminho está dentro do sandbox desta rodada?"""
        if not self.base:
            return False
        text = str(Path(path))
        return text == str(self.base) or text.startswith(str(self.base) + os.sep)

    def path(self, name):
        """Caminho dentro do sandbox (arquivo de fixture, config, cache)."""
        return self.base / name

    # -- ciclo de vida -------------------------------------------------------------------

    def __enter__(self):
        self.base = Path(tempfile.mkdtemp(prefix=PREFIX, dir=SANDBOX_ROOT))
        for name in ("home", "config", "cache", "data", "state"):
            (self.base / name).mkdir()
        for name, value in (("HOME", self.base / "home"),
                            ("XDG_CONFIG_HOME", self.base / "config"),
                            ("XDG_CACHE_HOME", self.base / "cache"),
                            ("XDG_DATA_HOME", self.base / "data"),
                            ("XDG_STATE_HOME", self.base / "state")):
            self._environment[name] = os.environ.get(name)
            os.environ[name] = str(value)
        # Importa o produto **depois** de o ambiente e os caminhos estarem isolados: módulo que
        # lê ambiente no import lê o ambiente limpo.
        import collector
        import credentials
        import providers

        self.collector, self.credentials, self.providers = collector, credentials, providers
        self.removed_from_environment = [name for name in self.variable_names()
                                        if os.environ.pop(name, None)]
        self._substitute()
        return self

    def __exit__(self, *_exception):
        for target, name, original in reversed(self._patched):
            if original is _MISSING:
                try:
                    delattr(target, name)
                except AttributeError:
                    pass
            else:
                setattr(target, name, original)
        for name, value in self._environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if self.base:
            shutil.rmtree(self.base, ignore_errors=True)
        return False

    def _patch(self, target, name, value):
        original = getattr(target, name, _MISSING)
        if original is _MISSING:
            # Árvore mais antiga, sem o ponto de substituição: a fixture fica instalada (para o
            # caso de o código passar a chamá-la) e a ausência é relatada — nunca escondida.
            self.absent_seams.append(f"{target.__name__}.{name}")
        self._patched.append((target, name, original))
        setattr(target, name, value)

    # -- substituições -------------------------------------------------------------------

    def _substitute(self):
        credentials, providers, collector = self.credentials, self.providers, self.collector
        real_read_file = credentials.read_file

        def keyring_get(name):
            self.calls["cofre_leitura"] += 1
            return self.keyring.get(name)

        def keyring_names():
            self.calls["cofre_nomes"] += 1
            return set(self.keyring)

        def keyring_available():
            self.calls["cofre_disponibilidade"] += 1
            return self.keyring_available

        def keyring_write(*_args, **_kwargs):
            self.violate("gravação no cofre do sistema")
            raise RuntimeError("isolated run: the system keyring is not written to")

        def read_file(path, discarded=None):
            self.calls["arquivo_leitura"] += 1
            if path and not self.inside(Path(path).expanduser()):
                self.violate(f"leitura de credencial fora do sandbox: {path}")
                return {}
            return real_read_file(path, discarded)

        def request(url, token=None, data=None, headers=None, local=False, timeout=8):
            self.calls["rede"] += 1
            if url in self.responses:
                return copy.deepcopy(self.responses[url])
            self.violate(f"consulta de rede: {url}")
            raise providers.Unavailable(
                "Isolated run: no service is queried and no response fixture was given for "
                "this URL.", "error")

        def which(name):
            self.calls["binario"] += 1
            return self.binaries.get(name)

        def local_server_processes():
            self.calls["processos"] += 1
            return iter(self.processes)

        def process(args, *_a, **_k):
            self.calls["worker"] += 1
            return WorkerProcess(args[-1], self.worker_result)

        self._patch(credentials, "keyring_get", keyring_get)
        self._patch(credentials, "keyring_names", keyring_names)
        self._patch(credentials, "keyring_available", keyring_available)
        self._patch(credentials, "keyring_set", keyring_write)
        self._patch(credentials, "keyring_delete", keyring_write)
        self._patch(credentials, "read_file", read_file)
        self._patch(providers, "request", request)
        self._patch(providers, "shutil", Module(shutil, which=which))
        self._patch(providers, "subprocess", Module(subprocess, Popen=process, run=process))
        self._patch(providers, "local_server_processes", local_server_processes)
        self._patch(collector, "launch_worker", self.launch_worker)
        # Árvore anterior aos pontos de substituição: `collect` criava o processo do worker
        # direto por `subprocess.Popen`, e é essa a chamada que se troca aqui.
        self._patch(collector, "subprocess", Module(subprocess, Popen=process))

    def launch_worker(self, id_):
        self.calls["worker"] += 1
        return WorkerProcess(id_, self.worker_result)

    def worker_result(self, id_):
        """Corpo do worker, do jeito que o produto o tem nesta árvore."""
        worker = getattr(self.collector, "worker", None)
        if worker is not None:
            return worker(id_)
        return self.providers.collect_provider(
            id_, self.providers.read_json(self.collector.paths()[1]))

    # -- verificação ---------------------------------------------------------------------

    def product_paths(self):
        """Caminhos que o produto resolve hoje, para conferir que todos caem no sandbox."""
        paths = {"config": self.collector.paths()[1],
                 "cache": self.collector.paths()[0],
                 "cache_de_cota": self.providers.quota_cache_path("claude"),
                 "cache_da_meta": self.providers.meta_cache_path(),
                 "login_do_claude": self.providers.claude_login_path({}),
                 "login_do_muse": self.providers.meta_login_path({})}
        try:
            import credentials_window
        except Exception:
            return paths
        paths["config_da_janela"] = credentials_window.config_paths()
        return paths

    def report(self):
        """Uma linha com o que foi substituído nesta rodada, para o harness imprimir em stderr."""
        parts = [f"sandbox {self.base}",
                 f"cofre: {self.calls['cofre_leitura']} leituras e "
                 f"{self.calls['cofre_disponibilidade']} consultas de disponibilidade (fixture)",
                 f"arquivo de credenciais: {self.calls['arquivo_leitura']} leituras (sandbox)",
                 f"rede: {self.calls['rede']} consultas",
                 f"executáveis locais: {self.calls['binario']} buscas (fixture)",
                 f"workers em processo: {self.calls['worker']}",
                 "ambiente sem: " + (", ".join(self.removed_from_environment) or "nada a remover")]
        if self.absent_seams:
            parts.append("sem ponto de substituição nesta árvore: " + ", ".join(self.absent_seams))
        return "isolamento — " + " | ".join(parts)

    def assert_clean(self, queries=0, expect=("cofre_leitura",)):
        """Falha a rodada quando o isolamento afirmado não é o que aconteceu.

        ``queries`` é o número de consultas de rede que a rodada **pode** ter feito (a de um
        dossiê sem configuração é zero), e ``expect`` são as substituições que precisam ter
        sido usadas: sem isso, um harness que deixou de passar por elas seria dado como
        isolado por não ter sido exercitado.
        """
        problems = list(self.violations)
        if self.calls["rede"] != queries:
            problems.append(f"consultas de rede: {self.calls['rede']} (esperado {queries})")
        leaked = [name for name in self.variable_names() if os.environ.get(name)]
        if leaked:
            problems.append("variável de credencial no ambiente: " + ", ".join(leaked))
        for name in expect:
            if not self.calls[name]:
                problems.append(f"a substituição de {name} não foi usada nenhuma vez")
        for name, path in self.product_paths().items():
            if not self.inside(Path(path)):
                problems.append(f"{name} resolveu para fora do sandbox: {path}")
        if problems:
            raise SystemExit("isolamento da evidência falhou:\n- " + "\n- ".join(problems))
