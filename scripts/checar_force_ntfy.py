# -*- coding: utf-8 -*-
"""Verifica se houve pedido de atualização forçada via ntfy.sh.

Imprime FORCE=yes|no. Sem secrets no Streamlit: o painel só publica
uma mensagem no tópico; este script (no Actions) lê a fila.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANNEL_FILE = ROOT / "public" / "force_channel.txt"
META = ROOT / "public" / "last_publish.json"
# só aceita pedidos recentes (evita reprocessar mensagens antigas)
JANELA = timedelta(minutes=20)


def _get(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "MOVIMENTACAO3R-actions", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _last_publish() -> datetime | None:
    if not META.exists():
        return None
    try:
        data = json.loads(META.read_text(encoding="utf-8"))
        ts = str(data.get("published_at_utc") or data.get("published_at") or "")
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def main() -> int:
    channel = CHANNEL_FILE.read_text(encoding="utf-8").strip()
    if not channel:
        print("FORCE=no")
        print("Motivo: force_channel.txt vazio")
        return 0

    last = _last_publish()
    # ntfy aceita duração (10m) ou unix; ISO costuma dar 400
    url = f"https://ntfy.sh/{channel}/json?poll=1&since=20m"
    try:
        raw = _get(url)
    except urllib.error.HTTPError as exc:
        print("FORCE=no")
        print(f"Motivo: ntfy HTTP {exc.code}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print("FORCE=no")
        print(f"Motivo: ntfy erro ({exc})")
        return 0

    agora = datetime.now(timezone.utc)
    # cada linha é um JSON (ou vazio)
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        event = str(msg.get("event") or "")
        if event and event != "message":
            continue
        # ignora mensagens anteriores à última publicação
        try:
            msg_time = datetime.fromtimestamp(int(msg.get("time") or 0), tz=timezone.utc)
        except Exception:
            msg_time = agora
        if last and msg_time <= last:
            continue
        if msg_time < agora - JANELA:
            continue
        text = str(msg.get("message") or msg.get("title") or "").lower()
        if "force" in text or "atualizar" in text or "omie" in text:
            print("FORCE=yes")
            print(f"Motivo: pedido ntfy id={msg.get('id')} msg={text[:80]!r}")
            return 0

    print("FORCE=no")
    print("Motivo: nenhum pedido recente no ntfy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
