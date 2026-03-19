const csvFileInput = document.getElementById("csvFile");
const filterInput = document.getElementById("filter");
const treeEl = document.getElementById("tree");
const detailEl = document.getElementById("detail");
const statusEl = document.getElementById("status");
const collapseAllBtn = document.getElementById("collapseAll");

let dataIndex = null;
let lastSelected = null;

csvFileInput.addEventListener("change", handleFileSelect);
filterInput.addEventListener("input", () => {
  if (!dataIndex) return;
  renderTree(filterInput.value.trim());
});
collapseAllBtn.addEventListener("click", () => {
  treeEl.querySelectorAll("details").forEach((node) => {
    node.open = false;
  });
});

function handleFileSelect(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  statusEl.textContent = "CSVを読み込み中...";
  const reader = new FileReader();
  reader.onload = () => {
    try {
      let text = reader.result;
      if (text && text.charCodeAt(0) === 0xfeff) {
        text = text.slice(1);
      }
      const parsed = parseCsv(text);
      dataIndex = buildIndex(parsed.rows, parsed.headerMap);
      renderTree(filterInput.value.trim());
      statusEl.textContent = `読み込み完了: rows=${parsed.rows.length}`;
    } catch (err) {
      console.error(err);
      statusEl.textContent = `読み込み失敗: ${err.message}`;
      treeEl.innerHTML = "";
      detailEl.innerHTML = "";
    }
  };
  reader.readAsText(file, "utf-8");
}

function parseCsv(text) {
  const rows = [];
  const header = [];
  let i = 0;
  let field = "";
  let row = [];
  let inQuotes = false;

  function pushField() {
    row.push(field);
    field = "";
  }

  function pushRow() {
    if (!header.length) {
      header.push(...row.map((h) => h.trim()));
    } else {
      rows.push(row);
    }
    row = [];
  }

  while (i < text.length) {
    const ch = text[i];

    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
    } else {
      if (ch === '"') {
        inQuotes = true;
      } else if (ch === ',') {
        pushField();
      } else if (ch === '\n') {
        pushField();
        pushRow();
      } else if (ch === '\r') {
        // skip
      } else {
        field += ch;
      }
    }

    i += 1;
  }

  if (field.length || row.length) {
    pushField();
    pushRow();
  }

  const headerMap = {};
  header.forEach((h, idx) => {
    headerMap[h.toLowerCase()] = idx;
  });

  if (
    headerMap.dataset == null ||
    headerMap.graph == null ||
    headerMap.subject == null ||
    headerMap.predicate == null ||
    headerMap.object == null
  ) {
    throw new Error("CSVヘッダが想定と違います。dataset, graph, subject, predicate, object が必要です。");
  }

  return { rows, headerMap };
}

function buildIndex(rows, headerMap) {
  const index = new Map();
  for (const row of rows) {
    const dataset = row[headerMap.dataset];
    const graph = row[headerMap.graph];
    const subject = row[headerMap.subject];
    const predicate = row[headerMap.predicate];
    const object = row[headerMap.object];
    const oType = headerMap.object_type != null ? row[headerMap.object_type] : "";
    const oDatatype = headerMap.object_datatype != null ? row[headerMap.object_datatype] : "";
    const oLang = headerMap.object_lang != null ? row[headerMap.object_lang] : "";

    const graphKey = `${dataset}::${graph}`;
    if (!index.has(graphKey)) {
      index.set(graphKey, { dataset, graph, subjects: new Map() });
    }
    const graphNode = index.get(graphKey);
    if (!graphNode.subjects.has(subject)) {
      graphNode.subjects.set(subject, { subject, objects: new Map() });
    }
    const subjectNode = graphNode.subjects.get(subject);
    if (!subjectNode.objects.has(object)) {
      subjectNode.objects.set(object, {
        object,
        predicates: new Map(),
        rows: []
      });
    }
    const objectNode = subjectNode.objects.get(object);
    if (!objectNode.predicates.has(predicate)) {
      objectNode.predicates.set(predicate, 0);
    }
    objectNode.predicates.set(predicate, objectNode.predicates.get(predicate) + 1);
    objectNode.rows.push({ predicate, object, oType, oDatatype, oLang, dataset, graph, subject });
  }
  return index;
}

function renderTree(filterText) {
  treeEl.innerHTML = "";
  detailEl.innerHTML = "<div class=\"detail-empty\">左のツリーから object を選択してください</div>";
  lastSelected = null;

  const rawTokens = filterText
    .toLowerCase()
    .split(/\s+/)
    .map((t) => t.trim())
    .filter(Boolean);
  const includeTokens = rawTokens.filter((t) => !t.startsWith("-"));
  const excludeTokens = rawTokens
    .filter((t) => t.startsWith("-"))
    .map((t) => t.slice(1))
    .filter(Boolean);
  const fragment = document.createDocumentFragment();

  const graphs = Array.from(dataIndex.values());
  for (const graphNode of graphs) {
    const graphLabel = `${graphNode.dataset} / ${graphNode.graph}`;
    const graphInclude = matchesAll(graphLabel, includeTokens);
    const graphExclude = matchesAny(graphLabel, excludeTokens);

    const graphDetails = document.createElement("details");
    graphDetails.className = "node graph";
    graphDetails.open = true;

    const graphSummary = document.createElement("summary");
    graphSummary.textContent = graphLabel;
    graphDetails.appendChild(graphSummary);

    let graphHasMatch = false;

    for (const subjectNode of graphNode.subjects.values()) {
      const subjectInclude = matchesAll(subjectNode.subject, includeTokens);
      const subjectExclude = matchesAny(subjectNode.subject, excludeTokens);
      const subjectDetails = document.createElement("details");
      subjectDetails.className = "node subject";
      subjectDetails.open = true;

      const subjectSummary = document.createElement("summary");
      subjectSummary.textContent = shortenTerm(subjectNode.subject);
      subjectSummary.title = subjectNode.subject;
      subjectDetails.appendChild(subjectSummary);

      let subjectHasMatch = false;

      for (const objectNode of subjectNode.objects.values()) {
        const predicatesList = Array.from(objectNode.predicates.keys());
        const predicateInclude = matchesAllList(predicatesList, includeTokens);
        const predicateExclude = matchesAnyList(predicatesList, excludeTokens);
        const objectInclude = matchesAll(objectNode.object, includeTokens);
        const objectExclude = matchesAny(objectNode.object, excludeTokens);

        const hasExcludeHit = graphExclude || subjectExclude || objectExclude || predicateExclude;
        if (hasExcludeHit) continue;

        const hasIncludeHit =
          includeTokens.length === 0 ||
          graphInclude ||
          subjectInclude ||
          objectInclude ||
          predicateInclude;

        const matches = hasIncludeHit;

        if (!matches) continue;

        subjectHasMatch = true;
        graphHasMatch = true;

        const objectItem = document.createElement("div");
        objectItem.className = "node object";
        objectItem.dataset.object = objectNode.object;
        objectItem.innerHTML = `
          <div class="object-label" title="${escapeHtml(objectNode.object)}">
            <span class="object-text">${escapeHtml(shortenTerm(objectNode.object))}</span>
            <span class="predicate-badges">${predicatesList.map((p) => `#${escapeHtml(shortenTerm(p))}`).join(" ")}</span>
          </div>
        `;
        objectItem.addEventListener("click", () => showDetail(graphNode, subjectNode, objectNode, objectItem));
        subjectDetails.appendChild(objectItem);
      }

      if (includeTokens.length === 0 || subjectHasMatch || subjectInclude || graphInclude) {
        graphDetails.appendChild(subjectDetails);
      }
    }

    if (includeTokens.length === 0 || graphHasMatch || graphInclude) {
      fragment.appendChild(graphDetails);
    }
  }

  treeEl.appendChild(fragment);
}

function matchesAll(value, tokens) {
  if (!tokens.length) return false;
  const target = String(value || "").toLowerCase();
  return tokens.every((t) => target.includes(t));
}

function matchesAny(value, tokens) {
  if (!tokens.length) return false;
  const target = String(value || "").toLowerCase();
  return tokens.some((t) => target.includes(t));
}

function matchesAllList(list, tokens) {
  if (!tokens.length) return false;
  return list.some((item) => matchesAll(item, tokens));
}

function matchesAnyList(list, tokens) {
  if (!tokens.length) return false;
  return list.some((item) => matchesAny(item, tokens));
}

function showDetail(graphNode, subjectNode, objectNode, objectItem) {
  if (lastSelected) lastSelected.classList.remove("selected");
  objectItem.classList.add("selected");
  lastSelected = objectItem;

  const predicates = Array.from(objectNode.predicates.entries())
    .map(([p, count]) => ({ predicate: p, count }))
    .sort((a, b) => a.predicate.localeCompare(b.predicate));

  const rows = objectNode.rows
    .map((r) => ({
      predicate: r.predicate,
      object: r.object,
      oType: r.oType,
      oDatatype: r.oDatatype,
      oLang: r.oLang
    }))
    .sort((a, b) => a.predicate.localeCompare(b.predicate));

  const predicateHtml = predicates
    .map((p) => `<span class="chip" title="${escapeHtml(p.predicate)}">${escapeHtml(shortenTerm(p.predicate))} (${p.count})</span>`)
    .join(" ");

  const rowsHtml = rows
    .map((r) => {
      const meta = [r.oType, r.oDatatype, r.oLang].filter(Boolean).join(" / ");
      return `
        <tr>
          <td title="${escapeHtml(r.predicate)}">${escapeHtml(shortenTerm(r.predicate))}</td>
          <td title="${escapeHtml(r.object)}">${escapeHtml(shortenTerm(r.object))}</td>
          <td>${escapeHtml(meta)}</td>
        </tr>
      `;
    })
    .join("");

  detailEl.innerHTML = `
    <div class="detail-head">
      <div class="detail-label">Graph</div>
      <div class="detail-value">
        <span class="detail-text">${escapeHtml(graphNode.dataset)} / ${escapeHtml(graphNode.graph)}</span>
        <button class="copy-btn" data-copy="${escapeHtml(graphNode.dataset)} / ${escapeHtml(graphNode.graph)}" title="コピー">Copy</button>
      </div>
      <div class="detail-label">Subject</div>
      <div class="detail-value">
        <span class="detail-text">${escapeHtml(subjectNode.subject)}</span>
        <button class="copy-btn" data-copy="${escapeHtml(subjectNode.subject)}" title="コピー">Copy</button>
      </div>
      <div class="detail-label">Object</div>
      <div class="detail-value">
        <span class="detail-text">${escapeHtml(objectNode.object)}</span>
        <button class="copy-btn" data-copy="${escapeHtml(objectNode.object)}" title="コピー">Copy</button>
      </div>
    </div>
    <div class="detail-section">
      <div class="detail-title">Predicates</div>
      <div class="chips">${predicateHtml || "(none)"}</div>
    </div>
    <div class="detail-section">
      <div class="detail-title">Triples</div>
      <table class="detail-table">
        <thead>
          <tr>
            <th>Predicate</th>
            <th>Object</th>
            <th>Object Meta</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml}
        </tbody>
      </table>
    </div>
  `;

  const copyButtons = detailEl.querySelectorAll(".copy-btn");
  copyButtons.forEach((btn) => {
    btn.addEventListener("click", async (event) => {
      event.stopPropagation();
      const value = btn.getAttribute("data-copy") || "";
      try {
        await navigator.clipboard.writeText(value);
        btn.textContent = "Copied";
        btn.classList.add("copied");
        setTimeout(() => {
          btn.textContent = "Copy";
          btn.classList.remove("copied");
        }, 1200);
      } catch (err) {
        console.error(err);
        btn.textContent = "Failed";
        setTimeout(() => {
          btn.textContent = "Copy";
        }, 1200);
      }
    });
  });
}

function shortenTerm(value) {
  if (!value) return "";
  const hashIndex = value.lastIndexOf("#");
  const slashIndex = value.lastIndexOf("/");
  const idx = Math.max(hashIndex, slashIndex);
  if (idx >= 0 && idx < value.length - 1) {
    return value.slice(idx + 1);
  }
  return value.length > 80 ? value.slice(0, 77) + "..." : value;
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
