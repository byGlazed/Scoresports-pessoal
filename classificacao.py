from nba_api.stats.endpoints import leaguestandingsv3

TEMPORADA = "2026-27"


def main():
    resposta = leaguestandingsv3.LeagueStandingsV3(season=TEMPORADA, timeout=30)
    df = resposta.get_data_frames()[0]

    for conferencia, nome in [("East", "Leste"), ("West", "Oeste")]:
        tabela = df[df["Conference"] == conferencia].sort_values("PlayoffRank")

        print(f"\nConferência {nome}")
        print(f"{'#':<4}{'Time':<26}{'V':>4}{'D':>4}{'%':>8}")

        for _, t in tabela.iterrows():
            time = f"{t['TeamCity']} {t['TeamName']}"
            print(
                f"{t['PlayoffRank']:<4}{time:<26}"
                f"{t['WINS']:>4}{t['LOSSES']:>4}{t['WinPCT']:>8.3f}"
            )


if __name__ == "__main__":
    main()