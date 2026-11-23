# -*- coding: utf-8 -*-
"""Painel 3R — só exibe o HTML gerado pelo GitHub Actions (sem chaves Omie).

O botão Atualizar do HTML chama ?force_refresh=1. Com o secret
GH_DISPATCH_TOKEN no Streamlit, dispara o workflow e espera o HTML novo.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

DASHBOARD = Path(__file__).resolve().parent / "public" / "dashboard.html"
REPO = "lelisson/MOVIMENTACAO3R"
WORKFLOW_FILE = "publicar.yml"
RAW_DASHBOARD = (
    f"https://raw.githubusercontent.com/{REPO}/main/public/dashboard.html"
)
RAW_META = (
    f"https://raw.githubusercontent.com/{REPO}/main/public/last_publish.json"
)
API_DISPATCH = (
    f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
)
API_RUNS = (
    f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_FILE}/runs"
    "?per_page=1&event=workflow_dispatch"
)

st.set_page_config(
    page_title="Estoque · 3R Indústria",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      html, body, [data-testid="stAppViewContainer"] {
        background: #0a0d14 !important;
      }
      #MainMenu, footer, header {visibility: hidden; height: 0;}
      [data-testid="stHeader"] {display: none;}
      [data-testid="stToolbar"] {display: none;}
      [data-testid="stDecoration"] {display: none;}
      [data-testid="stSidebar"] {display: none !important;}
      .block-container {
        padding: 0 !important;
        margin: 0 !important;
        max-width: 100% !important;
        width: 100% !important;
      }
      div[data-testid="stVerticalBlock"] {gap: 0 !important;}
      iframe {
        border: none !important;
        width: 100% !important;
        min-height: 100vh !important;
      }
      section.main > div {padding-left: 0 !important; padding-right: 0 !important;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _secret(name: str) -> str:
    try:
        val = st.secrets.get(name)  # type: ignore[attr-defined]
    except Exception:
        return ""
    if val is None:
        return ""
    return str(val).strip()


def _http_json(url: str, *, token: str = "", method: str = "GET", body: dict | None = None) -> dict | list | None:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "MOVIMENTACAO3R-streamlit",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read().decode("utf-8")
        if not raw:
            return None
        return json.loads(raw)


def _http_text(url: str, *, bust: bool = True) -> str:
    full = f"{url}?t={int(time.time())}" if bust else url
    req = urllib.request.Request(
        full,
        headers={
            "User-Agent": "MOVIMENTACAO3R-streamlit",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def _meta_published_at() -> str:
    try:
        text = _http_text(RAW_META)
        return str(json.loads(text).get("published_at") or "")
    except Exception:
        return ""


def _load_html() -> str:
    try:
        html = _http_text(RAW_DASHBOARD)
        if html and len(html) > 1000 and "<html" in html.lower():
            return html
    except Exception:
        pass
    if DASHBOARD.exists():
        return DASHBOARD.read_text(encoding="utf-8")
    return ""


def _dispatch_force(token: str) -> None:
    _http_json(
        API_DISPATCH,
        token=token,
        method="POST",
        body={"ref": "main", "inputs": {"force": "true"}},
    )


def _wait_publish(token: str, before: str, status, started_at: float) -> bool:
    """Espera o workflow forçado terminar e o last_publish.json mudar."""
    deadline = time.time() + 12 * 60
    saw_run = False
    while time.time() < deadline:
        try:
            # Confere meta primeiro (mais confiável após o push)
            now_meta = _meta_published_at()
            if now_meta and now_meta != before:
                status.update(label="Dados atualizados.", state="complete")
                return True

            runs = _http_json(API_RUNS, token=token) or {}
            items = runs.get("workflow_runs") if isinstance(runs, dict) else None
            run = None
            if items:
                for candidate in items:
                    # aceita run criado perto do disparo
                    created = candidate.get("created_at") or ""
                    run = candidate
                    if created:
                        break
            if run:
                saw_run = True
                conclusion = run.get("conclusion")
                status_run = run.get("status")
                elapsed = int(time.time() - started_at)
                status.update(
                    label=f"Coletando Omie… {status_run or '?'} ({elapsed}s)",
                    state="running",
                )
                if status_run == "completed" and conclusion != "success":
                    status.update(
                        label=f"Publicação falhou ({conclusion})",
                        state="error",
                    )
                    return False
        except Exception as exc:  # noqa: BLE001
            status.update(label=f"Aguardando Actions… ({exc})", state="running")
        time.sleep(8 if saw_run else 4)
    status.update(label="Tempo esgotado aguardando a publicação.", state="error")
    return False


def _force_refresh() -> None:
    token = _secret("GH_DISPATCH_TOKEN")
    if not token:
        st.error(
            "Para o botão **Atualizar** forçar a Omie, cadastre o secret "
            "`GH_DISPATCH_TOKEN` no Streamlit Cloud "
            "(PAT GitHub com permissão `actions:write` neste repositório). "
            "Chaves Omie continuam só no GitHub Actions."
        )
        st.link_button(
            "Abrir workflow no GitHub",
            f"https://github.com/{REPO}/actions/workflows/{WORKFLOW_FILE}",
        )
        if st.button("Voltar ao painel"):
            st.query_params.clear()
            st.rerun()
        return

    before = _meta_published_at()
    started = time.time()
    status = st.status("Disparando atualização forçada na Omie…", expanded=True)
    try:
        _dispatch_force(token)
        status.write("Workflow disparado. Coleta em andamento (pode levar alguns minutos).")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        status.update(label=f"Falha ao disparar Actions (HTTP {exc.code})", state="error")
        st.code(detail)
        return
    except Exception as exc:  # noqa: BLE001
        status.update(label=f"Falha ao disparar Actions: {exc}", state="error")
        return

    ok = _wait_publish(token, before, status, started)
    st.query_params.clear()
    if ok:
        st.cache_data.clear()
        time.sleep(1)
        st.rerun()


def main() -> None:
    if st.query_params.get("force_refresh"):
        _force_refresh()
        return

    # ?refresh= só recarrega a página (HTML já publicado)
    if st.query_params.get("refresh"):
        st.query_params.clear()
        st.rerun()

    html = _load_html()
    if not html:
        st.markdown(
            """
            <div style="max-width:720px;margin:48px auto;padding:28px 32px;background:#111622;
                        border:1px solid #1e2636;border-radius:12px;color:#e7ecf5;font-family:system-ui,sans-serif">
              <h2 style="margin:0 0 12px;font-size:20px">Painel ainda não publicado</h2>
              <p style="margin:0;color:#9ba7ba;line-height:1.5">
                O Streamlit <b>não usa chave Omie</b>. Os dados vêm de
                <code>public/dashboard.html</code>, gerado pelo GitHub Actions.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    components.html(html, height=1400, scrolling=True)


if __name__ == "__main__":
    main()
