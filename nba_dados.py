import re
from datetime import datetime

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
            "id": j["gameId"],
            "estado": j["gameStatus"],
            "status": j["gameStatusText"],
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

URL_CALENDARIO = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"


def _data_iso(texto):
    """Aceita '2026-10-23T00:00:00Z' ou '10/23/2026 00:00:00' e devolve '2026-10-23'."""
    texto = texto or ""
    if len(texto) >= 10 and texto[4] == "-":
        return texto[:10]
    try:
        return datetime.strptime(texto[:10], "%m/%d/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return None


def _agenda_bruta():
    import requests

    try:
        resp = requests.get(URL_CALENDARIO, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        dados = resp.json()
    except Exception:
        # plano B: o mesmo calendário pelo stats.nba.com
        from nba_api.stats.endpoints import scheduleleaguev2

        dados = scheduleleaguev2.ScheduleLeagueV2(season=TEMPORADA, timeout=30).get_dict()
    return dados.get("leagueSchedule", dados)


def _time_agenda(t, estado):
    return {
        "sigla": t.get("teamTricode") or "–",
        "nome": f"{t.get('teamCity', '')} {t.get('teamName', '')}".strip() or "A definir",
        "placar": t.get("score") if estado >= 2 else None,
        "lider": None,
    }


def buscar_calendario():
    agenda = _agenda_bruta()
    jogos = []
    for dia in agenda["gameDates"]:
        for g in dia["games"]:
            if g["gameId"].startswith("001"):
                continue  # ignora a pré-temporada
            data = _data_iso(g.get("gameDateEst")) or _data_iso(dia.get("gameDate"))
            if not data:
                continue
            estado = g["gameStatus"]
            jogos.append(
                {
                    "id": g["gameId"],
                    "data": data,
                    "status": (g.get("gameStatusText") or "").strip(),
                    "estado": estado,  # 1 = vai começar, 2 = ao vivo, 3 = terminou
                    "fora": _time_agenda(g["awayTeam"], estado),
                    "casa": _time_agenda(g["homeTeam"], estado),
                }
            )
    return jogos