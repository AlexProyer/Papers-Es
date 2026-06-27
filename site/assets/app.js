"use strict";

// Estado de la app
const state = {
  index: null,
  day: null,       // datos del día cargado
  filters: { source: "", topic: "", query: "" },
};

const $ = (sel) => document.querySelector(sel);

const els = {
  date: $("#date-select"),
  source: $("#source-select"),
  topic: $("#topic-select"),
  search: $("#search"),
  status: $("#status"),
  papers: $("#papers"),
  tpl: $("#card-template"),
};

async function getJSON(path) {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

async function init() {
  try {
    state.index = await getJSON("data/index.json");
  } catch (e) {
    els.status.textContent =
      "No se pudo cargar el índice de datos. ¿Ya corrió el build?";
    return;
  }

  const days = state.index.days || [];
  if (!days.length) {
    els.status.textContent = "Todavía no hay datos publicados.";
    return;
  }

  els.date.innerHTML = days
    .map((d) => `<option value="${d.file}">${d.date} · ${d.paper_count} papers</option>`)
    .join("");

  els.date.addEventListener("change", () => loadDay(els.date.value));
  els.source.addEventListener("change", () => {
    state.filters.source = els.source.value;
    render();
  });
  els.topic.addEventListener("change", () => {
    state.filters.topic = els.topic.value;
    render();
  });
  els.search.addEventListener("input", () => {
    state.filters.query = els.search.value.trim().toLowerCase();
    render();
  });

  await loadDay(days[0].file);
}

async function loadDay(file) {
  els.status.textContent = "Cargando…";
  try {
    state.day = await getJSON(`data/${file}`);
  } catch (e) {
    els.status.textContent = "No se pudo cargar ese día.";
    return;
  }
  populateFilterOptions();
  render();
}

function populateFilterOptions() {
  const papers = state.day.papers || [];
  const sources = [...new Set(papers.map((p) => p.source).filter(Boolean))].sort();
  const topics = [...new Set(papers.flatMap((p) => p.topics || []))].sort();

  els.source.innerHTML =
    `<option value="">Todas</option>` +
    sources.map((s) => `<option value="${s}">${s}</option>`).join("");
  els.topic.innerHTML =
    `<option value="">Todos</option>` +
    topics.map((t) => `<option value="${escapeAttr(t)}">${escapeHtml(t)}</option>`).join("");

  // Conservar selección si sigue siendo válida
  els.source.value = state.filters.source;
  els.topic.value = state.filters.topic;
}

function matches(paper) {
  const { source, topic, query } = state.filters;
  if (source && paper.source !== source) return false;
  if (topic && !(paper.topics || []).includes(topic)) return false;
  if (query) {
    const hay = [
      paper.title,
      (paper.authors || []).join(" "),
      (paper.topics || []).join(" "),
      paper.abstract_en,
      paper.summary_es ? Object.values(paper.summary_es).flat().join(" ") : "",
    ]
      .join(" ")
      .toLowerCase();
    if (!hay.includes(query)) return false;
  }
  return true;
}

function render() {
  const papers = (state.day.papers || []).filter(matches);
  els.status.textContent =
    `${papers.length} de ${(state.day.papers || []).length} papers · ` +
    `generado ${formatDate(state.day.generated_at)}`;

  els.papers.innerHTML = "";
  if (!papers.length) {
    els.papers.innerHTML = `<p class="empty">Ningún paper coincide con los filtros.</p>`;
    return;
  }
  const frag = document.createDocumentFragment();
  for (const p of papers) frag.appendChild(renderCard(p));
  els.papers.appendChild(frag);
}

function renderCard(p) {
  const node = els.tpl.content.cloneNode(true);
  const q = (sel) => node.querySelector(sel);

  const score = q(".score");
  score.textContent = `${p.score}`;
  score.classList.add(p.score >= 55 ? "high" : p.score >= 40 ? "mid" : "");

  q(".source").textContent = p.venue || p.source || "";
  q(".date").textContent = p.date || "";
  q(".title").textContent = p.title || "Sin título";
  q(".authors").textContent = (p.authors || []).join(", ") ||
    "Autores no disponibles";

  const s = p.summary_es;
  const tldr = q(".tldr");
  if (s && s.tldr) {
    tldr.textContent = s.tldr;
  } else {
    tldr.textContent = (p.abstract_en || "").slice(0, 220) +
      (p.abstract_en && p.abstract_en.length > 220 ? "…" : "") +
      "  (resumen en español no disponible)";
    tldr.classList.add("fallback");
  }

  const tags = q(".tags");
  const tagList = (s && s.tags) || p.topics || [];
  tags.innerHTML = tagList.map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("");

  const details = q(".summary");
  const body = q(".summary-body");
  if (s) {
    body.innerHTML = [
      ["Qué problema resuelve", s.problema],
      ["Qué propone", s.propuesta],
      ["Resultados clave", s.resultados],
      ["Por qué importa", s.por_que_importa],
    ]
      .filter(([, v]) => v)
      .map(([k, v]) => `<dt>${k}</dt><dd>${escapeHtml(v)}</dd>`)
      .join("");
  } else {
    details.remove();
  }

  const links = q(".links");
  let html = "";
  if (p.url) html += `<a href="${escapeAttr(p.url)}" target="_blank" rel="noopener">🔗 Paper</a>`;
  if (p.pdf_url) html += `<a href="${escapeAttr(p.pdf_url)}" target="_blank" rel="noopener">📄 PDF</a>`;
  links.innerHTML = html;

  return node;
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("es", { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function escapeAttr(s) { return escapeHtml(s); }

init();
