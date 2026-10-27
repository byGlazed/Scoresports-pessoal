from fastapi import FastAPI, HTTPException

import cache
import nba_dados

from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from datetime import datetime
from zoneinfo import ZoneInfo

app = FastAPI(title="Scoresports pessoal")

PASTA_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=PASTA_STATIC), name="static")


@app.get("/", include_in_schema=False)
def raiz():
    return FileResponse(PASTA_STATIC / "index.html")

def _obter(chave, ttl, buscar):
    try:
        return cache.obter(chave, ttl, buscar)
    except Exception:
        raise HTTPException(status_code=502, detail="Não foi possível obter dados da NBA agora.")


def _hoje():
    # a NBA organiza as datas pelo horário da costa leste dos EUA
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


def _ao_vivo():
    try:
        return {j["id"]: j for j in cache.obter("jogos", 15, nba_dados.buscar_jogos)}
    except Exception:
        return {}


@app.get("/datas")
def datas():
    agenda = _obter("calendario", 600, nba_dados.buscar_calendario)
    return {"datas": sorted({j["data"] for j in agenda}), "hoje": _hoje()}


@app.get("/jogos")
def jogos(data: str | None = None):
    agenda = _obter("calendario", 600, nba_dados.buscar_calendario)
    data = data or _hoje()
    ao_vivo = _ao_vivo()
    do_dia = [j for j in agenda if j["data"] == data]
    # se o jogo está no placar ao vivo, usa essa versão (mais atual e com líderes)
    return [ao_vivo.get(j["id"], j) for j in do_dia]


@app.get("/jogos/{game_id}/boxscore")
def boxscore(game_id: str):
    return _obter(f"boxscore:{game_id}", 15, lambda: nba_dados.buscar_boxscore(game_id))


@app.get("/classificacao")
def classificacao():
    return _obter("classificacao_v2", 3600, nba_dados.buscar_classificacao)