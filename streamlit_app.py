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
      #MainMenu, footer, header {visibility: hidden;}
      .block-container {padding-top: 0.4rem; padding-bottom: 0; max-width: 100%;}
      iframe {border: none !important;}
      div[data-testid="stToolbar"] {display: none;}
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

    # Botão do HTML (?refresh=) ou botão do Streamlit
    qp = st.query_params
    if qp.get("refresh"):
        st.session_state.refresh_nonce += 1
        _html_painel.clear()
        st.query_params.clear()

    bar = st.columns([4, 1.2, 1.2])
    with bar[0]:
        st.caption("3R Indústria · estoque Omie (somente leitura)")
    with bar[1]:
        if st.button("Atualizar", type="primary", use_container_width=True):
            st.session_state.refresh_nonce += 1
            _html_painel.clear()
            st.rerun()
    with bar[2]:
        st.caption(f"cache #{st.session_state.refresh_nonce}")

    demo = not _tem_credenciais()
    if demo:
        st.info(
            "Configure OMIE_3R_APP_KEY e OMIE_3R_APP_SECRET em "
            "Settings → Secrets do Streamlit Cloud. Nenhum segredo deve ir para o GitHub."
        )

    cache_key = f"{date.today().isoformat()}-{st.session_state.refresh_nonce}"
    try:
        with st.spinner("Carregando painel 3R (somente leitura na Omie)…"):
            html = _html_painel(cache_key, demo)
    except SystemExit as e:
        st.error(str(e) or "Falha ao montar o painel.")
        return
    except Exception as e:
        st.error(f"Erro ao montar o painel: {e}")
        return

    components.html(html, height=1200, scrolling=True)


if __name__ == "__main__":
    main()
