const FUSO = "America/Sao_Paulo";

const abertos = new Set(); // box scores abertos, para não fechar na atualização
let datas = [];            // dias que têm jogos
let hoje = null;
let dataAtual = null;
let haAoVivo = false;

const seletor = document.getElementById("seletor-data");
const botaoAnterior = document.getElementById("dia-anterior");
const botaoSeguinte = document.getElementById("dia-seguinte");
const botaoHoje = document.getElementById("hoje");

const dialogoJogador = document.getElementById("jogador-dialogo");
const conteudoJogador = document.getElementById("jogador-conteudo");
let jogadorAberto = null;

function el(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto !== undefined && texto !== null) e.textContent = texto;
  return e;
}

async function buscar(caminho) {
  const resp = await fetch(caminho);
  if (!resp.ok) throw new Error("Erro " + resp.status);
  return resp.json();
}

// uma célula pode ser um valor simples ou { texto, classe, aoClicar }
function tabela(colunas, linhas) {
  const t = el("table");
  const cab = el("tr");
  colunas.forEach((c) => cab.append(el("th", null, c)));
  t.append(cab);
  linhas.forEach((valores) => {
    const tr = el("tr");
    valores.forEach((v) => {
      if (v !== null && typeof v === "object") {
        const td = el("td", v.classe);
        if (v.aoClicar) {
          const botao = el("button", "link-jogador", v.texto);
          botao.addEventListener("click", v.aoClicar);
          td.append(botao);
        } else {
          td.textContent = v.texto;
        }
        tr.append(td);
      } else {
        tr.append(el("td", null, v));
      }
    });
    t.append(tr);
  });
  return t;
}

/* ---------- Horário de Brasília ---------- */

function horaBrasilia(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return null;
  return d.toLocaleTimeString("pt-BR", { timeZone: FUSO, hour: "2-digit", minute: "2-digit" });
}

function textoStatus(jogo) {
  const hora = jogo.estado === 1 && jogo.inicio ? horaBrasilia(jogo.inicio) : null;
  return hora ? `${hora} (Brasília)` : jogo.status;
}

/* ---------- Jogos ---------- */

function maisMenos(n) {
  if (n > 0) return { texto: "+" + n, classe: "positivo" };
  if (n < 0) return { texto: String(n), classe: "negativo" };
  return { texto: "0", classe: "" };
}

function tabelaBox(time) {
  const bloco = el("div", "bloco");
  bloco.append(el("h3", null, `${time.nome} (${time.placar})`));
  bloco.append(
    tabela(
      ["Jogador", "MIN", "PTS", "REB", "AST", "FG", "3PT", "FT", "TO", "PF", "STL", "BLK", "+/-"],
      time.jogadores.map((j) => [
        { texto: j.nome, aoClicar: () => abrirJogador(j) },
        j.min, j.pts, j.reb, j.ast,
        j.fg, j.tres, j.ll, j.to, j.faltas, j.stl, j.blk,
        maisMenos(j.mm),
      ])
    )
  );
  return bloco;
}

async function carregarBox(jogo, area) {
  area.textContent = "Carregando...";
  try {
    const box = await buscar(`/jogos/${jogo.id}/boxscore`);
    area.replaceChildren(
      tabelaBox(box.fora),
      tabelaBox(box.casa),
      el(
        "p",
        "legenda",
        "FG: arremessos de quadra · 3PT: bolas de três · FT: lances livres · TO: turnovers · " +
          "PF: faltas · STL: roubos de bola · BLK: tocos · +/-: saldo de pontos com o jogador em quadra"
      )
    );
  } catch {
    area.textContent = "Não foi possível carregar o box score.";
  }
}

function cartaoJogo(jogo) {
  const cartao = el("article", "cartao");

  const aoVivo = jogo.estado === 2;
  cartao.append(el("div", aoVivo ? "status ao-vivo" : "status", textoStatus(jogo)));

  for (const lado of [jogo.fora, jogo.casa]) {
    const linha = el("div", "time");
    linha.append(
      el("span", "sigla", lado.sigla),
      el("span", "nome", lado.nome),
      el("strong", "placar", lado.placar ?? "–")
    );
    cartao.append(linha);

    if (lado.lider) {
      const l = lado.lider;
      cartao.append(el("div", "lider", `${l.nome}: ${l.pts} pts, ${l.reb} reb, ${l.ast} ast`));
    }
  }

  // jogos que ainda não começaram não têm box score
  if (jogo.estado >= 2) {
    const botao = el("button", "detalhes", "Ver box score");
    const area = el("div", "box");
    area.hidden = true;

    async function alternar() {
      if (area.hidden) {
        area.hidden = false;
        cartao.classList.add("aberto");
        abertos.add(jogo.id);
        botao.textContent = "Esconder box score";
        await carregarBox(jogo, area);
      } else {
        area.hidden = true;
        cartao.classList.remove("aberto");
        abertos.delete(jogo.id);
        botao.textContent = "Ver box score";
      }
    }

    botao.addEventListener("click", alternar);
    cartao.append(botao, area);

    if (abertos.has(jogo.id)) alternar(); // reabre após atualizar a lista
  }

  return cartao;
}

async function carregarJogos() {
  const secao = document.getElementById("jogos");

  if (!dataAtual) {
    secao.replaceChildren(el("p", null, "Nenhuma data disponível."));
    return;
  }

  const dataPedida = dataAtual;
  try {
    const jogos = await buscar("/jogos?data=" + dataPedida);
    if (dataPedida !== dataAtual) return; // o usuário já trocou de dia

    haAoVivo = jogos.some((j) => j.estado === 2);
    if (jogos.length === 0) {
      secao.replaceChildren(el("p", null, "Nenhum jogo nesta data."));
    } else {
      secao.replaceChildren(...jogos.map(cartaoJogo));
    }
    document.getElementById("atualizado").textContent =
      "Atualizado às " + new Date().toLocaleTimeString("pt-BR", { timeZone: FUSO });
  } catch {
    if (dataPedida !== dataAtual) return;
    secao.replaceChildren(el("p", null, "Não foi possível carregar os jogos."));
  }
}

/* ---------- Navegação entre dias ---------- */

function diaVizinho(sentido) {
  if (sentido < 0) {
    const antes = datas.filter((d) => d < dataAtual);
    return antes.length ? antes[antes.length - 1] : null;
  }
  const depois = datas.filter((d) => d > dataAtual);
  return depois.length ? depois[0] : null;
}

function dataInicial() {
  if (datas.includes(hoje)) return hoje;
  const anteriores = datas.filter((d) => d < hoje);
  if (anteriores.length) return anteriores[anteriores.length - 1];
  return datas[0] || null;
}

function atualizarBarra() {
  seletor.value = dataAtual || "";
  botaoAnterior.disabled = !diaVizinho(-1);
  botaoSeguinte.disabled = !diaVizinho(1);
}

function mudarData(nova) {
  if (!nova || nova === dataAtual) return;
  dataAtual = nova;
  abertos.clear();
  atualizarBarra();
  carregarJogos();
}

botaoAnterior.addEventListener("click", () => mudarData(diaVizinho(-1)));
botaoSeguinte.addEventListener("click", () => mudarData(diaVizinho(1)));
botaoHoje.addEventListener("click", () => mudarData(dataInicial()));
seletor.addEventListener("change", () => mudarData(seletor.value));

/* ---------- Classificação ---------- */

async function carregarClassificacao() {
  const secao = document.getElementById("classificacao");
  secao.textContent = "Carregando...";
  try {
    const dados = await buscar("/classificacao");
    const blocos = Object.entries(dados).map(([conferencia, times]) => {
      const bloco = el("div", "bloco");
      bloco.append(el("h2", null, "Conferência " + conferencia));
      bloco.append(
        tabela(
          ["#", "Time", "V", "D", "%"],
          times.map((t) => [t.posicao, t.time, t.vitorias, t.derrotas, t.aproveitamento.toFixed(3)])
        )
      );
      return bloco;
    });
    secao.replaceChildren(...blocos);
  } catch {
    secao.textContent = "Não foi possível carregar a classificação.";
  }
}

/* ---------- Painel do jogador ---------- */

const ROTULOS_RECORDE = [
  ["pts", "Pontos"],
  ["reb", "Rebotes"],
  ["ast", "Assistências"],
  ["stl", "Roubos de bola"],
  ["blk", "Tocos"],
  ["tres", "Bolas de três"],
];

function dataCurta(iso) {
  // '2026-10-23' -> '23/10'
  return /^\d{4}-\d{2}-\d{2}/.test(iso) ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : iso;
}

function formatarPct(v) {
  return v === null || v === undefined ? "–" : v.toFixed(1) + "%";
}

function cartaoMedia(rotulo, valor) {
  const c = el("div", "media");
  c.append(el("strong", null, valor), el("span", null, rotulo));
  return c;
}

function blocoMedias(m) {
  const grade = el("div", "medias");
  grade.append(
    cartaoMedia("PTS", m.pts),
    cartaoMedia("REB", m.reb),
    cartaoMedia("AST", m.ast),
    cartaoMedia("STL", m.stl),
    cartaoMedia("BLK", m.blk),
    cartaoMedia("TO", m.to),
    cartaoMedia("MIN", m.min),
    cartaoMedia("FG%", formatarPct(m.fg_pct)),
    cartaoMedia("3PT%", formatarPct(m.tres_pct)),
    cartaoMedia("FT%", formatarPct(m.ll_pct))
  );
  return grade;
}

function blocoRecordes(recordes) {
  const caixa = el("div", "box");
  caixa.append(
    tabela(
      ["Estatística", "Recorde", "Jogo"],
      ROTULOS_RECORDE.map(([chave, nome]) => {
        const r = recordes[chave];
        return [nome, r.valor, `${dataCurta(r.jogo.data)} · ${r.jogo.confronto}`];
      })
    )
  );
  return caixa;
}

function graficoPontos(jogos) {
  // a lista vem do jogo mais recente para o mais antigo; o gráfico vai do primeiro ao último
  const ordem = [...jogos].reverse();
  const maximo = Math.max(...ordem.map((j) => j.pts), 1);
  const grafico = el("div", "grafico");
  ordem.forEach((j) => {
    const barra = el("div", "barra");
    barra.style.height = (j.pts / maximo) * 100 + "%";
    barra.title = `${dataCurta(j.data)} ${j.confronto}: ${j.pts} pts`;
    barra.append(el("span", null, j.pts));
    grafico.append(barra);
  });
  return grafico;
}

function resultado(wl) {
  if (wl === "W") return { texto: "V", classe: "positivo" };
  if (wl === "L") return { texto: "D", classe: "negativo" };
  return "";
}

function tabelaJogos(jogos) {
  const caixa = el("div", "box");
  caixa.append(
    tabela(
      ["Data", "Jogo", "Res.", "MIN", "PTS", "REB", "AST", "FG", "3PT"],
      jogos.map((j) => [
        dataCurta(j.data), j.confronto, resultado(j.resultado),
        j.min, j.pts, j.reb, j.ast, j.fg, j.tres,
      ])
    )
  );
  return caixa;
}

function corpoJogador(dados) {
  if (!dados.jogos_disputados) {
    return [el("p", null, "Ainda não jogou nesta temporada.")];
  }
  return [
    el("p", "status", `Temporada ${dados.temporada} · ${dados.jogos_disputados} jogos`),
    el("h3", null, "Médias da temporada"),
    blocoMedias(dados.medias),
    el("h3", null, "Recordes da temporada"),
    blocoRecordes(dados.recordes),
    el("h3", null, "Pontos por jogo"),
    graficoPontos(dados.jogos),
    el("h3", null, "Todos os jogos"),
    tabelaJogos(dados.jogos),
  ];
}

async function abrirJogador(jogador) {
  jogadorAberto = jogador.id;
  conteudoJogador.replaceChildren(el("h2", null, jogador.nome), el("p", null, "Carregando..."));
  if (!dialogoJogador.open) dialogoJogador.showModal();

  try {
    const dados = await buscar(`/jogadores/${jogador.id}`);
    if (jogadorAberto !== jogador.id) return; // fechou ou abriu outro jogador
    conteudoJogador.replaceChildren(el("h2", null, jogador.nome), ...corpoJogador(dados));
  } catch {
    if (jogadorAberto !== jogador.id) return;
    conteudoJogador.replaceChildren(
      el("h2", null, jogador.nome),
      el("p", null, "Não foi possível carregar os dados do jogador.")
    );
  }
}

document.getElementById("fechar-jogador").addEventListener("click", () => dialogoJogador.close());

// clicar fora do painel (no fundo escurecido) também fecha
dialogoJogador.addEventListener("click", (e) => {
  if (e.target === dialogoJogador) dialogoJogador.close();
});

dialogoJogador.addEventListener("close", () => {
  jogadorAberto = null;
});

/* ---------- Abas e atualização automática ---------- */

let abaAtual = "jogos";

document.querySelectorAll(".aba").forEach((botao) => {
  botao.addEventListener("click", () => {
    abaAtual = botao.dataset.aba;
    document.querySelectorAll(".aba").forEach((b) => b.classList.toggle("ativa", b === botao));
    document.getElementById("jogos").hidden = abaAtual !== "jogos";
    document.getElementById("barra-datas").hidden = abaAtual !== "jogos";
    document.getElementById("classificacao").hidden = abaAtual !== "classificacao";
    if (abaAtual === "jogos") carregarJogos();
    else carregarClassificacao();
  });
});

async function iniciar() {
  try {
    const info = await buscar("/datas");
    datas = info.datas;
    hoje = info.hoje;
    seletor.min = datas[0] || "";
    seletor.max = datas[datas.length - 1] || "";
    dataAtual = dataInicial();
  } catch {
    document
      .getElementById("jogos")
      .replaceChildren(el("p", null, "Não foi possível carregar o calendário."));
    return;
  }
  atualizarBarra();
  carregarJogos();
}

iniciar();

// só atualiza sozinho quando faz sentido: dia de hoje ou jogo em andamento
setInterval(() => {
  if (abaAtual === "jogos" && !document.hidden && (dataAtual === hoje || haAoVivo)) {
    carregarJogos();
  }
}, 20000);