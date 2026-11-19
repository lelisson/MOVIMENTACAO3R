# -*- coding: utf-8 -*-
"""Gera public/dashboard.html a partir da Omie (somente leitura).

Usado no GitHub Actions. Chaves vêm de OMIE_3R_APP_KEY / OMIE_3R_APP_SECRET
(no Actions: Secrets do repositório — nunca no Streamlit).
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Cache da CI (remessas etc.) — pasta local do runner, não vai para o git
os.environ.setdefault("ESTOQUE3R_CACHE", str(ROOT / "cache_ci"))

from estoque3r import montar_dashboard  # noqa: E402


def main() -> int:
    ini = date(2026, 1, 1)
    fim = date.today()
    print(f"Publicando painel 3R {ini} a {fim}…")
    html = montar_dashboard(ini, fim, demo=False, usar_cache=False)
    out = ROOT / "public" / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"OK: {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
