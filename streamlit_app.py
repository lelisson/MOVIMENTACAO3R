# -*- coding: utf-8 -*-
"""Painel 3R Indústria — controle de estoque (Omie, somente leitura) no Streamlit Cloud."""

from __future__ import annotations

from datetime import date

import streamlit as st
import streamlit.components.v1 as components

from estoque3r import montar_dashboard

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


def _ler_secret(nome: str) -> str:
    try:
        val = st.secrets.get(nome, "")
        return str(val or "").strip()
    except Exception:
        return ""


def _tem_credenciais() -> bool:
    return bool(_ler_secret("OMIE_3R_APP_KEY") and _ler_secret("OMIE_3R_APP_SECRET"))


@st.cache_data(ttl=30 * 60, show_spinner=False)
def _html_painel(cache_key: str) -> str:
    _ = cache_key
    ini = date(2026, 1, 1)
    fim = date.today()
    # Sempre dados reais da Omie (chaves vêm de st.secrets / env)
    return montar_dashboard(ini, fim, demo=False)


def main() -> None:
    if "refresh_nonce" not in st.session_state:
        st.session_state.refresh_nonce = 0

    qp = st.query_params
    if qp.get("refresh"):
        st.session_state.refresh_nonce += 1
        _html_painel.clear()
        st.query_params.clear()

    if not _tem_credenciais():
        st.markdown(
            """
            <div style="max-width:720px;margin:48px auto;padding:28px 32px;background:#111622;
                        border:1px solid #1e2636;border-radius:12px;color:#e7ecf5;font-family:system-ui,sans-serif">
              <h2 style="margin:0 0 12px;font-size:20px">Faltam as chaves da Omie</h2>
              <p style="margin:0 0 14px;color:#9ba7ba;line-height:1.5">
                Sem <code>OMIE_3R_APP_KEY</code> e <code>OMIE_3R_APP_SECRET</code> o painel
                <b>não consulta a Omie</b>. Configure nos Secrets da Cloud (nunca no GitHub):
              </p>
              <ol style="color:#9ba7ba;line-height:1.6;margin:0 0 16px;padding-left:20px">
                <li>No app Streamlit → ⋮ → <b>Settings</b> → <b>Secrets</b></li>
                <li>Cole o bloco abaixo e salve</li>
                <li>Faça <b>Reboot app</b></li>
              </ol>
              <pre style="background:#0a0d14;border:1px solid #1e2636;border-radius:8px;
                          padding:14px;overflow:auto;color:#a5b4fc;font-size:13px">OMIE_3R_APP_KEY = "sua_app_key_aqui"
OMIE_3R_APP_SECRET = "sua_app_secret_aqui"</pre>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    cache_key = f"{date.today().isoformat()}-{st.session_state.refresh_nonce}"
    try:
        with st.spinner("Consultando Omie (somente leitura)…"):
            html = _html_painel(cache_key)
    except SystemExit as e:
        st.error(str(e) or "Falha ao montar o painel.")
        return
    except Exception as e:
        st.error(f"Erro ao montar o painel: {e}")
        return

    components.html(html, height=1400, scrolling=True)


if __name__ == "__main__":
    main()
