# -*- coding: utf-8 -*-
"""Painel 3R — só exibe o HTML gerado pelo GitHub Actions (sem chaves Omie).

Botão Atualizar → ?force_refresh=1 → avisa o Actions via ntfy.sh e espera
o HTML novo. Sem secrets no Streamlit.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
DASHBOARD = ROOT / "public" / "dashboard.html"
CHANNEL_FILE = ROOT / "public" / "force_channel.txt"
REPO = "lelisson/MOVIMENTACAO3R"
RAW_DASHBOARD = (
    f"https://raw.githubusercontent.com/{REPO}/main/public/dashboard.html"
)
RAW_META = (
    f"https://raw.githubusercontent.com/{REPO}/main/public/last_publish.json"
)
RAW_CHANNEL = (
    f"https://raw.githubusercontent.com/{REPO}/main/public/force_channel.txt"
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


def _http_text(url: str, *, bust: bool = True, timeout: int = 60) -> str:
    full = f"{url}?t={int(time.time())}" if bust else url
    req = urllib.request.Request(
        full,
        headers={
            "User-Agent": "MOVIMENTACAO3R-streamlit",
            "Cache-Control": "no-cache",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def _http_post(url: str, body: bytes, content_type: str = "text/plain") -> None:
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": "MOVIMENTACAO3R-streamlit",
            "Content-Type": content_type,
            "Title": "force-omie-3r",
            "Priority": "high",
            "Tags": "arrows_counterclockwise",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def _meta_published_at() -> str:
    try:
        text = _http_text(RAW_META)
        return str(json.loads(text).get("published_at") or "")
    except Exception:
        return ""


def _force_channel() -> str:
    if CHANNEL_FILE.exists():
        ch = CHANNEL_FILE.read_text(encoding="utf-8").strip()
        if ch:
            return ch
    try:
        return _http_text(RAW_CHANNEL).strip()
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


def _wait_new_publish(before: str, status, started_at: float) -> bool:
    deadline = time.time() + 12 * 60
    while time.time() < deadline:
        elapsed = int(time.time() - started_at)
        status.update(
            label=f"Coletando Omie… aguardando publicação ({elapsed}s)",
            state="running",
        )
        now = _meta_published_at()
        if now and now != before:
            status.update(label="Dados atualizados.", state="complete")
            return True
        time.sleep(8)
    status.update(
        label="Ainda não saiu publicação nova. O Actions roda a cada ~5 min — tente de novo em breve.",
        state="error",
    )
    return False


def _force_refresh() -> None:
    channel = _force_channel()
    if not channel:
        st.error("Canal de atualização forçada não encontrado (public/force_channel.txt).")
        if st.button("Voltar ao painel"):
            st.query_params.clear()
            st.rerun()
        return

    before = _meta_published_at()
    started = time.time()
    status = st.status("Disparando atualização forçada na Omie…", expanded=True)
    try:
        _http_post(
            f"https://ntfy.sh/{channel}",
            b"force omie atualizar",
        )
        status.write(
            "Pedido enviado. O GitHub Actions deve coletar a Omie em até alguns minutos "
            "e reiniciar a janela de 4 horas."
        )
    except urllib.error.HTTPError as exc:
        status.update(label=f"Falha ao sinalizar force (HTTP {exc.code})", state="error")
        return
    except Exception as exc:  # noqa: BLE001
        status.update(label=f"Falha ao sinalizar force: {exc}", state="error")
        return

    ok = _wait_new_publish(before, status, started)
    st.query_params.clear()
    if ok:
        try:
            st.cache_data.clear()
        except Exception:
            pass
        time.sleep(1)
        st.rerun()
    elif st.button("Voltar ao painel"):
        st.rerun()


def main() -> None:
    if st.query_params.get("force_refresh"):
        _force_refresh()
        return

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
                Os dados vêm de <code>public/dashboard.html</code>, gerado pelo GitHub Actions.
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    components.html(html, height=1400, scrolling=True)


if __name__ == "__main__":
    main()
