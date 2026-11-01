import json
import re
import unicodedata
from datetime import date, datetime, timezone
from html import unescape
from pathlib import Path
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
        "time_id": t.get("teamId"),
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
                "camisa": j.get("jerseyNum"),
                "posicao": j.get("position"),
                "min": minutos,
                "pts": s["points"],
                "reb": s["reboundsTotal"],
                "ast": s["assists"],
                "fg": _arremessos(s.get("fieldGoalsMade"), s.get("fieldGoalsAttempted")),
                "tres": _arremessos(s.get("threePointersMade"), s.get("threePointersAttempted")),
                "ll": _arremessos(s.get("freeThrowsMade"), s.get("freeThrowsAttempted")),
                "dois": _arremessos(s.get("twoPointersMade"), s.get("twoPointersAttempted")),
                "reb_of": s.get("reboundsOffensive", 0),
                "reb_def": s.get("reboundsDefensive", 0),
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
        "time_id": t.get("teamId"),
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


def buscar_arremessos(game_id):
    """Todos os arremessos de quadra de um jogo, com a posição na quadra."""
    from nba_api.live.nba.endpoints import playbyplay

    acoes = playbyplay.PlayByPlay(game_id).get_dict()["game"]["actions"]
    arremessos = []
    for a in acoes:
        if a.get("actionType") not in ("2pt", "3pt"):
            continue
        x, y = a.get("xLegacy"), a.get("yLegacy")
        if x is None or y is None:
            continue
        arremessos.append(
            {
                "jogador": a.get("personId"),
                "x": x,
                "y": y,
                "feito": a.get("shotResult") == "Made",
                "periodo": a.get("period"),
                "tipo": a.get("actionType"),
                "distancia": a.get("shotDistance"),
                "relogio": _minutos(a.get("clock")),
            }
        )
    return arremessos


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
                "time_id": t.get("TeamID"),
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
        "time_id": t.get("teamId"),
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


# ---------- Pré-jogo: escalações prováveis, lesões, confronto direto, forma e líderes ----------

ARQUIVO_TRANSMISSOES = Path(__file__).parent / "transmissoes.json"
URL_LESOES = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

LIDERES_DO_TIME = [
    ("PTS", "Pontos"),
    ("REB", "Rebotes"),
    ("AST", "Assistências"),
    ("STL", "Roubos de bola"),
    ("BLK", "Tocos"),
    ("FG3M", "Bolas de três"),
]


def _sem_acento(texto):
    normal = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in normal if not unicodedata.combining(c)).lower().strip()


def chave_do_time(nome):
    """'Golden State Warriors' -> 'warriors' (a última palavra identifica o time)."""
    partes = _sem_acento(nome).split()
    return partes[-1] if partes else ""


def _minutos_decimais(valor):
    m = re.match(r"PT(\d+)M(\d+(?:\.\d+)?)", valor or "")
    return int(m.group(1)) + float(m.group(2)) / 60 if m else 0.0


def buscar_lesoes():
    """Relatório de lesões por time (fonte: ESPN, não oficial)."""
    import requests

    resp = requests.get(URL_LESOES, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    por_time = {}
    for t in resp.json().get("injuries", []):
        lista = []
        for i in t.get("injuries", []):
            atleta = i.get("athlete") or {}
            detalhes = i.get("details") or {}
            motivo = " ".join(p for p in (detalhes.get("type"), detalhes.get("detail")) if p)
            lista.append(
                {
                    "nome": atleta.get("displayName") or atleta.get("fullName") or "",
                    "posicao": (atleta.get("position") or {}).get("abbreviation"),
                    "status": i.get("status") or (i.get("type") or {}).get("description") or "",
                    "motivo": motivo,
                    "parte": detalhes.get("type") or "",
                    "detalhe": detalhes.get("detail") or "",
                    "retorno": detalhes.get("returnDate"),
                }
            )
        por_time[chave_do_time(t.get("displayName"))] = lista
    return por_time


def nomes_indisponiveis(lesionados):
    return {_sem_acento(l["nome"]) for l in lesionados if str(l.get("status", "")).lower() == "out"}


def jogos_recentes(agenda, sigla, limite=5):
    """Últimos jogos já encerrados de um time (do mais recente para o mais antigo)."""
    jogos = [
        j
        for j in agenda
        if j["estado"] == 3 and sigla in (j["fora"]["sigla"], j["casa"]["sigla"])
    ]
    jogos.sort(key=lambda j: j.get("inicio") or j["data"], reverse=True)
    recentes = []
    for j in jogos[:limite]:
        em_casa = j["casa"]["sigla"] == sigla
        meu, adversario = (j["casa"], j["fora"]) if em_casa else (j["fora"], j["casa"])
        pontos, pontos_adv = _inteiro(meu["placar"]), _inteiro(adversario["placar"])
        recentes.append(
            {
                "id": j["id"],
                "data": j["data"],
                "adversario": adversario["sigla"],
                "local": "casa" if em_casa else "fora",
                "pontos": pontos,
                "pontos_adv": pontos_adv,
                "resultado": "V" if pontos > pontos_adv else "D",
            }
        )
    return recentes


def buscar_titulares_do_jogo(game_id):
    """Quem jogou em cada time num jogo encerrado, com a marcação de titular."""
    from nba_api.live.nba.endpoints import boxscore

    jogo = boxscore.BoxScore(game_id).get_dict()["game"]
    resultado = {}
    for chave in ("awayTeam", "homeTeam"):
        time = jogo[chave]
        jogadores = []
        for p in time["players"]:
            s = p.get("statistics") or {}
            minutos = _minutos_decimais(s.get("minutes"))
            if minutos <= 0:
                continue  # não jogou
            jogadores.append(
                {
                    "id": p["personId"],
                    "nome": p["name"],
                    "posicao": p.get("position"),
                    "camisa": p.get("jerseyNum"),
                    "min": round(minutos, 1),
                    "titular": str(p.get("starter")) in ("1", "True", "true"),
                }
            )
        resultado[time["teamTricode"]] = jogadores
    return resultado


def montar_escalacao(recentes, caixas, sigla, indisponiveis):
    """Provável quinteto: quem mais começou jogando nos últimos jogos (sem os jogadores 'fora')."""
    contagem = {}
    jogos_base = 0
    for j in recentes:
        jogadores = (caixas.get(j["id"]) or {}).get(sigla)
        if not jogadores:
            continue
        jogos_base += 1
        for p in jogadores:
            reg = contagem.setdefault(
                p["id"],
                {
                    "id": p["id"],
                    "nome": p["nome"],
                    "posicao": p.get("posicao"),
                    "camisa": p.get("camisa"),
                    "titular_em": 0,
                    "minutos": 0.0,
                },
            )
            reg["minutos"] += p["min"]
            if p["titular"]:
                reg["titular_em"] += 1

    candidatos = [r for r in contagem.values() if _sem_acento(r["nome"]) not in indisponiveis]
    candidatos.sort(key=lambda r: (r["titular_em"], r["minutos"]), reverse=True)
    quinteto = candidatos[:5]
    for r in quinteto:
        r["min_medio"] = round(r.pop("minutos") / jogos_base, 1)
    return {
        "jogos_base": jogos_base,
        "criterio": "titulares" if any(r["titular_em"] for r in quinteto) else "minutos",
        "quinteto": quinteto,
    }


def montar_lideres_do_time(jogadores, sigla):
    """Maior média do time em cada estatística."""
    do_time = [
        j for j in jogadores if j.get("TEAM_ABBREVIATION") == sigla and _inteiro(j.get("GP")) > 0
    ]
    if not do_time:
        return []
    minimo_jogos = max(1, (7 * max(_inteiro(j.get("GP")) for j in do_time)) // 10)
    candidatos = [j for j in do_time if _inteiro(j.get("GP")) >= minimo_jogos]

    resultado = []
    for chave, rotulo in LIDERES_DO_TIME:
        melhor = max(candidatos, key=lambda j: _num(j.get(chave)) / _num(j.get("GP")))
        resultado.append(
            {
                "chave": chave,
                "rotulo": rotulo,
                "id": _inteiro(melhor.get("PLAYER_ID")),
                "nome": melhor.get("PLAYER_NAME") or "",
                "valor": round(_num(melhor.get(chave)) / _num(melhor.get("GP")), 1),
                "jogos": _inteiro(melhor.get("GP")),
            }
        )
    return resultado


def buscar_confronto_direto(id_a, id_b, sigla_a, sigla_b):
    """Últimos 10 jogos entre os dois times (temporada regular e playoffs)."""
    from nba_api.stats.endpoints import leaguegamefinder

    desde = date.today().replace(year=date.today().year - 7, month=1, day=1)
    df = leaguegamefinder.LeagueGameFinder(
        team_id_nullable=id_a,
        vs_team_id_nullable=id_b,
        date_from_nullable=desde.strftime("%m/%d/%Y"),
        timeout=45,
    ).get_data_frames()[0]

    linhas = [j for j in df.to_dict("records") if str(j.get("GAME_ID", ""))[:3] not in ("001", "003")]
    linhas.sort(key=lambda j: str(j.get("GAME_DATE")), reverse=True)

    jogos = []
    for j in linhas[:10]:
        pts_a = _inteiro(j.get("PTS"))
        pts_b = int(round(pts_a - _num(j.get("PLUS_MINUS"))))
        a_visitante = "@" in str(j.get("MATCHUP", ""))
        jogos.append(
            {
                "data": str(j.get("GAME_DATE"))[:10],
                "mandante": sigla_b if a_visitante else sigla_a,
                "visitante": sigla_a if a_visitante else sigla_b,
                "pontos_mandante": pts_b if a_visitante else pts_a,
                "pontos_visitante": pts_a if a_visitante else pts_b,
                "vencedor": sigla_a if j.get("WL") == "W" else sigla_b,
            }
        )
    vitorias_a = sum(1 for g in jogos if g["vencedor"] == sigla_a)
    return {"jogos": jogos, "vitorias_fora": vitorias_a, "vitorias_casa": len(jogos) - vitorias_a}


def buscar_transmissao(data, fora, casa):
    """Canais do jogo no Brasil, lidos do arquivo transmissoes.json (editável)."""
    try:
        conteudo = json.loads(ARQUIVO_TRANSMISSOES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for item in conteudo.get("jogos", []):
        if item.get("data") == data and item.get("fora") == fora and item.get("casa") == casa:
            return {
                "canais": list(item.get("canais") or []),
                "conferido_em": item.get("conferido_em"),
                "observacao": item.get("observacao"),
            }
    return None


def _resumo_time(t):
    return {"sigla": t["sigla"], "nome": t["nome"], "time_id": t.get("time_id")}


def montar_pre_jogo(jogo, agenda, obter):
    """Reúne tudo da tela de pré-jogo.

    `obter(chave, ttl_segundos, funcao)` devolve o dado (usando o cache) ou None se falhar,
    assim uma fonte fora do ar não derruba a página inteira.
    """
    fora, casa = jogo["fora"], jogo["casa"]
    falhas = []

    lesoes = obter("lesoes_v1", 1800, buscar_lesoes)
    if lesoes is None:
        falhas.append("lesoes")
        lesoes = {}

    estatisticas = obter("stats_jogadores_v1", 1800, buscar_stats_jogadores)
    if estatisticas is None:
        falhas.append("estatisticas")
        estatisticas = []

    confronto = None
    if fora.get("time_id") and casa.get("time_id"):
        confronto = obter(
            f"h2h_v2:{fora['time_id']}:{casa['time_id']}",
            43200,
            lambda: buscar_confronto_direto(fora["time_id"], casa["time_id"], fora["sigla"], casa["sigla"]),
        )
    if confronto is None:
        falhas.append("confronto")

    times = {}
    for lado, time in (("fora", fora), ("casa", casa)):
        recentes = jogos_recentes(agenda, time["sigla"])
        caixas = {}
        for r in recentes:
            caixa = obter(
                f"titulares_v1:{r['id']}", 86400, lambda gid=r["id"]: buscar_titulares_do_jogo(gid)
            )
            if caixa:
                caixas[r["id"]] = caixa
        lesionados = lesoes.get(chave_do_time(time["nome"]), [])
        times[lado] = {
            "forma": recentes,
            "escalacao": montar_escalacao(recentes, caixas, time["sigla"], nomes_indisponiveis(lesionados)),
            "lesionados": lesionados,
            "lideres": montar_lideres_do_time(estatisticas, time["sigla"]),
        }

    return {
        "jogo": {
            "id": jogo["id"],
            "data": jogo["data"],
            "inicio": jogo.get("inicio"),
            "estado": jogo["estado"],
            "status": jogo.get("status"),
            "fora": _resumo_time(fora),
            "casa": _resumo_time(casa),
        },
        "transmissao": buscar_transmissao(jogo["data"], fora["sigla"], casa["sigla"]),
        "confronto": confronto,
        "times": times,
        "falhas": falhas,
    }