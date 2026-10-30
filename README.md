# Scoresports

App pessoal de placares da NBA, feito para treinar programação. Mostra os jogos de cada dia da temporada (passados e futuros), placar ao vivo, box score completo, estatísticas dos jogadores e a classificação das conferências, tudo com horários no fuso de Brasília.

> Projeto de estudo, para uso pessoal. Não é afiliado à NBA e não tem fins comerciais.

## Funcionalidades

- **Jogos por dia:** navegação por setas ou calendário, desde a primeira rodada até o fim da temporada, incluindo os jogos futuros.
- **Placar ao vivo:** a página se atualiza sozinha a cada 20 segundos enquanto há jogo em andamento ou no dia de hoje.
- **Horário de Brasília:** os jogos que ainda não começaram mostram o horário local de Brasília, e os dias são agrupados pelo fuso de Brasília.
- **Box score completo:** pontos, rebotes, assistências, FG, bolas de três e lances livres (feitos/tentados), turnovers, faltas, roubos de bola, tocos e +/-.
- **Painel do jogador:** ao clicar no nome de um jogador no box score, abre um painel com as médias da temporada, os recordes da temporada (com o jogo em que aconteceram), um gráfico de pontos por jogo e a lista de todos os jogos.
- **Classificação:** tabela das conferências Leste e Oeste.

## Tecnologias

- **Python 3.10 ou superior**
- **[FastAPI](https://fastapi.tiangolo.com/)** e **Uvicorn** para a API
- **[nba_api](https://github.com/swar/nba_api)** para buscar os dados da NBA
- **SQLite** (módulo `sqlite3` do Python) para o cache
- **HTML, CSS e JavaScript** puros no front-end, sem frameworks

## Como rodar

```bash
git clone https://github.com/<seu-usuario>/Scoresports-pessoal.git
cd Scoresports-pessoal

python -m venv .venv

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
uvicorn api:app --reload
```

Depois abra **http://127.0.0.1:8000** no navegador. A documentação interativa da API fica em **http://127.0.0.1:8000/docs**.

No PowerShell, se a ativação do ambiente virtual for bloqueada, rode uma vez:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Estrutura do projeto

```
Scoresports-pessoal/
├── api.py              # rotas da API (FastAPI) e entrega da página
├── nba_dados.py        # busca e formata os dados da NBA
├── cache.py            # cache em SQLite com tempo de validade
├── placar_nba.py       # script de terminal: placar do dia
├── box_score.py        # script de terminal: box score de um jogo
├── classificacao.py    # script de terminal: classificação das conferências
├── requirements.txt
└── static/
    ├── index.html
    ├── style.css
    └── app.js
```

Os três scripts de terminal (`placar_nba.py`, `box_score.py` e `classificacao.py`) foram os primeiros passos do projeto e continuam funcionando de forma independente:

```bash
python placar_nba.py
python box_score.py            # primeiro jogo de hoje
python box_score.py 0022600099 # jogo específico, pelo ID
python classificacao.py
```

## Rotas da API

| Rota | O que devolve | Cache |
|------|---------------|-------|
| `GET /` | A página | n/a |
| `GET /datas` | Todos os dias com jogos na temporada e o dia de hoje (Brasília) | 10 min |
| `GET /jogos?data=AAAA-MM-DD` | Jogos do dia, com o placar ao vivo quando disponível | calendário: 10 min; ao vivo: 15 s |
| `GET /jogos/{id}/boxscore` | Box score completo de um jogo | 15 s |
| `GET /jogadores/{id}` | Médias, recordes e jogos do jogador na temporada | 10 min |
| `GET /classificacao` | Classificação do Leste e do Oeste | 1 h |

## Como funciona

```
navegador  ->  API (FastAPI)  ->  cache (SQLite)  ->  NBA (nba_api)
```

1. O navegador só conversa com a API do próprio projeto.
2. A API pede os dados ao módulo `cache.py`. Se o dado salvo ainda estiver dentro do tempo de validade, ele é devolvido na hora.
3. Se estiver vencido, o `nba_dados.py` busca na NBA, o resultado é salvo no banco (`cache.db`) e devolvido.
4. Se a NBA falhar e existir um dado antigo salvo, ele é usado no lugar, e a página continua funcionando.

Isso reduz o número de consultas à NBA e deixa a página mais rápida. Os dados vêm de três fontes: o feed de jogos ao vivo (placar e box score), o calendário estático da temporada e o `stats.nba.com` (classificação e histórico dos jogadores), todos acessados pelo `nba_api` ou por requisições simples.

## Configuração

A temporada exibida é definida pela constante `TEMPORADA` (por exemplo, `"2026-27"`) no início do `nba_dados.py`. O `classificacao.py` tem a sua própria. Quando uma nova temporada começar, é só atualizar esse valor.

## Limitações conhecidas

- Os dados vêm de endpoints **não oficiais** da NBA. Eles podem mudar, ficar lentos ou bloquear consultas sem aviso. O cache ameniza isso, mas não elimina.
- As estatísticas e recordes dos jogadores consideram apenas a **temporada regular**.
- As datas no histórico do jogador seguem o fuso dos EUA, então um jogo de madrugada em Brasília pode aparecer com a data do dia anterior nesse painel.
- A pré-temporada não aparece no calendário.

## Próximos passos

- [ ] Adicionar futebol como segunda fonte de dados (a ideia é usar um provedor com chave de API gratuita)
- [ ] Opção de ver playoffs
- [ ] Recordes da carreira, além dos da temporada
- [ ] Linha de totais por time no box score

## Aviso

Este projeto é de uso pessoal e educacional. Os dados pertencem à NBA e aos respectivos detentores, e o app não os redistribui nem os usa comercialmente.