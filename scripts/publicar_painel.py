# -*- coding: utf-8 -*-
"""Gera public/dashboard.html a partir da Omie (somente leitura).

Usado no GitHub Actions. Chaves vêm de OMIE_3R_APP_KEY / OMIE_3R_APP_SECRET
(no Actions: Secrets do repositório — nunca no Streamlit).
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Cache da CI (remessas etc.) — pasta local do runner, não vai para o git
os.environ.setdefault("ESTOQUE3R_CACHE", str(ROOT / "cache_ci"))

from estoque3r import montar_dashboard  # noqa: E402

SP = ZoneInfo("America/Sao_Paulo")


def main() -> int:
    ini = date(2026, 1, 1)
    fim = date.today()
    source = os.environ.get("PUBLISH_SOURCE", "schedule").strip() or "schedule"
    print(f"Publicando painel 3R {ini} a {fim}… (source={source})")
    html = montar_dashboard(ini, fim, demo=False, usar_cache=False)
    out = ROOT / "public" / "dashboard.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    agora = datetime.now(SP)
    meta = {
        "published_at": agora.isoformat(),
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "periodo_ate": fim.isoformat(),
        "bytes": out.stat().st_size,
    }
    meta_path = ROOT / "public" / "last_publish.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OK: {out} ({meta['bytes']} bytes)")
    print(f"META: {meta_path} published_at={meta['published_at']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
