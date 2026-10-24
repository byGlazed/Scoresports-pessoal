import re
import sys

from nba_api.live.nba.endpoints import boxscore, scoreboard


def formatar_minutos(valor):
    """Converte 'PT34M12.00S' em '34:12'."""
    m = re.match(r"PT(\d+)M(\d+)", valor or "")
    if not m:
        return "--"
    return f"{int(m.group(1))}:{m.group(2)}"


def mostrar_time(time):
    print(f"\n{time['teamCity']} {time['teamName']}  ({time['score']})")
    print(f"{'Jogador':<24}{'MIN':>7}{'PTS':>5}{'REB':>5}{'AST':>5}")

    jogadores = []
    for j in time["players"]:
        stats = j["statistics"]
        if formatar_minutos(stats["minutes"]) == "--":
            continue  # não jogou
        jogadores.append((j["name"], stats))

    jogadores.sort(key=lambda item: item[1]["points"], reverse=True)

    for nome, s in jogadores:
        print(
            f"{nome:<24}{formatar_minutos(s['minutes']):>7}"
            f"{s['points']:>5}{s['reboundsTotal']:>5}{s['assists']:>5}"
        )


def main():
    if len(sys.argv) > 1:
        game_id = sys.argv[1]
    else:
        jogos = scoreboard.ScoreBoard().games.get_dict()
        if not jogos:
            print("Nenhum jogo hoje.")
            return
        game_id = jogos[0]["gameId"]

    jogo = boxscore.BoxScore(game_id).get_dict()["game"]

    print(f"{jogo['awayTeam']['teamTricode']} x {jogo['homeTeam']['teamTricode']}  |  {jogo['gameStatusText']}")
    mostrar_time(jogo["awayTeam"])
    mostrar_time(jogo["homeTeam"])


if __name__ == "__main__":
    main()