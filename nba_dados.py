import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

TEMPORADA = "2026-27"
FUSO_BRASILIA = ZoneInfo("America/Sao_Paulo")


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
            "estado": j["gameStatus"],
            "status": j["gameStatusText"],
            "inicio": j.get("gameTimeUTC"),
            "fora": _time_jogo(j["awayTeam"], j["gameLeaders"]["awayLeaders"]),
            "casa": _time_jogo(j["homeTeam"], j["gameLeaders"]["homeLeaders"]),
        }
        for j in jogos
    ]


def _arremessos(feitos, tentados):
    return f"{feitos or 0}/{tentados or 0}"


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
                "id": j["personId"],
                "min": minutos,
                "pts": s["points"],
                "reb": s["reboundsTotal"],
                "ast": s["assists"],
                "fg": _arremessos(s.get("fieldGoalsMade"), s.get("fieldGoalsAttempted")),
                "tres": _arremessos(s.get("threePointersMade"), s.get("threePointersAttempted")),
                "ll": _arremessos(s.get("freeThrowsMade"), s.get("freeThrowsAttempted")),
                "to": s.get("turnovers", 0),
                "faltas": s.get("foulsPersonal", 0),
                "stl": s.get("steals", 0),
                "blk": s.get("blocks", 0),
                "mm": int(s.get("plusMinusPoints") or 0),
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


# ---------- Calendário da temporada ----------

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


def _inicio_utc(texto):
    """Converte '2026-10-23T23:00:00Z' em datetime com fuso; None se não der."""
    if not texto:
        return None
    try:
        dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def buscar_calendario():
    agenda = _agenda_bruta()
    jogos = []
    for dia in agenda["gameDates"]:
        for g in dia["games"]:
            if g["gameId"].startswith("001"):
                continue  # ignora a pré-temporada

            inicio = _inicio_utc(g.get("gameDateTimeUTC"))
            if inicio:
                data = inicio.astimezone(FUSO_BRASILIA).strftime("%Y-%m-%d")
                inicio_iso = inicio.isoformat()
            else:
                # plano B: sem horário UTC, usa a data da NBA
                data = _data_iso(g.get("gameDateEst")) or _data_iso(dia.get("gameDate"))
                inicio_iso = None
            if not data:
                continue

            estado = g["gameStatus"]
            jogos.append(
                {
                    "id": g["gameId"],
                    "data": data,
                    "inicio": inicio_iso,
                    "status": (g.get("gameStatusText") or "").strip(),
                    "estado": estado,  # 1 = vai começar, 2 = ao vivo, 3 = terminou
                    "fora": _time_agenda(g["awayTeam"], estado),
                    "casa": _time_agenda(g["homeTeam"], estado),
                }
            )
    return jogos


# ---------- Jogador ----------

_MESES = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
          "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}


def _num(valor):
    try:
        x = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if x != x else x  # NaN vira 0


def _inteiro(valor):
    return int(_num(valor))


def _data_do_log(texto):
    """Converte 'OCT 23, 2026' em '2026-10-23'."""
    texto = texto or ""
    if len(texto) >= 10 and texto[4] == "-":
        return texto[:10]
    try:
        mes, dia, ano = texto.replace(",", "").split()
        return f"{int(ano):04d}-{_MESES[mes.upper()[:3]]:02d}-{int(dia):02d}"
    except (ValueError, KeyError):
        return texto


def _resumo_jogo(j):
    return {
        "id": j.get("Game_ID"),
        "data": _data_do_log(j.get("GAME_DATE")),
        "confronto": j.get("MATCHUP", ""),
    }


def _media(jogos, campo):
    return round(sum(_num(j.get(campo)) for j in jogos) / len(jogos), 1)


def _porcentagem(jogos, feitos, tentados):
    f = sum(_num(j.get(feitos)) for j in jogos)
    t = sum(_num(j.get(tentados)) for j in jogos)
    return round(100 * f / t, 1) if t else None


def _recorde(jogos, campo):
    melhor = max(jogos, key=lambda j: _num(j.get(campo)))
    return {"valor": _inteiro(melhor.get(campo)), "jogo": _resumo_jogo(melhor)}


def _linha_jogo(j):
    return {
        **_resumo_jogo(j),
        "resultado": j.get("WL"),
        "min": _inteiro(j.get("MIN")),
        "pts": _inteiro(j.get("PTS")),
        "reb": _inteiro(j.get("REB")),
        "ast": _inteiro(j.get("AST")),
        "fg": _arremessos(_inteiro(j.get("FGM")), _inteiro(j.get("FGA"))),
        "tres": _arremessos(_inteiro(j.get("FG3M")), _inteiro(j.get("FG3A"))),
    }


def buscar_jogador(player_id):
    from nba_api.stats.endpoints import playergamelog

    df = playergamelog.PlayerGameLog(
        player_id=player_id,
        season=TEMPORADA,
        season_type_all_star="Regular Season",
        timeout=30,
    ).get_data_frames()[0]
    jogos = df.to_dict("records")  # do mais recente para o mais antigo

    base = {"id": player_id, "temporada": TEMPORADA, "jogos_disputados": len(jogos)}
    if not jogos:
        return {**base, "medias": None, "recordes": {}, "jogos": []}

    return {
        **base,
        "medias": {
            "min": _media(jogos, "MIN"),
            "pts": _media(jogos, "PTS"),
            "reb": _media(jogos, "REB"),
            "ast": _media(jogos, "AST"),
            "stl": _media(jogos, "STL"),
            "blk": _media(jogos, "BLK"),
            "to": _media(jogos, "TOV"),
            "fg_pct": _porcentagem(jogos, "FGM", "FGA"),
            "tres_pct": _porcentagem(jogos, "FG3M", "FG3A"),
            "ll_pct": _porcentagem(jogos, "FTM", "FTA"),
        },
        "recordes": {
            "pts": _recorde(jogos, "PTS"),
            "reb": _recorde(jogos, "REB"),
            "ast": _recorde(jogos, "AST"),
            "stl": _recorde(jogos, "STL"),
            "blk": _recorde(jogos, "BLK"),
            "tres": _recorde(jogos, "FG3M"),
        },
        "jogos": [_linha_jogo(j) for j in jogos],
    }