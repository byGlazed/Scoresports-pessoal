import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "cache.db"


def _conectar():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL,
            atualizado_em REAL NOT NULL
        )
        """
    )
    return conn


def obter(chave, ttl_segundos, buscar):
    """Devolve o dado do cache se ainda for recente; senão chama buscar()."""
    conn = _conectar()
    try:
        linha = conn.execute(
            "SELECT valor, atualizado_em FROM cache WHERE chave = ?", (chave,)
        ).fetchone()

        if linha and time.time() - linha[1] < ttl_segundos:
            return json.loads(linha[0])

        try:
            dados = buscar()
        except Exception:
            if linha:
                return json.loads(linha[0])  # API falhou: usa o dado antigo
            raise

        conn.execute(
            "INSERT OR REPLACE INTO cache (chave, valor, atualizado_em) VALUES (?, ?, ?)",
            (chave, json.dumps(dados, default=str), time.time()),
        )
        conn.commit()
        return dados
    finally:
        conn.close()