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
      /* ocupa a viewport sem faixas laterais */
      section.main > div {padding-left: 0 !important; padding-right: 0 !important;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _tem_credenciais() -> bool:
    try:
        k = str(st.secrets.get("OMIE_3R_APP_KEY", "") or "").strip()
        s = str(st.secrets.get("OMIE_3R_APP_SECRET", "") or "").strip()
        return bool(k and s)
    except Exception:
        return False


@st.cache_data(ttl=30 * 60, show_spinner=False)
def _html_painel(cache_key: str, demo: bool) -> str:
    _ = cache_key
    ini = date(2026, 1, 1)
    fim = date.today()
    return montar_dashboard(ini, fim, demo=demo)


def main() -> None:
    if "refresh_nonce" not in st.session_state:
        st.session_state.refresh_nonce = 0

    # Botão Atualizar do HTML (?refresh=) limpa cache e recarrega
    qp = st.query_params
    if qp.get("refresh"):
        st.session_state.refresh_nonce += 1
        _html_painel.clear()
        st.query_params.clear()

    demo = not _tem_credenciais()
    cache_key = f"{date.today().isoformat()}-{st.session_state.refresh_nonce}"

    try:
        with st.spinner("Carregando painel 3R…"):
            html = _html_painel(cache_key, demo)
    except SystemExit as e:
        st.error(str(e) or "Falha ao montar o painel.")
        return
    except Exception as e:
        st.error(f"Erro ao montar o painel: {e}")
        return

    # Altura generosa para preencher a tela; o painel HTML já é full-bleed
    components.html(html, height=1400, scrolling=True)


if __name__ == "__main__":
    main()
