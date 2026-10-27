import re

TEMPORADA = "2026-27"


def _minutos(valor):
    m = re.match(r"PT(\d+)M(\d+)", valor or "")
    return f"{int(m.group(1))}:{m.group(2)}" if m else None


def _lider(l):
    if not l.get("name"):
        return None
    return {"nome": l["name"], "pts": l["points"], "reb": l["rebounds"], "ast": l["assists"]}


def _time_jogo(t, lider):
    return {
        "sigla": t["teamTricode"],
        "nome": f"{t['teamCity']} {t['teamName']}",
        "placar": t["score"],
        "lider": _lider(lider),
    }


def buscar_jogos():
    from nba_api.live.nba.endpoints import scoreboard

    jogos = scoreboard.ScoreBoard().games.get_dict()
    return [
        {
            "id": j["gameId"],
            "status": j["gameStatusText"],
            "fora": _time_jogo(j["awayTeam"], j["gameLeaders"]["awayLeaders"]),
            "casa": _time_jogo(j["homeTeam"], j["gameLeaders"]["homeLeaders"]),
        }
        for j in jogos
    ]


def _time_box(t):
    jogadores = []
    for j in t["players"]:
        s = j["statistics"]
        minutos = _minutos(s["minutes"])
        if minutos is None:
            continue  # não jogou
        jogadores.append(
            {
                "nome": j["name"],
                "min": minutos,
                "pts": s["points"],
                "reb": s["reboundsTotal"],
                "ast": s["assists"],
            }
        )
    jogadores.sort(key=lambda x: x["pts"], reverse=True)
    return {
        "sigla": t["teamTricode"],
        "nome": f"{t['teamCity']} {t['teamName']}",
        "placar": t["score"],
        "jogadores": jogadores,
    }


def buscar_boxscore(game_id):
    from nba_api.live.nba.endpoints import boxscore

    jogo = boxscore.BoxScore(game_id).get_dict()["game"]
    return {
        "id": game_id,
        "status": jogo["gameStatusText"],
        "fora": _time_box(jogo["awayTeam"]),
        "casa": _time_box(jogo["homeTeam"]),
    }


def buscar_classificacao():
    from nba_api.stats.endpoints import leaguestandingsv3

    df = leaguestandingsv3.LeagueStandingsV3(season=TEMPORADA, timeout=30).get_data_frames()[0]
    resultado = {"Leste": [], "Oeste": []}
    for t in sorted(df.to_dict("records"), key=lambda t: t["PlayoffRank"]):
        conferencia = "Leste" if t["Conference"] == "East" else "Oeste"
        resultado[conferencia].append(
            {
                "posicao": t["PlayoffRank"],
                "time": f"{t['TeamCity']} {t['TeamName']}",
                "vitorias": t["WINS"],
                "derrotas": t["LOSSES"],
                "aproveitamento": t["WinPCT"],
            }
        )
    return resultado