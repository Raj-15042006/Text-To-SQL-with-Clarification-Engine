/**
 * Power BI-Style Model View (Table Relationship Diagram) & Manual Configurator
 * Integrates seamlessly with ClarifySQL workspace tenancy, schema extractor, and SQL engine.
 */

(function () {
  const CARD_WIDTH = 236;
  const CARD_HEADER_H = 40;

  const state = {
    viewMode: "chat", // "chat" | "model"
    schema: null,
    relationships: [],
    layouts: {},
    zoom: 1.0,
    panX: 40,
    panY: 40,
    selectedRelId: null,
    editingRel: null,
    drag: null, // { type: 'node' | 'pan' | 'connect', ... }
    autoDetectedCandidates: [],
    hasFittedInitial: false,
  };

  // Helper to get global auth headers from app.js if available
  function authHeaders(extra = {}) {
    if (typeof window.getAuthHeaders === "function") {
      return window.getAuthHeaders(extra);
    }
    const token = localStorage.getItem("nl2sql_auth_token");
    const h = { ...extra };
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  }

  function esc(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function notify(type, msg) {
    if (typeof window.showNotification === "function") {
      window.showNotification(type, msg);
    }
  }

  // DOM Cache
  const els = {};
  function cacheDom() {
    els.navViewChat = document.getElementById("nav-view-chat");
    els.navViewModel = document.getElementById("nav-view-model");
    els.chatViewport = document.getElementById("chat-viewport");
    els.composerSection = document.getElementById("composer-section");
    els.modelViewScreen = document.getElementById("model-view-screen");
    els.navRelCount = document.getElementById("nav-rel-count");

    // Sidebar triggers
    els.btnOpenFromSidebar = document.getElementById("btn-open-diagram-from-sidebar");
    els.btnSidebarNewRel = document.getElementById("btn-sidebar-new-rel");

    // Model Toolbar
    els.statsPill = document.getElementById("erd-stats-pill");
    els.btnNewRel = document.getElementById("btn-model-new-rel");
    els.btnAutoDetect = document.getElementById("btn-model-autodetect");
    els.btnManageRel = document.getElementById("btn-model-manage-rel");
    els.btnZoomOut = document.getElementById("btn-erd-zoom-out");
    els.btnZoomIn = document.getElementById("btn-erd-zoom-in");
    els.zoomLabel = document.getElementById("erd-zoom-label");
    els.btnFit = document.getElementById("btn-erd-fit");
    els.btnAutoLayout = document.getElementById("btn-erd-auto-layout");
    els.btnBackChat = document.getElementById("btn-erd-back-chat");

    // Canvas
    els.viewport = document.getElementById("erd-viewport");
    els.world = document.getElementById("erd-world");
    els.svgLayer = document.getElementById("erd-svg-layer");
    els.wiresGroup = document.getElementById("erd-wires-group");
    els.previewWire = document.getElementById("erd-preview-wire");
    els.tablesLayer = document.getElementById("erd-tables-layer");
    els.emptyState = document.getElementById("erd-empty-state");
    els.btnEmptyUpload = document.getElementById("btn-erd-empty-upload");

    // Inspector Popover
    els.popover = document.getElementById("erd-rel-popover");
    els.popoverDot = document.getElementById("popover-status-dot");
    els.popoverTitle = document.getElementById("popover-rel-title");
    els.popoverMeta = document.getElementById("popover-rel-meta");
    els.btnClosePopover = document.getElementById("btn-close-rel-popover");
    els.btnPopToggleActive = document.getElementById("btn-pop-toggle-active");
    els.btnPopEdit = document.getElementById("btn-pop-edit");
    els.btnPopQuery = document.getElementById("btn-pop-query");
    els.btnPopDelete = document.getElementById("btn-pop-delete");

    // Editor Modal
    els.editorModal = document.getElementById("relationship-editor-modal");
    els.editorTitle = document.getElementById("rel-editor-title");
    els.btnCloseEditor = document.getElementById("btn-close-rel-editor");
    els.selSrcTable = document.getElementById("rel-src-table");
    els.selSrcCol = document.getElementById("rel-src-col");
    els.selTgtTable = document.getElementById("rel-tgt-table");
    els.selTgtCol = document.getElementById("rel-tgt-col");
    els.btnSwap = document.getElementById("btn-rel-swap");
    els.inspectionBanner = document.getElementById("rel-editor-inspection");
    els.selCardinality = document.getElementById("rel-cardinality");
    els.selCrossFilter = document.getElementById("rel-cross-filter");
    els.chkIsActive = document.getElementById("rel-is-active");
    els.editorError = document.getElementById("rel-editor-error");
    els.btnRelDelete = document.getElementById("btn-rel-delete");
    els.btnRelCancel = document.getElementById("btn-rel-cancel");
    els.btnRelSave = document.getElementById("btn-rel-save");

    // Manage Modal
    els.manageModal = document.getElementById("manage-relationships-modal");
    els.btnCloseManage = document.getElementById("btn-close-manage-rel");
    els.btnManageClose = document.getElementById("btn-manage-close");
    els.btnManageNew = document.getElementById("btn-manage-new");
    els.btnManageAutoDetect = document.getElementById("btn-manage-autodetect");
    els.manageTbody = document.getElementById("manage-rel-tbody");

    // Auto-Detect Modal
    els.autoDetectModal = document.getElementById("autodetect-modal");
    els.btnCloseAutoDetect = document.getElementById("btn-close-autodetect");
    els.btnAutoDetectCancel = document.getElementById("btn-autodetect-cancel");
    els.btnAutoDetectApply = document.getElementById("btn-autodetect-apply");
    els.autoDetectList = document.getElementById("autodetect-results-list");
  }

  // =========================================================================
  // View Switching (Assistant <-> Model View)
  // =========================================================================
  function switchView(mode) {
    if (!els.modelViewScreen) return;
    state.viewMode = mode === "model" ? "model" : "chat";

    if (state.viewMode === "model") {
      if (els.chatViewport) els.chatViewport.style.display = "none";
      if (els.composerSection) els.composerSection.style.display = "none";
      els.modelViewScreen.style.display = "flex";

      if (els.navViewChat) {
        els.navViewChat.classList.remove("active");
        els.navViewChat.setAttribute("aria-selected", "false");
      }
      if (els.navViewModel) {
        els.navViewModel.classList.add("active");
        els.navViewModel.setAttribute("aria-selected", "true");
      }

      refreshAll();
    } else {
      els.modelViewScreen.style.display = "none";
      if (els.chatViewport) els.chatViewport.style.display = "block";
      if (els.composerSection) els.composerSection.style.display = "flex";

      if (els.navViewModel) {
        els.navViewModel.classList.remove("active");
        els.navViewModel.setAttribute("aria-selected", "false");
      }
      if (els.navViewChat) {
        els.navViewChat.classList.add("active");
        els.navViewChat.setAttribute("aria-selected", "true");
      }
      hidePopover();
    }
  }

  async function refreshAll() {
    try {
      const [schemaRes, relRes] = await Promise.all([
        fetch("/api/schema", { headers: authHeaders() }),
        fetch("/api/schema/relationships", { headers: authHeaders() }),
      ]);
      if (schemaRes.ok) {
        state.schema = await schemaRes.json();
      }
      if (relRes.ok) {
        const data = await relRes.json();
        state.relationships = data.relationships || [];
        state.layouts = data.layouts || {};
      }
      renderDiagram();
    } catch (e) {
      console.error("Model View refresh failed:", e);
    }
  }

  // Called by app.js when schema or relationships change
  function onSchemaUpdated(newSchema) {
    state.schema = newSchema;
    if (state.viewMode === "model") {
      renderDiagram();
    }
  }

  function onRelationshipsUpdated(relData) {
    state.relationships = (relData && relData.relationships) ? relData.relationships : [];
    if (relData && relData.layouts) {
      state.layouts = relData.layouts;
    }
    if (els.navRelCount) {
      const activeCount = state.relationships.filter((r) => r.is_active !== false).length;
      els.navRelCount.innerText = String(activeCount);
    }
    if (state.viewMode === "model") {
      renderDiagram();
    }
    if (els.manageModal && els.manageModal.style.display === "flex") {
      renderManageTable();
    }
  }

  // =========================================================================
  // Smart Auto-Layout Calculation
  // =========================================================================
  function estimateCardHeight(tableMeta) {
    const colCount = Math.min(tableMeta.columns.length, 10);
    return CARD_HEADER_H + 14 + colCount * 29;
  }

  function computeAutoLayouts(forceReset = false) {
    const tables = (state.schema && state.schema.tables) ? state.schema.tables : {};
    const tableNames = Object.keys(tables);
    if (tableNames.length === 0) return {};

    const out = forceReset ? {} : { ...state.layouts };
    const missing = forceReset ? tableNames : tableNames.filter((t) => !out[t]);
    if (missing.length === 0) return out;

    // Separate connected vs disconnected tables so related schemas group cleanly
    const linkedSet = new Set();
    const outDegree = {};
    const inDegree = {};
    tableNames.forEach((t) => {
      outDegree[t] = 0;
      inDegree[t] = 0;
    });

    state.relationships.forEach((r) => {
      if (tables[r.source_table] && tables[r.target_table]) {
        linkedSet.add(r.source_table);
        linkedSet.add(r.target_table);
        outDegree[r.source_table] = (outDegree[r.source_table] || 0) + 1;
        inDegree[r.target_table] = (inDegree[r.target_table] || 0) + 1;
      }
    });

    const connected = tableNames.filter((t) => linkedSet.has(t));
    const standalone = tableNames.filter((t) => !linkedSet.has(t));

    // Tier connected tables: Pure Lookup / Parent tables (inDegree > 0 && outDegree == 0) at top,
    // Mixed intermediate tables in middle, Fact/Child tables (outDegree > 0 && inDegree == 0) below
    const tierTop = connected.filter((t) => inDegree[t] > 0 && outDegree[t] === 0);
    const tierMid = connected.filter((t) => inDegree[t] > 0 && outDegree[t] > 0);
    const tierBot = connected.filter((t) => !tierTop.includes(t) && !tierMid.includes(t));

    const rows = [tierTop, tierMid, tierBot].filter((arr) => arr.length > 0);
    // If graph is cyclic/flat and only one tier, split cleanly up to 3 per row
    const finalRows = [];
    rows.forEach((row) => {
      for (let i = 0; i < row.length; i += 4) {
        finalRows.push(row.slice(i, i + 4));
      }
    });
    for (let i = 0; i < standalone.length; i += 4) {
      finalRows.push(standalone.slice(i, i + 4));
    }

    const X_GAP = 100;
    const Y_GAP = 72;
    let curY = 50;

    finalRows.forEach((row) => {
      let curX = 60;
      let maxRowH = 140;
      row.forEach((tblName) => {
        const h = estimateCardHeight(tables[tblName]);
        if (h > maxRowH) maxRowH = h;
        if (forceReset || !out[tblName]) {
          out[tblName] = { x: curX, y: curY };
        }
        curX += CARD_WIDTH + X_GAP;
      });
      curY += maxRowH + Y_GAP;
    });

    return out;
  }

  async function persistLayouts(layoutsObj) {
    try {
      await fetch("/api/schema/diagram-layout", {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ layouts: layoutsObj }),
      });
    } catch (_) {
      // Non-fatal
    }
  }

  // =========================================================================
  // Transform & Viewport Helpers
  // =========================================================================
  function applyWorldTransform() {
    if (!els.world) return;
    els.world.style.transform = `translate(${state.panX}px, ${state.panY}px) scale(${state.zoom})`;
    if (els.zoomLabel) {
      els.zoomLabel.innerText = `${Math.round(state.zoom * 100)}%`;
    }
  }

  function setZoom(nextZoom, focalClientX = null, focalClientY = null) {
    const clamped = Math.max(0.4, Math.min(1.8, nextZoom));
    if (focalClientX !== null && focalClientY !== null && els.viewport) {
      const rect = els.viewport.getBoundingClientRect();
      const vx = focalClientX - rect.left;
      const vy = focalClientY - rect.top;
      const worldX = (vx - state.panX) / state.zoom;
      const worldY = (vy - state.panY) / state.zoom;
      state.zoom = clamped;
      state.panX = vx - worldX * state.zoom;
      state.panY = vy - worldY * state.zoom;
    } else {
      state.zoom = clamped;
    }
    applyWorldTransform();
  }

  function fitToScreen() {
    if (!els.viewport || !state.schema || !state.schema.tables) return;
    const tables = state.schema.tables;
    const names = Object.keys(tables);
    if (names.length === 0) return;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    names.forEach((name) => {
      const pos = state.layouts[name] || { x: 60, y: 60 };
      const cardEl = els.tablesLayer.querySelector(`.erd-table-card[data-table="${CSS.escape(name)}"]`);
      const w = cardEl ? cardEl.offsetWidth : CARD_WIDTH;
      const h = cardEl ? cardEl.offsetHeight : estimateCardHeight(tables[name]);
      minX = Math.min(minX, pos.x);
      minY = Math.min(minY, pos.y);
      maxX = Math.max(maxX, pos.x + w);
      maxY = Math.max(maxY, pos.y + h);
    });

    const vRect = els.viewport.getBoundingClientRect();
    if (vRect.width < 50 || vRect.height < 50) return;

    const pad = 64;
    const contentW = Math.max(100, maxX - minX);
    const contentH = Math.max(100, maxY - minY);
    const scaleX = (vRect.width - pad * 2) / contentW;
    const scaleY = (vRect.height - pad * 2 - 48) / contentH;
    const targetZoom = Math.max(0.45, Math.min(1.05, Math.min(scaleX, scaleY)));

    state.zoom = targetZoom;
    state.panX = (vRect.width - contentW * targetZoom) / 2 - minX * targetZoom;
    state.panY = (vRect.height - 40 - contentH * targetZoom) / 2 - minY * targetZoom;
    applyWorldTransform();
  }

  // =========================================================================
  // Main Diagram Renderer (Cards + SVG Relationship Wires)
  // =========================================================================
  function renderDiagram() {
    if (!els.tablesLayer || !els.wiresGroup) return;

    const tables = (state.schema && state.schema.tables) ? state.schema.tables : {};
    const tableNames = Object.keys(tables);

    // Update top stats pill
    if (els.statsPill) {
      const activeRels = state.relationships.filter((r) => r.is_active !== false).length;
      const totalRels = state.relationships.length;
      const relStr = activeRels === totalRels
        ? `${totalRels} relationship${totalRels === 1 ? "" : "s"}`
        : `${activeRels}/${totalRels} active relationships`;
      els.statsPill.innerText = `${tableNames.length} table${tableNames.length === 1 ? "" : "s"} • ${relStr}`;
    }

    if (tableNames.length === 0) {
      els.tablesLayer.innerHTML = "";
      els.wiresGroup.innerHTML = "";
      if (els.emptyState) els.emptyState.style.display = "flex";
      hidePopover();
      return;
    }

    if (els.emptyState) els.emptyState.style.display = "none";

    // Merge auto-layout positions for any unpositioned tables
    const computed = computeAutoLayouts(false);
    const hadMissing = tableNames.some((t) => !state.layouts[t]);
    state.layouts = computed;
    if (hadMissing) {
      persistLayouts(state.layouts);
    }

    // Build Table Cards
    els.tablesLayer.innerHTML = "";
    tableNames.forEach((tblName) => {
      const tblMeta = tables[tblName];
      const pos = state.layouts[tblName] || { x: 60, y: 60 };
      const card = buildTableCard(tblMeta, pos);
      els.tablesLayer.appendChild(card);
    });

    applyWorldTransform();
    renderWires();

    if (!state.hasFittedInitial && state.viewMode === "model") {
      state.hasFittedInitial = true;
      requestAnimationFrame(() => fitToScreen());
    }
  }

  function getTypeShortBadge(dataType) {
    const dt = (dataType || "TEXT").toUpperCase();
    if (dt.includes("INT") || dt.includes("SERIAL")) return "123";
    if (dt.includes("NUMERIC") || dt.includes("DECIMAL") || dt.includes("FLOAT") || dt.includes("REAL") || dt.includes("DOUBLE")) return "1.2";
    if (dt.includes("DATE") || dt.includes("TIME")) return "📅";
    if (dt.includes("BOOL")) return "✓";
    return "ABC";
  }

  function buildTableCard(tblMeta, pos) {
    const card = document.createElement("div");
    card.className = "erd-table-card";
    card.dataset.table = tblMeta.name;
    card.style.left = `${pos.x}px`;
    card.style.top = `${pos.y}px`;
    card.style.width = `${CARD_WIDTH}px`;

    // Check if table participates in any active relationship
    const hasLink = state.relationships.some(
      (r) => r.source_table === tblMeta.name || r.target_table === tblMeta.name
    );
    if (hasLink) card.classList.add("has-links");

    const colsHtml = tblMeta.columns.map((col) => {
      const pkBadge = col.is_primary_key ? `<span class="col-key-icon pk" title="Primary Key">🔑</span>` : "";
      const fkBadge = col.is_foreign_key ? `<span class="col-key-icon fk" title="Foreign Key → ${esc(col.foreign_key_target || '')}">🔗</span>` : "";
      const typeGlyph = (!col.is_primary_key && !col.is_foreign_key)
        ? `<span class="col-type-glyph">${getTypeShortBadge(col.data_type)}</span>`
        : "";

      return `
        <div class="erd-col-row" data-table="${esc(tblMeta.name)}" data-col="${esc(col.name)}">
          <span class="col-port left" title="Drag to link column"></span>
          <div class="col-row-main">
            ${pkBadge}${fkBadge}${typeGlyph}
            <span class="col-name-txt" title="${esc(col.name)} (${esc(col.data_type)})">${esc(col.name)}</span>
            <button type="button" class="col-query-btn" data-table="${esc(tblMeta.name)}" data-col="${esc(col.name)}" title="Ask Assistant about ${esc(tblMeta.name)}.${esc(col.name)}">🔍</button>
            <span class="col-dt-pill">${esc(col.data_type.split("(")[0].slice(0, 7))}</span>
          </div>
          <span class="col-port right" title="Drag to link column"></span>
        </div>
      `;
    }).join("");

    card.innerHTML = `
      <div class="erd-card-header" title="Drag to reposition table">
        <div class="erd-card-title-wrap">
          <svg class="erd-tbl-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="3" y="3" width="18" height="18" rx="2"></rect>
            <line x1="3" y1="9" x2="21" y2="9"></line>
            <line x1="9" y1="21" x2="9" y2="9"></line>
          </svg>
          <span class="erd-card-title">${esc(tblMeta.name)}</span>
        </div>
        <div class="erd-card-actions">
          <span class="erd-col-count">${tblMeta.columns.length}</span>
          <button class="btn-card-query" title="Ask AI about ${esc(tblMeta.name)}">▶</button>
        </div>
      </div>
      <div class="erd-card-cols">
        ${colsHtml}
      </div>
    `;

    // Header Drag -> Move Card
    const header = card.querySelector(".erd-card-header");
    header.addEventListener("mousedown", (e) => {
      if (e.target.closest(".btn-card-query")) return;
      e.preventDefault();
      e.stopPropagation();
      const curPos = state.layouts[tblMeta.name] || { x: pos.x, y: pos.y };
      card.classList.add("dragging");
      state.drag = {
        type: "node",
        tableName: tblMeta.name,
        cardEl: card,
        startClientX: e.clientX,
        startClientY: e.clientY,
        origX: curPos.x,
        origY: curPos.y,
      };
    });

    // Quick Query button on card header
    const qBtn = card.querySelector(".btn-card-query");
    if (qBtn) {
      qBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const queryInput = document.getElementById("query-input");
        if (queryInput) {
          queryInput.value = `Show summary and sample rows from ${tblMeta.name}`;
          switchView("chat");
          if (typeof window.handleQuerySubmit === "function") {
            window.handleQuerySubmit();
          } else {
            document.getElementById("btn-submit")?.click();
          }
        }
      });
    }

    // Scroll inside tall table -> keep wires aligned
    const colsWrap = card.querySelector(".erd-card-cols");
    if (colsWrap) {
      colsWrap.addEventListener("scroll", () => {
        renderWires();
      });
    }

    // Column Drag-to-Link Ports & Row Drag Initiation
    card.querySelectorAll(".erd-col-row").forEach((colRow) => {
      const initiateConnectDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        const fromTbl = colRow.dataset.table;
        const fromCol = colRow.dataset.col;
        const pt = getColumnPortWorldCoords(fromTbl, fromCol, "right");
        card.classList.add("link-source");
        colRow.classList.add("linking-source");

        state.drag = {
          type: "connect",
          fromTable: fromTbl,
          fromColumn: fromCol,
          startX: pt ? pt.x : pos.x + CARD_WIDTH,
          startY: pt ? pt.y : pos.y + CARD_HEADER_H + 16,
          hoveredRow: null,
        };
      };

      // Allow dragging either from edge connector dots OR grabbing column with shift/port click
      colRow.querySelectorAll(".col-port").forEach((port) => {
        port.addEventListener("mousedown", initiateConnectDrag);
      });
      // Visual Column Picker button inside Model View
      const qBtn = colRow.querySelector(".col-query-btn");
      if (qBtn) {
        qBtn.addEventListener("mousedown", (e) => { e.stopPropagation(); });
        qBtn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          const t = qBtn.dataset.table;
          const c = qBtn.dataset.col;
          switchView("chat");
          const qIn = document.getElementById("query-input");
          if (qIn) {
            qIn.value = `Show breakdown and numeric figures for ${c} from ${t}`;
            qIn.focus();
            qIn.dispatchEvent(new Event("input"));
          }
          if (typeof window.showNotification === "function") {
            window.showNotification("info", `Picked column ${t}.${c} from ER Diagram — press Return to run!`);
          }
        });
      }

      // Clicking/dragging directly on a column row while moving >4px also connects smoothly (Power BI UX!)
      colRow.addEventListener("mousedown", (e) => {
        if (e.button !== 0 || (e.target && e.target.closest(".col-query-btn"))) return;
        e.stopPropagation();
        const startX = e.clientX;
        const startY = e.clientY;
        let started = false;

        const onMoveStart = (me) => {
          if (started) return;
          if (Math.hypot(me.clientX - startX, me.clientY - startY) > 4) {
            started = true;
            cleanupPre();
            initiateConnectDrag(e);
          }
        };
        const cleanupPre = () => {
          window.removeEventListener("mousemove", onMoveStart);
          window.removeEventListener("mouseup", cleanupPre);
        };
        window.addEventListener("mousemove", onMoveStart);
        window.addEventListener("mouseup", cleanupPre);
      });
    });

    return card;
  }

  // =========================================================================
  // Precision SVG Wire Geometry & Rendering
  // =========================================================================
  function getColumnAnchorY(tableName, colName) {
    const pos = state.layouts[tableName] || { x: 0, y: 0 };
    const cardEl = els.tablesLayer.querySelector(`.erd-table-card[data-table="${CSS.escape(tableName)}"]`);
    if (!cardEl) return pos.y + CARD_HEADER_H + 14;

    const colsWrap = cardEl.querySelector(".erd-card-cols");
    const colRow = cardEl.querySelector(`.erd-col-row[data-col="${CSS.escape(colName)}"]`);
    if (!colsWrap || !colRow) {
      return pos.y + CARD_HEADER_H + 14;
    }

    const relTop = colRow.offsetTop - colsWrap.scrollTop + colRow.offsetHeight / 2;
    const minY = CARD_HEADER_H + 8;
    const maxY = cardEl.offsetHeight - 8;
    const clampedLocalY = Math.max(minY, Math.min(maxY, relTop));
    return pos.y + clampedLocalY;
  }

  function getColumnPortWorldCoords(tableName, colName, side = "right") {
    const pos = state.layouts[tableName] || { x: 0, y: 0 };
    const cardEl = els.tablesLayer.querySelector(`.erd-table-card[data-table="${CSS.escape(tableName)}"]`);
    const w = cardEl ? cardEl.offsetWidth : CARD_WIDTH;
    const y = getColumnAnchorY(tableName, colName);
    const x = side === "left" ? pos.x : pos.x + w;
    return { x, y };
  }

  function cubicBezierPoint(p0, p1, p2, p3, t) {
    const u = 1 - t;
    const tt = t * t;
    const uu = u * u;
    const uuu = uu * u;
    const ttt = tt * t;
    const x = uuu * p0.x + 3 * uu * t * p1.x + 3 * u * tt * p2.x + ttt * p3.x;
    const y = uuu * p0.y + 3 * uu * t * p1.y + 3 * u * tt * p2.y + ttt * p3.y;

    const dx = 3 * uu * (p1.x - p0.x) + 6 * u * t * (p2.x - p1.x) + 3 * tt * (p3.x - p2.x);
    const dy = 3 * uu * (p1.y - p0.y) + 6 * u * t * (p2.y - p1.y) + 3 * tt * (p3.y - p2.y);
    const angle = Math.atan2(dy, dx) * (180 / Math.PI);
    return { x, y, angle };
  }

  function getEndpointBadges(cardinality) {
    switch (cardinality) {
      case "One-to-One": return { src: "1", tgt: "1" };
      case "One-to-Many": return { src: "1", tgt: "*" };
      case "Many-to-Many": return { src: "*", tgt: "*" };
      case "Many-to-One":
      default:
        return { src: "*", tgt: "1" };
    }
  }

  function renderWires() {
    if (!els.wiresGroup || !state.schema || !state.schema.tables) return;
    els.wiresGroup.innerHTML = "";
    const tables = state.schema.tables;

    // Clear old highlights unless hovered/selected
    document.querySelectorAll(".erd-col-row.rel-highlight").forEach((el) => el.classList.remove("rel-highlight"));

    state.relationships.forEach((rel, idx) => {
      if (!tables[rel.source_table] || !tables[rel.target_table]) return;

      const srcPos = state.layouts[rel.source_table] || { x: 0, y: 0 };
      const tgtPos = state.layouts[rel.target_table] || { x: 0, y: 0 };

      const srcY = getColumnAnchorY(rel.source_table, rel.source_column);
      const tgtY = getColumnAnchorY(rel.target_table, rel.target_column);

      // Offset slightly if multiple relationships share same pair of tables
      const pairOffset = (idx % 3 - 1) * 4;

      let startSide = "right";
      let endSide = "left";
      const centerDiffX = (tgtPos.x + CARD_WIDTH / 2) - (srcPos.x + CARD_WIDTH / 2);

      if (rel.source_table === rel.target_table) {
        startSide = "right";
        endSide = "right";
      } else if (srcPos.x + CARD_WIDTH + 24 < tgtPos.x) {
        startSide = "right";
        endSide = "left";
      } else if (tgtPos.x + CARD_WIDTH + 24 < srcPos.x) {
        startSide = "left";
        endSide = "right";
      } else if (centerDiffX >= 0) {
        startSide = "right";
        endSide = "right";
      } else {
        startSide = "left";
        endSide = "left";
      }

      const x1 = startSide === "right" ? srcPos.x + CARD_WIDTH : srcPos.x;
      const y1 = srcY + pairOffset;
      const x2 = endSide === "right" ? tgtPos.x + CARD_WIDTH : tgtPos.x;
      const y2 = tgtY + pairOffset;

      const dx = Math.abs(x2 - x1);
      let c1x, c2x;
      if (startSide !== endSide) {
        const handleDist = Math.max(55, Math.min(180, dx * 0.48));
        c1x = startSide === "right" ? x1 + handleDist : x1 - handleDist;
        c2x = endSide === "left" ? x2 - handleDist : x2 + handleDist;
      } else {
        // Same-side arc (stacked vertically or self-reference)
        const arcOut = 65 + Math.min(45, Math.abs(y2 - y1) * 0.15);
        c1x = startSide === "right" ? x1 + arcOut : x1 - arcOut;
        c2x = endSide === "right" ? x2 + arcOut : x2 - arcOut;
      }

      const p0 = { x: x1, y: y1 };
      const p1 = { x: c1x, y: y1 };
      const p2 = { x: c2x, y: y2 };
      const p3 = { x: x2, y: y2 };
      const d = `M ${p0.x} ${p0.y} C ${p1.x} ${p1.y}, ${p2.x} ${p2.y}, ${p3.x} ${p3.y}`;

      const isActive = rel.is_active !== false;
      const isSelected = state.selectedRelId === rel.id;
      const badges = getEndpointBadges(rel.cardinality);

      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", `erd-wire-group ${isActive ? "active" : "inactive"} ${isSelected ? "selected" : ""} ${rel.is_manual ? "manual" : ""}`);
      g.dataset.relId = rel.id;

      // Wide invisible hit path for effortless hover & click
      const hitPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      hitPath.setAttribute("d", d);
      hitPath.setAttribute("class", "erd-wire-hit");

      // Visible wire
      const visPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
      visPath.setAttribute("d", d);
      visPath.setAttribute("class", "erd-wire-line");
      if (!isActive) {
        visPath.setAttribute("stroke-dasharray", "6,5");
      }

      // Endpoint dots
      const dot1 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot1.setAttribute("cx", x1);
      dot1.setAttribute("cy", y1);
      dot1.setAttribute("r", "3.5");
      dot1.setAttribute("class", "erd-wire-dot");

      const dot2 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      dot2.setAttribute("cx", x2);
      dot2.setAttribute("cy", y2);
      dot2.setAttribute("r", "3.5");
      dot2.setAttribute("class", "erd-wire-dot");

      // Cardinality Badges ('1' and '*') slightly outward from table edges
      const srcBadgePos = {
        x: x1 + (startSide === "right" ? 16 : -16),
        y: y1 - 11
      };
      const tgtBadgePos = {
        x: x2 + (endSide === "right" ? 16 : -16),
        y: y2 - 11
      };

      const badgeSrcBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      badgeSrcBg.setAttribute("x", srcBadgePos.x - 8);
      badgeSrcBg.setAttribute("y", srcBadgePos.y - 8);
      badgeSrcBg.setAttribute("width", "16");
      badgeSrcBg.setAttribute("height", "16");
      badgeSrcBg.setAttribute("rx", "4");
      badgeSrcBg.setAttribute("class", "erd-card-badge-bg");

      const badgeSrcTxt = document.createElementNS("http://www.w3.org/2000/svg", "text");
      badgeSrcTxt.setAttribute("x", srcBadgePos.x);
      badgeSrcTxt.setAttribute("y", srcBadgePos.y + 3.5);
      badgeSrcTxt.setAttribute("text-anchor", "middle");
      badgeSrcTxt.setAttribute("class", "erd-card-badge-txt");
      badgeSrcTxt.textContent = badges.src;

      const badgeTgtBg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      badgeTgtBg.setAttribute("x", tgtBadgePos.x - 8);
      badgeTgtBg.setAttribute("y", tgtBadgePos.y - 8);
      badgeTgtBg.setAttribute("width", "16");
      badgeTgtBg.setAttribute("height", "16");
      badgeTgtBg.setAttribute("rx", "4");
      badgeTgtBg.setAttribute("class", "erd-card-badge-bg");

      const badgeTgtTxt = document.createElementNS("http://www.w3.org/2000/svg", "text");
      badgeTgtTxt.setAttribute("x", tgtBadgePos.x);
      badgeTgtTxt.setAttribute("y", tgtBadgePos.y + 3.5);
      badgeTgtTxt.setAttribute("text-anchor", "middle");
      badgeTgtTxt.setAttribute("class", "erd-card-badge-txt");
      badgeTgtTxt.textContent = badges.tgt;

      // Midpoint Cross-Filter Direction Chevron (Power BI Style)
      const mid = cubicBezierPoint(p0, p1, p2, p3, 0.5);
      const arrowGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
      arrowGroup.setAttribute("class", "erd-crossfilter-arrow");

      const crossFilter = rel.cross_filter_direction || "Single";
      // In Many-to-One (*:1), filters flow Target (1) -> Source (*), i.e., reverse of p0->p3 curve
      // In One-to-Many (1:*), filters flow Source (1) -> Target (*), i.e., along p0->p3 curve
      const flipDir = rel.cardinality === "Many-to-One" ? 180 : 0;
      const rot = mid.angle + flipDir;

      if (crossFilter === "Both") {
        arrowGroup.setAttribute("transform", `translate(${mid.x}, ${mid.y}) rotate(${mid.angle})`);
        arrowGroup.innerHTML = `
          <circle cx="0" cy="0" r="10" class="erd-arrow-halo"></circle>
          <path d="M -6 0 L -1 -4.5 L -1 4.5 Z" class="erd-arrow-head"></path>
          <path d="M 6 0 L 1 -4.5 L 1 4.5 Z" class="erd-arrow-head"></path>
        `;
      } else {
        arrowGroup.setAttribute("transform", `translate(${mid.x}, ${mid.y}) rotate(${rot})`);
        arrowGroup.innerHTML = `
          <circle cx="0" cy="0" r="9" class="erd-arrow-halo"></circle>
          <path d="M -4 -5 L 5 0 L -4 5 L -1.5 0 Z" class="erd-arrow-head"></path>
        `;
      }

      g.appendChild(hitPath);
      g.appendChild(visPath);
      g.appendChild(dot1);
      g.appendChild(dot2);
      g.appendChild(badgeSrcBg);
      g.appendChild(badgeSrcTxt);
      g.appendChild(badgeTgtBg);
      g.appendChild(badgeTgtTxt);
      g.appendChild(arrowGroup);

      // Highlight connected columns on hover & selection
      const highlightEndpoints = (on) => {
        const sRow = els.tablesLayer.querySelector(`.erd-col-row[data-table="${CSS.escape(rel.source_table)}"][data-col="${CSS.escape(rel.source_column)}"]`);
        const tRow = els.tablesLayer.querySelector(`.erd-col-row[data-table="${CSS.escape(rel.target_table)}"][data-col="${CSS.escape(rel.target_column)}"]`);
        if (sRow) sRow.classList.toggle("rel-highlight", on);
        if (tRow) tRow.classList.toggle("rel-highlight", on);
      };

      if (isSelected) highlightEndpoints(true);

      g.addEventListener("mouseenter", () => highlightEndpoints(true));
      g.addEventListener("mouseleave", () => {
        if (state.selectedRelId !== rel.id) highlightEndpoints(false);
      });

      g.addEventListener("click", (e) => {
        e.stopPropagation();
        selectRelationship(rel);
      });

      g.addEventListener("dblclick", (e) => {
        e.stopPropagation();
        openEditModal(rel);
      });

      els.wiresGroup.appendChild(g);
    });
  }

  // =========================================================================
  // Relationship Selection Popover
  // =========================================================================
  function selectRelationship(rel) {
    state.selectedRelId = rel.id;
    renderWires();

    if (!els.popover) return;
    const isActive = rel.is_active !== false;
    els.popover.style.display = "block";
    els.popoverDot.className = `popover-status-dot ${isActive ? "active" : "inactive"}`;
    els.popoverTitle.innerText = `${rel.source_table}.${rel.source_column} → ${rel.target_table}.${rel.target_column}`;
    els.popoverMeta.innerText = `${rel.cardinality || "Many-to-One"} • ${rel.cross_filter_direction || "Single"} Cross-Filter • ${isActive ? "Active" : "Inactive"}${rel.is_manual ? " • Manual" : " • SQL FK"}`;
    els.btnPopToggleActive.innerText = isActive ? "Set Inactive" : "Activate";
  }

  function hidePopover() {
    state.selectedRelId = null;
    if (els.popover) els.popover.style.display = "none";
    renderWires();
  }

  // =========================================================================
  // Relationship Create / Edit Modal
  // =========================================================================
  function populateTableSelects() {
    const tables = (state.schema && state.schema.tables) ? Object.keys(state.schema.tables) : [];
    const optionsHtml = tables.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
    if (els.selSrcTable) els.selSrcTable.innerHTML = optionsHtml;
    if (els.selTgtTable) els.selTgtTable.innerHTML = optionsHtml;
  }

  function populateColumnSelect(selectEl, tableName, preferredCol = null) {
    if (!selectEl) return;
    const tbl = (state.schema && state.schema.tables) ? state.schema.tables[tableName] : null;
    const cols = tbl ? tbl.columns : [];
    selectEl.innerHTML = cols.map((c) => {
      const tag = c.is_primary_key ? " (PK)" : "";
      return `<option value="${esc(c.name)}">${esc(c.name)}${tag}</option>`;
    }).join("");
    if (preferredCol && cols.some((c) => c.name === preferredCol)) {
      selectEl.value = preferredCol;
    }
  }

  async function inspectCardinalityPreview() {
    if (!els.inspectionBanner) return;
    const st = els.selSrcTable.value;
    const sc = els.selSrcCol.value;
    const tt = els.selTgtTable.value;
    const tc = els.selTgtCol.value;
    if (!st || !sc || !tt || !tc || (st === tt && sc === tc)) {
      els.inspectionBanner.style.display = "none";
      return;
    }

    els.inspectionBanner.style.display = "block";
    els.inspectionBanner.innerHTML = `<span class="inspect-muted">Analyzing key uniqueness & match coverage...</span>`;

    try {
      const res = await fetch("/api/schema/relationships/detect-cardinality", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          source_table: st,
          source_column: sc,
          target_table: tt,
          target_column: tc,
        }),
      });
      if (!res.ok) {
        els.inspectionBanner.style.display = "none";
        return;
      }
      const data = await res.json();
      if (!state.editingRel && data.suggested_cardinality) {
        els.selCardinality.value = data.suggested_cardinality;
      }
      const matchBadge = data.match_rate_pct !== null && data.match_rate_pct !== undefined
        ? ` &bull; <strong>${data.match_rate_pct}%</strong> key overlap`
        : "";
      els.inspectionBanner.innerHTML = `
        <div class="inspect-line">
          <span class="inspect-badge">Detected: ${esc(data.suggested_cardinality)}</span>
          <span class="inspect-note">${esc(data.note)}${matchBadge}</span>
        </div>
      `;
    } catch (_) {
      els.inspectionBanner.style.display = "none";
    }
  }

  function openCreateModal(prefill = null) {
    if (!els.editorModal) return;
    const tables = (state.schema && state.schema.tables) ? Object.keys(state.schema.tables) : [];
    if (tables.length < 1) {
      notify("error", "Upload or connect at least one dataset before creating relationships.");
      return;
    }

    state.editingRel = null;
    els.editorTitle.innerText = "Create Relationship";
    els.btnRelDelete.style.display = "none";
    els.editorError.style.display = "none";

    populateTableSelects();
    const srcTbl = (prefill && prefill.source_table) ? prefill.source_table : tables[0];
    const tgtTbl = (prefill && prefill.target_table) ? prefill.target_table : (tables[1] || tables[0]);

    els.selSrcTable.value = srcTbl;
    populateColumnSelect(els.selSrcCol, srcTbl, prefill ? prefill.source_column : null);

    els.selTgtTable.value = tgtTbl;
    populateColumnSelect(els.selTgtCol, tgtTbl, prefill ? prefill.target_column : null);

    els.selSrcTable.disabled = false;
    els.selSrcCol.disabled = false;
    els.selTgtTable.disabled = false;
    els.selTgtCol.disabled = false;
    if (els.btnSwap) els.btnSwap.disabled = false;

    els.selCardinality.value = (prefill && prefill.cardinality) || "Many-to-One";
    els.selCrossFilter.value = (prefill && prefill.cross_filter_direction) || "Single";
    els.chkIsActive.checked = true;

    els.editorModal.style.display = "flex";
    inspectCardinalityPreview();
  }

  function openEditModal(rel) {
    if (!els.editorModal || !rel) return;
    state.editingRel = rel;
    els.editorTitle.innerText = rel.is_native ? "Configure Foreign Key Relationship" : "Edit Relationship";
    els.btnRelDelete.style.display = "inline-flex";
    els.editorError.style.display = "none";

    populateTableSelects();
    els.selSrcTable.value = rel.source_table;
    populateColumnSelect(els.selSrcCol, rel.source_table, rel.source_column);
    els.selTgtTable.value = rel.target_table;
    populateColumnSelect(els.selTgtCol, rel.target_table, rel.target_column);

    // Native SQL FKs keep fixed table/column endpoints (cardinality/cross-filter/active remain configurable)
    const lockEndpoints = Boolean(rel.is_native);
    els.selSrcTable.disabled = lockEndpoints;
    els.selSrcCol.disabled = lockEndpoints;
    els.selTgtTable.disabled = lockEndpoints;
    els.selTgtCol.disabled = lockEndpoints;
    if (els.btnSwap) els.btnSwap.disabled = lockEndpoints;

    els.selCardinality.value = rel.cardinality || "Many-to-One";
    els.selCrossFilter.value = rel.cross_filter_direction || "Single";
    els.chkIsActive.checked = rel.is_active !== false;

    els.editorModal.style.display = "flex";
    inspectCardinalityPreview();
  }

  function closeEditorModal() {
    if (els.editorModal) els.editorModal.style.display = "none";
    state.editingRel = null;
  }

  async function saveEditorModal() {
    els.editorError.style.display = "none";
    const payload = {
      source_table: els.selSrcTable.value,
      source_column: els.selSrcCol.value,
      target_table: els.selTgtTable.value,
      target_column: els.selTgtCol.value,
      cardinality: els.selCardinality.value,
      cross_filter_direction: els.selCrossFilter.value,
      is_active: els.chkIsActive.checked,
    };

    els.btnRelSave.disabled = true;
    els.btnRelSave.innerText = "Saving...";
    try {
      const url = state.editingRel
        ? `/api/schema/relationships/${encodeURIComponent(state.editingRel.id)}`
        : "/api/schema/relationships";
      const method = state.editingRel ? "PUT" : "POST";

      const res = await fetch(url, {
        method,
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        els.editorError.style.display = "block";
        els.editorError.className = "test-result error";
        els.editorError.innerText = data.detail || "Could not save relationship.";
        return;
      }

      closeEditorModal();
      hidePopover();
      notify("info", `Saved relationship: ${payload.source_table}.${payload.source_column} → ${payload.target_table}.${payload.target_column}`);
      if (typeof window.fetchSchema === "function") {
        await window.fetchSchema();
      } else {
        await refreshAll();
      }
    } catch (err) {
      els.editorError.style.display = "block";
      els.editorError.className = "test-result error";
      els.editorError.innerText = `Network error: ${err.message}`;
    } finally {
      els.btnRelSave.disabled = false;
      els.btnRelSave.innerText = "Save Relationship";
    }
  }

  async function deleteRelationshipById(relId) {
    try {
      const res = await fetch(`/api/schema/relationships/${encodeURIComponent(relId)}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        notify("error", d.detail || "Could not delete relationship.");
        return;
      }
      closeEditorModal();
      hidePopover();
      notify("info", "Relationship removed from data model.");
      if (typeof window.fetchSchema === "function") {
        await window.fetchSchema();
      } else {
        await refreshAll();
      }
    } catch (err) {
      notify("error", `Delete error: ${err.message}`);
    }
  }

  async function toggleRelationshipActive(rel) {
    try {
      const res = await fetch(`/api/schema/relationships/${encodeURIComponent(rel.id)}`, {
        method: "PUT",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ is_active: !(rel.is_active !== false) }),
      });
      if (!res.ok) return;
      if (typeof window.fetchSchema === "function") {
        await window.fetchSchema();
      } else {
        await refreshAll();
      }
      const updated = state.relationships.find((r) => r.id === rel.id);
      if (updated && state.selectedRelId === rel.id) {
        selectRelationship(updated);
      }
    } catch (_) {}
  }

  // =========================================================================
  // Manage Relationships Modal (Table View)
  // =========================================================================
  function openManageModal() {
    if (!els.manageModal) return;
    els.manageModal.style.display = "flex";
    renderManageTable();
  }

  function renderManageTable() {
    if (!els.manageTbody) return;
    if (!state.relationships || state.relationships.length === 0) {
      els.manageTbody.innerHTML = `<tr><td colspan="7" class="empty-state">No relationships configured yet. Click "+ New..." or "Auto-detect..." to link tables.</td></tr>`;
      return;
    }

    els.manageTbody.innerHTML = "";
    state.relationships.forEach((rel) => {
      const tr = document.createElement("tr");
      const isActive = rel.is_active !== false;
      tr.innerHTML = `
        <td><input type="checkbox" class="manage-active-chk" ${isActive ? "checked" : ""} title="Toggle active state"></td>
        <td class="mono-cell">${esc(rel.source_table)}.<strong>${esc(rel.source_column)}</strong></td>
        <td class="mono-cell">${esc(rel.target_table)}.<strong>${esc(rel.target_column)}</strong></td>
        <td><span class="card-chip">${esc(rel.cardinality || "Many-to-One")}</span></td>
        <td>${esc(rel.cross_filter_direction || "Single")}</td>
        <td><span class="origin-pill ${rel.is_manual ? "manual" : "native"}">${rel.is_manual ? "Manual" : "SQL FK"}</span></td>
        <td class="manage-actions-cell">
          <button class="btn-tbl-act edit">Edit</button>
          <button class="btn-tbl-act del">Delete</button>
        </td>
      `;

      tr.querySelector(".manage-active-chk").addEventListener("change", () => toggleRelationshipActive(rel));
      tr.querySelector(".edit").addEventListener("click", () => {
        els.manageModal.style.display = "none";
        openEditModal(rel);
      });
      tr.querySelector(".del").addEventListener("click", () => deleteRelationshipById(rel.id));

      els.manageTbody.appendChild(tr);
    });
  }

  // =========================================================================
  // Smart Auto-Detect Modal
  // =========================================================================
  async function openAutoDetectModal() {
    if (!els.autoDetectModal) return;
    els.autoDetectModal.style.display = "flex";
    els.autoDetectList.innerHTML = `<div class="loading-state">Scanning tables and column key signatures...</div>`;
    els.btnAutoDetectApply.style.display = "none";
    state.autoDetectedCandidates = [];

    try {
      const res = await fetch("/api/schema/relationships/auto-detect", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ apply: false }),
      });
      const data = await res.json();
      const cands = data.candidates || [];
      state.autoDetectedCandidates = cands;

      if (cands.length === 0) {
        els.autoDetectList.innerHTML = `
          <div class="empty-state" style="padding: 26px 12px;">
            No new relationship suggestions detected.<br>
            <span style="font-size:12px; color:var(--ink-secondary);">All matching keys are already linked, or you can drag any column to another table manually.</span>
          </div>
        `;
        return;
      }

      els.btnAutoDetectApply.style.display = "inline-flex";
      els.autoDetectList.innerHTML = "";
      cands.forEach((c, idx) => {
        const item = document.createElement("label");
        item.className = "autodetect-item";
        const overlapStr = (c.match_rate_pct !== null && c.match_rate_pct !== undefined)
          ? `<span class="ad-pill good">${c.match_rate_pct}% match</span>`
          : "";
        item.innerHTML = `
          <input type="checkbox" class="ad-check" data-idx="${idx}" checked>
          <div class="ad-body">
            <div class="ad-title-row">
              <span class="ad-link">${esc(c.source_table)}.${esc(c.source_column)} &rarr; ${esc(c.target_table)}.${esc(c.target_column)}</span>
              <span class="ad-pill">${esc(c.cardinality)}</span>
              ${overlapStr}
            </div>
            <div class="ad-reason">${esc(c.reason)}</div>
          </div>
        `;
        els.autoDetectList.appendChild(item);
      });
    } catch (err) {
      els.autoDetectList.innerHTML = `<div class="test-result error">${esc(err.message)}</div>`;
    }
  }

  async function applyAutoDetected() {
    const selected = [];
    els.autoDetectList.querySelectorAll(".ad-check:checked").forEach((chk) => {
      const idx = parseInt(chk.dataset.idx, 10);
      if (state.autoDetectedCandidates[idx]) {
        selected.push(state.autoDetectedCandidates[idx]);
      }
    });
    if (selected.length === 0) {
      els.autoDetectModal.style.display = "none";
      return;
    }

    els.btnAutoDetectApply.disabled = true;
    els.btnAutoDetectApply.innerText = "Applying...";
    try {
      const res = await fetch("/api/schema/relationships/auto-detect", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ apply: true, candidates: selected }),
      });
      if (res.ok) {
        const data = await res.json();
        els.autoDetectModal.style.display = "none";
        notify("info", `Applied ${data.applied_count || selected.length} detected relationship(s).`);
        if (typeof window.fetchSchema === "function") {
          await window.fetchSchema();
        } else {
          await refreshAll();
        }
      }
    } finally {
      els.btnAutoDetectApply.disabled = false;
      els.btnAutoDetectApply.innerText = "Apply Selected Relationships";
    }
  }

  // =========================================================================
  // Canvas Pointer / Drag / Zoom / Connect Interaction
  // =========================================================================
  function clientToWorld(clientX, clientY) {
    const rect = els.viewport.getBoundingClientRect();
    return {
      x: (clientX - rect.left - state.panX) / state.zoom,
      y: (clientY - rect.top - state.panY) / state.zoom,
    };
  }

  function setupEvents() {
    // View Switching
    if (els.navViewChat) els.navViewChat.addEventListener("click", () => switchView("chat"));
    if (els.navViewModel) els.navViewModel.addEventListener("click", () => switchView("model"));
    if (els.btnBackChat) els.btnBackChat.addEventListener("click", () => switchView("chat"));
    if (els.btnOpenFromSidebar) {
      els.btnOpenFromSidebar.addEventListener("click", () => {
        switchView("model");
        if (window.innerWidth <= 768 && typeof window.toggleSidebar === "function") {
          window.toggleSidebar(false);
        }
      });
    }
    if (els.btnSidebarNewRel) {
      els.btnSidebarNewRel.addEventListener("click", () => openCreateModal());
    }

    // Toolbar Actions
    if (els.btnNewRel) els.btnNewRel.addEventListener("click", () => openCreateModal());
    if (els.btnAutoDetect) els.btnAutoDetect.addEventListener("click", openAutoDetectModal);
    if (els.btnManageRel) els.btnManageRel.addEventListener("click", openManageModal);

    if (els.btnZoomIn) els.btnZoomIn.addEventListener("click", () => setZoom(state.zoom + 0.15));
    if (els.btnZoomOut) els.btnZoomOut.addEventListener("click", () => setZoom(state.zoom - 0.15));
    if (els.btnFit) els.btnFit.addEventListener("click", fitToScreen);
    if (els.btnAutoLayout) {
      els.btnAutoLayout.addEventListener("click", async () => {
        state.layouts = computeAutoLayouts(true);
        renderDiagram();
        fitToScreen();
        await persistLayouts(state.layouts);
        notify("info", "Tables auto-arranged cleanly.");
      });
    }
    if (els.btnEmptyUpload) {
      els.btnEmptyUpload.addEventListener("click", () => {
        document.getElementById("btn-open-upload")?.click();
      });
    }

    // Canvas Panning & Wheel Zoom
    if (els.viewport) {
      els.viewport.addEventListener("mousedown", (e) => {
        if (e.target.closest(".erd-table-card") || e.target.closest(".erd-rel-popover") || e.target.closest(".erd-wire-group")) {
          return;
        }
        hidePopover();
        state.drag = {
          type: "pan",
          startClientX: e.clientX,
          startClientY: e.clientY,
          origPanX: state.panX,
          origPanY: state.panY,
        };
        els.viewport.classList.add("panning");
      });

      els.viewport.addEventListener("wheel", (e) => {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 0.1 : -0.1;
        setZoom(state.zoom + factor, e.clientX, e.clientY);
      }, { passive: false });
    }

    // Global Mouse Move / Mouse Up for Node Drag, Pan, and Column Wire Drag
    window.addEventListener("mousemove", (e) => {
      if (!state.drag) return;

      if (state.drag.type === "node") {
        const dx = (e.clientX - state.drag.startClientX) / state.zoom;
        const dy = (e.clientY - state.drag.startClientY) / state.zoom;
        const nx = Math.round(state.drag.origX + dx);
        const ny = Math.round(state.drag.origY + dy);
        state.layouts[state.drag.tableName] = { x: nx, y: ny };
        state.drag.cardEl.style.left = `${nx}px`;
        state.drag.cardEl.style.top = `${ny}px`;
        renderWires();
      } else if (state.drag.type === "pan") {
        state.panX = state.drag.origPanX + (e.clientX - state.drag.startClientX);
        state.panY = state.drag.origPanY + (e.clientY - state.drag.startClientY);
        applyWorldTransform();
      } else if (state.drag.type === "connect") {
        const wPt = clientToWorld(e.clientX, e.clientY);
        // Check drop target column under cursor
        if (state.drag.hoveredRow) {
          state.drag.hoveredRow.classList.remove("drop-target");
          state.drag.hoveredRow = null;
        }
        const under = document.elementFromPoint(e.clientX, e.clientY);
        const targetRow = under ? under.closest(".erd-col-row") : null;
        let tx = wPt.x;
        let ty = wPt.y;
        let endSide = wPt.x >= state.drag.startX ? "left" : "right";

        if (targetRow && !(targetRow.dataset.table === state.drag.fromTable && targetRow.dataset.col === state.drag.fromColumn)) {
          targetRow.classList.add("drop-target");
          state.drag.hoveredRow = targetRow;
          const anchor = getColumnPortWorldCoords(targetRow.dataset.table, targetRow.dataset.col, endSide);
          if (anchor) {
            tx = anchor.x;
            ty = anchor.y;
          }
        }

        const startPt = getColumnPortWorldCoords(
          state.drag.fromTable,
          state.drag.fromColumn,
          tx >= state.drag.startX - CARD_WIDTH / 2 ? "right" : "left"
        );
        const sx = startPt.x;
        const sy = startPt.y;
        const dist = Math.max(40, Math.abs(tx - sx) * 0.45);
        const c1x = sx + (tx >= sx ? dist : -dist);
        const c2x = tx + (tx >= sx ? -dist : dist);

        if (els.previewWire) {
          els.previewWire.style.display = "block";
          els.previewWire.setAttribute("d", `M ${sx} ${sy} C ${c1x} ${sy}, ${c2x} ${ty}, ${tx} ${ty}`);
        }
      }
    });

    window.addEventListener("mouseup", () => {
      if (!state.drag) return;
      const d = state.drag;
      state.drag = null;

      if (d.type === "node") {
        d.cardEl.classList.remove("dragging");
        persistLayouts({ [d.tableName]: state.layouts[d.tableName] });
      } else if (d.type === "pan") {
        if (els.viewport) els.viewport.classList.remove("panning");
      } else if (d.type === "connect") {
        if (els.previewWire) els.previewWire.style.display = "none";
        document.querySelectorAll(".erd-table-card.link-source").forEach((c) => c.classList.remove("link-source"));
        document.querySelectorAll(".erd-col-row.linking-source, .erd-col-row.drop-target").forEach((r) => {
          r.classList.remove("linking-source", "drop-target");
        });

        if (d.hoveredRow) {
          const toTbl = d.hoveredRow.dataset.table;
          const toCol = d.hoveredRow.dataset.col;
          openCreateModal({
            source_table: d.fromTable,
            source_column: d.fromColumn,
            target_table: toTbl,
            target_column: toCol,
          });
        }
      }
    });

    // Popover Actions
    if (els.btnClosePopover) els.btnClosePopover.addEventListener("click", hidePopover);
    if (els.btnPopToggleActive) {
      els.btnPopToggleActive.addEventListener("click", () => {
        const rel = state.relationships.find((r) => r.id === state.selectedRelId);
        if (rel) toggleRelationshipActive(rel);
      });
    }
    if (els.btnPopEdit) {
      els.btnPopEdit.addEventListener("click", () => {
        const rel = state.relationships.find((r) => r.id === state.selectedRelId);
        if (rel) openEditModal(rel);
      });
    }
    if (els.btnPopDelete) {
      els.btnPopDelete.addEventListener("click", () => {
        if (state.selectedRelId) deleteRelationshipById(state.selectedRelId);
      });
    }
    if (els.btnPopQuery) {
      els.btnPopQuery.addEventListener("click", () => {
        const rel = state.relationships.find((r) => r.id === state.selectedRelId);
        if (!rel) return;
        const qi = document.getElementById("query-input");
        if (qi) {
          qi.value = `Show ${rel.source_table} linked to ${rel.target_table} with details`;
          switchView("chat");
          document.getElementById("btn-submit")?.click();
        }
      });
    }

    // Editor Modal Listeners
    if (els.btnCloseEditor) els.btnCloseEditor.addEventListener("click", closeEditorModal);
    if (els.btnRelCancel) els.btnRelCancel.addEventListener("click", closeEditorModal);
    if (els.editorModal) {
      els.editorModal.addEventListener("click", (e) => {
        if (e.target === els.editorModal) closeEditorModal();
      });
    }
    if (els.selSrcTable) {
      els.selSrcTable.addEventListener("change", () => {
        populateColumnSelect(els.selSrcCol, els.selSrcTable.value);
        inspectCardinalityPreview();
      });
    }
    if (els.selTgtTable) {
      els.selTgtTable.addEventListener("change", () => {
        populateColumnSelect(els.selTgtCol, els.selTgtTable.value);
        inspectCardinalityPreview();
      });
    }
    if (els.selSrcCol) els.selSrcCol.addEventListener("change", inspectCardinalityPreview);
    if (els.selTgtCol) els.selTgtCol.addEventListener("change", inspectCardinalityPreview);

    if (els.btnSwap) {
      els.btnSwap.addEventListener("click", () => {
        const st = els.selSrcTable.value;
        const sc = els.selSrcCol.value;
        const tt = els.selTgtTable.value;
        const tc = els.selTgtCol.value;
        els.selSrcTable.value = tt;
        populateColumnSelect(els.selSrcCol, tt, tc);
        els.selTgtTable.value = st;
        populateColumnSelect(els.selTgtCol, st, sc);
        inspectCardinalityPreview();
      });
    }

    if (els.btnRelSave) els.btnRelSave.addEventListener("click", saveEditorModal);
    if (els.btnRelDelete) {
      els.btnRelDelete.addEventListener("click", () => {
        if (state.editingRel) deleteRelationshipById(state.editingRel.id);
      });
    }

    // Manage Relationships Modal Listeners
    if (els.btnCloseManage) els.btnCloseManage.addEventListener("click", () => els.manageModal.style.display = "none");
    if (els.btnManageClose) els.btnManageClose.addEventListener("click", () => els.manageModal.style.display = "none");
    if (els.manageModal) {
      els.manageModal.addEventListener("click", (e) => {
        if (e.target === els.manageModal) els.manageModal.style.display = "none";
      });
    }
    if (els.btnManageNew) {
      els.btnManageNew.addEventListener("click", () => {
        els.manageModal.style.display = "none";
        openCreateModal();
      });
    }
    if (els.btnManageAutoDetect) {
      els.btnManageAutoDetect.addEventListener("click", () => {
        els.manageModal.style.display = "none";
        openAutoDetectModal();
      });
    }

    // Auto-Detect Modal Listeners
    if (els.btnCloseAutoDetect) els.btnCloseAutoDetect.addEventListener("click", () => els.autoDetectModal.style.display = "none");
    if (els.btnAutoDetectCancel) els.btnAutoDetectCancel.addEventListener("click", () => els.autoDetectModal.style.display = "none");
    if (els.autoDetectModal) {
      els.autoDetectModal.addEventListener("click", (e) => {
        if (e.target === els.autoDetectModal) els.autoDetectModal.style.display = "none";
      });
    }
    if (els.btnAutoDetectApply) els.btnAutoDetectApply.addEventListener("click", applyAutoDetected);
  }

  document.addEventListener("DOMContentLoaded", () => {
    cacheDom();
    setupEvents();
  });

  // Expose API to app.js
  window.erdDiagram = {
    switchView,
    refresh: refreshAll,
    onSchemaUpdated,
    onRelationshipsUpdated,
    openCreateModal,
    openEditModal,
    openManageModal,
    openAutoDetectModal,
  };
})();

