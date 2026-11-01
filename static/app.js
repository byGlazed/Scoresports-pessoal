const FUSO = "America/Sao_Paulo";

// Intervalos de atualização da aba Jogos (em milissegundos)
const INTERVALO_AO_VIVO = 10000; // há jogo em andamento
const INTERVALO_NORMAL = 30000;  // nenhum jogo em andamento

const SVG_NS = "http://www.w3.org/2000/svg";
const urlLogo = (id) => `https://cdn.nba.com/logos/nba/${id}/global/L/logo.svg`;
const urlFoto = (id, tamanho = "1040x760") =>
  `https://cdn.nba.com/headshots/nba/latest/${tamanho}/${id}.png`;

const abertos = new Set();         // box scores abertos, para não fechar na atualização
const ultimoBox = new Map();       // id do jogo -> { box, estado } do último box score recebido
const timeEscolhido = new Map();   // id do jogo -> "fora" | "casa" (time exibido no box score)
const cacheTemporada = new Map();  // id do jogador -> dados da temporada
const cacheArremessos = new Map(); // "idJogo:idJogador" -> lista de arremessos
const falhas = new Set();          // pedidos que deram erro (para mostrar a mensagem certa)
const cachePreJogo = new Map();    // id do jogo -> { dados, em } (pré-jogo dos jogos que vão acontecer)
const abaPreJogo = new Map();      // id do jogo -> aba escolhida no pré-jogo

let datas = [];                    // dias que têm jogos
let hoje = null;
let dataAtual = null;
let haAoVivo = false;
let abaAtual = "jogos";
let modoLideres = "media";

const seletor = document.getElementById("seletor-data");
const botaoAnterior = document.getElementById("dia-anterior");
const botaoSeguinte = document.getElementById("dia-seguinte");
const botaoHoje = document.getElementById("hoje");
const faixaDatas = document.getElementById("faixa-datas");

const dialogoJogador = document.getElementById("jogador-dialogo");
const conteudoJogador = document.getElementById("jogador-conteudo");

/* ---------- Funções de apoio ---------- */

function el(tag, classe, texto) {
  const e = document.createElement(tag);
  if (classe) e.className = classe;
  if (texto !== undefined && texto !== null) e.textContent = texto;
  return e;
}

function svg(tag, atributos = {}) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [chave, valor] of Object.entries(atributos)) e.setAttribute(chave, String(valor));
  return e;
}

async function buscar(caminho) {
  const resp = await fetch(caminho);
  if (!resp.ok) throw new Error("Erro " + resp.status);
  return resp.json();
}

function imagem(url, classe, alt = "") {
  const img = el("img", classe);
  img.src = url;
  img.alt = alt;
  img.loading = "lazy";
  img.addEventListener("error", () => {
    img.hidden = true; // se a imagem não carregar, ela simplesmente some
  });
  return img;
}

function logoTime(timeId, classe = "logo") {
  return timeId ? imagem(urlLogo(timeId), classe) : null;
}

// uma célula pode ser um valor simples ou { texto, classe, aoClicar, logo }
function tabela(colunas, linhas) {
  const t = el("table");
  const cab = el("tr");
  colunas.forEach((c) => cab.append(el("th", null, c)));
  t.append(cab);

  linhas.forEach((valores) => {
    const tr = el("tr");
    valores.forEach((v) => {
      const objeto = v !== null && typeof v === "object";
      const td = el("td", objeto ? v.classe : null);
      if (objeto) {
        const logo = v.logo ? logoTime(v.logo, "logo-mini") : null;
        if (logo) td.append(logo);
        if (v.aoClicar) {
          const botao = el("button", "link-jogador", v.texto);
          botao.addEventListener("click", v.aoClicar);
          td.append(botao);
        } else {
          td.append(el("span", null, v.texto));
        }
      } else {
        td.textContent = v ?? "";
      }
      tr.append(td);
    });
    t.append(tr);
  });
  return t;
}

// só cria link para endereços conhecidos (NBA.com, ESPN Brasil, Prime Video e YouTube)
const PREFIXOS_LINK = [
  "https://www.nba.com/",
  "https://www.espn.com.br/",
  "https://www.primevideo.com/",
  "https://www.youtube.com/",
];

function linkSeguro(texto, url) {
  if (typeof url === "string" && PREFIXOS_LINK.some((p) => url.startsWith(p))) {
    const a = el("a", null, texto);
    a.href = url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  }
  return el("span", null, texto);
}

function maisMenos(n) {
  if (n > 0) return { texto: "+" + n, classe: "positivo" };
  if (n < 0) return { texto: String(n), classe: "negativo" };
  return { texto: "0", classe: "" };
}

// "12/13" -> "12/13 (92%)"
function comPct(valor) {
  if (typeof valor !== "string" || !valor.includes("/")) return "–";
  const [feitos, tentados] = valor.split("/").map(Number);
  return tentados > 0 ? `${feitos}/${tentados} (${Math.round((100 * feitos) / tentados)}%)` : valor;
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

/* ---------- Box score ---------- */

function tabelaBox(time, contexto) {
  const caixa = el("div", "box");
  caixa.append(
    tabela(
      ["Jogador", "MIN", "PTS", "REB", "AST", "FG", "3PT", "FT", "TO", "PF", "STL", "BLK", "+/-"],
      time.jogadores.map((j) => [
        { texto: j.nome, aoClicar: () => abrirJogador(j, contexto) },
        j.min, j.pts, j.reb, j.ast,
        j.fg, j.tres, j.ll, j.to, j.faltas, j.stl, j.blk,
        maisMenos(j.mm),
      ])
    )
  );
  return caixa;
}

function mostrarBox(box, area, jogo) {
  const lado = timeEscolhido.get(jogo.id) || "fora";

  // botões para escolher qual time aparece (visitante ou mandante)
  const escolha = el("div", "segmentos");
  for (const chave of ["fora", "casa"]) {
    const time = box[chave];
    const botao = el("button", chave === lado ? "ativo" : "");
    const logo = logoTime(time.time_id, "logo-mini");
    if (logo) botao.append(logo);
    botao.append(el("span", null, time.sigla));
    botao.addEventListener("click", () => {
      timeEscolhido.set(jogo.id, chave);
      const atual = (ultimoBox.get(jogo.id) || {}).box || box;
      mostrarBox(atual, area, jogo);
    });
    escolha.append(botao);
  }

  area.replaceChildren(
    escolha,
    tabelaBox(box[lado], { jogo, box, lado }),
    el(
      "p",
      "legenda",
      "FG: arremessos de quadra · 3PT: bolas de três · FT: lances livres · TO: turnovers · " +
        "PF: faltas · STL: roubos de bola · BLK: tocos · +/-: saldo de pontos com o jogador em quadra. " +
        "Toque no nome de um jogador para ver o mapa de arremessos."
    )
  );
}

async function carregarBox(jogo, area) {
  // mostra na hora o último box recebido, para a tela não piscar a cada atualização
  const guardado = ultimoBox.get(jogo.id);
  if (guardado) {
    mostrarBox(guardado.box, area, jogo);
    // jogo terminado e box final já guardado: não precisa buscar de novo
    if (guardado.estado === 3 && jogo.estado === 3) return;
  } else {
    area.textContent = "Carregando...";
  }

  try {
    const box = await buscar(`/jogos/${jogo.id}/boxscore`);
    ultimoBox.set(jogo.id, { box, estado: jogo.estado });
    mostrarBox(box, area, jogo);
  } catch {
    if (!guardado) area.textContent = "Não foi possível carregar o box score.";
  }
}

/* ---------- Pré-jogo (jogos que ainda vão acontecer) ---------- */

const VALIDADE_PRE_JOGO = 5 * 60 * 1000; // busca de novo depois de 5 minutos

const ABAS_PRE_JOGO = [
  ["assistir", "Onde assistir"],
  ["escalacoes", "Escalações"],
  ["confronto", "Confronto direto"],
  ["medias", "Médias"],
];

const ESTATISTICAS_DO_TIME = [
  ["PTS", "Pontos"],
  ["REB", "Rebotes"],
  ["AST", "Assistências"],
  ["STL", "Roubos de bola"],
  ["BLK", "Tocos"],
  ["FG3M", "Bolas de três"],
];

const LINKS_PROGRAMACAO = [
  ["ESPN Brasil", "https://www.espn.com.br/nba/"],
  ["Prime Video", "https://www.primevideo.com/"],
  ["YouTube da NBA Brasil", "https://www.youtube.com/results?search_query=NBA+Brasil+ao+vivo"],
];

const STATUS_LESAO = {
  out: ["Fora", "negativo"],
  "day-to-day": ["Dúvida", "alerta"],
  questionable: ["Dúvida", "alerta"],
  doubtful: ["Improvável", "negativo"],
  probable: ["Provável", "positivo"],
  available: ["Disponível", "positivo"],
};

// a fonte das lesões (ESPN) vem em inglês; traduzimos os termos mais comuns
const TERMOS_LESAO = {
  knee: "joelho", ankle: "tornozelo", foot: "pé", hip: "quadril", calf: "panturrilha",
  shoulder: "ombro", wrist: "punho", thumb: "polegar", finger: "dedo", groin: "virilha",
  back: "costas", hamstring: "posterior da coxa", achilles: "tendão de Aquiles",
  quadricep: "quadríceps", quad: "quadríceps", hand: "mão", elbow: "cotovelo", toe: "dedo do pé",
  neck: "pescoço", head: "cabeça", leg: "perna", rib: "costela", eye: "olho", nose: "nariz",
  illness: "doença", rest: "descanso", concussion: "concussão", soreness: "dor",
  sprain: "entorse", strain: "distensão", surgery: "cirurgia", fracture: "fratura",
  tendinitis: "tendinite", contusion: "contusão", injury: "lesão", bruise: "hematoma",
  "personal reasons": "motivos pessoais", "injury management": "controle de lesão",
  "load management": "controle de carga", "g league": "G League",
};

function statusLesao(status) {
  const chave = String(status || "").toLowerCase();
  return STATUS_LESAO[chave] || [status || "Sem status", "alerta"];
}

function traduzirTermo(texto) {
  const original = String(texto || "").trim();
  return TERMOS_LESAO[original.toLowerCase()] || original;
}

function descreverLesao(l) {
  const parte = traduzirTermo(l.parte);
  const detalhe = traduzirTermo(l.detalhe);
  if (parte && detalhe) return `${detalhe} (${parte})`;
  return parte || detalhe || traduzirTermo(l.motivo);
}

function dataCurtaAno(iso) {
  // '2026-10-23' -> '23/10/26'
  return /^\d{4}-\d{2}-\d{2}/.test(iso) ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(2, 4)}` : iso;
}

function cabecalhoTime(time) {
  const c = el("div", "pre-time");
  const logo = logoTime(time.time_id, "logo-mini");
  if (logo) c.append(logo);
  c.append(el("strong", null, time.nome));
  return c;
}

/* --- aba "Onde assistir" --- */

function painelAssistir(dados) {
  const painel = el("div", "pre-painel");
  painel.append(el("h3", null, "Onde assistir no Brasil"));

  const hora = dados.jogo.inicio ? horaBrasilia(dados.jogo.inicio) : null;
  if (hora) {
    painel.append(el("p", "info", `${dataBR(dados.jogo.data)} às ${hora} (horário de Brasília)`));
  }

  const t = dados.transmissao;
  if (t && t.canais.length) {
    const canais = el("div", "canais");
    t.canais.forEach((c) => canais.append(el("span", "canal", c)));
    painel.append(canais);
    const nota = [];
    if (t.conferido_em) nota.push(`Conferido em ${dataBR(t.conferido_em)}`);
    if (t.observacao) nota.push(t.observacao);
    if (nota.length) painel.append(el("p", "legenda", nota.join(" · ")));
  } else {
    painel.append(
      el("p", "status", "O canal deste jogo ainda não está cadastrado no app. Confira a programação abaixo.")
    );
  }

  painel.append(
    el(
      "p",
      "info",
      "O NBA League Pass (assinatura, pelo app da NBA ou pelo Prime Video) mostra todos os jogos. " +
        "A ESPN 2, com o Disney+ Premium, e o Prime Video transmitem jogos selecionados, " +
        "e o canal da NBA Brasil no YouTube exibe alguns jogos ao vivo."
    )
  );

  const links = el("p", "links-programacao", "Conferir a programação: ");
  LINKS_PROGRAMACAO.forEach(([texto, url]) => links.append(linkSeguro(texto, url)));
  painel.append(links);
  return painel;
}

/* --- aba "Escalações" (provável quinteto e lesionados) --- */

function colunaEscalacao(dados, lado) {
  const time = dados.jogo[lado];
  const info = dados.times[lado];
  const coluna = el("div", "pre-coluna");
  coluna.append(cabecalhoTime(time));

  coluna.append(el("h4", null, "Provável quinteto"));
  const esc = info.escalacao;
  if (!esc || esc.quinteto.length === 0) {
    coluna.append(el("p", "status", "Ainda não há jogos suficientes para estimar o quinteto."));
  } else {
    const lista = el("div", "lista-jogadores");
    for (const p of esc.quinteto) {
      const linha = el("div", "linha-jogador");
      const botao = el("button", "link-jogador", p.nome);
      botao.addEventListener("click", () =>
        abrirJogador({ id: p.id, nome: p.nome, time: time.nome, camisa: p.camisa, posicao: p.posicao })
      );
      linha.append(
        el("span", "pos", p.posicao || "–"),
        botao,
        el(
          "span",
          "detalhe",
          esc.criterio === "titulares" ? `titular em ${p.titular_em}/${esc.jogos_base}` : `${p.min_medio} min`
        )
      );
      lista.append(linha);
    }
    coluna.append(
      lista,
      el(
        "p",
        "legenda",
        esc.criterio === "titulares"
          ? `Estimativa com base em quem mais começou jogando nos últimos ${esc.jogos_base} jogo(s), sem os jogadores marcados como fora.`
          : `Estimativa com base em quem mais jogou nos últimos ${esc.jogos_base} jogo(s).`
      )
    );
  }

  coluna.append(el("h4", null, "Lesionados"));
  if (dados.falhas.includes("lesoes")) {
    coluna.append(el("p", "status", "A lista de lesões está indisponível agora."));
  } else if (info.lesionados.length === 0) {
    coluna.append(el("p", "status", "Nenhum jogador no relatório de lesões."));
  } else {
    const lista = el("div", "lista-lesoes");
    for (const l of info.lesionados) {
      const [rotulo, classe] = statusLesao(l.status);
      const linha = el("div", "linha-lesao");
      linha.append(el("span", "chip-status " + classe, rotulo), el("span", "nome-lesao", l.nome));
      const partes = [descreverLesao(l)];
      if (/^\d{4}-\d{2}-\d{2}/.test(l.retorno || "")) partes.push("retorno previsto " + dataBR(l.retorno.slice(0, 10)));
      const texto = partes.filter(Boolean).join(" · ");
      if (texto) linha.append(el("span", "detalhe", texto));
      lista.append(linha);
    }
    coluna.append(lista, el("p", "legenda", "Fonte das lesões: ESPN (não oficial)."));
  }
  return coluna;
}

function painelEscalacoes(dados) {
  const colunas = el("div", "pre-colunas");
  colunas.append(colunaEscalacao(dados, "fora"), colunaEscalacao(dados, "casa"));
  return colunas;
}

/* --- aba "Confronto direto" (e forma recente) --- */

function blocoForma(time, forma) {
  const bloco = el("div", "pre-coluna");
  bloco.append(cabecalhoTime(time));
  if (forma.length === 0) {
    bloco.append(el("p", "status", "Ainda sem jogos nesta temporada."));
    return bloco;
  }

  const selos = el("div", "forma");
  [...forma].reverse().forEach((j) => {
    const selo = el("span", j.resultado === "V" ? "v" : "d", j.resultado);
    selo.title = `${dataCurta(j.data)} ${j.local === "casa" ? "vs" : "@"} ${j.adversario}: ${j.pontos}-${j.pontos_adv}`;
    selos.append(selo);
  });

  const caixa = el("div", "box");
  caixa.append(
    tabela(
      ["Data", "Jogo", "Placar"],
      forma.map((j) => [
        dataCurta(j.data),
        `${j.local === "casa" ? "vs" : "@"} ${j.adversario}`,
        { texto: `${j.pontos}-${j.pontos_adv}`, classe: j.resultado === "V" ? "positivo" : "negativo" },
      ])
    )
  );
  bloco.append(selos, caixa);
  return bloco;
}

function painelConfronto(dados) {
  const painel = el("div", "pre-painel");
  painel.append(el("h3", null, "Últimos confrontos entre os times"));

  const c = dados.confronto;
  if (!c || c.jogos.length === 0) {
    const texto = dados.falhas.includes("confronto")
      ? "O confronto direto está indisponível agora."
      : "Os times não se enfrentaram nos últimos anos.";
    painel.append(el("p", "status", texto));
  } else {
    const { fora, casa } = dados.jogo;
    painel.append(
      el("p", "resumo-h2h", `${fora.sigla} ${c.vitorias_fora} × ${c.vitorias_casa} ${casa.sigla} nos últimos ${c.jogos.length} jogos`)
    );
    const caixa = el("div", "box");
    caixa.append(
      tabela(
        ["Data", "Mandante", "Placar", "Visitante"],
        c.jogos.map((g) => {
          const mandanteVenceu = g.vencedor === g.mandante;
          return [
            dataCurtaAno(g.data),
            { texto: g.mandante, classe: mandanteVenceu ? "forte" : "fraco" },
            `${g.pontos_mandante} - ${g.pontos_visitante}`,
            { texto: g.visitante, classe: mandanteVenceu ? "fraco" : "forte" },
          ];
        })
      )
    );
    painel.append(caixa);
  }

  painel.append(el("h3", null, "Últimos jogos de cada time"));
  const colunas = el("div", "pre-colunas");
  colunas.append(blocoForma(dados.jogo.fora, dados.times.fora.forma), blocoForma(dados.jogo.casa, dados.times.casa.forma));
  painel.append(colunas);
  return painel;
}

/* --- aba "Médias" (maior média de cada time em cada estatística) --- */

function ladoMedia(lider, sigla, classe) {
  const lado = el("div", classe);
  if (!lider) {
    lado.append(el("span", "detalhe", "–"));
    return lado;
  }
  const botao = el("button", "link-jogador", lider.nome);
  botao.addEventListener("click", () => abrirJogador({ id: lider.id, nome: lider.nome, time: sigla }));
  lado.append(botao, el("strong", null, lider.valor.toFixed(1)));
  return lado;
}

function painelMedias(dados) {
  const painel = el("div", "pre-painel");
  painel.append(el("h3", null, "Maiores médias de cada time"));

  const { fora, casa } = dados.jogo;
  const lideresFora = dados.times.fora.lideres;
  const lideresCasa = dados.times.casa.lideres;
  if (lideresFora.length === 0 && lideresCasa.length === 0) {
    const texto = dados.falhas.includes("estatisticas")
      ? "As estatísticas estão indisponíveis agora."
      : "Ainda não há estatísticas nesta temporada.";
    painel.append(el("p", "status", texto));
    return painel;
  }

  const cabecalho = el("div", "medias-linha cabecalho");
  cabecalho.append(cabecalhoTime(fora), el("span"), cabecalhoTime(casa));
  painel.append(cabecalho);

  for (const [chave, rotulo] of ESTATISTICAS_DO_TIME) {
    const linha = el("div", "medias-linha");
    linha.append(
      ladoMedia(lideresFora.find((l) => l.chave === chave), fora.sigla, "media-lado"),
      el("span", "rotulo-media", rotulo),
      ladoMedia(lideresCasa.find((l) => l.chave === chave), casa.sigla, "media-lado dir")
    );
    painel.append(linha);
  }
  painel.append(el("p", "legenda", "Médias por jogo na temporada. Só entram jogadores com pelo menos 70% dos jogos do time."));
  return painel;
}

/* --- estrutura do pré-jogo --- */

function mostrarPreJogo(dados, area, jogo) {
  const atual = abaPreJogo.get(jogo.id) || "assistir";

  const abas = el("div", "segmentos");
  for (const [chave, rotulo] of ABAS_PRE_JOGO) {
    const botao = el("button", chave === atual ? "ativo" : "", rotulo);
    botao.addEventListener("click", () => {
      abaPreJogo.set(jogo.id, chave);
      mostrarPreJogo((cachePreJogo.get(jogo.id) || {}).dados || dados, area, jogo);
    });
    abas.append(botao);
  }

  const paineis = {
    assistir: painelAssistir,
    escalacoes: painelEscalacoes,
    confronto: painelConfronto,
    medias: painelMedias,
  };
  area.replaceChildren(abas, paineis[atual](dados));
}

async function carregarPreJogo(jogo, area) {
  // mostra na hora o que já temos e só busca de novo depois de alguns minutos
  const guardado = cachePreJogo.get(jogo.id);
  if (guardado) {
    mostrarPreJogo(guardado.dados, area, jogo);
    if (Date.now() - guardado.em < VALIDADE_PRE_JOGO) return;
  } else {
    area.textContent = "Carregando o pré-jogo... (na primeira vez pode levar alguns segundos)";
  }

  try {
    const dados = await buscar(`/jogos/${jogo.id}/pre-jogo`);
    cachePreJogo.set(jogo.id, { dados, em: Date.now() });
    mostrarPreJogo(dados, area, jogo);
  } catch {
    if (!guardado) area.textContent = "Não foi possível carregar o pré-jogo agora.";
  }
}

/* ---------- Lista de jogos ---------- */

function cartaoJogo(jogo) {
  const cartao = el("article", "jogo");

  const aoVivo = jogo.estado === 2;
  const topo = el("div", "jogo-topo");
  topo.append(el("span", aoVivo ? "status ao-vivo" : "status", textoStatus(jogo)));
  cartao.append(topo);

  const terminou = jogo.estado === 3;
  const maior = Math.max(Number(jogo.fora.placar), Number(jogo.casa.placar));

  for (const lado of [jogo.fora, jogo.casa]) {
    const perdeu = terminou && Number(lado.placar) < maior;
    const linha = el("div", perdeu ? "lado perdedor" : "lado");
    linha.append(
      logoTime(lado.time_id) || el("span", "logo vazio"),
      el("span", "nome-time", lado.nome),
      el("strong", "pontos", lado.placar ?? "–")
    );
    cartao.append(linha);

    if (lado.lider) {
      const l = lado.lider;
      cartao.append(el("div", "lider", `${l.nome} · ${l.pts} pts, ${l.reb} reb, ${l.ast} ast`));
    }
  }

  // jogo que ainda não começou mostra o pré-jogo; os demais mostram o box score
  const preJogo = jogo.estado === 1;
  const rotulo = preJogo ? "pré-jogo" : "box score";
  const botao = el("button", "detalhes", "Ver " + rotulo);
  const area = el("div", "box");
  area.hidden = true;

  async function alternar() {
    if (area.hidden) {
      area.hidden = false;
      cartao.classList.add("aberto");
      abertos.add(jogo.id);
      botao.textContent = "Esconder " + rotulo;
      await (preJogo ? carregarPreJogo(jogo, area) : carregarBox(jogo, area));
    } else {
      area.hidden = true;
      cartao.classList.remove("aberto");
      abertos.delete(jogo.id);
      botao.textContent = "Ver " + rotulo;
    }
  }

  botao.addEventListener("click", alternar);
  cartao.append(botao, area);

  if (abertos.has(jogo.id)) alternar(); // reabre após atualizar a lista

  return cartao;
}

async function carregarJogos() {
  const secao = document.getElementById("jogos");

  if (!dataAtual) {
    secao.replaceChildren(el("p", "status", "Nenhuma data disponível."));
    return;
  }

  const dataPedida = dataAtual;
  try {
    const jogos = await buscar("/jogos?data=" + dataPedida);
    if (dataPedida !== dataAtual) return; // o usuário já trocou de dia

    haAoVivo = jogos.some((j) => j.estado === 2);
    if (jogos.length === 0) {
      secao.replaceChildren(el("p", "status", "Nenhum jogo nesta data."));
    } else {
      secao.replaceChildren(...jogos.map(cartaoJogo));
    }
    document.getElementById("atualizado").textContent =
      "Atualizado às " +
      new Date().toLocaleTimeString("pt-BR", { timeZone: FUSO }) +
      (haAoVivo ? " · ao vivo: atualiza a cada 10 segundos" : "");
  } catch {
    if (dataPedida !== dataAtual) return;
    secao.replaceChildren(el("p", "status", "Não foi possível carregar os jogos."));
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

function rotuloDia(iso) {
  const d = new Date(iso + "T12:00:00");
  const semana = d.toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");
  return { semana, dia: `${iso.slice(8, 10)}/${iso.slice(5, 7)}` };
}

// mostra 7 dias com jogos ao redor do dia escolhido
function desenharFaixa() {
  if (!dataAtual || datas.length === 0) {
    faixaDatas.replaceChildren();
    return;
  }
  const TAMANHO = 7;
  let i = datas.findIndex((d) => d >= dataAtual);
  if (i < 0) i = datas.length - 1;
  const inicio = Math.max(0, Math.min(i - 3, datas.length - TAMANHO));

  faixaDatas.replaceChildren(
    ...datas.slice(inicio, inicio + TAMANHO).map((d) => {
      const { semana, dia } = rotuloDia(d);
      let classe = "dia";
      if (d === dataAtual) classe += " ativo";
      if (d === hoje) classe += " hoje";
      const botao = el("button", classe);
      botao.append(el("span", "semana", semana), el("span", "numero", dia));
      botao.addEventListener("click", () => mudarData(d));
      return botao;
    })
  );
}

function atualizarBarra() {
  seletor.value = dataAtual || "";
  botaoAnterior.disabled = !diaVizinho(-1);
  botaoSeguinte.disabled = !diaVizinho(1);
  desenharFaixa();
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

function celulaPosicao(posicao) {
  // 1º ao 6º: playoffs direto; 7º ao 10º: play-in
  const classe = posicao <= 6 ? "zona-direta" : posicao <= 10 ? "zona-playin" : null;
  return { texto: posicao, classe };
}

async function carregarClassificacao() {
  const secao = document.getElementById("classificacao");
  if (!secao.hasChildNodes()) secao.textContent = "Carregando...";
  try {
    const dados = await buscar("/classificacao");
    const cartoes = Object.entries(dados).map(([conferencia, times]) => {
      const cartao = el("article", "cartao");
      cartao.append(el("h2", null, "Conferência " + conferencia));
      const caixa = el("div", "box");
      caixa.append(
        tabela(
          ["#", "Time", "V", "D", "%"],
          times.map((t) => [
            celulaPosicao(t.posicao),
            { texto: t.time, logo: t.time_id },
            t.vitorias,
            t.derrotas,
            t.aproveitamento.toFixed(3),
          ])
        )
      );
      cartao.append(
        caixa,
        el("p", "legenda", "Verde: 1º ao 6º, direto aos playoffs · Âmbar: 7º ao 10º, play-in")
      );
      return cartao;
    });
    secao.replaceChildren(...cartoes);
  } catch {
    secao.replaceChildren(el("p", "status", "Não foi possível carregar a classificação."));
  }
}

/* ---------- Líderes da temporada ---------- */

function cartaoLideres(categoria, modo) {
  const cartao = el("article", "cartao");
  cartao.append(el("h3", null, categoria.rotulo));

  if (categoria.jogadores.length === 0) {
    cartao.append(el("p", "status", "Ainda não há jogadores que atendam ao mínimo exigido."));
    return cartao;
  }

  const colunas = categoria.percentual
    ? ["#", "Jogador", "Time", "Feitos/Tent.", "%"]
    : ["#", "Jogador", "Time", "J", modo === "media" ? "Média" : "Total"];

  const linhas = categoria.jogadores.map((j) => [
    j.posicao,
    { texto: j.nome, aoClicar: () => abrirJogador(j) },
    j.time,
    categoria.percentual ? j.extra : j.jogos,
    categoria.percentual
      ? j.valor.toFixed(1) + "%"
      : modo === "media"
        ? j.valor.toFixed(1)
        : j.valor,
  ]);

  const caixa = el("div", "box");
  caixa.append(tabela(colunas, linhas));
  cartao.append(caixa);
  return cartao;
}

function textoNotaLideres(dados) {
  const partes = [];
  if (dados.modo === "media") {
    partes.push(
      `Médias por jogo: entram jogadores com pelo menos ${dados.minimo_jogos} jogo(s), ` +
        `cerca de 70% dos ${dados.jogos_da_liga} jogos disputados pela liga até agora.`
    );
  } else {
    partes.push("Totais da temporada: todos os jogadores que já entraram em quadra.");
  }
  partes.push(
    "Os percentuais exigem um mínimo de arremessos feitos, proporcional aos jogos disputados " +
      "(baseado na regra da NBA), e não mudam com a opção escolhida. J = jogos disputados."
  );
  return partes.join(" ");
}

async function carregarLideres() {
  const grade = document.getElementById("lideres-grade");
  const modoPedido = modoLideres;
  if (!grade.hasChildNodes()) grade.textContent = "Carregando...";

  try {
    const dados = await buscar("/lideres?modo=" + modoPedido);
    if (modoPedido !== modoLideres) return; // o usuário já trocou de opção
    grade.replaceChildren(...dados.categorias.map((c) => cartaoLideres(c, dados.modo)));
    document.getElementById("nota-lideres").textContent = textoNotaLideres(dados);
  } catch {
    if (modoPedido !== modoLideres) return;
    grade.replaceChildren(el("p", "status", "Não foi possível carregar os líderes agora."));
  }
}

const botoesModo = document.querySelectorAll("#modo-lideres button");
botoesModo.forEach((botao) => {
  botao.addEventListener("click", () => {
    modoLideres = botao.dataset.modo;
    botoesModo.forEach((b) => b.classList.toggle("ativo", b === botao));
    carregarLideres();
  });
});

/* ---------- Corridas do MVP e do calouro do ano ---------- */

function dataBR(iso) {
  // '2026-11-07' -> '07/11/2026'
  return /^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso.slice(8)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}` : iso;
}

function celulaMovimento(e) {
  if (e.movimento === "subiu") return { texto: `▲ ${e.anterior - e.posicao}`, classe: "positivo" };
  if (e.movimento === "desceu") return { texto: `▼ ${e.posicao - e.anterior}`, classe: "negativo" };
  if (e.movimento === "novo") return { texto: "novo", classe: "positivo" };
  if (e.movimento === "igual") return { texto: "=", classe: "" };
  return "";
}

function cartaoCorrida(titulo, corrida) {
  const cartao = el("article", "cartao");
  cartao.append(el("h2", null, titulo));

  if (!corrida.ranking.length) {
    cartao.append(
      el(
        "p",
        "status",
        "A NBA ainda não publicou o primeiro ranking desta temporada. " +
          "Quando sair, ele aparece aqui sozinho."
      )
    );
    const fonte = el("p", "fonte");
    fonte.append(linkSeguro("Ver a página dos rankings no NBA.com", corrida.pagina));
    cartao.append(fonte);
    return cartao;
  }

  cartao.append(el("p", "edicao", `Edição de ${dataBR(corrida.data)}`));

  const caixa = el("div", "box");
  caixa.append(
    tabela(
      ["#", "Jogador", "Time", "Mov.", "Médias na temporada"],
      corrida.ranking.map((e) => [e.posicao, e.nome, e.time, celulaMovimento(e), e.stats || ""])
    )
  );
  cartao.append(caixa);

  const fonte = el("p", "fonte", "Ranking semanal do NBA.com · ");
  fonte.append(linkSeguro("ler a análise completa", corrida.url));
  cartao.append(fonte);
  return cartao;
}

async function carregarCorridas() {
  const secao = document.getElementById("corridas");
  if (!secao.hasChildNodes()) secao.textContent = "Carregando...";
  try {
    const dados = await buscar("/corridas");
    secao.replaceChildren(
      cartaoCorrida("Corrida pelo MVP", dados.mvp),
      cartaoCorrida("Corrida pelo calouro do ano", dados.roy)
    );
  } catch {
    secao.replaceChildren(el("p", "status", "Não foi possível carregar os rankings da NBA agora."));
  }
}

/* ---------- Painel do jogador ---------- */

// estado do painel aberto: { jogador, contexto, aba, periodo }
// contexto existe quando o painel foi aberto pelo box score: { jogo, box, lado }
let dialogo = null;
let corpoEl = null;
let chipAtivo = null;
let temporizadorDialogo = null;

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

function periodoRotulo(p) {
  return p <= 4 ? "Q" + p : "OT" + (p - 4);
}

function nomeCurto(nome) {
  const partes = String(nome).trim().split(/\s+/);
  if (partes.length < 2) return String(nome);
  return `${partes[0][0]}. ${partes.slice(1).join(" ")}`;
}

function boxAtual(contexto) {
  return (ultimoBox.get(contexto.jogo.id) || {}).box || contexto.box;
}

/* --- aba "Temporada" --- */

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
    return [el("p", "status", "Ainda não jogou nesta temporada.")];
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

function corpoTemporadaDoJogador() {
  const id = dialogo.jogador.id;
  const dados = cacheTemporada.get(id);
  if (!dados) {
    const texto = falhas.has("temporada:" + id)
      ? "Não foi possível carregar os dados do jogador."
      : "Carregando...";
    return [el("p", "status", texto)];
  }
  return corpoJogador(dados);
}

/* --- aba "Neste jogo": mapa de arremessos e estatísticas --- */

function textoArremesso(a) {
  const quando = periodoRotulo(a.periodo) + (a.relogio ? " " + a.relogio : "");
  const tipo = a.tipo === "3pt" ? "bola de três" : "arremesso de 2";
  const distancia = a.distancia !== null && a.distancia !== undefined ? ` · ${a.distancia} pés` : "";
  return `${quando} · ${tipo}${distancia} · ${a.feito ? "acertou" : "errou"}`;
}

// Quadra desenhada em SVG com as medidas da NBA (cada unidade = 1/10 de pé).
// A cesta fica no ponto (0, 0), no topo; o eixo y cresce em direção à meia-quadra.
function quadraComArremessos(lista) {
  const linha = { fill: "none", stroke: "#1b1710", "stroke-opacity": 0.75, "stroke-width": 2 };
  const raiz = svg("svg", {
    viewBox: "-255 -52 510 480",
    class: "quadra",
    role: "img",
    "aria-label": "Mapa dos arremessos do jogador na quadra",
  });

  raiz.append(
    svg("rect", { x: -250, y: -47.5, width: 500, height: 470, fill: "#a88f60" }),
    svg("rect", { x: -80, y: -47.5, width: 160, height: 190, fill: "#97804f" }),
    svg("rect", { x: -250, y: -47.5, width: 500, height: 470, ...linha }),
    svg("rect", { x: -80, y: -47.5, width: 160, height: 190, ...linha }),
    svg("rect", { x: -60, y: -47.5, width: 120, height: 190, ...linha }),
    svg("path", { d: "M -60 142.5 A 60 60 0 0 0 60 142.5", ...linha }),
    svg("path", { d: "M -60 142.5 A 60 60 0 0 1 60 142.5", ...linha, "stroke-dasharray": "8 8" }),
    svg("path", { d: "M -40 0 A 40 40 0 0 0 40 0", ...linha }),
    svg("line", { x1: -30, y1: -8, x2: 30, y2: -8, ...linha }),
    svg("circle", { cx: 0, cy: 0, r: 7.5, ...linha }),
    svg("path", { d: "M -220 -47.5 L -220 89.5 A 237.5 237.5 0 0 0 220 89.5 L 220 -47.5", ...linha }),
    svg("path", { d: "M -60 422.5 A 60 60 0 0 1 60 422.5", ...linha }),
    svg("path", { d: "M -20 422.5 A 20 20 0 0 1 20 422.5", ...linha })
  );

  // erros primeiro, acertos por cima
  const ordenada = [...lista].sort((a, b) => Number(a.feito) - Number(b.feito));
  for (const a of ordenada) {
    const x = Number(a.x);
    const y = Number(a.y);
    const marca = a.feito
      ? svg("circle", { cx: x, cy: y, r: 9, fill: "#34c77b", stroke: "#10151a", "stroke-width": 3 })
      : svg("path", {
          d: `M ${x - 7} ${y - 7} L ${x + 7} ${y + 7} M ${x - 7} ${y + 7} L ${x + 7} ${y - 7}`,
          fill: "none",
          stroke: "#ee5a5f",
          "stroke-width": 4,
          "stroke-linecap": "round",
        });
    const dica = svg("title");
    dica.textContent = textoArremesso(a);
    marca.append(dica);
    raiz.append(marca);
  }
  return raiz;
}

function resumoArremessos(lista) {
  const resumo = el("p", "resumo-arremessos");
  if (lista.length === 0) {
    resumo.textContent = "Nenhum arremesso de quadra neste período.";
    return resumo;
  }
  const feitos = lista.filter((a) => a.feito).length;
  const tres = lista.filter((a) => a.tipo === "3pt");
  const tresFeitos = tres.filter((a) => a.feito).length;

  const total = el("span");
  total.append(el("strong", null, `${feitos}/${lista.length}`), ` na quadra (${Math.round((100 * feitos) / lista.length)}%)`);
  const bolas = el("span");
  bolas.append(el("strong", null, `${tresFeitos}/${tres.length}`), " bolas de três");
  const legenda = el("span");
  legenda.append(el("span", "marca-acerto", "●"), " acerto  ", el("span", "marca-erro", "✕"), " erro");
  resumo.append(total, bolas, legenda);
  return resumo;
}

function secaoArremessos() {
  const { jogador, contexto, periodo } = dialogo;
  const chave = `${contexto.jogo.id}:${jogador.id}`;
  const secao = el("div", "arremessos");
  secao.append(el("h3", null, "Mapa de arremessos"));

  const lista = cacheArremessos.get(chave);
  if (!lista) {
    const texto = falhas.has("arremessos:" + chave)
      ? "Não foi possível carregar os arremessos deste jogo."
      : "Carregando...";
    secao.append(el("p", "status", texto));
    return secao;
  }

  // filtro por período: Todos, Q1..Q4 e prorrogações, se houver
  const periodos = Math.max(4, ...lista.map((a) => a.periodo || 0));
  const opcoes = [["todos", "Todos"]];
  for (let p = 1; p <= periodos; p++) opcoes.push([p, periodoRotulo(p)]);

  const filtro = el("div", "segmentos");
  for (const [valor, rotulo] of opcoes) {
    const botao = el("button", periodo === valor ? "ativo" : "", rotulo);
    botao.addEventListener("click", () => {
      dialogo.periodo = valor;
      desenharCorpo();
    });
    filtro.append(botao);
  }

  const filtrada = periodo === "todos" ? lista : lista.filter((a) => a.periodo === periodo);
  secao.append(filtro, quadraComArremessos(filtrada), resumoArremessos(filtrada));
  return secao;
}

function linhaStat(rotulo, valor, opcoes = {}) {
  const linha = el("div", opcoes.sub ? "linha-stat sub" : "linha-stat");
  linha.append(
    el("span", "rotulo", rotulo),
    el("span", opcoes.classe ? "valor " + opcoes.classe : "valor", valor)
  );
  return linha;
}

function grupoStats(...linhas) {
  const grupo = el("div", "grupo");
  grupo.append(...linhas);
  return grupo;
}

function linhaDoJogadorNoBox() {
  const { jogador, contexto } = dialogo;
  const time = boxAtual(contexto)[contexto.lado];
  return time.jogadores.find((j) => j.id === jogador.id) || jogador;
}

function corpoJogo() {
  const j = linhaDoJogadorNoBox();
  const mm = maisMenos(j.mm);

  const grupos = el("div", "grupos");
  grupos.append(
    grupoStats(linhaStat("Minutos", j.min)),
    grupoStats(
      linhaStat("Pontos", j.pts),
      linhaStat("Lances livres", comPct(j.ll)),
      linhaStat("Arremessos de 2", comPct(j.dois)),
      linhaStat("Bolas de três", comPct(j.tres)),
      linhaStat("Arremessos de quadra", comPct(j.fg))
    ),
    grupoStats(
      linhaStat("Rebotes", j.reb),
      linhaStat("Ofensivos", j.reb_of ?? "–", { sub: true }),
      linhaStat("Defensivos", j.reb_def ?? "–", { sub: true })
    ),
    grupoStats(
      linhaStat("Assistências", j.ast),
      linhaStat("Roubos de bola", j.stl),
      linhaStat("Tocos", j.blk),
      linhaStat("Turnovers", j.to),
      linhaStat("Faltas", j.faltas),
      linhaStat("+/-", mm.texto, { classe: mm.classe })
    )
  );

  return [secaoArremessos(), el("h3", null, "Estatísticas no jogo"), grupos];
}

/* --- estrutura do painel --- */

function desenharCorpo() {
  if (!dialogo || !corpoEl) return;
  const itens = dialogo.contexto && dialogo.aba === "jogo" ? corpoJogo() : corpoTemporadaDoJogador();
  corpoEl.replaceChildren(...itens);
}

function infoDoJogador() {
  const { jogador, contexto } = dialogo;
  const info = el("div", "jogador-info");
  info.append(el("h2", null, jogador.nome));

  const sub = el("p", "jogador-sub");
  let nomeTime = jogador.time || "";
  if (contexto) {
    const time = boxAtual(contexto)[contexto.lado];
    nomeTime = time.nome;
    const logo = logoTime(time.time_id, "logo-mini");
    if (logo) sub.append(logo);
  }
  const partes = [];
  if (jogador.camisa) partes.push("#" + jogador.camisa);
  if (jogador.posicao) partes.push(jogador.posicao);
  if (nomeTime) partes.push(nomeTime);
  sub.append(el("span", null, partes.join(" · ")));
  info.append(sub);
  return info;
}

function abasDoJogador() {
  const seg = el("div", "segmentos");
  for (const [chave, rotulo] of [["jogo", "Neste jogo"], ["temporada", "Temporada"]]) {
    const botao = el("button", dialogo.aba === chave ? "ativo" : "", rotulo);
    botao.addEventListener("click", () => {
      dialogo.aba = chave;
      desenharJogador();
    });
    seg.append(botao);
  }
  return seg;
}

// colegas de time em uma faixa horizontal, para trocar de jogador sem fechar o painel
function faixaEquipe() {
  const { contexto, jogador } = dialogo;
  const time = boxAtual(contexto)[contexto.lado];
  const faixa = el("div", "equipe-faixa");
  chipAtivo = null;

  for (const j of time.jogadores) {
    const ativo = j.id === jogador.id;
    const chip = el("button", ativo ? "chip-jogador ativo" : "chip-jogador");
    chip.append(imagem(urlFoto(j.id, "260x190"), "foto-mini"), el("span", null, nomeCurto(j.nome)));
    chip.addEventListener("click", () => trocarJogador(j));
    faixa.append(chip);
    if (ativo) chipAtivo = chip;
  }
  return faixa;
}

function desenharJogador() {
  const { jogador, contexto } = dialogo;

  const cabecalho = el("div", "jogador-cabecalho");
  cabecalho.append(imagem(urlFoto(jogador.id), "foto", jogador.nome), infoDoJogador());

  corpoEl = el("div", "jogador-corpo");
  const partes = [cabecalho];
  if (contexto) partes.push(abasDoJogador());
  partes.push(corpoEl);
  if (contexto) partes.push(faixaEquipe());

  conteudoJogador.replaceChildren(...partes);
  desenharCorpo();
  if (chipAtivo) chipAtivo.scrollIntoView({ inline: "center", block: "nearest" });
}

function redesenharSeAtual(idJogador) {
  if (dialogo && dialogo.jogador.id === idJogador) desenharCorpo();
}

async function carregarTemporada(jogador) {
  if (cacheTemporada.has(jogador.id)) return;
  falhas.delete("temporada:" + jogador.id);
  try {
    cacheTemporada.set(jogador.id, await buscar(`/jogadores/${jogador.id}`));
  } catch {
    falhas.add("temporada:" + jogador.id);
  }
  redesenharSeAtual(jogador.id);
}

async function carregarArremessos(jogador, jogo, forcar = false) {
  const chave = `${jogo.id}:${jogador.id}`;
  if (cacheArremessos.has(chave) && !forcar) return;
  falhas.delete("arremessos:" + chave);
  try {
    const dados = await buscar(`/jogos/${jogo.id}/arremessos/${jogador.id}`);
    cacheArremessos.set(chave, dados.arremessos);
  } catch {
    falhas.add("arremessos:" + chave);
  }
  redesenharSeAtual(jogador.id);
}

function carregarDadosDoPainel() {
  const { jogador, contexto } = dialogo;
  carregarTemporada(jogador);
  if (contexto) carregarArremessos(jogador, contexto.jogo);
}

function trocarJogador(jogador) {
  dialogo.jogador = jogador;
  dialogo.periodo = "todos";
  desenharJogador();
  carregarDadosDoPainel();
}

function pararAtualizacaoDoPainel() {
  if (temporizadorDialogo) clearInterval(temporizadorDialogo);
  temporizadorDialogo = null;
}

// com o jogo em andamento, o painel também se atualiza (estatísticas e arremessos)
function iniciarAtualizacaoDoPainel() {
  pararAtualizacaoDoPainel();
  if (!dialogo || !dialogo.contexto || dialogo.contexto.jogo.estado !== 2) return;

  temporizadorDialogo = setInterval(async () => {
    if (!dialogo || !dialogoJogador.open || document.hidden) return;
    const { jogador, contexto } = dialogo;
    try {
      const box = await buscar(`/jogos/${contexto.jogo.id}/boxscore`);
      ultimoBox.set(contexto.jogo.id, { box, estado: contexto.jogo.estado });
      if (/^final/i.test(box.status || "")) pararAtualizacaoDoPainel();
    } catch {
      // mantém o que já está na tela
    }
    await carregarArremessos(jogador, contexto.jogo, true);
  }, INTERVALO_AO_VIVO);
}

function abrirJogador(jogador, contexto) {
  dialogo = {
    jogador,
    contexto: contexto || null,
    aba: contexto ? "jogo" : "temporada",
    periodo: "todos",
  };
  if (!dialogoJogador.open) dialogoJogador.showModal();
  desenharJogador();
  carregarDadosDoPainel();
  iniciarAtualizacaoDoPainel();
}

document.getElementById("fechar-jogador").addEventListener("click", () => dialogoJogador.close());

// clicar fora do painel (no fundo escurecido) também fecha
dialogoJogador.addEventListener("click", (e) => {
  if (e.target === dialogoJogador) dialogoJogador.close();
});

dialogoJogador.addEventListener("close", () => {
  dialogo = null;
  corpoEl = null;
  chipAtivo = null;
  pararAtualizacaoDoPainel();
});

/* ---------- Abas ---------- */

const ABAS = {
  jogos: carregarJogos,
  classificacao: carregarClassificacao,
  lideres: carregarLideres,
  corridas: carregarCorridas,
};

document.querySelectorAll(".aba").forEach((botao) => {
  botao.addEventListener("click", () => {
    abaAtual = botao.dataset.aba;
    document.querySelectorAll(".aba").forEach((b) => b.classList.toggle("ativa", b === botao));
    for (const id of Object.keys(ABAS)) {
      document.getElementById(id).hidden = id !== abaAtual;
    }
    document.getElementById("barra-datas").hidden = abaAtual !== "jogos";
    document.getElementById("atualizado").hidden = abaAtual !== "jogos";
    ABAS[abaAtual]();
  });
});

/* ---------- Início e atualização automática ---------- */

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
      .replaceChildren(el("p", "status", "Não foi possível carregar o calendário."));
    return;
  }
  atualizarBarra();
  carregarJogos();
}

// Atualiza a aba Jogos sozinha: a cada 10 s quando há jogo ao vivo, a cada 30 s nos demais casos.
// O box score aberto é atualizado junto, porque a lista inteira é desenhada de novo.
function agendarAtualizacao() {
  setTimeout(async () => {
    if (abaAtual === "jogos" && !document.hidden && (dataAtual === hoje || haAoVivo)) {
      await carregarJogos();
    }
    agendarAtualizacao();
  }, haAoVivo ? INTERVALO_AO_VIVO : INTERVALO_NORMAL);
}

// ao voltar para a aba do navegador, atualiza na hora
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && abaAtual === "jogos") carregarJogos();
});

iniciar();
agendarAtualizacao();