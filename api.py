import logging
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import cache
import nba_dados

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Scoresports pessoal")

PASTA_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=PASTA_STATIC), name="static")

# Tempo de validade do cache (em segundos) dos dados que mudam durante o jogo.
# Fica um pouco abaixo do intervalo de atualização da página (10 s).
TTL_AO_VIVO = 8


@app.get("/", include_in_schema=False)
def raiz():
    return FileResponse(PASTA_STATIC / "index.html")


def _obter(chave, ttl, buscar):
    try:
        return cache.obter(chave, ttl, buscar)
    except Exception:
        logger.exception("Falha ao obter '%s'", chave)
        raise HTTPException(status_code=502, detail="Não foi possível obter dados da NBA agora.")


def _hoje():
    return datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")


def _calendario():
    return _obter("calendario_v2", 600, nba_dados.buscar_calendario)


def _ao_vivo():
    try:
        return {j["id"]: j for j in cache.obter("jogos_v2", TTL_AO_VIVO, nba_dados.buscar_jogos)}
    except Exception:
        return {}


@app.get("/datas")
def datas():
    agenda = _calendario()
    return {"datas": sorted({j["data"] for j in agenda}), "hoje": _hoje()}


@app.get("/jogos")
def jogos(data: str | None = None):
    agenda = _calendario()
    data = data or _hoje()
    ao_vivo = _ao_vivo()
    do_dia = [j for j in agenda if j["data"] == data]
    # se o jogo está no placar ao vivo, usa essa versão (mais atual e com líderes)
    return [ao_vivo.get(j["id"], j) for j in do_dia]


@app.get("/jogos/{game_id}/boxscore")
def boxscore(game_id: str):
    return _obter(f"boxscore_v3:{game_id}", TTL_AO_VIVO, lambda: nba_dados.buscar_boxscore(game_id))


@app.get("/jogadores/{player_id}")
def jogador(player_id: int):
    return _obter(f"jogador_v1:{player_id}", 600, lambda: nba_dados.buscar_jogador(player_id))


@app.get("/lideres")
def lideres(modo: Literal["media", "total"] = "media"):
    # uma única consulta (totais de todos os jogadores) serve para as duas visões
    jogadores = _obter("stats_jogadores_v1", 1800, nba_dados.buscar_stats_jogadores)
    return nba_dados.montar_lideres(jogadores, modo)


@app.get("/corridas")
def corridas():
    # os rankings da NBA saem uma vez por semana, então 2 horas de cache bastam
    return _obter("corridas_v1", 7200, nba_dados.buscar_corridas)


@app.get("/classificacao")
def classificacao():
    return _obter("classificacao_v2", 3600, nba_dados.buscar_classificacao)