from fastapi import FastAPI, HTTPException

import cache
import nba_dados

app = FastAPI(title="Scoresports pessoal")


def _obter(chave, ttl, buscar):
    try:
        return cache.obter(chave, ttl, buscar)
    except Exception:
        raise HTTPException(status_code=502, detail="Não foi possível obter dados da NBA agora.")


@app.get("/jogos")
def jogos():
    return _obter("jogos", 15, nba_dados.buscar_jogos)


@app.get("/jogos/{game_id}/boxscore")
def boxscore(game_id: str):
    return _obter(f"boxscore:{game_id}", 15, lambda: nba_dados.buscar_boxscore(game_id))


@app.get("/classificacao")
def classificacao():
    return _obter("classificacao_v2", 3600, nba_dados.buscar_classificacao)