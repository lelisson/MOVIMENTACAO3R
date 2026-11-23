# -*- coding: utf-8 -*-
"""Decide se a publicação automática deve rodar (janela de 4 horas).

Exit 0 + imprime RUN=yes|no para o workflow.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
META = ROOT / "public" / "last_publish.json"
JANELA = timedelta(hours=4)


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def main() -> int:
    force = os.environ.get("FORCE_PUBLISH", "").strip().lower() in {"1", "true", "yes"}
    if force:
        print("RUN=yes")
        print("Motivo: atualização forçada")
        return 0

    if not META.exists():
        print("RUN=yes")
        print("Motivo: ainda não há last_publish.json")
        return 0

    try:
        data = json.loads(META.read_text(encoding="utf-8"))
        published = _parse(str(data["published_at"]))
    except Exception as exc:  # noqa: BLE001
        print("RUN=yes")
        print(f"Motivo: meta inválida ({exc})")
        return 0

    agora = datetime.now(timezone.utc)
    idade = agora - published.astimezone(timezone.utc)
    restante = JANELA - idade
    if idade >= JANELA:
        print("RUN=yes")
        print(f"Motivo: última publicação há {idade}")
        return 0

    print("RUN=no")
    print(
        f"Motivo: dentro da janela de 4h "
        f"(última {published.isoformat()}, falta ~{restante})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
