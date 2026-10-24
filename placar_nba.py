from nba_api.live.nba.endpoints import scoreboard


def formatar_lider(lider):
    if not lider.get("name"):
        return "sem dados ainda"
    return (
        f"{lider['name']} "
        f"({lider['points']} pts, {lider['rebounds']} reb, {lider['assists']} ast)"
    )


def mostrar_jogo(jogo):
    casa = jogo["homeTeam"]
    fora = jogo["awayTeam"]
    lideres = jogo["gameLeaders"]

    print(
        f"{fora['teamTricode']} {fora['score']} x "
        f"{casa['score']} {casa['teamTricode']}  |  {jogo['gameStatusText']}"
    )
    print(f"   {fora['teamTricode']}: {formatar_lider(lideres['awayLeaders'])}")
    print(f"   {casa['teamTricode']}: {formatar_lider(lideres['homeLeaders'])}")
    print()


def main():
    jogos = scoreboard.ScoreBoard().games.get_dict()

    if not jogos:
        print("Nenhum jogo hoje.")
        return

    for jogo in jogos:
        mostrar_jogo(jogo)


if __name__ == "__main__":
    main()