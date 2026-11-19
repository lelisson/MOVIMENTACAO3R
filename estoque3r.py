# -*- coding: utf-8 -*-
"""
Dashboard interativo — controle de estoque por NF de origem · 3R Indústria.

Regras de negócio:
  - Período padrão: 01/01/2026 até hoje
  - Entradas: somente CFOP 1901 (alimentam o saldo)
  - Saídas: somente CFOP 5902 (consomem o saldo da NF na observação, quando houver)
  - Nem toda saída tem NF de origem na observação — essas não abatem saldo por lote
  - CFOP 5124: só contabilização financeira (valor da NF) — não move estoque
  - Posição: estoque inicial + movimentação do período = estoque final

Segurança:
  - Somente leitura na Omie (whitelist de métodos)
  - Chaves via OMIE_3R_APP_KEY / OMIE_3R_APP_SECRET (env ou Streamlit secrets)
  - Nunca gravar segredo no repositório
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SAIDA_DIR = BASE_DIR / "saida"
TEMPLATE = BASE_DIR / "templates" / "dashboard_estoque_3r.html"
PAINEL_CSS = BASE_DIR / "frontend" / "painel.css"
CHART_JS = BASE_DIR / "frontend" / "vendor" / "chart.umd.min.js"
# Cache só em pasta local/tmp — nunca versionado no git
CACHE_DIR = Path(os.environ.get("ESTOQUE3R_CACHE") or (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "3REstoque" / "cache"))

EP_NF = "https://app.omie.com.br/api/v1/produtos/nfconsultar/"
EP_REMESSA = "https://app.omie.com.br/api/v1/produtos/remessa/"

READ_ONLY_CALLS = {
    "ListarNF": EP_NF,
    "ConsultarNF": EP_NF,
    "ConsultarRemessa": EP_REMESSA,  # observação / NF de origem fica em infAdic.cDadosAdic
}
CFOP_ENTRADA = frozenset({"1901"})
CFOP_SAIDA = frozenset({"5902"})
CFOP_FINANCEIRO = frozenset({"5124"})  # valor da NF; não altera saldo

# Observação tipicamente traz a NF de origem (ex.: "REFERENTE A NF 41798", "NF 12")
RE_NF_ORIGEM = re.compile(
    r"(?:referente\s+a\s+)?(?:nf[\s\-eº°:]*|nfe[\s\-:]*|origem[\s\-:]*|ref(?:er[eê]ncia)?[\s\-:]*|"
    r"nota[\s\-]*fiscal[\s\-:]*|n[º°\.]\s*)(\d{1,9})",
    re.IGNORECASE,
)
RE_SO_NUMERO = re.compile(r"^\s*(\d{1,9})\s*$")


def die(msg: str, code: int = 1) -> None:
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(code)


def br_data(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def iso_de_br(texto: str) -> str:
    """dd/mm/aaaa -> aaaa-mm-dd; se já ISO, devolve."""
    t = (texto or "").strip()
    if not t:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", t):
        return t
    try:
        return datetime.strptime(t[:10], "%d/%m/%Y").date().isoformat()
    except ValueError:
        return t


def norm_nf(v: object) -> str:
    s = re.sub(r"\D", "", str(v or ""))
    return s.lstrip("0") or "0"


def norm_cfop(v: object) -> str:
    return re.sub(r"\D", "", str(v or ""))


def ler_env_usuario(nome: str) -> str:
    """Mesmo padrão da JCA: os.environ e, no Windows, HKCU\\Environment."""
    valor = (os.getenv(nome) or "").strip()
    if valor or os.name != "nt":
        return valor
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return str(winreg.QueryValueEx(k, nome)[0]).strip()
    except OSError:
        return ""


def carregar_credenciais() -> tuple[str, str]:
    """Ordem: Streamlit secrets → env/os → HKCU Windows. Nunca lê arquivo do repo."""
    key = secret = ""
    try:
        import streamlit as st  # type: ignore

        if hasattr(st, "secrets"):
            key = str(st.secrets.get("OMIE_3R_APP_KEY", "") or "").strip()
            secret = str(st.secrets.get("OMIE_3R_APP_SECRET", "") or "").strip()
    except Exception:
        pass
    if not key:
        key = ler_env_usuario("OMIE_3R_APP_KEY")
    if not secret:
        secret = ler_env_usuario("OMIE_3R_APP_SECRET")
    if not key or not secret:
        die(
            "Defina OMIE_3R_APP_KEY e OMIE_3R_APP_SECRET "
            "(Streamlit secrets ou variáveis de ambiente do usuário)."
        )
    return key, secret


def omie_call(call: str, param: dict, app_key: str, app_secret: str) -> dict:
    endpoint = READ_ONLY_CALLS.get(call)
    if not endpoint:
        die(f"Bloqueado por segurança: método não é somente leitura ({call})")
    payload = {
        "call": call,
        "app_key": app_key,
        "app_secret": app_secret,
        "param": [param],
    }
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "3REstoque/1.0-readonly"},
        method="POST",
    )
    for tentativa in range(1, 6):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if isinstance(body, dict) and body.get("faultstring"):
                die(f"Omie ({call}): {body.get('faultstring')}")
            return body
        except urllib.error.HTTPError as e:
            detalhe = e.read().decode("utf-8", errors="replace")
            if "API_ADDON_REQUIRED" in detalhe:
                die(
                    "Conexão igual à JCA (app_key/app_secret), mas o aplicativo Omie da 3R "
                    "ainda não tem o plano \"APIs Omie\" contratado. Na JCA Matriz/Filial o "
                    "plano já está ativo nesse app — por isso funciona sem pedir de novo. "
                    "Na conta Omie da 3R: Meus Aplicativos → engrenagem do app dessas chaves → "
                    "Resumo → Adicionais → contratar APIs Omie "
                    "(https://store.omie.com.br/apps/apis-omie). "
                    "Enquanto isso: python gerar_dashboard_estoque_3r.py --demo"
                )
            if e.code in (429, 500, 502, 503, 504) and tentativa < 5:
                time.sleep(2 * tentativa)
                continue
            die(f"HTTP {e.code} em {call}: {detalhe[:400]}")
        except urllib.error.URLError as e:
            if tentativa < 5:
                time.sleep(2 * tentativa)
                continue
            die(f"Falha de rede em {call}: {e}")
    die(f"Falha ao chamar {call}")
    return {}


def nf_cancelada(nf: dict) -> bool:
    ide = nf.get("ide") or {}
    d_can = str(ide.get("dCan") or "").strip()
    return bool(d_can and d_can not in ("00/00/0000", "01/01/1900"))


def listar_nf(
    ini: date,
    fim: date,
    tp_nf: str,
    app_key: str,
    app_secret: str,
    status: str = "N",
) -> list[dict]:
    """status: N = não cancelada, C = cancelada."""
    notas: list[dict] = []
    pagina = 1
    while True:
        resp = omie_call(
            "ListarNF",
            {
                "pagina": pagina,
                "registros_por_pagina": 50,
                "apenas_importado_api": "N",
                "dEmiInicial": br_data(ini),
                "dEmiFinal": br_data(fim),
                "tpNF": tp_nf,
                "cDetalhesPedido": "S",
                "filtrar_por_status": status,
            },
            app_key,
            app_secret,
        )
        lote = resp.get("nfCadastro") or []
        for nf in lote:
            nf["_cancelada"] = status == "C" or nf_cancelada(nf)
        notas.extend(lote)
        total = int(resp.get("total_de_paginas") or 1)
        rot = "ativas" if status == "N" else "canceladas"
        print(f"  tpNF={tp_nf} {rot} página {pagina}/{total} (+{len(lote)})")
        if pagina >= total:
            break
        pagina += 1
        time.sleep(0.35)
    return notas


def listar_nf_todas(ini: date, fim: date, tp_nf: str, app_key: str, app_secret: str) -> list[dict]:
    ativas = listar_nf(ini, fim, tp_nf, app_key, app_secret, "N")
    canceladas = listar_nf(ini, fim, tp_nf, app_key, app_secret, "C")
    return ativas + canceladas


def _add_obs(partes: list[str], v: object) -> None:
    if v is None or v == "":
        return
    if isinstance(v, (dict, list)):
        texto = json.dumps(v, ensure_ascii=False)
    else:
        texto = str(v).strip()
    if texto:
        partes.append(texto)


def texto_observacao(nf: dict) -> str:
    """Junta campos possíveis de observação / informações adicionais (somente leitura)."""
    partes: list[str] = []
    # preenchido por enriquecer_obs_remessa (infAdic.cDadosAdic da Remessa Omie)
    _add_obs(partes, nf.get("_obs_remessa"))

    pedido = nf.get("pedido") or {}
    if isinstance(pedido, dict):
        for k in (
            "observacoes",
            "obs",
            "observacao",
            "cObs",
            "obs_venda",
            "observacao_venda",
            "dadosAdic",
            "infAdic",
            "cDadosAdic",
        ):
            _add_obs(partes, pedido.get(k))
        for bloco in ("cabecalho", "informacoes_adicionais", "infoCadastro"):
            sub = pedido.get(bloco)
            if isinstance(sub, dict):
                for k, v in sub.items():
                    if v and any(x in k.lower() for x in ("obs", "adic", "inf")):
                        _add_obs(partes, v)

    compl = nf.get("compl") or {}
    if isinstance(compl, dict):
        for k, v in compl.items():
            if v and any(x in k.lower() for x in ("obs", "adic", "inf")):
                _add_obs(partes, v)

    for k in ("observacoes", "obs", "infAdic", "infCpl"):
        _add_obs(partes, nf.get(k))

    for k, v in nf.items():
        if not v or k in ("pedido", "compl", "_obs_remessa"):
            continue
        if any(x in k.lower() for x in ("obs", "infadic", "infcpl")):
            _add_obs(partes, v)

    vistos: set[str] = set()
    out: list[str] = []
    for p in partes:
        t = p.strip()
        if t and t not in vistos:
            vistos.add(t)
            out.append(t)
    return " | ".join(out)


def _cache_remessa_path() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / "remessa_obs.json"


def enriquecer_obs_remessa(notas: list[dict], app_key: str, app_secret: str) -> None:
    """
    Na 3R a NF de origem fica na Remessa (infAdic.cDadosAdic), não no ListarNF.
    Consulta somente leitura via ConsultarRemessa usando compl.nIdPedido.
    Cache local em %LOCALAPPDATA%\\3REstoque\\cache\\remessa_obs.json.
    """
    ids: list[int] = []
    vistos: set[int] = set()
    for nf in notas:
        tem_5902 = any(
            norm_cfop((d.get("prod") or {}).get("CFOP")) in CFOP_SAIDA for d in (nf.get("det") or [])
        )
        if not tem_5902:
            continue
        n_id = int((nf.get("compl") or {}).get("nIdPedido") or 0)
        if n_id and n_id not in vistos:
            vistos.add(n_id)
            ids.append(n_id)

    path = _cache_remessa_path()
    mapa: dict[str, str] = {}
    if path.exists():
        try:
            mapa = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            mapa = {}

    faltam = [n for n in ids if str(n) not in mapa]
    print(f"  Observações de remessa: {len(ids)} pedidos · cache {len(ids) - len(faltam)} · novas {len(faltam)}")
    for i, n_id in enumerate(faltam, 1):
        try:
            resp = omie_call("ConsultarRemessa", {"nCodRem": n_id}, app_key, app_secret)
            inf = resp.get("infAdic") or {}
            obs = resp.get("obs") or {}
            texto = " | ".join(
                x
                for x in (
                    str(inf.get("cDadosAdic") or "").strip(),
                    str(obs.get("cObs") or "").strip(),
                )
                if x
            )
            mapa[str(n_id)] = texto  # vazio = sem referência (normal)
        except SystemExit:
            raise
        except Exception as e:
            print(f"  remessa {n_id}: {e}")
            mapa[str(n_id)] = ""
        if i % 25 == 0 or i == len(faltam):
            print(f"  remessas novas {i}/{len(faltam)}")
        time.sleep(0.12)
    if faltam:
        path.write_text(json.dumps(mapa, ensure_ascii=False), encoding="utf-8")

    com_texto = 0
    for nf in notas:
        n_id = int((nf.get("compl") or {}).get("nIdPedido") or 0)
        texto = mapa.get(str(n_id), "")
        if texto:
            nf["_obs_remessa"] = texto
            com_texto += 1
    print(f"  remessas com texto de observação: {com_texto}")


def extrair_nf_origem(obs: str) -> str | None:
    """Só vincula quando a observação deixa a NF de origem explícita. Sem chute."""
    if not obs:
        return None
    m = RE_NF_ORIGEM.search(obs)
    if m:
        return norm_nf(m.group(1))
    m2 = RE_SO_NUMERO.match(obs.strip())
    if m2:
        return norm_nf(m2.group(1))
    return None


def valor_total_nf(nf: dict) -> float:
    total = nf.get("total") or {}
    icms = total.get("ICMSTot") or total.get("icmsTot") or {}
    for k in ("vNF", "vProd", "vLiq"):
        if icms.get(k) is not None:
            try:
                return float(icms.get(k) or 0)
            except (TypeError, ValueError):
                pass
    # fallback: soma dos itens
    soma = 0.0
    for det in nf.get("det") or []:
        prod = det.get("prod") or {}
        try:
            soma += float(prod.get("vProd") or prod.get("vTotItem") or 0)
        except (TypeError, ValueError):
            pass
    return soma


def dest_nome(nf: dict) -> str:
    d = nf.get("nfDestInt") or nf.get("dest") or {}
    if isinstance(d, dict):
        return str(d.get("cRazao") or d.get("xNome") or d.get("razao_social") or "").strip()
    return ""


def iter_itens_estoque(nf: dict):
    """Somente CFOPs que movem estoque: 1901 (entrada) e 5902 (saída)."""
    ide = nf.get("ide") or {}
    nNF = norm_nf(ide.get("nNF"))
    data = iso_de_br(str(ide.get("dEmi") or ""))
    data_canc = iso_de_br(str(ide.get("dCan") or ""))
    cancelada = bool(nf.get("_cancelada")) or nf_cancelada(nf)
    obs = texto_observacao(nf)
    nf_origem = extrair_nf_origem(obs)
    for det in nf.get("det") or []:
        prod = det.get("prod") or {}
        cfop = norm_cfop(prod.get("CFOP"))
        tp = str(ide.get("tpNF") or "")
        if tp == "0" and cfop not in CFOP_ENTRADA:
            continue
        if tp == "1" and cfop not in CFOP_SAIDA:
            continue
        if tp not in ("0", "1"):
            continue
        qtde = float(prod.get("qCom") or prod.get("qTrib") or 0)
        if abs(qtde) < 1e-12:
            continue
        yield {
            "nf": nNF,
            "data": data,
            "data_canc": data_canc,
            "cancelada": cancelada,
            "produto": str(prod.get("xProd") or "").strip(),
            "codigo": str(prod.get("cProd") or "").strip(),
            "cfop": cfop,
            "qtde": qtde,
            "valor": float(prod.get("vProd") or prod.get("vTotItem") or 0),
            "obs": obs,
            "nf_origem": nf_origem,
            "tpNF": tp,
        }


def extrair_financeiro_5124(notas: list[dict]) -> list[dict]:
    """
    CFOP 5124: contabiliza valor da NF (financeiro).
    Não entra no cálculo de saldo de estoque.
    """
    por_nf: dict[str, dict] = {}
    for nf in notas:
        ide = nf.get("ide") or {}
        nNF = norm_nf(ide.get("nNF"))
        data = iso_de_br(str(ide.get("dEmi") or ""))
        itens_5124 = []
        for det in nf.get("det") or []:
            prod = det.get("prod") or {}
            cfop = norm_cfop(prod.get("CFOP"))
            if cfop not in CFOP_FINANCEIRO:
                continue
            itens_5124.append(
                {
                    "produto": str(prod.get("xProd") or "").strip(),
                    "codigo": str(prod.get("cProd") or "").strip(),
                    "qtde": float(prod.get("qCom") or prod.get("qTrib") or 0),
                    "valor_item": float(prod.get("vProd") or prod.get("vTotItem") or 0),
                }
            )
        if not itens_5124:
            continue
        v_nf = valor_total_nf(nf)
        # se a NF misturar CFOPs, usa soma só dos itens 5124
        outros = any(
            norm_cfop((d.get("prod") or {}).get("CFOP")) not in CFOP_FINANCEIRO
            for d in (nf.get("det") or [])
        )
        if outros:
            v_nf = sum(i["valor_item"] for i in itens_5124)
        chave = nNF
        if chave not in por_nf:
            por_nf[chave] = {
                "nf": nNF,
                "data": data,
                "data_canc": iso_de_br(str(ide.get("dCan") or "")),
                "cancelada": bool(nf.get("_cancelada")) or nf_cancelada(nf),
                "cfop": "5124",
                "cliente": dest_nome(nf),
                "valor_nf": round(v_nf, 2),
                "qtde": 0.0,
                "itens": 0,
                "move_estoque": False,
            }
        por_nf[chave]["qtde"] += sum(i["qtde"] for i in itens_5124)
        por_nf[chave]["itens"] += len(itens_5124)
        por_nf[chave]["valor_nf"] = round(v_nf, 2)
    out = list(por_nf.values())
    out.sort(key=lambda r: (r["data"] or "", r["nf"]))
    return out


def processar_notas(
    entradas_raw: list[dict],
    saidas_raw: list[dict],
    app_key: str | None = None,
    app_secret: str | None = None,
    enriquecer: bool = True,
) -> tuple[list[dict], list[dict], list[dict]]:
    if enriquecer and app_key and app_secret:
        enriquecer_obs_remessa(saidas_raw, app_key, app_secret)
    entradas = [it for nf in entradas_raw for it in iter_itens_estoque(nf)]
    saidas = [it for nf in saidas_raw for it in iter_itens_estoque(nf)]
    # 5124 costuma ser saída (industrialização); varre entrada e saída
    financeiro = extrair_financeiro_5124(entradas_raw + saidas_raw)
    return entradas, saidas, financeiro


def coletar(ini: date, fim: date) -> tuple[list[dict], list[dict], list[dict]]:
    key, secret = carregar_credenciais()
    print(f"Coletando NF-e 3R ({br_data(ini)} a {br_data(fim)}) — somente leitura…")
    entradas_raw = listar_nf_todas(ini, fim, "0", key, secret)
    saidas_raw = listar_nf_todas(ini, fim, "1", key, secret)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{ini:%Y%m%d}_{fim:%Y%m%d}"
    # cache bruto das NFs (sem segredo); obs da remessa é consultada a cada processamento
    (CACHE_DIR / f"nf_entrada_{tag}.json").write_text(
        json.dumps(entradas_raw, ensure_ascii=False), encoding="utf-8"
    )
    (CACHE_DIR / f"nf_saida_{tag}.json").write_text(
        json.dumps(saidas_raw, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  cache local: {CACHE_DIR}")
    return processar_notas(entradas_raw, saidas_raw, key, secret)


def carregar_cache(ini: date, fim: date) -> tuple[list[dict], list[dict], list[dict]]:
    tag = f"{ini:%Y%m%d}_{fim:%Y%m%d}"
    pe = CACHE_DIR / f"nf_entrada_{tag}.json"
    ps = CACHE_DIR / f"nf_saida_{tag}.json"
    if not pe.exists() or not ps.exists():
        die(f"Cache não encontrado em {CACHE_DIR} para o período. Rode sem --cache primeiro.")
    entradas_raw = json.loads(pe.read_text(encoding="utf-8"))
    saidas_raw = json.loads(ps.read_text(encoding="utf-8"))
    key, secret = carregar_credenciais()
    return processar_notas(entradas_raw, saidas_raw, key, secret)


def dados_demo() -> tuple[list[dict], list[dict], list[dict]]:
    """Exemplo do usuário + amostra para validar o painel sem API."""
    entradas = [
        {
            "nf": "12",
            "data": "2026-08-05",
            "produto": "Insumo A",
            "codigo": "INS-A",
            "cfop": "1901",
            "qtde": 10000.0,
            "valor": 50000.0,
            "obs": "",
            "nf_origem": None,
            "tpNF": "0",
        },
        {
            "nf": "15",
            "data": "2026-09-10",
            "produto": "Insumo B",
            "codigo": "INS-B",
            "cfop": "1901",
            "qtde": 4000.0,
            "valor": 18000.0,
            "obs": "",
            "nf_origem": None,
            "tpNF": "0",
        },
        {
            "nf": "20",
            "data": "2026-10-02",
            "produto": "Insumo A",
            "codigo": "INS-A",
            "cfop": "1901",
            "qtde": 2500.0,
            "valor": 12500.0,
            "obs": "",
            "nf_origem": None,
            "tpNF": "0",
        },
    ]
    saidas = [
        {
            "nf": "1",
            "data": "2026-08-20",
            "produto": "Insumo A",
            "codigo": "INS-A",
            "cfop": "5902",
            "qtde": 1000.0,
            "valor": 0.0,
            "obs": "NF origem 12",
            "nf_origem": "12",
            "tpNF": "1",
        },
        {
            "nf": "2",
            "data": "2026-09-15",
            "produto": "Insumo B",
            "codigo": "INS-B",
            "cfop": "5902",
            "qtde": 500.0,
            "valor": 0.0,
            "obs": "Consumo ref NF 15",
            "nf_origem": "15",
            "tpNF": "1",
        },
        {
            "nf": "3",
            "data": "2026-10-18",
            "produto": "Insumo A",
            "codigo": "INS-A",
            "cfop": "5902",
            "qtde": 800.0,
            "valor": 0.0,
            "obs": "origem 20",
            "nf_origem": "20",
            "tpNF": "1",
        },
        {
            "nf": "5",
            "data": "2026-11-05",
            "produto": "Insumo B",
            "codigo": "INS-B",
            "cfop": "5902",
            "qtde": 200.0,
            "valor": 0.0,
            "obs": "sem referencia clara",
            "nf_origem": None,
            "tpNF": "1",
        },
    ]
    # CFOP 5124: só financeiro — não entra em entradas/saídas de estoque
    financeiro = [
        {
            "nf": "30",
            "data": "2026-09-22",
            "cfop": "5124",
            "cliente": "Cliente industrialização XYZ",
            "valor_nf": 18500.0,
            "qtde": 1200.0,
            "itens": 1,
            "move_estoque": False,
        },
        {
            "nf": "31",
            "data": "2026-10-28",
            "cfop": "5124",
            "cliente": "Cliente industrialização ABC",
            "valor_nf": 9200.5,
            "qtde": 600.0,
            "itens": 1,
            "move_estoque": False,
        },
    ]
    return entradas, saidas, financeiro


def calcular_saldos(entradas: list[dict], saidas: list[dict]) -> list[dict]:
    """
    Agrupa por (NF origem, código produto).
    Entrada soma; saída com nf_origem abate do lote correspondente.
    Se o código não casar, abate pelo primeiro lote da mesma NF.
    """
    lotes: dict[tuple[str, str], dict] = {}
    ordem: list[tuple[str, str]] = []

    for e in entradas:
        chave = (e["nf"], e["codigo"] or e["produto"])
        if chave not in lotes:
            lotes[chave] = {
                "nf": e["nf"],
                "data": e["data"],
                "produto": e["produto"],
                "codigo": e["codigo"],
                "cfop": e["cfop"],
                "entrada": 0.0,
                "saida": 0.0,
            }
            ordem.append(chave)
        lotes[chave]["entrada"] += e["qtde"]
        if e["data"] and (not lotes[chave]["data"] or e["data"] < lotes[chave]["data"]):
            lotes[chave]["data"] = e["data"]

    por_nf: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for chave in ordem:
        por_nf[chave[0]].append(chave)

    for s in saidas:
        origem = s.get("nf_origem")
        if not origem:
            continue
        cod = s["codigo"] or s["produto"]
        chave = (origem, cod)
        if chave not in lotes:
            # tenta só pela NF de origem
            candidatos = por_nf.get(origem) or []
            if not candidatos:
                # cria lote fantasma negativo para evidenciar saída sem entrada no período
                chave = (origem, cod or "?")
                lotes[chave] = {
                    "nf": origem,
                    "data": s["data"],
                    "produto": s["produto"] or "(sem entrada no período)",
                    "codigo": s["codigo"],
                    "cfop": "",
                    "entrada": 0.0,
                    "saida": 0.0,
                }
                ordem.append(chave)
                por_nf[origem].append(chave)
            else:
                chave = candidatos[0]
        lotes[chave]["saida"] += s["qtde"]

    saldos: list[dict] = []
    for chave in ordem:
        r = lotes[chave]
        entrada = r["entrada"]
        saida = r["saida"]
        saldo = entrada - saida
        pct_rest = (saldo / entrada) if entrada > 1e-12 else (0.0 if saida > 0 else 1.0)
        saldos.append(
            {
                "nf": r["nf"],
                "data": r["data"],
                "produto": r["produto"],
                "codigo": r["codigo"],
                "cfop": r["cfop"],
                "entrada": round(entrada, 6),
                "saida": round(saida, 6),
                "saldo": round(saldo, 6),
                "pct_restante": max(pct_rest, 0.0) if saldo >= 0 else pct_rest,
            }
        )
    # Ordem de entrada da NF de origem (data, depois número)
    saldos.sort(key=lambda x: (x.get("data") or "", int(re.sub(r"\D", "", str(x.get("nf") or "0")) or 0)))
    return saldos


def css_painel() -> str:
    if not PAINEL_CSS.exists():
        die(f"CSS base não encontrado: {PAINEL_CSS}")
    return PAINEL_CSS.read_text(encoding="utf-8")


def gerar_html(
    meta: dict,
    saldos: list[dict],
    entradas: list[dict],
    saidas: list[dict],
    financeiro: list[dict],
) -> str:
    if not TEMPLATE.exists():
        die(f"Template não encontrado: {TEMPLATE}")
    if not CHART_JS.exists():
        die(f"Chart.js não encontrado: {CHART_JS}")
    payload = {
        "meta": meta,
        "saldos": saldos,
        "entradas": entradas,
        "saidas": saidas,
        "financeiro_5124": financeiro,
    }
    estatico = dict(payload)
    dados_js = json.dumps(estatico, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = TEMPLATE.read_text(encoding="utf-8")
    out = tpl.replace("/*__PAINEL_STYLES__*/", css_painel())
    out = out.replace("/*__CHART_JS__*/", CHART_JS.read_text(encoding="utf-8"))
    out = out.replace("__PAYLOAD__", body)
    return out.replace("</head>", f"<script>window.__STATIC__={dados_js};</script>\n</head>", 1)


def montar_dashboard(ini: date, fim: date, *, demo: bool = False, usar_cache: bool = False) -> str:
    """Gera o HTML do painel (string). Não grava segredos."""
    if demo:
        entradas, saidas, financeiro = dados_demo()
        fonte = "demo"
    elif usar_cache:
        entradas, saidas, financeiro = carregar_cache(ini, fim)
        fonte = "cache local"
    else:
        entradas, saidas, financeiro = coletar(ini, fim)

    saldos = calcular_saldos(entradas, saidas)
    tot_fin = sum(float(r.get("valor_nf") or 0) for r in financeiro)
    meta = {
        "empresa": "3R Indústria",
        "periodo": f"{br_data(ini)} a {br_data(fim)}",
        "historico_desde": ini.isoformat(),
        "historico_ate": fim.isoformat(),
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "fonte": fonte,
        "cfop_entrada": "1901",
        "cfop_saida": "5902",
        "cfop_financeiro": "5124",
        "regra": (
            "Estoque: 1901 entrada / 5902 saída (obs. REFERENTE A NF = origem). "
            "Saída sem referência não abate saldo por lote. "
            "CFOP 5124 só valor financeiro. Posição: inicial + movimento = final."
        ),
        "financeiro_5124_total": round(tot_fin, 2),
    }
    return gerar_html(meta, saldos, entradas, saidas, financeiro)


def main() -> None:
    hoje = date.today()
    p = argparse.ArgumentParser(description="Dashboard estoque 3R Indústria (Omie, somente leitura).")
    p.add_argument("--de", default="01/01/2026", help="Data inicial (dd/mm/aaaa).")
    p.add_argument("--ate", default=hoje.strftime("%d/%m/%Y"), help="Data final (dd/mm/aaaa).")
    p.add_argument("--demo", action="store_true", help="Gera painel com dados de exemplo (sem API).")
    p.add_argument("--cache", action="store_true", help="Usa JSON já baixado no cache local.")
    p.add_argument("--abrir", action="store_true", help="Abre o HTML no navegador ao terminar.")
    args = p.parse_args()

    ini = datetime.strptime(args.de, "%d/%m/%Y").date()
    fim = datetime.strptime(args.ate, "%d/%m/%Y").date()
    if fim < ini:
        die("Data final anterior à inicial.")

    html = montar_dashboard(ini, fim, demo=args.demo, usar_cache=args.cache)
    SAIDA_DIR.mkdir(exist_ok=True)
    out = SAIDA_DIR / f"Dashboard_Estoque_3R_Industria_{ini.isoformat()}_a_{fim.isoformat()}.html"
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard: {out}")

    if args.abrir:
        os.startfile(str(out))  # noqa: S606 — abrir HTML local no Windows


if __name__ == "__main__":
    main()
