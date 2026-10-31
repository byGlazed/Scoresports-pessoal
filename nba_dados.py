import re
from datetime import date, datetime, timezone
from html import unescape
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


# ---------- Líderes da temporada ----------

# chave do stats.nba.com -> nome exibido (a ordem aqui é a ordem na página)
CATEGORIAS_LIDERES = {
    "PTS": "Pontos",
    "REB": "Rebotes",
    "AST": "Assistências",
    "STL": "Roubos de bola",
    "BLK": "Tocos",
    "FG3M": "Bolas de três feitas",
    "FGM": "Arremessos de quadra feitos",
    "FTM": "Lances livres feitos",
    "TOV": "Turnovers",
    "FG_PCT": "Aproveitamento de arremessos (FG%)",
    "FG3_PCT": "Aproveitamento de bolas de três (3PT%)",
    "FT_PCT": "Aproveitamento de lances livres (FT%)",
}

# percentual -> (feitos, tentados, mínimo de feitos por jogo da liga)
# Baseado nos mínimos da NBA para uma temporada de 82 jogos:
# 300 arremessos, 82 bolas de três e 125 lances livres feitos.
PERCENTUAIS = {
    "FG_PCT": ("FGM", "FGA", 300 / 82),
    "FG3_PCT": ("FG3M", "FG3A", 82 / 82),
    "FT_PCT": ("FTM", "FTA", 125 / 82),
}

CAMPOS_STATS = [
    "PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GP", "MIN",
    "PTS", "REB", "AST", "STL", "BLK", "TOV",
    "FGM", "FGA", "FG_PCT", "FG3M", "FG3A", "FG3_PCT", "FTM", "FTA", "FT_PCT",
]


def buscar_stats_jogadores():
    """Totais da temporada de todos os jogadores (as médias saem de total / jogos)."""
    from nba_api.stats.endpoints import leaguedashplayerstats

    df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=TEMPORADA,
        season_type_all_star="Regular Season",
        per_mode_detailed="Totals",
        timeout=45,
    ).get_data_frames()[0]
    return [{c: j.get(c) for c in CAMPOS_STATS} for j in df.to_dict("records")]


def _linha_lider(posicao, j, valor, extra=None):
    return {
        "posicao": posicao,
        "id": _inteiro(j.get("PLAYER_ID")),
        "nome": j.get("PLAYER_NAME") or "",
        "time": j.get("TEAM_ABBREVIATION") or "",
        "jogos": _inteiro(j.get("GP")),
        "valor": valor,
        "extra": extra,
    }


def _lideres_contagem(jogadores, chave, modo, minimo_jogos, limite):
    candidatos = [j for j in jogadores if _inteiro(j.get("GP")) >= minimo_jogos]

    def valor(j):
        total = _num(j.get(chave))
        return total if modo == "total" else total / _num(j.get("GP"))

    candidatos.sort(key=valor, reverse=True)
    return [
        _linha_lider(i, j, _inteiro(valor(j)) if modo == "total" else round(valor(j), 1))
        for i, j in enumerate(candidatos[:limite], start=1)
    ]


def _lideres_percentual(jogadores, feitos, tentados, minimo_por_jogo, max_jogos, limite):
    minimo_feitos = minimo_por_jogo * max_jogos
    candidatos = [
        j
        for j in jogadores
        if _num(j.get(tentados)) > 0 and _num(j.get(feitos)) >= minimo_feitos
    ]
    candidatos.sort(key=lambda j: _num(j.get(feitos)) / _num(j.get(tentados)), reverse=True)
    return [
        _linha_lider(
            i,
            j,
            round(100 * _num(j.get(feitos)) / _num(j.get(tentados)), 1),
            f"{_inteiro(j.get(feitos))}/{_inteiro(j.get(tentados))}",
        )
        for i, j in enumerate(candidatos[:limite], start=1)
    ]


def montar_lideres(jogadores, modo, limite=10):
    """Top 10 de cada categoria. modo: 'media' (por jogo) ou 'total'."""
    max_jogos = max((_inteiro(j.get("GP")) for j in jogadores), default=0)
    # médias por jogo: mínimo de 70% dos jogos da liga; totais: qualquer jogador
    minimo_jogos = 1 if modo == "total" else max(1, (7 * max_jogos) // 10)

    categorias = []
    for chave, rotulo in CATEGORIAS_LIDERES.items():
        if chave in PERCENTUAIS:
            feitos, tentados, minimo_por_jogo = PERCENTUAIS[chave]
            lista = _lideres_percentual(jogadores, feitos, tentados, minimo_por_jogo, max_jogos, limite)
        else:
            lista = _lideres_contagem(jogadores, chave, modo, minimo_jogos, limite)
        categorias.append(
            {"chave": chave, "rotulo": rotulo, "percentual": chave in PERCENTUAIS, "jogadores": lista}
        )

    return {
        "modo": modo,
        "jogos_da_liga": max_jogos,
        "minimo_jogos": minimo_jogos,
        "categorias": categorias,
    }


# ---------- Corridas do MVP e do calouro do ano (Ladders do NBA.com) ----------

URL_LADDER_MVP = "https://www.nba.com/news/category/kia-race-to-the-mvp-ladder"
URL_LADDER_ROY = "https://www.nba.com/news/category/kia-rookie-ladder"

_MESES_SLUG = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
               "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}

_ABREVIACOES = [
    (r"\bpoints?\b", "pts"),
    (r"\brebounds?\b", "reb"),
    (r"\bassists?\b", "ast"),
    (r"\bsteals?\b", "stl"),
    (r"\bblocks?\b", "blk"),
]


def _baixar(url):
    import requests

    resp = requests.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.text


def _data_do_slug(slug):
    """'kia-mvp-ladder-march-27-2026' -> date(2026, 3, 27)."""
    m = re.search(r"([a-z]+)-(\d{1,2})-(\d{4})", slug)
    if not m:
        return None
    mes = _MESES_SLUG.get(m.group(1)[:3])
    if not mes:
        return None
    try:
        return date(int(m.group(3)), mes, int(m.group(2)))
    except ValueError:
        return None


def _candidatos_ladder(html, prefixo):
    """Edições da temporada atual, da mais nova para a mais antiga (no máximo 3)."""
    inicio_temporada = date(int(TEMPORADA[:4]), 10, 1)
    vistos = {}
    for slug in re.findall(rf"/news\\?/({prefixo}[a-z0-9-]*)", html):
        if any(palavra in slug for palavra in ("update", "tracker", "watchlist")):
            continue
        data = _data_do_slug(slug)
        if data and data >= inicio_temporada:
            vistos[slug] = data
    ordenados = sorted(vistos.items(), key=lambda item: item[1], reverse=True)
    return [(f"https://www.nba.com/news/{slug}", data) for slug, data in ordenados[:3]]


def _html_para_texto(trecho):
    trecho = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", trecho)
    trecho = re.sub(r"(?i)<br\s*/?>|</(?:p|div|li|h[1-6]|tr)>", "\n", trecho)
    trecho = re.sub(r"<[^>]+>", "", trecho)
    return unescape(trecho)


def _abreviar_stats(texto):
    for padrao, abreviacao in _ABREVIACOES:
        texto = re.sub(padrao, abreviacao, texto, flags=re.I)
    return texto


def _extrair_ranking(html):
    """Lê os títulos numerados do artigo ('1. Nome, Time') e as linhas de estatística.

    Só guarda fatos (posição, jogador, time, movimento e médias da temporada).
    O texto da análise não é copiado: a página manda o leitor para o artigo original.
    """
    cabecalhos = list(re.finditer(r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", html))
    ranking = {}
    for i, c in enumerate(cabecalhos):
        titulo = " ".join(_html_para_texto(c.group(2)).split())
        m = re.match(r"(\d{1,2})\s*[.)]\s*(.+)$", titulo)
        if not m:
            continue
        posicao = int(m.group(1))
        if posicao in ranking or posicao > 15:
            continue

        nome, _, time = m.group(2).rpartition(",")
        if not nome:
            nome, time = m.group(2), ""

        fim = cabecalhos[i + 1].start() if i + 1 < len(cabecalhos) else len(html)
        corpo = _html_para_texto(html[c.end():fim])

        anterior = None
        movimento = None
        u = re.search(
            r"Last\s+week\W{0,3}s\s+ranking\s*:\s*(?:No\.?\s*(\d+)|(Not\s+ranked))",
            corpo,
            re.I,
        )
        if u:
            if u.group(1):
                anterior = int(u.group(1))
                if anterior > posicao:
                    movimento = "subiu"
                elif anterior < posicao:
                    movimento = "desceu"
                else:
                    movimento = "igual"
            else:
                movimento = "novo"

        s = re.search(r"Season\s+\w+\s*:\s*([^\n]+)", corpo, re.I)
        stats = _abreviar_stats(s.group(1).strip())[:80] if s else None

        ranking[posicao] = {
            "posicao": posicao,
            "nome": nome.strip(),
            "time": time.strip(),
            "anterior": anterior,
            "movimento": movimento,
            "stats": stats,
        }
    return [ranking[p] for p in sorted(ranking)]


def _ranking_valido(ranking):
    # Um ranking de verdade tem pelo menos 3 jogadores com "Last week" ou "Season stats".
    # Isso evita confundir artigos numerados que não são o ranking semanal.
    return len(ranking) >= 3 and sum(1 for e in ranking if e["movimento"] or e["stats"]) >= 3


def _titulo_pagina(html):
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    titulo = " ".join(unescape(m.group(1)).split()) if m else ""
    return re.sub(r"\s*\|\s*NBA\.com\s*$", "", titulo)


def _buscar_ladder(url_categoria, prefixo):
    pagina_categoria = _baixar(url_categoria)
    for url, data in _candidatos_ladder(pagina_categoria, prefixo):
        artigo = _baixar(url)
        ranking = _extrair_ranking(artigo)
        if _ranking_valido(ranking):
            return {
                "titulo": _titulo_pagina(artigo),
                "url": url,
                "data": data.isoformat(),
                "ranking": ranking[:10],
                "pagina": url_categoria,
            }
    return {"titulo": None, "url": None, "data": None, "ranking": [], "pagina": url_categoria}


def buscar_corridas():
    return {
        "mvp": _buscar_ladder(URL_LADDER_MVP, "kia-mvp-ladder"),
        "roy": _buscar_ladder(URL_LADDER_ROY, "kia-rookie-ladder"),
    }