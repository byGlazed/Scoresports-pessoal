import cache
from nba_api.stats.endpoints import leaguestandingsv3

TEMPORADA = "2026-27"
UMA_HORA = 3600


def buscar_classificacao():
    resposta = leaguestandingsv3.LeagueStandingsV3(season=TEMPORADA, timeout=30)
    df = resposta.get_data_frames()[0]
    return df.to_dict("records")


def main():
    dados = cache.obter("classificacao", UMA_HORA, buscar_classificacao)

    for conferencia, nome in [("East", "Leste"), ("West", "Oeste")]:
        tabela = sorted(
            (t for t in dados if t["Conference"] == conferencia),
            key=lambda t: t["PlayoffRank"],
        )

        print(f"\nConferência {nome}")
        print(f"{'#':<4}{'Time':<26}{'V':>4}{'D':>4}{'%':>8}")

        for t in tabela:
            time = f"{t['TeamCity']} {t['TeamName']}"
            print(
                f"{t['PlayoffRank']:<4}{time:<26}"
                f"{t['WINS']:>4}{t['LOSSES']:>4}{t['WinPCT']:>8.3f}"
            )


if __name__ == "__main__":
    main()