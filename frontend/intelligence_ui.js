/**
 * Clarification Intelligence, Reasoning Transparency, Semantic Memory & Governance UI
 */
(function () {
  "use strict";

  function esc(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function authHeaders(extra = {}) {
    if (typeof window.getAuthHeaders === "function") {
      return window.getAuthHeaders(extra);
    }
    const token = localStorage.getItem("clarify_auth_token");
    const h = { ...extra };
    if (token) h["Authorization"] = `Bearer ${token}`;
    return h;
  }

  function notify(type, msg) {
    if (typeof window.showNotification === "function") {
      window.showNotification(type, msg);
    }
  }

  // ---------------------------------------------------------------------------
  // 1. Assistant Card Intelligence Blocks (Thinking, Confidence, Assumptions, Provenance, Warnings)
  // ---------------------------------------------------------------------------
  function buildHeaderMetaHtml(session, uid) {
    const score = session.confidence_score;
    const level = session.confidence_level || (score >= 85 ? "High" : score >= 65 ? "Medium" : "Low");
    const reasons = Array.isArray(session.confidence_reasons) ? session.confidence_reasons : [];
    const costInfo = session.cost_info || null;

    let parts = [];
    if (score !== undefined && score !== null) {
      const cls = level === "High" ? "conf-high" : level === "Medium" ? "conf-med" : "conf-low";
      parts.push(`
        <div class="intel-conf-wrap">
          <button type="button" class="intel-conf-pill ${cls}" id="btn-conf-${uid}" title="Click to inspect confidence breakdown">
            <span>${esc(level)} Confidence</span>
            <b>${esc(score)}%</b>
          </button>
          <div class="intel-conf-popover" id="conf-pop-${uid}" style="display:none;">
            <div class="conf-pop-title">Why ${esc(score)}% Confidence?</div>
            ${reasons.length ? reasons.map(r => `<div class="conf-reason-row">${esc(r)}</div>`).join("") : '<div class="conf-reason-row">+ Standard validated execution</div>'}
          </div>
        </div>
      `);
    }
    if (costInfo && costInfo.cost_level) {
      const cCls = costInfo.cost_level === "High" ? "cost-high" : costInfo.cost_level === "Medium" ? "cost-med" : "cost-low";
      parts.push(`<span class="intel-cost-pill ${cCls}" title="${esc(costInfo.plan_summary || '')}">Scan: ${esc(costInfo.cost_level)}</span>`);
    }
    return parts.join("");
  }

  function buildThinkingAccordionHtml(session, uid) {
    const steps = Array.isArray(session.thinking_steps) ? session.thinking_steps : [];
    if (!steps.length) return "";

    const phaseIcons = {
      Think: "🧠",
      Analyze: "🔍",
      Verify: "🛡️",
      Synthesize: "✨"
    };

    const itemsHtml = steps.map(s => `
      <div class="thinking-step-item">
        <div class="thinking-step-badge">${phaseIcons[s.phase] || "•"} ${esc(s.phase)}</div>
        <div class="thinking-step-body">
          <div class="thinking-step-title">${esc(s.title)}</div>
          <div class="thinking-step-detail">${esc(s.detail)}</div>
        </div>
      </div>
    `).join("");

    return `
      <div class="thinking-accordion" id="think-acc-${uid}">
        <button type="button" class="thinking-toggle-btn" id="btn-think-${uid}" aria-expanded="false">
          <span class="think-pulse">🧠</span>
          <span class="think-summary-txt">Thought Process &amp; Verification (${steps.length} reasoning stages)</span>
          <span class="think-chevron" id="think-chev-${uid}">▸</span>
        </button>
        <div class="thinking-steps-body" id="think-body-${uid}" style="display:none;">
          ${itemsHtml}
        </div>
      </div>
    `;
  }

  function buildGovernanceAlertsHtml(session) {
    const dq = Array.isArray(session.data_quality_warnings) ? session.data_quality_warnings : [];
    const pii = session.pii_warning;
    const costWarn = session.cost_info && session.cost_info.warning ? session.cost_info.warning : null;
    if (!dq.length && !pii && !costWarn) return "";

    let html = `<div class="intel-alerts-stack">`;
    if (pii) {
      html += `<div class="intel-alert intel-alert-pii">🔒 ${esc(pii)}</div>`;
    }
    if (costWarn) {
      html += `<div class="intel-alert intel-alert-cost">⏱️ ${esc(costWarn)}</div>`;
    }
    dq.forEach(w => {
      html += `<div class="intel-alert intel-alert-dq">⚠️ ${esc(w)}</div>`;
    });
    html += `</div>`;
    return html;
  }

  function buildAskAfterBannerHtml(session, uid) {
    const aaa = session.ask_after_answer;
    if (!aaa || !Array.isArray(aaa.alternatives) || !aaa.alternatives.length) return "";
    const orig = session.original_query || session.user_query || "";
    const altBtns = aaa.alternatives.map(alt => {
      const switchQ = `${orig} [Clarified: ${alt.label} (${alt.constraint || alt.label})]`;
      const rowMeta = alt.estimated_rows !== undefined && alt.estimated_rows !== null ? ` (~${alt.estimated_rows} rows)` : "";
      return `<button type="button" class="intel-switch-pill" data-switch-query="${esc(switchQ)}">${esc(alt.label)}${esc(rowMeta)}</button>`;
    }).join("");

    return `
      <div class="ask-after-banner" id="aaa-banner-${uid}">
        <div class="aaa-top">⚡ <b>Fast Assumption Applied:</b> Used <i>${esc(aaa.assumed_label)}</i>. Switch instantly:</div>
        <div class="aaa-pills-row">${altBtns}</div>
      </div>
    `;
  }

  function buildAssumptionsHtml(session, uid) {
    const assumptions = Array.isArray(session.assumptions) ? session.assumptions : [];
    if (!assumptions.length) return "";

    const rowsHtml = assumptions.map(a => {
      const alts = Array.isArray(a.alternatives) ? a.alternatives : [];
      const altHtml = alts.map(alt =>
        `<button type="button" class="assumption-alt-btn" data-switch-query="${esc(alt.switch_query)}">Switch: ${esc(alt.label)}</button>`
      ).join("");
      return `
        <div class="assumption-chip">
          <span class="assumption-key">${esc(a.label)}:</span>
          <span class="assumption-val">${esc(a.value)}</span>
          ${altHtml}
        </div>
      `;
    }).join("");

    return `
      <div class="assumptions-ledger" id="assump-${uid}">
        <div class="assumptions-title">📌 Assumption Ledger (click to switch interpretation):</div>
        <div class="assumptions-row">${rowsHtml}</div>
      </div>
    `;
  }

  function buildProvenanceHtml(session, uid) {
    const prov = Array.isArray(session.provenance) ? session.provenance : [];
    if (!prov.length) return "";

    const rows = prov.map(p => `
      <tr>
        <td><span class="prov-badge">${esc(p.clause_type)}</span></td>
        <td>${esc(p.phrase)}</td>
        <td><code>${esc(p.sql_clause)}</code></td>
      </tr>
    `).join("");

    return `
      <div class="provenance-wrap" id="prov-wrap-${uid}">
        <button type="button" class="btn btn-secondary btn-sm prov-toggle-btn" id="btn-toggle-prov-${uid}">
          <span>🔗 Query Provenance (${prov.length})</span>
        </button>
        <div class="provenance-panel" id="prov-panel-${uid}" style="display:none;">
          <table class="prov-table">
            <thead><tr><th>Clause</th><th>Prompt Meaning</th><th>Compiled SQL</th></tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  function buildSchemaGapCardHtml(session) {
    const gap = session.schema_gap || {};
    const missing = Array.isArray(gap.missing_terms) ? gap.missing_terms : [];
    const suggestions = Array.isArray(gap.closest_suggestions) ? gap.closest_suggestions : [];
    const suggBtns = suggestions.map(s =>
      `<button type="button" class="intel-switch-pill" data-switch-query="${esc('Show summary of ' + s)}">Explore ${esc(s)}</button>`
    ).join("");

    return `
      <div class="schema-gap-card">
        <div class="schema-gap-head">🚧 Schema-Gap Guard (Zero Hallucination)</div>
        <div class="schema-gap-msg">${esc(session.natural_explanation || gap.message || "Requested entity does not match your connected tables.")}</div>
        ${missing.length ? `<div class="schema-gap-tags">Unmatched terms: ${missing.map(m => `<code>${esc(m)}</code>`).join(" ")}</div>` : ""}
        ${suggBtns ? `<div class="schema-gap-sugg"><span>Available fields you can explore:</span><div class="aaa-pills-row">${suggBtns}</div></div>` : ""}
      </div>
    `;
  }

  function wireCardEvents(card, session, uid) {
    const btnThink = card.querySelector(`#btn-think-${uid}`);
    const bodyThink = card.querySelector(`#think-body-${uid}`);
    const chevThink = card.querySelector(`#think-chev-${uid}`);
    if (btnThink && bodyThink) {
      btnThink.addEventListener("click", () => {
        const open = bodyThink.style.display === "flex";
        bodyThink.style.display = open ? "none" : "flex";
        btnThink.setAttribute("aria-expanded", String(!open));
        if (chevThink) chevThink.innerText = open ? "▸" : "▾";
      });
    }

    const btnConf = card.querySelector(`#btn-conf-${uid}`);
    const popConf = card.querySelector(`#conf-pop-${uid}`);
    if (btnConf && popConf) {
      btnConf.addEventListener("click", (e) => {
        e.stopPropagation();
        popConf.style.display = popConf.style.display === "block" ? "none" : "block";
      });
    }

    const btnProv = card.querySelector(`#btn-toggle-prov-${uid}`);
    const panelProv = card.querySelector(`#prov-panel-${uid}`);
    if (btnProv && panelProv) {
      btnProv.addEventListener("click", () => {
        const open = panelProv.style.display === "block";
        panelProv.style.display = open ? "none" : "block";
      });
    }

    card.querySelectorAll("[data-switch-query]").forEach(btn => {
      btn.addEventListener("click", () => {
        const q = btn.getAttribute("data-switch-query");
        if (q && typeof window.ClarifyRunQuery === "function") {
          window.ClarifyRunQuery(q);
        }
      });
    });
  }

  async function submitDualFeedback(sessionId, query, feedbackResult, feedbackQuestion) {
    try {
      await fetch("/api/governance/feedback", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          session_id: sessionId || null,
          query: query || null,
          feedback_result: feedbackResult,
          feedback_question: feedbackQuestion
        })
      });
    } catch (e) {
      console.warn("Dual feedback error:", e);
    }
  }

  // ---------------------------------------------------------------------------
  // 2. Governance, Memory, Glossary, Persona & Quality Metrics Modal
  // ---------------------------------------------------------------------------
  const govModal = document.getElementById("governance-modal");
  const topBtnGov = document.getElementById("top-btn-governance");
  const btnCloseGov = document.getElementById("btn-close-governance");
  const btnCloseGovFooter = document.getElementById("btn-close-gov-footer");
  const topPersonaName = document.getElementById("top-persona-name");
  const topGovBadge = document.getElementById("top-gov-badge");

  async function fetchSummary() {
    try {
      const res = await fetch("/api/governance/summary", { headers: authHeaders() });
      if (!res.ok) return null;
      const data = await res.json();
      updateTopPersonaBadge(data.persona, data.available_personas);
      renderPersonaTab(data.persona, data.available_personas || {});
      renderMemoryTab(data.personal_memories || []);
      renderGlossaryTab(data.glossary_approved || [], data.glossary_pending || []);
      renderMetricsTab(data.quality_metrics || {}, data.audit_log || []);
      return data;
    } catch (e) {
      console.warn("Governance summary failed:", e);
      return null;
    }
  }

  function updateTopPersonaBadge(persona, available) {
    const labelMap = { general: "Analyst", finance: "Finance", marketing: "Marketing", operations: "Ops", academic: "Academic" };
    if (topPersonaName) {
      topPersonaName.innerText = labelMap[persona] || persona || "Analyst";
    }
    if (topGovBadge && available && available[persona]) {
      topGovBadge.innerText = "Hub";
    }
  }

  function renderPersonaTab(activePersona, available) {
    const container = document.getElementById("gov-persona-list");
    if (!container) return;
    const icons = { general: "🧭", finance: "💹", marketing: "📣", operations: "🚚", academic: "🎓" };
    container.innerHTML = Object.entries(available).map(([key, info]) => {
      const isAct = key === activePersona;
      return `
        <button type="button" class="persona-card ${isAct ? "active" : ""}" data-persona="${esc(key)}">
          <div class="persona-card-top">
            <span class="persona-emoji">${icons[key] || "🧠"}</span>
            <span class="persona-label">${esc(info.label || key)}</span>
            ${isAct ? '<span class="persona-check">Active ✓</span>' : ''}
          </div>
          <div class="persona-desc">${esc(info.description || "")}</div>
        </button>
      `;
    }).join("");

    container.querySelectorAll(".persona-card").forEach(btn => {
      btn.addEventListener("click", async () => {
        const p = btn.getAttribute("data-persona");
        const res = await fetch("/api/governance/persona", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ persona: p })
        });
        if (res.ok) {
          notify("success", `Active role persona switched to ${p.toUpperCase()}`);
          fetchSummary();
        }
      });
    });
  }

  function renderMemoryTab(memories) {
    const cnt = document.getElementById("gov-mem-count");
    const container = document.getElementById("gov-memory-list");
    if (cnt) cnt.innerText = memories.length;
    if (!container) return;

    if (!memories.length) {
      container.innerHTML = `<div class="empty-gov-state">No Personal Semantic Memory learned yet. Answer a clarification question while signed in to teach your personal preferences!</div>`;
      return;
    }

    container.innerHTML = memories.map(m => {
      const confPct = Math.round((m.effective_confidence || m.base_confidence || 0.9) * 100);
      const decayCls = m.needs_reconfirmation ? "decay-warn" : "decay-ok";
      return `
        <div class="gov-item-card">
          <div class="gov-item-main">
            <div class="gov-item-title">
              <b>${esc(m.term_key)}</b> &rarr; <span>${esc(m.preferred_label)}</span>
              <span class="mem-conf-pill ${decayCls}">${confPct}% conf</span>
            </div>
            <div class="gov-item-sub">Constraint: <code>${esc(m.implied_constraint)}</code> &bull; ${esc(m.decay_reason || "")} &bull; Used ${m.use_count || 1}x</div>
          </div>
          <button type="button" class="btn btn-secondary btn-sm btn-del-mem" data-mem-id="${esc(m.id)}">Forget</button>
        </div>
      `;
    }).join("");

    container.querySelectorAll(".btn-del-mem").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-mem-id");
        const res = await fetch(`/api/governance/memory/${encodeURIComponent(id)}`, {
          method: "DELETE",
          headers: authHeaders()
        });
        if (res.ok) {
          notify("success", "Removed personal semantic memory.");
          fetchSummary();
        }
      });
    });
  }

  function renderGlossaryTab(approved, pending) {
    const cnt = document.getElementById("gov-gls-count");
    const container = document.getElementById("gov-glossary-list");
    const all = [...pending, ...approved];
    if (cnt) cnt.innerText = all.length;
    if (!container) return;

    if (!all.length) {
      container.innerHTML = `<div class="empty-gov-state">No business terms defined yet. Add one above so the AI uses your exact team definitions.</div>`;
      return;
    }

    container.innerHTML = all.map(g => {
      const isPend = g.status === "pending";
      return `
        <div class="gov-item-card ${isPend ? 'pending-item' : ''}">
          <div class="gov-item-main">
            <div class="gov-item-title">
              <b>${esc(g.term)}</b>
              <span class="gls-status-pill ${esc(g.status)}">${esc(g.status)}</span>
            </div>
            <div class="gov-item-sub">${esc(g.definition)}</div>
            <div class="gov-item-sub">SQL: <code>${esc(g.sql_expression)}</code></div>
          </div>
          ${isPend ? `
            <div class="gls-actions">
              <button type="button" class="btn btn-primary btn-sm btn-gls-decide" data-id="${esc(g.id)}" data-st="approved">Approve</button>
              <button type="button" class="btn btn-secondary btn-sm btn-gls-decide" data-id="${esc(g.id)}" data-st="rejected">Reject</button>
            </div>
          ` : ''}
        </div>
      `;
    }).join("");

    container.querySelectorAll(".btn-gls-decide").forEach(btn => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-id");
        const st = btn.getAttribute("data-st");
        const res = await fetch(`/api/governance/glossary/${encodeURIComponent(id)}/decision`, {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ status: st })
        });
        if (res.ok) {
          notify("success", `Glossary term ${st}.`);
          fetchSummary();
        }
      });
    });
  }

  function renderMetricsTab(m, audit) {
    const grid = document.getElementById("gov-metrics-grid");
    const tbody = document.getElementById("gov-audit-tbody");
    const acnt = document.getElementById("gov-audit-count");
    if (grid) {
      grid.innerHTML = `
        <div class="metric-item"><span class="metric-val">${esc(m.total_queries ?? 0)}</span><span class="metric-lbl">Audited Queries</span></div>
        <div class="metric-item"><span class="metric-val">${esc(m.clarification_rate_pct ?? 0)}%</span><span class="metric-lbl">Clarification Rate</span></div>
        <div class="metric-item"><span class="metric-val">${esc(m.question_usefulness_pct ?? 100)}%</span><span class="metric-lbl">Question Usefulness</span></div>
        <div class="metric-item"><span class="metric-val">${esc(m.avg_resolution_turns ?? 1)}</span><span class="metric-lbl">Avg Turns</span></div>
        <div class="metric-item"><span class="metric-val">${esc(m.silent_failure_rate_pct ?? 0)}%</span><span class="metric-lbl">Silent Failure Rate</span></div>
      `;
    }
    if (acnt) acnt.innerText = `${audit.length} recent entries`;
    if (tbody) {
      if (!audit.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="loading-state">No query events recorded yet.</td></tr>`;
      } else {
        tbody.innerHTML = audit.slice(0, 15).map(r => `
          <tr>
            <td>${esc((r.timestamp || "").slice(11, 19))}</td>
            <td title="${esc(r.query)}">${esc((r.query || "").slice(0, 42))}${(r.query || "").length > 42 ? "…" : ""}</td>
            <td>${esc(r.ambiguity_score)}</td>
            <td>${esc(r.cost_level)}</td>
            <td>${(r.pii_columns && r.pii_columns.length) ? esc(r.pii_columns.join(", ")) : "None"}</td>
            <td>${r.success ? "✓ OK" : "✗ Err"}</td>
          </tr>
        `).join("");
      }
    }
  }

  function wireGovernanceModal() {
    if (topBtnGov && govModal) {
      topBtnGov.addEventListener("click", () => {
        govModal.style.display = "flex";
        fetchSummary();
      });
    }
    const closeFn = () => { if (govModal) govModal.style.display = "none"; };
    if (btnCloseGov) btnCloseGov.addEventListener("click", closeFn);
    if (btnCloseGovFooter) btnCloseGovFooter.addEventListener("click", closeFn);

    document.querySelectorAll("#gov-seg-control .seg-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const tab = btn.getAttribute("data-gov-tab");
        document.querySelectorAll("#gov-seg-control .seg-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        ["persona", "memory", "glossary", "metrics"].forEach(p => {
          const el = document.getElementById(`gov-pane-${p}`);
          if (el) el.style.display = (p === tab) ? "block" : "none";
        });
      });
    });

    const btnAddGls = document.getElementById("btn-gls-add");
    if (btnAddGls) {
      btnAddGls.addEventListener("click", async () => {
        const term = (document.getElementById("gls-term-in")?.value || "").trim();
        const expr = (document.getElementById("gls-expr-in")?.value || "").trim();
        const def = (document.getElementById("gls-def-in")?.value || "").trim();
        const autoApp = Boolean(document.getElementById("gls-auto-approve")?.checked);
        if (!term || !expr || !def) {
          notify("error", "Please enter Term, SQL Expression, and Definition.");
          return;
        }
        const res = await fetch("/api/governance/glossary", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ term, sql_expression: expr, definition: def, auto_approve: autoApp })
        });
        if (res.ok) {
          document.getElementById("gls-term-in").value = "";
          document.getElementById("gls-expr-in").value = "";
          document.getElementById("gls-def-in").value = "";
          notify("success", `Saved glossary term '${term}'.`);
          fetchSummary();
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    wireGovernanceModal();
    fetchSummary();
  });

  window.IntelligenceUI = {
    buildHeaderMetaHtml,
    buildThinkingAccordionHtml,
    buildGovernanceAlertsHtml,
    buildAskAfterBannerHtml,
    buildAssumptionsHtml,
    buildProvenanceHtml,
    buildSchemaGapCardHtml,
    wireCardEvents,
    submitDualFeedback,
    refreshSummary: fetchSummary
  };
})();

