const STATUS_LABEL = {
  ok: "OK",
  warning: "Warning",
  error: "Error",
  info: "Info",
  not_run: "Not run yet",
};

let registryFlat = []; // [{isin, category, fund_name, klasse_name}]

async function loadRegistry() {
  const res = await fetch("/api/registry");
  const registry = await res.json();
  registryFlat = [];
  for (const [category, catDef] of Object.entries(registry)) {
    for (const [fundName, classes] of Object.entries(catDef.funds)) {
      for (const [klasseName, isin] of Object.entries(classes)) {
        registryFlat.push({ isin, category, fund_name: fundName, klasse_name: klasseName });
      }
    }
  }
  const datalist = document.getElementById("isin-options");
  datalist.innerHTML = registryFlat
    .map((r) => `<option value="${r.isin}">${r.fund_name} ${r.klasse_name} (${r.isin})</option>`)
    .join("");
}

function relativeTime(iso) {
  if (!iso) return "never";
  const then = new Date(iso);
  const diffMs = Date.now() - then.getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

function renderSummary(dashboard) {
  const counts = { ok: 0, warning: 0, error: 0, info: 0, not_run: 0 };
  for (const funds of Object.values(dashboard)) {
    for (const rows of Object.values(funds)) {
      for (const row of rows) counts[row.status]++;
    }
  }
  const el = document.getElementById("summary-pills");
  el.innerHTML = Object.entries(counts)
    .filter(([, n]) => n > 0)
    .map(([status, n]) => `<span class="pill pill-${status}">${STATUS_LABEL[status]}: ${n}</span>`)
    .join("");
}

function renderDashboard(dashboard) {
  renderSummary(dashboard);
  const container = document.getElementById("dashboard");
  container.innerHTML = "";

  const categoryOrder = ["Smallcaps", "Hoog Dividend", "Value", "Vastgoed", "Infrastructuur", "Credits"];
  const categories = Object.keys(dashboard).sort(
    (a, b) => categoryOrder.indexOf(a) - categoryOrder.indexOf(b)
  );

  for (const category of categories) {
    const funds = dashboard[category];
    const section = document.createElement("section");
    section.className = "category-section";

    let flagged = 0;
    let total = 0;
    for (const rows of Object.values(funds)) {
      for (const row of rows) {
        total++;
        if (row.status === "warning" || row.status === "error") flagged++;
      }
    }

    const header = document.createElement("div");
    header.className = "category-header";
    header.innerHTML = `<h2>${category}</h2><span class="category-counts">${total} shareclasses${
      flagged ? ` &middot; ${flagged} flagged` : ""
    }</span>`;
    section.appendChild(header);

    for (const [fundName, rows] of Object.entries(funds)) {
      const card = document.createElement("div");
      card.className = "fund-card";
      card.innerHTML = `<div class="fund-card-header">${fundName}</div>`;

      for (const row of rows) {
        const rowEl = document.createElement("div");
        rowEl.className = "shareclass-row";
        rowEl.dataset.isin = row.isin;
        rowEl.innerHTML = `
          <span class="status-dot ${row.status}"></span>
          <span class="klasse-name">${row.klasse_name}</span>
          <span class="isin-code">${row.isin}</span>
          <span class="report-period">${row.report_period ? "Period: " + row.report_period : "No data yet"} &middot; ${relativeTime(row.fetched_at)}</span>
          ${row.finding_count > 0 ? `<span class="finding-badge ${row.status}">${row.finding_count} finding${row.finding_count > 1 ? "s" : ""}</span>` : ""}
        `;
        rowEl.addEventListener("click", () => openDetail(row.isin));
        card.appendChild(rowEl);
      }
      section.appendChild(card);
    }
    container.appendChild(section);
  }

  if (categories.length === 0) {
    container.innerHTML = '<p class="empty-state">No shareclasses in registry.</p>';
  }
}

async function refreshDashboard() {
  const res = await fetch("/api/dashboard");
  const dashboard = await res.json();
  renderDashboard(dashboard);
}

async function openDetail(isin) {
  const res = await fetch(`/api/shareclass/${isin}`);
  const data = await res.json();
  const overlay = document.getElementById("detail-overlay");
  const content = document.getElementById("detail-content");

  const latest = data.history[0];
  const status = latest ? latest.status : "not_run";

  let findingsHtml = "";
  if (latest && latest.findings.length > 0) {
    findingsHtml = latest.findings
      .map((f) => `<div class="finding-item ${f.severity}"><strong>${f.code}</strong> &mdash; ${f.message}</div>`)
      .join("");
  } else if (latest) {
    findingsHtml = '<p class="muted">No issues found in the latest run.</p>';
  } else {
    findingsHtml = '<p class="muted">No runs yet for this shareclass.</p>';
  }

  const historyHtml = data.history
    .map(
      (h) => `
      <div class="history-row">
        <span>${h.report_period || "—"} &middot; ${new Date(h.fetched_at).toLocaleString()}</span>
        <span>
          <span class="status-dot ${h.status}" style="display:inline-block;vertical-align:middle;margin-right:6px;"></span>
          ${h.findings.length} finding${h.findings.length === 1 ? "" : "s"}
          &nbsp;<a class="pdf-link" href="/api/pdf/${h.id}" target="_blank">PDF</a>
        </span>
      </div>`
    )
    .join("");

  content.innerHTML = `
    <p class="detail-title">${data.meta.fund_name} &mdash; ${data.meta.klasse_name}</p>
    <p class="detail-sub">${data.meta.isin} &middot; ${data.meta.category} &middot; template: ${data.meta.template}</p>
    <p class="detail-sub"><a class="pdf-link" href="${data.live_factsheet_url}" target="_blank" rel="noopener">Open designated latest factsheet &#8599;</a></p>
    <div class="detail-status-banner ${status}">${STATUS_LABEL[status] || status}</div>
    <div class="section-title">Findings (latest run)</div>
    ${findingsHtml}
    <div class="section-title">Expected components (${data.expected_components.length})</div>
    <p class="muted" style="font-size:13px;">${data.expected_components.join(", ")}</p>
    <div class="section-title">History</div>
    ${historyHtml || '<p class="muted">No history yet.</p>'}
  `;
  overlay.hidden = false;
}

document.getElementById("detail-close").addEventListener("click", () => {
  document.getElementById("detail-overlay").hidden = true;
});
document.getElementById("detail-overlay").addEventListener("click", (e) => {
  if (e.target.id === "detail-overlay") e.target.hidden = true;
});

document.getElementById("fetch-all-btn").addEventListener("click", async () => {
  const progress = document.getElementById("fetch-progress");
  const progressText = document.getElementById("fetch-progress-text");
  progress.hidden = false;
  progressText.textContent = "Fetching latest factsheets for all shareclasses… this can take a minute.";
  try {
    const res = await fetch("/api/fetch-all", { method: "POST" });
    const data = await res.json();
    progressText.textContent = `Done: ${data.summary.ok} ok, ${data.summary.warning} warning, ${data.summary.error} error, ${data.summary.info} info.`;
    await refreshDashboard();
    setTimeout(() => (progress.hidden = true), 4000);
  } catch (e) {
    progressText.textContent = `Fetch failed: ${e}`;
  }
});

document.getElementById("upload-btn").addEventListener("click", () => {
  document.getElementById("upload-overlay").hidden = false;
});
document.getElementById("upload-close").addEventListener("click", () => {
  document.getElementById("upload-overlay").hidden = true;
});
document.getElementById("upload-overlay").addEventListener("click", (e) => {
  if (e.target.id === "upload-overlay") e.target.hidden = true;
});

document.getElementById("upload-submit").addEventListener("click", async () => {
  const isinInput = document.getElementById("upload-isin").value.trim();
  const fileInput = document.getElementById("upload-file");
  const resultEl = document.getElementById("upload-result");

  const match = registryFlat.find(
    (r) => r.isin.toLowerCase() === isinInput.toLowerCase() || isinInput.toUpperCase().includes(r.isin)
  );
  const isin = match ? match.isin : isinInput.toUpperCase();

  if (!fileInput.files.length) {
    resultEl.innerHTML = '<p class="finding-item error">Please choose a PDF file.</p>';
    return;
  }
  const formData = new FormData();
  formData.append("isin", isin);
  formData.append("file", fileInput.files[0]);

  resultEl.innerHTML = '<p class="muted">Analyzing&hellip;</p>';
  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    resultEl.innerHTML = `<div class="finding-item ${data.status}">Analyzed as <strong>${data.status}</strong> &mdash; ${data.findings.length} finding(s).</div>`;
    await refreshDashboard();
  } catch (e) {
    resultEl.innerHTML = `<p class="finding-item error">${e.message}</p>`;
  }
});

(async function init() {
  await loadRegistry();
  await refreshDashboard();
})();
