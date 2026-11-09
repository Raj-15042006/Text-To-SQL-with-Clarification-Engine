// Apple Design Conversational Application Logic for ClarifySQL
// Universal Multi-Domain Formulas, Saved Chats & Account Cloud Storage Persistence

let activeConversationId = localStorage.getItem("clarify_active_conv_id") || null;
let currentSession = null;
let activeSchema = null;
let activeTable = null;
let currentSourceMode = "sample";
let isSubmitting = false;

// User Account & Storage State
let currentAuthToken = localStorage.getItem("nl2sql_auth_token") || null;
let currentUser = null;
let myUploadedTables = [];

function getAuthHeaders(extra = {}) {
  const headers = { ...extra };
  if (currentAuthToken) {
    headers["Authorization"] = `Bearer ${currentAuthToken}`;
  }
  return headers;
}

// DOM Elements
const queryInput = document.getElementById("query-input");
const btnSubmit = document.getElementById("btn-submit");
const btnAskText = document.getElementById("btn-ask-text");
const spinner = document.getElementById("spinner");
const runIcon = document.getElementById("run-icon");
const btnClearPrompt = document.getElementById("btn-clear-prompt");

// Chat Stream Elements
const chatViewport = document.getElementById("chat-viewport");
const chatWelcomeHero = document.getElementById("chat-welcome-hero");
const chatThread = document.getElementById("chat-thread");
const chatLoadingBubble = document.getElementById("chat-loading-bubble");
const loadingBubbleText = document.getElementById("loading-bubble-text");
const notificationBar = document.getElementById("notification-bar");
const navChatTitle = document.getElementById("nav-chat-title");

// Sidebar & Tabs
const btnNewChat = document.getElementById("btn-new-chat");
const topBtnNewChat = document.getElementById("top-btn-new-chat");
const tabChats = document.getElementById("tab-chats");
const tabTables = document.getElementById("tab-tables");
const tabRelations = document.getElementById("tab-relations");
const paneChats = document.getElementById("pane-chats");
const paneTables = document.getElementById("pane-tables");
const paneRelations = document.getElementById("pane-relations");
const sidebarChatList = document.getElementById("sidebar-chat-list");
const sidebarTableList = document.getElementById("sidebar-table-list");
const sidebarRelationList = document.getElementById("sidebar-relation-list");
const btnClearAllChats = document.getElementById("btn-clear-all-chats");
const dbNameLabel = document.getElementById("db-name-label");
const dbTypeLabel = document.getElementById("db-type-label");
const statusDot = document.getElementById("status-dot");

// Top Nav & Modals
const btnToggleSidebar = document.getElementById("btn-toggle-sidebar");
const btnCloseSidebar = document.getElementById("btn-close-sidebar");
const sidebar = document.getElementById("sidebar");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");
const topBtnSettings = document.getElementById("top-btn-settings");
const topStatusDot = document.getElementById("top-status-dot");
const topDbName = document.getElementById("top-db-name");
const btnOpenSettings = document.getElementById("btn-open-settings");
const btnCloseSettings = document.getElementById("btn-close-settings");
const settingsModal = document.getElementById("settings-modal");
const modalOptSample = document.getElementById("modal-opt-sample");
const modalOptPostgres = document.getElementById("modal-opt-postgres");
const pgConfigSection = document.getElementById("pg-config-section");
const btnTestConn = document.getElementById("btn-test-conn");
const btnSaveConn = document.getElementById("btn-save-conn");
const modalTestResult = document.getElementById("modal-test-result");

// Account & Workspace Modal Elements
const topBtnAccount = document.getElementById("top-btn-account");
const topUserName = document.getElementById("top-user-name");
const userAvatarPill = document.getElementById("user-avatar-pill");
const topUserUploadsCount = document.getElementById("top-user-uploads-count");
const btnSidebarAccount = document.getElementById("btn-sidebar-account");
const sidebarAccountName = document.getElementById("sidebar-account-name");
const sidebarAccountSub = document.getElementById("sidebar-account-sub");
const sidebarAccountAvatar = document.getElementById("sidebar-account-avatar");
const accountModal = document.getElementById("account-modal");
const btnCloseAccount = document.getElementById("btn-close-account");
const tabAccProfile = document.getElementById("tab-acc-profile");
const tabAccUploads = document.getElementById("tab-acc-uploads");
const tabAccSwitch = document.getElementById("tab-acc-switch");
const tabAccRegister = document.getElementById("tab-acc-register");
const paneAccProfile = document.getElementById("pane-acc-profile");
const paneAccUploads = document.getElementById("pane-acc-uploads");
const paneAccSwitch = document.getElementById("pane-acc-switch");
const paneAccRegister = document.getElementById("pane-acc-register");
const btnAccLogout = document.getElementById("btn-acc-logout");
const btnModalOpenUpload = document.getElementById("btn-modal-open-upload");
const btnDoLogin = document.getElementById("btn-do-login");
const btnDoRegister = document.getElementById("btn-do-register");

// Upload Modal
const btnOpenUpload = document.getElementById("btn-open-upload");
const topBtnUpload = document.getElementById("top-btn-upload");
const uploadModal = document.getElementById("upload-modal");
const btnCloseUpload = document.getElementById("btn-close-upload");
const btnCancelUpload = document.getElementById("btn-cancel-upload");
const uploadDropzone = document.getElementById("upload-dropzone");
const fileInput = document.getElementById("file-input");
const selectedFileBadge = document.getElementById("selected-file-badge");
const uploadTargetTable = document.getElementById("upload-target-table");
const uploadResultBox = document.getElementById("upload-result-box");
const btnStartUpload = document.getElementById("btn-start-upload");
const btnUploadLabel = document.getElementById("btn-upload-label");
const uploadSpinner = document.getElementById("upload-spinner");

let selectedUploadFile = null;

// AI Model & Learning Controls
const topBtnModel = document.getElementById("top-btn-model");
const topModelDot = document.getElementById("top-model-dot");
const topModelIcon = document.getElementById("top-model-icon");
const topModelName = document.getElementById("top-model-name");
const topModelAcc = document.getElementById("top-model-acc");
const modelModal = document.getElementById("model-modal");
const btnCloseModel = document.getElementById("btn-close-model");
const btnCloseModelFooter = document.getElementById("btn-close-model-footer");
const cardProviderLocal = document.getElementById("card-provider-local");
const cardProviderGemini = document.getElementById("card-provider-gemini");
const checkLocal = document.getElementById("check-local");
const checkGemini = document.getElementById("check-gemini");
const metricSamples = document.getElementById("metric-samples");
const metricAccuracy = document.getElementById("metric-accuracy");
const metricVocab = document.getElementById("metric-vocab");
const metricLatency = document.getElementById("metric-latency");
const modelMetricsStatus = document.getElementById("model-metrics-status");
const btnTriggerRetrain = document.getElementById("btn-trigger-retrain");
const btnRetrainLabel = document.getElementById("btn-retrain-label");
const learnedMemoryList = document.getElementById("learned-memory-list");
const memoryCountLabel = document.getElementById("memory-count-label");

// Flagship Auth Gateway Modal Elements
const authGatewayModal = document.getElementById("auth-gateway-modal");
const tabGwSignin = document.getElementById("tab-gw-signin");
const tabGwRegister = document.getElementById("tab-gw-register");
const paneGwSignin = document.getElementById("pane-gw-signin");
const paneGwRegister = document.getElementById("pane-gw-register");
const authGwTitle = document.getElementById("auth-gw-title");
const authGwSub = document.getElementById("auth-gw-sub");
const btnGwDoLogin = document.getElementById("btn-gw-do-login");
const btnGwDoRegister = document.getElementById("btn-gw-do-register");
const btnGwDemoRaj = document.getElementById("btn-gw-demo-raj");
const gwLoginUser = document.getElementById("gw-login-user");
const gwLoginPass = document.getElementById("gw-login-pass");
const gwLoginError = document.getElementById("gw-login-error");
const gwRegUser = document.getElementById("gw-reg-user");
const gwRegName = document.getElementById("gw-reg-name");
const gwRegEmail = document.getElementById("gw-reg-email");
const gwRegPass = document.getElementById("gw-reg-pass");
const gwRegError = document.getElementById("gw-reg-error");

let activeAIProvider = "local";

// ==========================================================================
// Initialization
// ==========================================================================
document.addEventListener("DOMContentLoaded", async () => {
  setupEventHandlers();
  await initAuth();
  fetchSchema();
  fetchRelationships();
  fetchConversations();
  fetchModelStatus();
});

function setupEventHandlers() {
  btnSubmit.addEventListener("click", handleQuerySubmit);

  // Auto-expand textarea & toggle clear button
  queryInput.addEventListener("input", () => {
    queryInput.style.height = "auto";
    queryInput.style.height = Math.min(queryInput.scrollHeight, 180) + "px";
    if (btnClearPrompt) {
      btnClearPrompt.style.display = queryInput.value.trim() ? "inline-block" : "none";
    }
  });

  // Keyboard: Enter executes, Shift+Enter makes newline
  queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleQuerySubmit();
    }
  });

  // Clear composer button
  if (btnClearPrompt) {
    btnClearPrompt.addEventListener("click", () => {
      queryInput.value = "";
      queryInput.style.height = "auto";
      btnClearPrompt.style.display = "none";
      queryInput.focus();
    });
  }

  // New Chat Handlers
  if (btnNewChat) btnNewChat.addEventListener("click", () => startNewChat());
  if (topBtnNewChat) topBtnNewChat.addEventListener("click", () => startNewChat());
  if (btnClearAllChats) btnClearAllChats.addEventListener("click", handleClearAllChats);

  // Sidebar toggle & mobile drawer
  if (btnToggleSidebar) btnToggleSidebar.addEventListener("click", () => toggleSidebar());
  if (btnCloseSidebar) btnCloseSidebar.addEventListener("click", () => toggleSidebar(false));
  if (sidebarBackdrop) sidebarBackdrop.addEventListener("click", () => toggleSidebar(false));

  // Sidebar Tab Switching
  if (tabChats) tabChats.addEventListener("click", () => setActiveTab(tabChats, paneChats));
  if (tabTables) tabTables.addEventListener("click", () => setActiveTab(tabTables, paneTables));
  if (tabRelations) tabRelations.addEventListener("click", () => {
    setActiveTab(tabRelations, paneRelations);
    fetchRelationships();
  });

  // Quick hero cards delegation
  document.querySelectorAll(".quick-hero-card").forEach(card => {
    card.addEventListener("click", () => {
      queryInput.value = card.dataset.q;
      handleQuerySubmit();
    });
  });

  // Settings Modal triggers
  if (topBtnSettings) topBtnSettings.addEventListener("click", () => settingsModal.style.display = "flex");
  if (btnOpenSettings) btnOpenSettings.addEventListener("click", () => settingsModal.style.display = "flex");
  if (btnCloseSettings) btnCloseSettings.addEventListener("click", () => settingsModal.style.display = "none");
  if (settingsModal) {
    settingsModal.addEventListener("click", (e) => {
      if (e.target === settingsModal) settingsModal.style.display = "none";
    });
  }

  if (modalOptSample) {
    modalOptSample.addEventListener("click", () => {
      modalOptSample.classList.add("active");
      modalOptPostgres.classList.remove("active");
      pgConfigSection.style.display = "none";
      currentSourceMode = "sample";
    });
  }

  if (modalOptPostgres) {
    modalOptPostgres.addEventListener("click", () => {
      modalOptPostgres.classList.add("active");
      modalOptSample.classList.remove("active");
      pgConfigSection.style.display = "block";
      currentSourceMode = "postgresql";
    });
  }

  if (btnTestConn) btnTestConn.addEventListener("click", handleTestConnection);
  if (btnSaveConn) btnSaveConn.addEventListener("click", handleApplyDbSource);

  // Upload Modal Triggers
  if (btnOpenUpload) btnOpenUpload.addEventListener("click", openUploadDialog);
  if (topBtnUpload) topBtnUpload.addEventListener("click", openUploadDialog);
  if (btnCloseUpload) btnCloseUpload.addEventListener("click", closeUploadDialog);
  if (btnCancelUpload) btnCancelUpload.addEventListener("click", closeUploadDialog);
  if (uploadModal) {
    uploadModal.addEventListener("click", (e) => {
      if (e.target === uploadModal) closeUploadDialog();
    });
  }

  // Dropzone drag & drop
  if (uploadDropzone && fileInput) {
    uploadDropzone.addEventListener("click", (e) => {
      if (e.target !== fileInput) {
        fileInput.click();
      }
    });
    fileInput.addEventListener("click", (e) => {
      e.stopPropagation();
    });
    fileInput.addEventListener("change", handleFileChosen);

    uploadDropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      uploadDropzone.classList.add("dragover");
    });
    uploadDropzone.addEventListener("dragleave", () => {
      uploadDropzone.classList.remove("dragover");
    });
    uploadDropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      uploadDropzone.classList.remove("dragover");
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        processSelectedFile(e.dataTransfer.files[0]);
      }
    });
  }

  if (btnStartUpload) btnStartUpload.addEventListener("click", handleUploadSubmit);

  // Account & Flagship Auth Gateway Modal Triggers
  const openAccountModal = () => {
    if (!currentUser) {
      openAuthGateway("signin");
      return;
    }
    if (!accountModal) return;
    accountModal.style.display = "flex";
    setAccountTab(tabAccProfile, paneAccProfile);
    loadAvailableUsersForSwitcher();
    fetchMyUploadedTables();
  };

  if (topBtnAccount) topBtnAccount.addEventListener("click", openAccountModal);
  if (btnSidebarAccount) btnSidebarAccount.addEventListener("click", openAccountModal);
  if (btnCloseAccount) btnCloseAccount.addEventListener("click", () => accountModal.style.display = "none");
  if (accountModal) {
    accountModal.addEventListener("click", (e) => {
      if (e.target === accountModal) accountModal.style.display = "none";
    });
  }

  // Flagship Auth Gateway Event Listeners
  if (tabGwSignin) tabGwSignin.addEventListener("click", () => switchAuthGatewayTab("signin"));
  if (tabGwRegister) tabGwRegister.addEventListener("click", () => switchAuthGatewayTab("register"));

  if (btnGwDemoRaj) {
    btnGwDemoRaj.addEventListener("click", async () => {
      btnGwDemoRaj.disabled = true;
      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username: "raj", password: "password123" })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          currentAuthToken = data.token;
          localStorage.setItem("nl2sql_auth_token", currentAuthToken);
          currentUser = data.user;
          closeAuthGateway();
          updateAccountUI();
          await fetchSchema();
          await fetchMyUploadedTables();
          await fetchConversations();
          startNewChat(false);
          showNotification("info", "Welcome back, Raj! All 17 previous chats and datasets are ready.");
        } else {
          showNotification("error", data.detail || "Demo sign in failed.");
        }
      } catch (err) {
        showNotification("error", `Network error: ${err.message}`);
      } finally {
        btnGwDemoRaj.disabled = false;
      }
    });
  }

  if (btnGwDoLogin) {
    btnGwDoLogin.addEventListener("click", async () => {
      const username = gwLoginUser ? gwLoginUser.value.trim() : "";
      const password = gwLoginPass ? gwLoginPass.value : "";
      if (!username || !password) {
        if (gwLoginError) {
          gwLoginError.style.display = "block";
          gwLoginError.className = "test-result error";
          gwLoginError.innerText = "Please enter both username and password.";
        }
        return;
      }
      btnGwDoLogin.disabled = true;
      btnGwDoLogin.innerText = "Signing in...";
      if (gwLoginError) gwLoginError.style.display = "none";

      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
          if (gwLoginError) {
            gwLoginError.style.display = "block";
            gwLoginError.className = "test-result error";
            gwLoginError.innerText = data.detail || data.message || "Invalid username or password.";
          }
          return;
        }

        currentAuthToken = data.token;
        localStorage.setItem("nl2sql_auth_token", currentAuthToken);
        currentUser = data.user;
        closeAuthGateway();
        updateAccountUI();
        await fetchSchema();
        await fetchMyUploadedTables();
        await fetchConversations();
        startNewChat(false);
        showNotification("info", `Signed in as ${currentUser.display_name || currentUser.username}`);
      } catch (err) {
        if (gwLoginError) {
          gwLoginError.style.display = "block";
          gwLoginError.className = "test-result error";
          gwLoginError.innerText = `Sign in error: ${err.message}`;
        }
      } finally {
        btnGwDoLogin.disabled = false;
        btnGwDoLogin.innerText = "Sign In";
      }
    });
  }

  if (gwLoginPass) {
    gwLoginPass.addEventListener("keydown", (e) => {
      if (e.key === "Enter") btnGwDoLogin.click();
    });
  }

  if (btnGwDoRegister) {
    btnGwDoRegister.addEventListener("click", async () => {
      const username = gwRegUser ? gwRegUser.value.trim() : "";
      const display_name = gwRegName ? gwRegName.value.trim() : "";
      const email = gwRegEmail ? gwRegEmail.value.trim() : "";
      const password = gwRegPass ? gwRegPass.value : "";

      if (!username || username.length < 3) {
        if (gwRegError) {
          gwRegError.style.display = "block";
          gwRegError.className = "test-result error";
          gwRegError.innerText = "Username must be at least 3 characters.";
        }
        return;
      }
      if (!password || password.length < 4) {
        if (gwRegError) {
          gwRegError.style.display = "block";
          gwRegError.className = "test-result error";
          gwRegError.innerText = "Password must be at least 4 characters.";
        }
        return;
      }

      btnGwDoRegister.disabled = true;
      btnGwDoRegister.innerText = "Creating Account...";
      if (gwRegError) gwRegError.style.display = "none";

      try {
        const res = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, display_name: display_name || username, email, password })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
          if (gwRegError) {
            gwRegError.style.display = "block";
            gwRegError.className = "test-result error";
            gwRegError.innerText = data.detail || data.message || "Registration failed.";
          }
          return;
        }

        currentAuthToken = data.token;
        localStorage.setItem("nl2sql_auth_token", currentAuthToken);
        currentUser = data.user;
        closeAuthGateway();
        updateAccountUI();
        await fetchSchema();
        await fetchMyUploadedTables();
        await fetchConversations();
        startNewChat(false);
        showNotification("info", `Account created! Welcome to your private workspace, ${currentUser.display_name}!`);
      } catch (err) {
        if (gwRegError) {
          gwRegError.style.display = "block";
          gwRegError.className = "test-result error";
          gwRegError.innerText = `Registration error: ${err.message}`;
        }
      } finally {
        btnGwDoRegister.disabled = false;
        btnGwDoRegister.innerText = "Create Account & Launch";
      }
    });
  }

  if (gwRegPass) {
    gwRegPass.addEventListener("keydown", (e) => {
      if (e.key === "Enter") btnGwDoRegister.click();
    });
  }

  if (tabAccProfile) tabAccProfile.addEventListener("click", () => setAccountTab(tabAccProfile, paneAccProfile));
  if (tabAccUploads) tabAccUploads.addEventListener("click", () => {
    setAccountTab(tabAccUploads, paneAccUploads);
    fetchMyUploadedTables();
  });
  if (tabAccSwitch) tabAccSwitch.addEventListener("click", () => {
    setAccountTab(tabAccSwitch, paneAccSwitch);
    loadAvailableUsersForSwitcher();
  });
  if (tabAccRegister) tabAccRegister.addEventListener("click", () => setAccountTab(tabAccRegister, paneAccRegister));

  if (btnAccLogout) btnAccLogout.addEventListener("click", handleLogout);
  if (btnModalOpenUpload) btnModalOpenUpload.addEventListener("click", () => {
    if (accountModal) accountModal.style.display = "none";
    openUploadDialog();
  });
  if (btnDoLogin) btnDoLogin.addEventListener("click", handleLoginSubmit);
  if (btnDoRegister) btnDoRegister.addEventListener("click", handleRegisterSubmit);

  // Model Settings & Self-Learning Handlers
  if (topBtnModel) topBtnModel.addEventListener("click", openModelModal);
  if (btnCloseModel) btnCloseModel.addEventListener("click", closeModelModal);
  if (btnCloseModelFooter) btnCloseModelFooter.addEventListener("click", closeModelModal);
  if (modelModal) {
    modelModal.addEventListener("click", (e) => {
      if (e.target === modelModal) closeModelModal();
    });
  }

  if (cardProviderLocal) {
    cardProviderLocal.addEventListener("click", () => switchProvider("local"));
  }
  if (cardProviderGemini) {
    cardProviderGemini.addEventListener("click", () => switchProvider("gemini"));
  }
  if (btnTriggerRetrain) {
    btnTriggerRetrain.addEventListener("click", triggerModelRetrain);
  }
}

function setAccountTab(activeBtn, activePane) {
  [tabAccProfile, tabAccUploads, tabAccSwitch, tabAccRegister].forEach(b => b && b.classList.remove("active"));
  [paneAccProfile, paneAccUploads, paneAccSwitch, paneAccRegister].forEach(p => p && (p.style.display = "none"));
  if (activeBtn) activeBtn.classList.add("active");
  if (activePane) activePane.style.display = "block";
}

// ==========================================================================
// AI Engine & Self-Learning System
// ==========================================================================
async function fetchModelStatus() {
  try {
    const res = await fetch("/api/model/status");
    if (!res.ok) return;
    const data = await res.json();
    activeAIProvider = (data.active_provider || "local").toLowerCase();

    // Update top bar chip
    if (activeAIProvider === "local" || activeAIProvider === "self_learning") {
      if (topModelDot) topModelDot.className = "model-mode-dot";
      if (topModelIcon) topModelIcon.innerText = "🤖";
      if (topModelName) topModelName.innerText = "Local NLP";
      const rawAcc = data.accuracy !== undefined ? data.accuracy : (data.intent_accuracy !== undefined ? data.intent_accuracy : 100);
      const acc = Math.round(rawAcc <= 1.0 ? rawAcc * 100 : rawAcc);
      if (topModelAcc) {
        topModelAcc.innerText = `${acc}%`;
        topModelAcc.className = "model-accuracy-badge";
        topModelAcc.style.display = "inline-block";
      }
    } else {
      if (topModelDot) topModelDot.className = "model-mode-dot gemini-mode";
      if (topModelIcon) topModelIcon.innerText = "✨";
      if (topModelName) topModelName.innerText = "Gemini 2.5";
      if (topModelAcc) {
        topModelAcc.innerText = "Cloud";
        topModelAcc.className = "model-accuracy-badge gemini-badge";
        topModelAcc.style.display = "inline-block";
      }
    }

    // Update modal cards
    if (cardProviderLocal && cardProviderGemini) {
      if (activeAIProvider === "local" || activeAIProvider === "self_learning") {
        cardProviderLocal.classList.add("active");
        cardProviderGemini.classList.remove("active");
        if (checkLocal) checkLocal.innerText = "✓";
        if (checkGemini) checkGemini.innerText = "";
      } else {
        cardProviderGemini.classList.add("active");
        cardProviderLocal.classList.remove("active");
        if (checkGemini) checkGemini.innerText = "✓";
        if (checkLocal) checkLocal.innerText = "";
      }
    }

    // Update modal metrics
    const rawAcc = data.accuracy !== undefined ? data.accuracy : (data.intent_accuracy !== undefined ? data.intent_accuracy : 100);
    const accPct = Math.round(rawAcc <= 1.0 ? rawAcc * 100 : rawAcc);
    if (metricSamples) metricSamples.innerText = data.sample_count || 0;
    if (metricAccuracy) metricAccuracy.innerText = `${accPct}%`;
    if (metricVocab) metricVocab.innerText = data.vocabulary_size || 0;
    if (metricLatency) metricLatency.innerText = "< 1ms";
    if (modelMetricsStatus) {
      modelMetricsStatus.innerText = data.is_trained ? "Trained & Ready" : "Initializing";
    }
  } catch (err) {
    console.warn("Failed to fetch model status:", err);
  }
}

async function openModelModal() {
  if (modelModal) modelModal.style.display = "flex";
  await fetchModelStatus();
  await fetchLearnedSamples();
}

function closeModelModal() {
  if (modelModal) modelModal.style.display = "none";
}

async function switchProvider(provider) {
  try {
    const res = await fetch("/api/model/switch-provider", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider })
    });
    const data = await res.json();
    if (data.success) {
      activeAIProvider = provider;
      await fetchModelStatus();
      showNotification("success", `Active AI Engine switched to ${provider === 'local' ? 'Local Self-Learning NLP' : 'Google Gemini 2.5'}`);
    } else {
      showNotification("error", data.detail || "Failed to switch provider");
    }
  } catch (err) {
    showNotification("error", "Error connecting to model provider API");
  }
}

async function triggerModelRetrain() {
  if (!btnTriggerRetrain) return;
  btnTriggerRetrain.disabled = true;
  if (btnRetrainLabel) btnRetrainLabel.innerText = "Training...";
  try {
    const res = await fetch("/api/model/train", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      await fetchModelStatus();
      await fetchLearnedSamples();
      showNotification("success", `Model Retrained in ${data.training_time_ms.toFixed(1)}ms (${data.sample_count} samples, ${Math.round(data.accuracy * 100)}% acc)`);
    } else {
      showNotification("error", data.detail || "Retrain failed.");
    }
  } catch (err) {
    showNotification("error", "Failed to trigger retraining.");
  } finally {
    btnTriggerRetrain.disabled = false;
    if (btnRetrainLabel) btnRetrainLabel.innerText = "Retrain Model";
  }
}

async function fetchLearnedSamples() {
  if (!learnedMemoryList) return;
  try {
    const res = await fetch("/api/model/samples?limit=30");
    if (!res.ok) return;
    const samples = await res.json();
    if (memoryCountLabel) memoryCountLabel.innerText = `${samples.length} recorded interactions`;

    if (samples.length === 0) {
      learnedMemoryList.innerHTML = `<div class="loading-state">No training memories recorded yet.</div>`;
      return;
    }

    learnedMemoryList.innerHTML = samples.map(s => `
      <div class="memory-sample-card">
        <div class="memory-sample-top">
          <span class="memory-sample-intent">${escapeHtml(s.intent || "QUERY")}</span>
          <span class="memory-sample-query" title="${escapeHtml(s.query)}">${escapeHtml(s.query)}</span>
          <span style="font-size:10px; color:${s.feedback_score > 0 ? '#248a3d' : '#d70015'}">${s.feedback_score > 0 ? '✓ Confirmed' : '✎ Corrected'}</span>
        </div>
        <div class="memory-sample-sql" title="${escapeHtml(s.sql)}">${escapeHtml(s.sql)}</div>
      </div>
    `).join("");
  } catch (err) {
    console.warn("Failed to fetch learned samples:", err);
  }
}

async function submitModelFeedback(query, sql, feedback, correctedSql = null, tablesUsed = []) {
  try {
    const res = await fetch("/api/model/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query,
        sql: sql,
        feedback: feedback,
        corrected_sql: correctedSql,
        tables_used: tablesUsed
      })
    });
    const data = await res.json();
    if (data.success) {
      await fetchModelStatus();
      return true;
    }
    return false;
  } catch (err) {
    console.error("Feedback error:", err);
    return false;
  }
}

// ==========================================================================
// Account & Authentication Management
// ==========================================================================
function openAuthGateway(tab = "signin") {
  if (!authGatewayModal) return;
  authGatewayModal.style.display = "flex";
  switchAuthGatewayTab(tab);
}

function closeAuthGateway() {
  if (!authGatewayModal) return;
  authGatewayModal.style.display = "none";
}

function switchAuthGatewayTab(tab) {
  if (tab === "signin") {
    if (tabGwSignin) tabGwSignin.classList.add("active");
    if (tabGwRegister) tabGwRegister.classList.remove("active");
    if (paneGwSignin) paneGwSignin.style.display = "flex";
    if (paneGwRegister) paneGwRegister.style.display = "none";
    if (authGwTitle) authGwTitle.innerText = "Sign In to Your Workspace";
    if (authGwSub) authGwSub.innerText = "Isolated datasets, private conversation threads, and offline intelligence.";
    if (gwLoginError) gwLoginError.style.display = "none";
    setTimeout(() => gwLoginUser && gwLoginUser.focus(), 80);
  } else {
    if (tabGwRegister) tabGwRegister.classList.add("active");
    if (tabGwSignin) tabGwSignin.classList.remove("active");
    if (paneGwRegister) paneGwRegister.style.display = "flex";
    if (paneGwSignin) paneGwSignin.style.display = "none";
    if (authGwTitle) authGwTitle.innerText = "Create Your Account";
    if (authGwSub) authGwSub.innerText = "Start fresh in an isolated workspace with 0 datasets and private activity.";
    if (gwRegError) gwRegError.style.display = "none";
    setTimeout(() => gwRegUser && gwRegUser.focus(), 80);
  }
}

async function initAuth() {
  try {
    let authenticated = false;
    if (currentAuthToken) {
      const meRes = await fetch("/api/auth/me", { headers: getAuthHeaders() });
      if (meRes.ok) {
        const meData = await meRes.json();
        if (meData.authenticated && meData.user) {
          currentUser = meData.user;
          myUploadedTables = meData.uploaded_tables || [];
          authenticated = true;
        }
      }
    }

    if (!authenticated) {
      // Do not auto-authenticate as raj; display the flagship auth gateway modal
      currentUser = null;
      currentAuthToken = null;
      localStorage.removeItem("nl2sql_auth_token");
      updateAccountUI();
      renderSidebarTables({ tables: {} });
      renderSidebarChats([]);
      openAuthGateway("signin");
      return;
    }

    updateAccountUI();
    await fetchSchema();
    await fetchMyUploadedTables();
    await fetchConversations();
  } catch (err) {
    console.error("Auth init error:", err);
  }
}

function updateAccountUI() {
  if (!currentUser) {
    if (topUserName) topUserName.innerText = "Sign In";
    if (userAvatarPill) userAvatarPill.innerText = "👤";
    if (sidebarAccountName) sidebarAccountName.innerText = "Not Signed In";
    if (sidebarAccountAvatar) sidebarAccountAvatar.innerText = "👤";
    if (sidebarAccountSub) sidebarAccountSub.innerText = "Click to sign in or create account";
    return;
  }
  const initial = (currentUser.display_name || currentUser.username || "U").charAt(0).toUpperCase();
  const name = currentUser.display_name || currentUser.username;
  const username = `@${currentUser.username}`;
  const email = currentUser.email || `${currentUser.username}@example.com`;

  if (topUserName) topUserName.innerText = name;
  if (userAvatarPill) userAvatarPill.innerText = initial;
  if (sidebarAccountName) sidebarAccountName.innerText = name;
  if (sidebarAccountAvatar) sidebarAccountAvatar.innerText = initial;

  const profileModalAvatar = document.getElementById("profile-modal-avatar");
  const profileModalDisplayName = document.getElementById("profile-modal-display-name");
  const profileModalUsername = document.getElementById("profile-modal-username");
  const profileModalEmail = document.getElementById("profile-modal-email");

  if (profileModalAvatar) profileModalAvatar.innerText = initial;
  if (profileModalDisplayName) profileModalDisplayName.innerText = name;
  if (profileModalUsername) profileModalUsername.innerText = username;
  if (profileModalEmail) profileModalEmail.innerText = email;
}

async function fetchMyUploadedTables() {
  try {
    const res = await fetch("/api/auth/my-tables", { headers: getAuthHeaders() });
    if (!res.ok) return;
    myUploadedTables = await res.json();
    const count = myUploadedTables.length;

    if (topUserUploadsCount) {
      topUserUploadsCount.innerText = `${count} upload${count === 1 ? '' : 's'}`;
    }
    if (sidebarAccountSub) {
      sidebarAccountSub.innerText = `${count} uploaded dataset${count === 1 ? '' : 's'}`;
    }
    const tabUploadsCount = document.getElementById("tab-uploads-count");
    if (tabUploadsCount) tabUploadsCount.innerText = count;

    const statTablesCount = document.getElementById("stat-tables-count");
    if (statTablesCount) statTablesCount.innerText = count;

    renderAccountUploadsList();
    if (activeSchema && activeSchema.tables) {
      renderSidebarTables(activeSchema);
    }
  } catch (err) {
    console.error("Failed to fetch my tables:", err);
  }
}

function renderAccountUploadsList() {
  const container = document.getElementById("account-uploads-list");
  if (!container) return;

  if (!myUploadedTables || myUploadedTables.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="padding: 24px 12px;">
        <p>No datasets uploaded under this account yet.</p>
        <span style="font-size:11.5px; color:var(--ink-tertiary); margin-top:4px;">Upload .csv, .xlsx, or .sql files to persist them with your account.</span>
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  myUploadedTables.forEach(t => {
    const card = document.createElement("div");
    card.className = "uploaded-dataset-card";
    const dateStr = formatRelativeTime(t.uploaded_at);
    const rowStr = t.row_count ? `${t.row_count.toLocaleString()} rows` : "Table dataset";

    card.innerHTML = `
      <div class="dataset-meta">
        <span class="dataset-name">${escapeHtml(t.table_name)}</span>
        <span class="dataset-sub">${escapeHtml(t.filename || "file")} &bull; ${rowStr} &bull; ${dateStr}</span>
      </div>
      <div class="dataset-actions" style="display:flex; align-items:center; gap:8px;">
        <button class="btn-dataset-query" data-table="${escapeHtml(t.table_name)}">Query Data &rarr;</button>
        <button class="btn-dataset-delete" data-table="${escapeHtml(t.table_name)}" title="Delete uploaded table" style="background:transparent; border:1px solid rgba(255,59,48,0.3); color:#ff3b30; border-radius:var(--radius-sm); padding:4px 8px; font-size:11.5px; cursor:pointer; transition:all 0.15s ease;">Delete</button>
      </div>
    `;

    card.querySelector(".btn-dataset-query").addEventListener("click", () => {
      if (accountModal) accountModal.style.display = "none";
      queryInput.value = `Show summary and top 5 rows of ${t.table_name}`;
      handleQuerySubmit();
    });

    const btnDelete = card.querySelector(".btn-dataset-delete");
    if (btnDelete) {
      btnDelete.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`Are you sure you want to drop table '${t.table_name}' from the database?`)) return;
        btnDelete.disabled = true;
        btnDelete.innerText = "Deleting...";
        try {
          const dRes = await fetch(`/api/upload/${encodeURIComponent(t.table_name)}`, {
            method: "DELETE",
            headers: getAuthHeaders()
          });
          const dData = await dRes.json();
          if (dRes.ok && dData.success) {
            showNotification("info", `Table '${t.table_name}' deleted successfully.`);
            await fetchMyUploadedTables();
            await fetchSchema();
          } else {
            showNotification("error", dData.detail || "Failed to delete table.");
            btnDelete.disabled = false;
            btnDelete.innerText = "Delete";
          }
        } catch (dErr) {
          showNotification("error", `Network error: ${dErr.message}`);
          btnDelete.disabled = false;
          btnDelete.innerText = "Delete";
        }
      });
    }

    container.appendChild(card);
  });
}

async function loadAvailableUsersForSwitcher() {
  const chipsContainer = document.getElementById("quick-user-chips");
  if (!chipsContainer) return;
  chipsContainer.innerHTML = "<span style='font-size:12px; color:var(--ink-tertiary);'>Loading accounts...</span>";

  try {
    const res = await fetch("/api/auth/users");
    if (!res.ok) return;
    const users = await res.json();
    chipsContainer.innerHTML = "";

    users.forEach(u => {
      const chip = document.createElement("button");
      chip.className = "user-switch-chip";
      if (currentUser && currentUser.id === u.id) chip.classList.add("active");
      const init = (u.display_name || u.username).charAt(0).toUpperCase();

      chip.innerHTML = `
        <span class="chip-avatar">${init}</span>
        <span>${escapeHtml(u.display_name || u.username)}</span>
      `;

      chip.addEventListener("click", async () => {
        // Fast switch for pre-existing users
        const loginInp = document.getElementById("login-username");
        if (loginInp) loginInp.value = u.username;
        const passInp = document.getElementById("login-password");
        if (passInp) passInp.value = "password123";
        handleLoginSubmit();
      });

      chipsContainer.appendChild(chip);
    });
  } catch (err) {
    chipsContainer.innerHTML = "<span style='font-size:12px; color:var(--ink-tertiary);'>Could not load users.</span>";
  }
}

async function handleLoginSubmit() {
  const userInp = document.getElementById("login-username");
  const passInp = document.getElementById("login-password");
  const resultBox = document.getElementById("login-result-box");

  const username = userInp ? userInp.value.trim() : "";
  const password = passInp ? passInp.value : "";

  if (!username || !password) {
    if (resultBox) {
      resultBox.style.display = "block";
      resultBox.className = "test-result error";
      resultBox.innerText = "Please enter username and password.";
    }
    return;
  }

  if (resultBox) {
    resultBox.style.display = "block";
    resultBox.className = "test-result";
    resultBox.innerText = "Signing in...";
  }

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password })
    });
    const data = await res.json();

    if (!res.ok || !data.success) {
      if (resultBox) {
        resultBox.className = "test-result error";
        resultBox.innerText = data.detail || data.message || "Invalid credentials.";
      }
      return;
    }

    currentAuthToken = data.token;
    localStorage.setItem("nl2sql_auth_token", currentAuthToken);
    currentUser = data.user;

    if (resultBox) {
      resultBox.className = "test-result success";
      resultBox.innerText = "Signed in successfully!";
    }

    updateAccountUI();
    await fetchSchema();
    await fetchMyUploadedTables();
    startNewChat(false);
    await fetchConversations();
    showNotification("info", `Signed in as ${currentUser.display_name || currentUser.username}`);

    setTimeout(() => {
      if (accountModal) accountModal.style.display = "none";
      if (resultBox) resultBox.style.display = "none";
    }, 800);
  } catch (err) {
    if (resultBox) {
      resultBox.className = "test-result error";
      resultBox.innerText = `Sign in error: ${err.message}`;
    }
  }
}

async function handleRegisterSubmit() {
  const userInp = document.getElementById("reg-username");
  const nameInp = document.getElementById("reg-display-name");
  const emailInp = document.getElementById("reg-email");
  const passInp = document.getElementById("reg-password");
  const resultBox = document.getElementById("reg-result-box");

  const username = userInp ? userInp.value.trim() : "";
  const display_name = nameInp ? nameInp.value.trim() : "";
  const email = emailInp ? emailInp.value.trim() : "";
  const password = passInp ? passInp.value : "";

  if (!username || username.length < 3) {
    if (resultBox) {
      resultBox.style.display = "block";
      resultBox.className = "test-result error";
      resultBox.innerText = "Username must be at least 3 characters.";
    }
    return;
  }
  if (!password || password.length < 4) {
    if (resultBox) {
      resultBox.style.display = "block";
      resultBox.className = "test-result error";
      resultBox.innerText = "Password must be at least 4 characters.";
    }
    return;
  }

  if (resultBox) {
    resultBox.style.display = "block";
    resultBox.className = "test-result";
    resultBox.innerText = "Creating account...";
  }

  try {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, display_name: display_name || username, email, password })
    });
    const data = await res.json();

    if (!res.ok || !data.success) {
      if (resultBox) {
        resultBox.className = "test-result error";
        resultBox.innerText = data.detail || data.message || "Registration failed.";
      }
      return;
    }

    currentAuthToken = data.token;
    localStorage.setItem("nl2sql_auth_token", currentAuthToken);
    currentUser = data.user;

    if (resultBox) {
      resultBox.className = "test-result success";
      resultBox.innerText = "Account created and signed in!";
    }

    updateAccountUI();
    await fetchSchema();
    await fetchMyUploadedTables();
    startNewChat(false);
    await fetchConversations();
    showNotification("info", `Account created: Welcome ${currentUser.display_name}!`);

    setTimeout(() => {
      if (accountModal) accountModal.style.display = "none";
      if (resultBox) resultBox.style.display = "none";
    }, 800);
  } catch (err) {
    if (resultBox) {
      resultBox.className = "test-result error";
      resultBox.innerText = `Registration error: ${err.message}`;
    }
  }
}

async function handleLogout() {
  try {
    if (currentAuthToken) {
      await fetch("/api/auth/logout", { method: "POST", headers: getAuthHeaders() });
    }
  } catch (e) {
    console.error("Logout error:", e);
  }
  currentAuthToken = null;
  localStorage.removeItem("nl2sql_auth_token");
  currentUser = null;
  myUploadedTables = [];
  activeSchema = { database_name: "", tables: {} };
  renderSidebarTables(activeSchema);
  renderSidebarChats([]);
  updateAccountUI();
  if (accountModal) accountModal.style.display = "none";
  openAuthGateway("signin");
  showNotification("info", "Signed out successfully.");
}

function setActiveTab(activeBtn, activePane) {
  [tabChats, tabTables, tabRelations].forEach(b => b && b.classList.remove("active"));
  [paneChats, paneTables, paneRelations].forEach(p => p && (p.style.display = "none"));
  activeBtn.classList.add("active");
  activePane.style.display = "flex";
}

function toggleSidebar(forceState) {
  if (!sidebar) return;
  if (window.innerWidth <= 768) {
    const shouldOpen = typeof forceState === "boolean" ? forceState : !sidebar.classList.contains("open");
    if (shouldOpen) {
      sidebar.classList.add("open");
      if (sidebarBackdrop) sidebarBackdrop.classList.add("active");
    } else {
      sidebar.classList.remove("open");
      if (sidebarBackdrop) sidebarBackdrop.classList.remove("active");
    }
  } else {
    sidebar.classList.toggle("collapsed");
  }
}

// ==========================================================================
// Conversation Management & Context Continuation
// ==========================================================================
async function fetchConversations() {
  if (!sidebarChatList) return;
  try {
    const res = await fetch("/api/conversations", { headers: getAuthHeaders() });
    if (!res.ok) return;
    const conversations = await res.json();
    renderSidebarChats(conversations);

    const statChatsCount = document.getElementById("stat-chats-count");
    if (statChatsCount) statChatsCount.innerText = conversations.length;

    // If active conversation ID exists, load it
    if (activeConversationId) {
      const exists = conversations.some(c => c.id === activeConversationId);
      if (exists) {
        loadConversation(activeConversationId, false);
      } else if (conversations.length > 0) {
        loadConversation(conversations[0].id, false);
      } else {
        startNewChat(false);
      }
    } else if (conversations.length > 0) {
      loadConversation(conversations[0].id, false);
    } else {
      startNewChat(false);
    }
  } catch (err) {
    sidebarChatList.innerHTML = "<div class='empty-state'>Could not load chats</div>";
  }
}

function renderSidebarChats(conversations) {
  sidebarChatList.innerHTML = "";
  if (!conversations || conversations.length === 0) {
    sidebarChatList.innerHTML = "<div class='empty-state'>No saved conversations yet</div>";
    return;
  }

  conversations.forEach(c => {
    const item = document.createElement("div");
    item.className = "chat-item";
    item.id = `chat-item-${c.id}`;
    if (activeConversationId === c.id) item.classList.add("active");

    const timeStr = formatRelativeTime(c.updated_at);
    item.innerHTML = `
      <div class="chat-item-info">
        <span class="chat-item-title">${escapeHtml(c.title)}</span>
        <div class="chat-item-meta">
          <span>${timeStr}</span>
          <span class="chat-item-badge">${c.message_count} msgs</span>
        </div>
      </div>
      <button class="btn-delete-chat" title="Delete conversation" data-id="${c.id}">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"></line>
          <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>
      </button>
    `;

    item.addEventListener("click", (e) => {
      if (e.target.closest(".btn-delete-chat")) {
        e.stopPropagation();
        handleDeleteConversation(c.id);
        return;
      }
      loadConversation(c.id);
    });

    sidebarChatList.appendChild(item);
  });
}

function startNewChat(focusInput = true) {
  activeConversationId = null;
  localStorage.removeItem("clarify_active_conv_id");
  currentSession = null;

  document.querySelectorAll(".chat-item").forEach(i => i.classList.remove("active"));
  if (navChatTitle) navChatTitle.innerText = "New Conversation";

  // Show Welcome Hero, clear thread
  chatThread.innerHTML = "";
  chatWelcomeHero.style.display = "flex";
  hideLoadingBubble();
  hideNotification();

  if (focusInput && queryInput) {
    queryInput.value = "";
    queryInput.style.height = "auto";
    if (btnClearPrompt) btnClearPrompt.style.display = "none";
    queryInput.focus();
  }
}

async function loadConversation(convId, focusInput = true) {
  if (!convId) return;
  activeConversationId = convId;
  localStorage.setItem("clarify_active_conv_id", convId);

  // Highlight in sidebar
  document.querySelectorAll(".chat-item").forEach(i => i.classList.remove("active"));
  const activeEl = document.getElementById(`chat-item-${convId}`);
  if (activeEl) activeEl.classList.add("active");

  try {
    const res = await fetch(`/api/conversations/${encodeURIComponent(convId)}`, { headers: getAuthHeaders() });
    if (!res.ok) {
      startNewChat();
      return;
    }
    const conv = await res.json();
    if (navChatTitle) navChatTitle.innerText = conv.title || "Conversation";

    renderConversation(conv);
    if (focusInput && queryInput) queryInput.focus();
  } catch (err) {
    showNotification("error", `Could not load conversation: ${err.message}`);
  }
}

function renderConversation(conv) {
  chatThread.innerHTML = "";
  hideLoadingBubble();

  if (!conv.messages || conv.messages.length === 0) {
    chatWelcomeHero.style.display = "flex";
    return;
  }

  chatWelcomeHero.style.display = "none";

  let lastUserQuery = "";
  conv.messages.forEach(msg => {
    if (msg.role === "user") {
      lastUserQuery = msg.content;
      appendUserMessageBubble(msg.content, msg.timestamp);
    } else if (msg.role === "assistant") {
      if (msg.status === "awaiting_clarification" && msg.clarification) {
        appendClarificationCard(msg.clarification, msg.session_id);
      } else {
        appendAssistantCard({
          user_query: lastUserQuery,
          natural_explanation: msg.content,
          generated_sql: msg.sql,
          sql_explanation: msg.sql_explanation,
          relationships_used: msg.relationships,
          execution: {
            columns: msg.columns,
            rows: msg.rows,
            row_count: msg.row_count,
            execution_time_ms: msg.execution_time_ms,
            success: msg.status === "success"
          },
          status: msg.status
        });
      }
    }
  });

  scrollChatToBottom();
}

async function handleDeleteConversation(convId) {
  try {
    const res = await fetch(`/api/conversations/${encodeURIComponent(convId)}`, {
      method: "DELETE",
      headers: getAuthHeaders()
    });
    if (res.ok) {
      if (activeConversationId === convId) {
        startNewChat();
      }
      fetchConversations();
    }
  } catch (err) {
    console.error("Delete failed:", err);
  }
}

async function handleClearAllChats() {
  if (!confirm("Are you sure you want to clear all saved chats for this account?")) return;
  try {
    await fetch("/api/conversations", {
      method: "DELETE",
      headers: getAuthHeaders()
    });
    startNewChat();
    fetchConversations();
  } catch (err) {
    console.error("Clear all failed:", err);
  }
}

// ==========================================================================
// Natural Language Query Execution (Multi-Turn Conversational)
// ==========================================================================
async function handleQuerySubmit() {
  const query = queryInput.value.trim();
  if (!query || isSubmitting) return;

  isSubmitting = true;
  setComposerLoading(true);
  hideNotification();

  // Hide hero, append user prompt bubble immediately
  chatWelcomeHero.style.display = "none";
  appendUserMessageBubble(query, new Date().toISOString());

  // Show dynamic progressive loading indicator
  startProgressiveLoading("⚡ Analyzing intent & context across universal domains...");
  scrollChatToBottom();

  // Clear composer input immediately for snappy feel
  queryInput.value = "";
  queryInput.style.height = "auto";
  if (btnClearPrompt) btnClearPrompt.style.display = "none";

  try {
    const payload = {
      query: query,
      conversation_id: activeConversationId
    };

    const res = await fetch("/api/query", {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload)
    });

    stopProgressiveLoading();

    if (!res.ok) {
      const err = await res.json();
      appendAssistantCard({
        status: "error",
        error_message: err.detail || "Query execution failed."
      });
      return;
    }

    currentSession = await res.json();

    // Link active conversation ID
    if (currentSession.conversation_id) {
      activeConversationId = currentSession.conversation_id;
      localStorage.setItem("clarify_active_conv_id", activeConversationId);
    }

    // Ambiguity / Clarification case
    currentSession.user_query = query;
    if (currentSession.status === "awaiting_clarification" && currentSession.analysis && currentSession.analysis.clarification) {
      appendClarificationCard(currentSession.analysis.clarification, currentSession.session_id, currentSession.analysis);
    } else {
      appendAssistantCard(currentSession);
    }

    // Refresh sidebar conversations and model learning metrics
    fetchConversations();
    fetchModelStatus();
  } catch (err) {
    stopProgressiveLoading();
    appendAssistantCard({
      status: "error",
      error_message: `Network error: ${err.message}`
    });
  } finally {
    isSubmitting = false;
    setComposerLoading(false);
    stopProgressiveLoading();
    scrollChatToBottom();
  }
}

// ==========================================================================
// Clarification Choice Handler
// ==========================================================================
async function handleClarifySelection(sessionId, optionId, customText, cardEl) {
  if (isSubmitting) return;
  isSubmitting = true;
  setComposerLoading(true);

  if (cardEl) {
    cardEl.classList.add("selected");
  }

  startProgressiveLoading("⚙️ Applying selection & compiling SQL...");
  scrollChatToBottom();

  try {
    const res = await fetch(`/api/query/${sessionId}/clarify`, {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ option_id: optionId, custom_text: customText })
    });

    stopProgressiveLoading();

    if (!res.ok) {
      const err = await res.json();
      appendAssistantCard({
        status: "error",
        error_message: err.detail || "Clarification failed."
      });
      return;
    }

    currentSession = await res.json();
    appendAssistantCard(currentSession);
    fetchConversations();
    fetchModelStatus();
  } catch (err) {
    stopProgressiveLoading();
    appendAssistantCard({
      status: "error",
      error_message: `Error: ${err.message}`
    });
  } finally {
    isSubmitting = false;
    setComposerLoading(false);
    stopProgressiveLoading();
    scrollChatToBottom();
  }
}

// ==========================================================================
// Chat Stream DOM Renderers
// ==========================================================================
function appendUserMessageBubble(text, timestamp) {
  const turn = document.createElement("div");
  turn.className = "chat-turn chat-turn-user";

  const bubble = document.createElement("div");
  bubble.className = "user-bubble";
  bubble.innerHTML = `
    <div class="user-text">${escapeHtml(text)}</div>
    <span class="user-time">${formatTimeOnly(timestamp)}</span>
  `;

  turn.appendChild(bubble);
  chatThread.appendChild(turn);
}

function appendClarificationCard(clarify, sessionId, analysis = null) {
  const turn = document.createElement("div");
  turn.className = "chat-turn chat-turn-assistant";

  const missingInfoHtml = (analysis && analysis.missing_information)
    ? `<div style="font-size: 12px; color: var(--ink-secondary); margin-top: 3px; font-weight: 400;">${escapeHtml(analysis.missing_information)}</div>`
    : "";

  const card = document.createElement("div");
  card.className = "assistant-card clarification-card-turn";
  
  card.innerHTML = `
    <div class="assistant-header">
      <div class="assistant-identity">
        <span class="assistant-sparkle">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
          </svg>
        </span>
        <div>
          <span class="assistant-title">${escapeHtml(clarify.question)}</span>
          ${missingInfoHtml}
        </div>
      </div>
      <span class="assistant-tag">${escapeHtml((clarify.ambiguity_type || "").toUpperCase().replace(/_/g, " "))} AMBIGUITY</span>
    </div>
    <div class="clarification-options" id="clarify-opts-${sessionId}"></div>
    <div class="custom-input-row">
      <input type="text" class="custom-clarify-inline" placeholder="Or specify custom requirement..." id="custom-in-${sessionId}">
      <button class="btn btn-secondary btn-sm" id="btn-custom-${sessionId}">Apply</button>
    </div>
  `;

  const optsContainer = card.querySelector(`#clarify-opts-${sessionId}`);
  clarify.options.forEach(opt => {
    const optBtn = document.createElement("button");
    optBtn.className = "option-card";
    optBtn.innerHTML = `
      <span class="opt-title">${escapeHtml(opt.label)}</span>
      <span class="opt-desc">${escapeHtml(opt.description || opt.implied_filter_or_metric || "")}</span>
    `;

    optBtn.addEventListener("click", () => {
      optsContainer.querySelectorAll(".option-card").forEach(c => c.classList.remove("selected"));
      optBtn.classList.add("selected");
      handleClarifySelection(sessionId, opt.id, null, optBtn);
    });

    optsContainer.appendChild(optBtn);
  });

  const customInput = card.querySelector(`#custom-in-${sessionId}`);
  const customBtn = card.querySelector(`#btn-custom-${sessionId}`);
  customBtn.addEventListener("click", () => {
    const val = customInput.value.trim();
    if (val) handleClarifySelection(sessionId, null, val, null);
  });

  turn.appendChild(card);
  chatThread.appendChild(turn);
}

function appendAssistantCard(session) {
  const turn = document.createElement("div");
  turn.className = "chat-turn chat-turn-assistant";

  const card = document.createElement("div");
  card.className = "assistant-card";

  // Check for workspace zero-dataset guidance state
  if (session.status === "no_dataset") {
    card.innerHTML = `
      <div class="assistant-no-dataset-card">
        <div class="no-dataset-header">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <span>Workspace Guidance: No Datasets Available</span>
        </div>
        <div class="no-dataset-text">
          ${renderMarkdownExplanation(session.natural_explanation || "No database tables found in your workspace.")}
        </div>
        <button class="no-dataset-action-btn" id="btn-card-upload-${session.session_id || Date.now()}">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
          + Upload Dataset (CSV, Excel, JSON)
        </button>
      </div>
    `;
    const btnUp = card.querySelector(`button[id^="btn-card-upload-"]`);
    if (btnUp) {
      btnUp.addEventListener("click", () => {
        if (uploadModal) uploadModal.style.display = "flex";
      });
    }
    turn.appendChild(card);
    chatThread.appendChild(turn);
    return;
  }

  // Check for error state without generated SQL
  const isError = session.status === "error" || Boolean(session.error_message);
  if (isError && !session.generated_sql) {
    card.innerHTML = `
      <div class="assistant-header">
        <div class="assistant-identity">
          <span style="color:#d70015; font-size:16px;">⚠️</span>
          <span class="assistant-title">Execution Notice</span>
        </div>
      </div>
      <div class="analysis-body" style="color:var(--ink);">
        ${renderMarkdownExplanation(session.error_message || "Could not execute the query on the active database schema.")}
      </div>
    `;
    turn.appendChild(card);
    chatThread.appendChild(turn);
    return;
  }

  // Header
  const headerHtml = `
    <div class="assistant-header">
      <div class="assistant-identity">
        <span class="${isError ? '' : 'assistant-sparkle'}">
          ${isError ? '<span style="color:#d70015; font-size:16px;">⚠️</span>' : '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>'}
        </span>
        <span class="assistant-title">${isError ? 'Execution Notice' : 'AI Answer'}</span>
      </div>
      <span class="assistant-tag" style="${isError ? 'background:rgba(215,0,21,0.1); color:#d70015;' : ''}">${isError ? 'Needs Tuning' : 'Direct Insight'}</span>
    </div>
  `;

  // Narrative Body
  const narrativeText = isError ? (session.error_message || "An error occurred.") : (session.natural_explanation || "Query completed successfully.");
  const narrativeHtml = `<div class="analysis-body" style="${isError ? 'color:#d70015;' : ''}">${renderMarkdownExplanation(narrativeText)}</div>`;

  // Relational Banner (if joins/relationships were used)
  let relationsHtml = "";
  if (session.relationships_used && session.relationships_used.length > 0) {
    const pills = session.relationships_used.map(r => `<span class="rel-pill">${escapeHtml(r)}</span>`).join("");
    relationsHtml = `
      <div class="relationships-banner" style="display: flex;">
        <span class="rel-banner-label">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path>
            <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path>
          </svg>
          Active Schema Relationships & Joins:
        </span>
        ${pills}
      </div>
    `;
  }

  // Collapsible SQL Inspector
  let sqlHtml = "";
  const uid = Math.random().toString(36).substring(2, 9);
  if (session.generated_sql) {
    sqlHtml = `
      <div class="sql-action-row" style="display:flex; justify-content:flex-end;">
        <button class="btn btn-secondary btn-sm btn-inspect-sql" id="btn-toggle-sql-${uid}">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="16 18 22 12 16 6"></polyline>
            <polyline points="8 6 2 12 8 18"></polyline>
          </svg>
          <span>View SQL</span>
        </button>
      </div>
      <div class="sql-inspector" id="sql-inspector-${uid}" style="display: none; margin-top: 8px;">
        <div class="sql-inspector-bar">
          <span class="sql-tag">PostgreSQL Query (Validated by SQLGlot)</span>
          <button class="btn-copy" id="btn-copy-sql-${uid}">Copy</button>
        </div>
        <pre class="sql-code"><code>${escapeHtml(session.generated_sql)}</code></pre>
      </div>
    `;
  }

  // Numbers Data Table
  let tableHtml = "";
  const exec = session.execution;
  if (exec && exec.columns && exec.columns.length > 0) {
    const tableId = `table-${uid}`;
    const headerCols = exec.columns.map(c => `<th>${escapeHtml(c)}</th>`).join("");
    
    let bodyRows = "";
    if (exec.rows && exec.rows.length > 0) {
      bodyRows = exec.rows.map(row => {
        const cells = exec.columns.map(col => {
          const val = row[col];
          const isNum = typeof val === "number" || (!isNaN(Number(val)) && val !== null && val !== "");
          const align = isNum ? 'style="text-align: right;"' : '';
          return `<td ${align}>${val !== null && val !== undefined ? escapeHtml(String(val)) : "—"}</td>`;
        }).join("");
        return `<tr>${cells}</tr>`;
      }).join("");
    } else {
      bodyRows = `<tr><td colspan="${exec.columns.length}" style="text-align:center; padding:16px; color:var(--ink-tertiary);">0 records returned.</td></tr>`;
    }

    const execTime = exec.execution_time_ms ? `${exec.execution_time_ms}ms` : "";
    const recCount = `${exec.row_count || (exec.rows ? exec.rows.length : 0)} record(s)`;

    tableHtml = `
      <div class="table-container" style="margin-top: 10px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <div style="font-size: 12px; font-weight: 600; color: var(--ink-secondary);">Database Records</div>
          <button class="btn btn-secondary btn-sm" id="btn-export-${uid}">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
            <span>Export CSV</span>
          </button>
        </div>
        <table class="apple-table" id="${tableId}">
          <thead><tr>${headerCols}</tr></thead>
          <tbody>${bodyRows}</tbody>
        </table>
        <div class="table-footer-meta">
          <span>${recCount}</span>
          <span>${execTime}</span>
        </div>
      </div>
    `;
  }

  // Smart Contextual Follow-up Chips
  const followups = generateContextualFollowups(session);
  let followupsHtml = "";
  if (followups.length > 0) {
    const chips = followups.map(f => 
      `<button class="context-chip" data-query="${escapeHtml(f)}">
        <span class="chip-sparkle">↳</span>
        <span>${escapeHtml(f)}</span>
      </button>`
    ).join("");
    followupsHtml = `
      <div class="card-followups">
        <span class="followups-label">Suggested Contextual Follow-ups:</span>
        <div class="followup-chips-row">${chips}</div>
      </div>
    `;
  }

  // Self-Learning & Teaching Controls
  let feedbackHtml = "";
  const queryText = session.resolved_query || session.original_query || session.user_query || "";
  if (session.generated_sql && queryText) {
    feedbackHtml = `
      <div class="model-feedback-row" id="fb-row-${uid}">
        <div class="feedback-label">
          <span>🧠 Teach Model:</span>
        </div>
        <div class="feedback-actions">
          <button class="btn-feedback" id="btn-thumb-up-${uid}" title="Reinforce this SQL in model memory">
            <span>👍 Accurate</span>
          </button>
          <button class="btn-feedback" id="btn-edit-teach-${uid}" title="Provide corrected SQL to train model">
            <span>✏️ Teach / Edit SQL</span>
          </button>
        </div>
      </div>
      <div class="feedback-editor-box" id="fb-editor-${uid}" style="display: none;">
        <span class="feedback-editor-title">Provide Correct SQL to Train Local Model:</span>
        <textarea class="feedback-textarea" id="fb-sql-input-${uid}">${escapeHtml(session.generated_sql)}</textarea>
        <div class="feedback-editor-actions">
          <button class="btn btn-secondary btn-sm" id="btn-cancel-teach-${uid}">Cancel</button>
          <button class="btn btn-primary btn-sm" id="btn-save-teach-${uid}">Train Model</button>
        </div>
      </div>
    `;
  }

  card.innerHTML = headerHtml + narrativeHtml + relationsHtml + sqlHtml + tableHtml + followupsHtml + feedbackHtml;

  // Wire SQL Toggle & Copy buttons for this specific card
  const toggleSqlBtn = card.querySelector(`#btn-toggle-sql-${uid}`);
  const sqlBox = card.querySelector(`#sql-inspector-${uid}`);
  if (toggleSqlBtn && sqlBox) {
    toggleSqlBtn.addEventListener("click", () => {
      const isShown = sqlBox.style.display === "block";
      sqlBox.style.display = isShown ? "none" : "block";
      toggleSqlBtn.querySelector("span").innerText = isShown ? "View SQL" : "Hide SQL";
    });
  }

  const copySqlBtn = card.querySelector(`#btn-copy-sql-${uid}`);
  if (copySqlBtn && session.generated_sql) {
    copySqlBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(session.generated_sql);
      copySqlBtn.innerText = "Copied!";
      setTimeout(() => copySqlBtn.innerText = "Copy", 1500);
    });
  }

  // Wire Export CSV
  const exportBtn = card.querySelector(`#btn-export-${uid}`);
  if (exportBtn && exec) {
    exportBtn.addEventListener("click", () => exportTableToCSV(exec.columns, exec.rows));
  }

  // Wire contextual follow-up chips
  card.querySelectorAll(".context-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const q = chip.getAttribute("data-query");
      if (q && queryInput) {
        queryInput.value = q;
        queryInput.style.height = "auto";
        handleQuerySubmit();
      }
    });
  });

  // Wire Self-Learning Feedback Buttons
  const thumbUpBtn = card.querySelector(`#btn-thumb-up-${uid}`);
  const editTeachBtn = card.querySelector(`#btn-edit-teach-${uid}`);
  const editorBox = card.querySelector(`#fb-editor-${uid}`);
  const cancelTeachBtn = card.querySelector(`#btn-cancel-teach-${uid}`);
  const saveTeachBtn = card.querySelector(`#btn-save-teach-${uid}`);
  const sqlInput = card.querySelector(`#fb-sql-input-${uid}`);

  if (thumbUpBtn) {
    thumbUpBtn.addEventListener("click", async () => {
      thumbUpBtn.disabled = true;
      thumbUpBtn.classList.add("active-pos");
      thumbUpBtn.innerHTML = `<span>✓ Reinforced in Model</span>`;
      await submitModelFeedback(queryText, session.generated_sql, 1, null, session.tables_used || []);
      showNotification("success", "Query reinforced into model training memory!");
    });
  }

  if (editTeachBtn && editorBox) {
    editTeachBtn.addEventListener("click", () => {
      const isVisible = editorBox.style.display === "flex" || editorBox.style.display === "block";
      editorBox.style.display = isVisible ? "none" : "flex";
      editTeachBtn.classList.toggle("active-edit", !isVisible);
    });
  }

  if (cancelTeachBtn && editorBox) {
    cancelTeachBtn.addEventListener("click", () => {
      editorBox.style.display = "none";
      if (editTeachBtn) editTeachBtn.classList.remove("active-edit");
    });
  }

  if (saveTeachBtn && sqlInput && editorBox) {
    saveTeachBtn.addEventListener("click", async () => {
      const corrected = sqlInput.value.trim();
      if (!corrected) return;
      saveTeachBtn.disabled = true;
      saveTeachBtn.innerText = "Training...";
      const ok = await submitModelFeedback(queryText, session.generated_sql, 1, corrected, session.tables_used || []);
      if (ok) {
        editorBox.style.display = "none";
        if (editTeachBtn) {
          editTeachBtn.classList.add("active-edit");
          editTeachBtn.innerHTML = `<span>✓ Model Retrained</span>`;
        }
        showNotification("success", "Model retrained with your corrected SQL query!");
      } else {
        saveTeachBtn.disabled = false;
        saveTeachBtn.innerText = "Train Model";
        showNotification("error", "Failed to update model memory.");
      }
    });
  }

  turn.appendChild(card);
  chatThread.appendChild(turn);
}

function generateContextualFollowups(session) {
  const followups = [];
  const q = (session.resolved_query || session.original_query || "").toLowerCase();
  const sql = (session.generated_sql || "").toLowerCase();
  const rows = session.execution?.rows || [];

  if (q.includes("net run rate") || sql.includes("net_run_rate")) {
    followups.push("Which team has the highest?");
    followups.push("Now show only teams with positive NRR");
    followups.push("What formula was used?");
  } else if (q.includes("compound interest") || sql.includes("power(")) {
    followups.push("What if the rate is 7%?");
    followups.push("Calculate for 5 years instead");
  } else if (q.includes("strike rate") || sql.includes("balls_faced")) {
    followups.push("Sort by highest strike rate");
    followups.push("Show player with highest economy");
  } else if (q.includes("sales") || sql.includes("sales")) {
    followups.push("Group by store city");
    followups.push("Show top 3 transactions");
  } else if (rows.length > 3) {
    followups.push("Show only the top 3");
    followups.push("Explain this SQL step-by-step");
  } else if (sql) {
    followups.push("Explain this query");
  }

  return followups.slice(0, 3);
}

let progressiveLoadingTimer = null;

function startProgressiveLoading(initialText) {
  if (progressiveLoadingTimer) {
    clearInterval(progressiveLoadingTimer);
    progressiveLoadingTimer = null;
  }
  const stages = [
    "⚡ Analyzing intent & context...",
    "🔍 Checking schema & domain formulas...",
    "⚙️ Compiling SQL & querying PostgreSQL...",
    "✨ Formatting insights & data..."
  ];
  let stageIndex = 0;
  showLoadingBubble(initialText || stages[0]);

  progressiveLoadingTimer = setInterval(() => {
    stageIndex++;
    if (stageIndex < stages.length) {
      showLoadingBubble(stages[stageIndex]);
    } else {
      clearInterval(progressiveLoadingTimer);
      progressiveLoadingTimer = null;
    }
  }, 1000);
}

function stopProgressiveLoading() {
  if (progressiveLoadingTimer) {
    clearInterval(progressiveLoadingTimer);
    progressiveLoadingTimer = null;
  }
  hideLoadingBubble();
}

function showLoadingBubble(text = "Compiling SQL & querying PostgreSQL...") {
  if (loadingBubbleText) loadingBubbleText.innerText = text;
  if (chatLoadingBubble) chatLoadingBubble.style.display = "inline-flex";
}

function hideLoadingBubble() {
  if (chatLoadingBubble) chatLoadingBubble.style.display = "none";
}

function scrollChatToBottom() {
  setTimeout(() => {
    if (chatViewport) {
      chatViewport.scrollTo({ top: chatViewport.scrollHeight, behavior: "smooth" });
    }
  }, 50);
}

function setComposerLoading(loading) {
  if (loading) {
    btnSubmit.disabled = true;
    btnAskText.innerText = "Running...";
    if (runIcon) runIcon.style.display = "none";
    spinner.style.display = "block";
  } else {
    btnSubmit.disabled = false;
    btnAskText.innerText = "Run";
    if (runIcon) runIcon.style.display = "inline-block";
    spinner.style.display = "none";
  }
}

// ==========================================================================
// Schema & Table Browser
// ==========================================================================
async function fetchSchema() {
  if (!sidebarTableList) return;
  sidebarTableList.innerHTML = "<div class='loading-state'>Loading tables...</div>";
  try {
    const res = await fetch("/api/schema", { headers: getAuthHeaders() });
    if (!res.ok) throw new Error("Could not load schema.");
    activeSchema = await res.json();
    renderSidebarTables(activeSchema);

    // Update Status Labels
    if (activeSchema.source_type === "postgresql") {
      statusDot.style.backgroundColor = "#0071e3";
      dbNameLabel.innerText = "PostgreSQL";
      dbTypeLabel.innerText = activeSchema.database_name || "Live Instance";
      if (topStatusDot) topStatusDot.style.backgroundColor = "#0071e3";
      if (topDbName) topDbName.innerText = "PostgreSQL";
    } else {
      statusDot.style.backgroundColor = "#34c759";
      dbNameLabel.innerText = "Sample Database";
      dbTypeLabel.innerText = activeSchema.database_name || "Academic & Sales";
      if (topStatusDot) topStatusDot.style.backgroundColor = "#34c759";
      if (topDbName) topDbName.innerText = "Sample DB";
    }
  } catch (err) {
    sidebarTableList.innerHTML = `<div class='loading-state' style='color:#d70015;'>${err.message}</div>`;
  }
}

function renderSidebarTables(schema) {
  sidebarTableList.innerHTML = "";
  const tables = (schema && schema.tables) ? schema.tables : {};
  if (Object.keys(tables).length === 0) {
    sidebarTableList.innerHTML = `
      <div class="empty-workspace-state">
        <div class="empty-state-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 7c0-1.66 3.58-3 8-3s8 1.34 8 3v10c0 1.66-3.58 3-8 3s-8-1.34-8-3V7z"></path>
            <path d="M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3"></path>
          </svg>
        </div>
        <div class="empty-state-title">No Datasets Connected</div>
        <div class="empty-state-desc">This account starts with 0 tables. Ingest a CSV, Excel, or JSON dataset to start querying.</div>
        <button class="btn btn-primary btn-sm" id="btn-sidebar-empty-upload" style="margin-top:6px;">+ Upload Dataset</button>
      </div>
    `;
    const btnEmptyUpload = document.getElementById("btn-sidebar-empty-upload");
    if (btnEmptyUpload) {
      btnEmptyUpload.addEventListener("click", () => {
        if (uploadModal) uploadModal.style.display = "flex";
      });
    }
    return;
  }

  const myTableNames = new Set((myUploadedTables || []).map(t => (t.table_name || "").toLowerCase()));

  Object.values(tables).forEach((table) => {
    const row = document.createElement("div");
    row.className = "table-row-item";

    const isMyUpload = myTableNames.has((table.name || "").toLowerCase());
    const uploadBadge = isMyUpload ? `<span class="table-upload-tag" title="Saved with your user account">My Upload</span>` : "";

    let fkInfo = "";
    if (table.foreign_keys && table.foreign_keys.length > 0) {
      const targets = table.foreign_keys.map(f => f.references.split('.')[0]).join(", ");
      fkInfo = `<div style="font-size:10px; color:var(--ink-tertiary); margin-top:2px;">↳ links to ${targets}</div>`;
    }

    row.innerHTML = `
      <div style="flex:1; overflow:hidden;">
        <div class="item-left">
          <span class="item-icon">${isMyUpload ? "📂" : "▤"}</span>
          <span class="item-name">${escapeHtml(table.name)}</span>
          ${uploadBadge}
        </div>
        ${fkInfo}
      </div>
      <span class="item-meta">${table.columns.length} cols</span>
    `;

    row.addEventListener("click", () => {
      queryInput.value = `Show summary and sample rows from ${table.name}`;
      if (window.innerWidth <= 768) toggleSidebar(false);
      handleQuerySubmit();
    });

    sidebarTableList.appendChild(row);
  });
}

async function fetchRelationships() {
  if (!sidebarRelationList) return;
  sidebarRelationList.innerHTML = "<div class='loading-state'>Loading relationships...</div>";
  try {
    const res = await fetch("/api/schema/relationships", { headers: getAuthHeaders() });
    if (!res.ok) throw new Error("Could not load relationships.");
    const data = await res.json();
    const rels = data.relationships || [];

    sidebarRelationList.innerHTML = "";
    if (rels.length === 0) {
      sidebarRelationList.innerHTML = "<div class='empty-state'>No foreign keys defined</div>";
      return;
    }

    rels.forEach((rel) => {
      const card = document.createElement("div");
      card.className = "relation-card";
      card.innerHTML = `
        <div class="relation-card-header">
          <span class="relation-path">${escapeHtml(rel.source_table)} → ${escapeHtml(rel.target_table)}</span>
          <span class="relation-type">Foreign Key</span>
        </div>
        <div class="relation-condition">${escapeHtml(rel.join_condition)}</div>
        <div class="relation-action">Query linked records →</div>
      `;

      card.addEventListener("click", () => {
        queryInput.value = `Show ${rel.source_table} linked to ${rel.target_table} with details`;
        if (window.innerWidth <= 768) toggleSidebar(false);
        handleQuerySubmit();
      });

      sidebarRelationList.appendChild(card);
    });
  } catch (err) {
    sidebarRelationList.innerHTML = `<div class='empty-state'>${err.message}</div>`;
  }
}

// ==========================================================================
// CSV Export & Markdown Helper
// ==========================================================================
function exportTableToCSV(columns, rows) {
  if (!columns || columns.length === 0) return;
  const lines = [];
  lines.push(columns.join(","));

  if (rows && rows.length > 0) {
    rows.forEach(r => {
      const rowVals = columns.map(c => {
        const val = r[c] !== null && r[c] !== undefined ? String(r[c]) : "";
        return `"${val.replace(/"/g, '""')}"`;
      });
      lines.push(rowVals.join(","));
    });
  }

  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `query_export_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function renderMarkdownExplanation(text) {
  if (!text) return "";
  let html = escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  const lines = html.split('\n');
  let inList = false;
  let res = [];

  for (let rawLine of lines) {
    let line = rawLine.trim();
    if (!line) {
      if (inList) { res.push('</ul>'); inList = false; }
      continue;
    }

    if (line.startsWith('### ')) {
      if (inList) { res.push('</ul>'); inList = false; }
      res.push(`<div class="analysis-section-title">${line.substring(4)}</div>`);
    } else if (line.startsWith('## ')) {
      if (inList) { res.push('</ul>'); inList = false; }
      res.push(`<div class="analysis-section-title" style="font-size:14.5px;">${line.substring(3)}</div>`);
    } else if (line.startsWith('# ')) {
      if (inList) { res.push('</ul>'); inList = false; }
      res.push(`<div class="analysis-section-title" style="font-size:15px;">${line.substring(2)}</div>`);
    } else if (line.startsWith('- ') || line.startsWith('• ') || line.startsWith('* ')) {
      if (!inList) { res.push('<ul>'); inList = true; }
      res.push(`<li>${line.substring(2)}</li>`);
    } else if (/^\d+\.\s/.test(line)) {
      if (!inList) { res.push('<ul>'); inList = true; }
      res.push(`<li>${line.replace(/^\d+\.\s/, '')}</li>`);
    } else {
      if (inList) { res.push('</ul>'); inList = false; }
      res.push(`<p>${line}</p>`);
    }
  }
  if (inList) res.push('</ul>');
  return res.join('');
}

function escapeHtml(text) {
  if (!text) return "";
  const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
  return String(text).replace(/[&<>"']/g, (m) => map[m]);
}

function formatRelativeTime(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const diffMin = Math.round((Date.now() - d.getTime()) / 60000);
    if (diffMin < 1) return "Just now";
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffH = Math.round(diffMin / 60);
    if (diffH < 24) return `${diffH}h ago`;
    return d.toLocaleDateString([], { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

function formatTimeOnly(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function hideNotification() {
  if (notificationBar) notificationBar.style.display = "none";
}

function showNotification(type, message) {
  if (!notificationBar) return;
  notificationBar.style.display = "block";
  notificationBar.className = `notification-bar ${type}`;
  notificationBar.innerText = message;
}

// ==========================================================================
// Database Connection Settings Modal
// ==========================================================================
async function handleTestConnection() {
  modalTestResult.style.display = "block";
  modalTestResult.className = "test-result";
  modalTestResult.innerText = "Connecting to PostgreSQL...";

  const payload = {
    host: document.getElementById("cfg-host").value.trim(),
    port: parseInt(document.getElementById("cfg-port").value.trim() || "5432"),
    dbname: document.getElementById("cfg-dbname").value.trim(),
    user: document.getElementById("cfg-user").value.trim(),
    password: document.getElementById("cfg-password").value,
  };

  try {
    const res = await fetch("/api/schema/test-connection", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await res.json();
    if (result.success) {
      modalTestResult.className = "test-result success";
      modalTestResult.innerText = `Connected: ${result.message}`;
    } else {
      modalTestResult.className = "test-result error";
      modalTestResult.innerText = result.message;
    }
  } catch (err) {
    modalTestResult.className = "test-result error";
    modalTestResult.innerText = `Request error: ${err.message}`;
  }
}

async function handleApplyDbSource() {
  try {
    const payload = { source: currentSourceMode };
    if (currentSourceMode === "postgresql") {
      payload.host = document.getElementById("cfg-host").value.trim();
      payload.port = parseInt(document.getElementById("cfg-port").value.trim() || "5432");
      payload.dbname = document.getElementById("cfg-dbname").value.trim();
      payload.user = document.getElementById("cfg-user").value.trim();
      payload.password = document.getElementById("cfg-password").value;
    }
    const res = await fetch("/api/schema/switch-source", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(`Could not switch catalog: ${data.detail || data.message}`);
      return;
    }
    settingsModal.style.display = "none";
    fetchSchema();
    fetchRelationships();
    showNotification("info", data.message || "Catalog updated.");
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
}

// ==========================================================================
// Dataset Upload Dialog Handlers
// ==========================================================================
function openUploadDialog() {
  if (!uploadModal) return;
  uploadModal.style.display = "flex";
  selectedUploadFile = null;
  if (fileInput) fileInput.value = "";
  if (selectedFileBadge) {
    selectedFileBadge.style.display = "none";
    selectedFileBadge.innerText = "";
  }
  if (uploadTargetTable) uploadTargetTable.value = "";
  if (uploadResultBox) {
    uploadResultBox.style.display = "none";
    uploadResultBox.innerText = "";
  }
  if (btnStartUpload) btnStartUpload.disabled = true;
}

function closeUploadDialog() {
  if (!uploadModal) return;
  uploadModal.style.display = "none";
}

function handleFileChosen(e) {
  if (e.target.files && e.target.files.length > 0) {
    processSelectedFile(e.target.files[0]);
  }
}

function processSelectedFile(file) {
  selectedUploadFile = file;
  const sizeKb = (file.size / 1024).toFixed(1);
  if (selectedFileBadge) {
    selectedFileBadge.style.display = "inline-flex";
    selectedFileBadge.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
        <polyline points="14 2 14 8 20 8"></polyline>
      </svg>
      <span>${escapeHtml(file.name)} (${sizeKb} KB)</span>
    `;
  }
  if (uploadTargetTable && !uploadTargetTable.value.trim()) {
    const rawName = file.name.replace(/\.[^/.]+$/, "");
    const cleanName = rawName.toLowerCase().replace(/[^a-z0-9_]/g, "_").slice(0, 40);
    uploadTargetTable.value = cleanName;
  }
  if (btnStartUpload) btnStartUpload.disabled = false;
  if (uploadResultBox) uploadResultBox.style.display = "none";
}

async function handleUploadSubmit() {
  if (!selectedUploadFile) return;

  btnStartUpload.disabled = true;
  btnUploadLabel.innerText = "Ingesting...";
  uploadSpinner.style.display = "inline-block";
  uploadResultBox.style.display = "block";
  uploadResultBox.className = "test-result";
  uploadResultBox.innerText = "Reading and converting dataset into live database table...";

  const formData = new FormData();
  formData.append("file", selectedUploadFile);
  const targetTable = uploadTargetTable ? uploadTargetTable.value.trim() : "";
  if (targetTable) {
    formData.append("custom_table_name", targetTable);
  }

  try {
    const res = await fetch("/api/upload", {
      method: "POST",
      headers: getAuthHeaders(),
      body: formData,
    });
    let result = {};
    try {
      result = await res.json();
    } catch (_) {
      result = { detail: res.statusText || `Server returned status ${res.status}` };
    }

    if (!res.ok || !result.success) {
      uploadResultBox.className = "test-result error";
      uploadResultBox.innerText = `Ingestion failed: ${result.detail || result.message || "Unknown error"}`;
      btnStartUpload.disabled = false;
      btnUploadLabel.innerText = "Ingest Dataset";
      uploadSpinner.style.display = "none";
      return;
    }

    uploadResultBox.className = "test-result success";
    const tblName = result.table_name || (result.tables_created && result.tables_created[0]) || targetTable;
    uploadResultBox.innerText = `✓ ${result.message || `Table '${tblName}' created successfully and saved with your account!`}`;
    showNotification("info", `Dataset '${tblName}' saved with your account and ready for queries!`);

    await fetchMyUploadedTables();
    await fetchSchema();

    setTimeout(() => {
      closeUploadDialog();
      queryInput.value = `Show summary and first 5 rows of ${tblName}`;
      handleQuerySubmit();
    }, 1200);
  } catch (err) {
    uploadResultBox.className = "test-result error";
    uploadResultBox.innerText = `Network error during upload: ${err.message}`;
    btnStartUpload.disabled = false;
  } finally {
    btnUploadLabel.innerText = "Ingest Dataset";
    uploadSpinner.style.display = "none";
  }
}
