#!/usr/bin/env python3
"""Captura o menu e a dica do applet no painel real, com os dados de demonstração.

O que sai daqui são as prévias do README (`docs/menu*.png` e `docs/tooltip*.png`). O snapshot de
demonstração — que se declara "nenhum dado real" — é injetado na instância viva pela interface do
Looking Glass (`org.Cinnamon.Eval`), sem tocar o cache nem o snapshot de verdade do usuário; no fim
a extensão é recarregada e o painel volta ao dado real. O ponteiro é movido e o clique é
sintetizado por XTest, porque o applet abre a dica por hover e o menu por clique de verdade.

Uso (sessão gráfica do dono do painel, do diretório do repositório):

    /usr/bin/python3 scripts/capturar-painel.py [--uuid UUID] [--destino docs]

Idioma: vale o que estiver configurado na instância. O arquivo de saída leva o sufixo do idioma
(`menu.png` para inglês, `menu.pt-BR.png` para português), então o par se produz rodando uma vez
com a preferência em cada idioma — a preferência é mudada no diálogo do applet, à mão: este script
não escreve configuração nenhuma.

Requer `python3-xlib`, o `import` do ImageMagick, `gdbus` e o applet carregado no painel. Não é
coberto pela suíte (precisa da sessão gráfica com o applet vivo).
"""

import argparse
import json
import subprocess
import sys
import time
from ast import literal_eval
from typing import Any

from Xlib import X, display
from Xlib.ext import xtest

LOCALIZA = """
  const alvo = %s;
  let d = null;
  const paineis = Main.panelManager.panels;
  for (let i = 0; i < paineis.length; i++) {
    const painel = paineis[i];
    if (!painel) continue;
    const caixas = [painel._leftBox, painel._centerBox, painel._rightBox];
    for (let k = 0; k < caixas.length; k++) {
      const filhos = caixas[k].get_children();
      for (let j = 0; j < filhos.length; j++) {
        const x = filhos[j]._delegate;
        if (x && x._uuid === alvo) d = x;
      }
    }
  }
"""

CAIXAS = """
    const dica = d._applet_tooltip && d._applet_tooltip._tooltip ? d._applet_tooltip._tooltip : null;
    const menu = d.menu ? d.menu.actor : null;
    const caixa = a => a ? {pos: [Math.round(a.get_transformed_position()[0]),
                                  Math.round(a.get_transformed_position()[1])],
                            tam: [Math.round(a.get_transformed_size()[0]),
                                  Math.round(a.get_transformed_size()[1])],
                            visivel: a.visible} : null;
    JSON.stringify({dica: caixa(dica), menu: caixa(menu), idioma: d._language,
                    backend: d._backend, ator: caixa(d.actor)});
"""


def avaliar(js: str) -> Any:
    """Roda um trecho no processo do Cinnamon e devolve o valor já decodificado."""
    saida = subprocess.run(
        ["gdbus", "call", "--session", "--dest", "org.Cinnamon", "--object-path", "/org/Cinnamon",
         "--method", "org.Cinnamon.Eval", js],
        capture_output=True, text=True, check=True).stdout.strip()
    if ", " not in saida:
        return {"bruto": saida}
    bruto = saida[saida.index(", ") + 2:]
    if bruto.endswith(")"):
        bruto = bruto[:-1]
    valor: Any = literal_eval(bruto)
    for _ in range(5):
        if not isinstance(valor, str):
            break
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError:
            break
    return valor


def com_instancia(uuid: str, js: str) -> str:
    return ("try {\n" + LOCALIZA + "\n  if (!d) { 'nao achei a instancia'; } else {\n"
            + js + "\n  }\n} catch (e) { 'ERRO: ' + e; }\n") % json.dumps(uuid)


def mover(ecra, x: int, y: int, pausa: float = 0.4) -> None:
    xtest.fake_input(ecra, X.MotionNotify, x=x, y=y)
    ecra.sync()
    time.sleep(pausa)


def clicar(ecra, x: int, y: int) -> None:
    mover(ecra, x, y)
    xtest.fake_input(ecra, X.ButtonPress, 1)
    ecra.sync()
    time.sleep(0.08)
    xtest.fake_input(ecra, X.ButtonRelease, 1)
    ecra.sync()
    time.sleep(1.8)


def capturar(nome: str, recorte: str) -> None:
    subprocess.run(["import", "-window", "root", "-crop", recorte, "+repage", nome], check=True)
    print("escrito:", nome)


def recorte_da_uniao(caixas: list[dict], resolucao: list[int], margem: int) -> str | None:
    """Recorte que contém os popups inteiros e a faixa do painel, com margem.

    Devolve None se alguma caixa não estiver visível ou vier vazia: popup fechado tem geometria
    sem sentido, e recorte montado dela sai da tela inteira (foi o que aconteceu na primeira
    rodada deste script).
    """
    usaveis = [c for c in caixas if c and c.get("visivel") and c["tam"][0] > 0 and c["tam"][1] > 0]
    if len(usaveis) != len(caixas):
        return None
    xs = [c["pos"][0] for c in usaveis]
    y2 = [c["pos"][1] + c["tam"][1] for c in usaveis]
    x2 = [c["pos"][0] + c["tam"][0] for c in usaveis]
    x0 = max(0, min(xs) - margem)
    largura = min(resolucao[0], max(x2) + margem) - x0
    altura = min(resolucao[1], max(y2) + margem)
    return f"{largura}x{altura}+{x0}+0"


def medir(ecra, uuid: str, centro: tuple[int, int], longe: tuple[int, int]) -> tuple[dict, dict]:
    """Abre a dica e o menu pelo evento real e devolve as duas caixas medidas."""
    mover(ecra, *longe, pausa=1.0)
    mover(ecra, *centro, pausa=2.0)
    dica = avaliar(com_instancia(uuid, CAIXAS))["dica"]
    for tentativa in range(3):
        clicar(ecra, *centro)
        menu = avaliar(com_instancia(uuid, CAIXAS))["menu"]
        if menu and menu.get("visivel"):
            break
        print(f"o menu não abriu na tentativa {tentativa + 1}; tentando de novo")
    else:
        menu = None
    return dica, menu


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uuid", default="ai-usage@claudio.drews")
    parser.add_argument("--destino", default="docs")
    parser.add_argument("--margem", type=int, default=30)
    argumentos = parser.parse_args()

    ecra = display.Display()
    tela = ecra.screen()
    if isinstance(tela, int) or tela is None:          # tela é índice, não objeto
        tela = ecra.screen(0)
    resolucao = [tela.width_in_pixels, tela.height_in_pixels]

    estado = avaliar(com_instancia(argumentos.uuid, CAIXAS))
    if not isinstance(estado, dict) or "backend" not in estado:
        print("não consegui falar com a instância viva:", estado)
        return 1
    idioma = str(estado["idioma"])
    sufixo = "" if idioma.startswith("en") else "." + idioma.replace("_", "-")
    ator = estado["ator"]
    centro = (ator["pos"][0] + ator["tam"][0] // 2, ator["pos"][1] + ator["tam"][1] // 2)
    longe = (centro[0] // 2, centro[1] + 800)
    print(f"instância viva em {estado['backend']}, idioma {idioma}, ícone em {centro}")

    demo = subprocess.run(["/usr/bin/python3", str(estado["backend"]) + "/collector.py", "demo"],
                          capture_output=True, text=True, check=True).stdout

    try:
        # Põe o fictício só na memória da instância e abre cada popup pelo evento real.
        avaliar(com_instancia(argumentos.uuid, "d._snapshot = " + demo + "; d._refreshIcon(); 'ok';"))
        dica, menu = medir(ecra, argumentos.uuid, centro, longe)
        print("caixa da dica:", dica and [dica["pos"], dica["tam"]])
        print("caixa do menu:", menu and [menu["pos"], menu["tam"]])
        recorte = recorte_da_uniao([dica, menu], resolucao, argumentos.margem)
        if not recorte:
            print("um dos popups não abriu: não vou capturar com recorte inventado")
            return 1
        print("recorte:", recorte)

        # O recorte é o mesmo para os dois, então as capturas são feitas com ele já decidido.
        clicar(ecra, *centro)                       # fecha o menu do passo de medição
        mover(ecra, *longe, pausa=0.8)
        mover(ecra, *centro, pausa=2.0)
        capturar(f"{argumentos.destino}/tooltip{sufixo}.png", recorte)
        clicar(ecra, *centro)
        capturar(f"{argumentos.destino}/menu{sufixo}.png", recorte)
    finally:
        avaliar(com_instancia(argumentos.uuid, "d.menu.close(); 'ok';"))
        avaliar("try { const E = imports.ui.extension; "
                "E.reloadExtension(" + json.dumps(argumentos.uuid) + ", E.Type.APPLET); 'ok'; }"
                " catch (e) { 'erro: ' + e; }")
        print("applet recarregado: o painel voltou ao snapshot real")
    return 0


if __name__ == "__main__":
    sys.exit(main())
