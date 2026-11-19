# -*- coding: utf-8 -*-
"""Painel 3R — só exibe o HTML gerado pelo GitHub Actions (sem chaves Omie no Streamlit)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

DASHBOARD = Path(__file__).resolve().parent / "public" / "dashboard.html"

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


def main() -> None:
    # ?refresh= no HTML só recarrega a página (busca o HTML já publicado)
    if st.query_params.get("refresh"):
        st.query_params.clear()
        st.rerun()

    if not DASHBOARD.exists():
        st.markdown(
            """
            <div style="max-width:720px;margin:48px auto;padding:28px 32px;background:#111622;
                        border:1px solid #1e2636;border-radius:12px;color:#e7ecf5;font-family:system-ui,sans-serif">
              <h2 style="margin:0 0 12px;font-size:20px">Painel ainda não publicado</h2>
              <p style="margin:0;color:#9ba7ba;line-height:1.5">
                O Streamlit <b>não usa chave Omie</b>. Os dados vêm do arquivo
                <code>public/dashboard.html</code>, gerado pelo GitHub Actions.
              </p>
              <ol style="color:#9ba7ba;line-height:1.6;margin:16px 0 0;padding-left:20px">
                <li>No GitHub → Settings → Secrets → Actions → cadastre
                    <code>OMIE_3R_APP_KEY</code> e <code>OMIE_3R_APP_SECRET</code></li>
                <li>Actions → <b>Publicar painel Omie</b> → Run workflow</li>
                <li>Recarregue este app</li>
              </ol>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    html = DASHBOARD.read_text(encoding="utf-8")
    components.html(html, height=1400, scrolling=True)


if __name__ == "__main__":
    main()
