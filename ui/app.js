// State variables
let activeIndex = -1;
let searchTimeout = null;
let isStreaming = false;
let currentMode = 'ai'; // 'ai', 'verbatim', 'source'
let currentResults = [];
let currentModalItem = null;

// Conversation History & Turn state
let activeConversationId = null;
let shownTurnSources = {}; // turnId -> boolean
let turnSourcesData = {}; // turnId -> sources list

// Open Source Mode state
let openSourceOffset = 0;
let openSourceLimit = 20;
let openSourceGroup = 'all';

// K depth state
let currentK = 15;

// Modal passages state
let modalChunksList = [];
let modalCurrentIndex = -1;

// DOM Elements
const searchInput = document.getElementById("search-input");
const resultsArea = document.getElementById("results-area");
const emptyState = document.getElementById("empty-state");
const resultsList = document.getElementById("results-list");
const liveSearchContainer = document.getElementById("live-search-container");
const conversationContainer = document.getElementById("conversation-container");
const openSourceContainer = document.getElementById("open-source-container");
const openSourceList = document.getElementById("open-source-list");
const paginationContainer = document.getElementById("pagination-container");
const paginationInfo = document.getElementById("pagination-info");
const loadMoreBtn = document.getElementById("load-more-btn");
const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebar-toggle");
const newChatBtn = document.getElementById("new-chat-btn");

const sectionToday = document.getElementById("section-today");
const sectionYesterday = document.getElementById("section-yesterday");
const sectionEarlier = document.getElementById("section-earlier");
const listToday = document.getElementById("list-today");
const listYesterday = document.getElementById("list-yesterday");
const listEarlier = document.getElementById("list-earlier");

// Top Bar Elements
const statusDot = document.querySelector(".status-dot");
const statusText = document.querySelector(".status-text");
const reingestBtn = document.getElementById("reingest-btn");

// Slider Elements
const kSlider = document.getElementById("k-slider");
const kValueLabel = document.getElementById("k-value");

// Modal Navigation Elements
const modalBreadcrumbs = document.getElementById("modalBreadcrumbs");
const modalPrev = document.getElementById("modalPrev");
const modalNext = document.getElementById("modalNext");
const modalBreadcrumbLabel = document.getElementById("modalBreadcrumbLabel");

// Conversation actions & export
const conversationActions = document.getElementById("conversation-actions");
const exportThreadBtn = document.getElementById("export-thread-btn");

// Error Console Elements
const consoleToggleBtn = document.getElementById("console-toggle-btn");
const consoleContent = document.getElementById("console-content");
const consoleErrorCount = document.getElementById("console-error-count");
const consoleClearBtn = document.getElementById("console-clear-btn");
const consoleLogsList = document.getElementById("console-logs-list");

// Toast helper
function showToast(message, isSuccess = false) {
  const toast = document.createElement("div");
  toast.style.position = "fixed";
  toast.style.bottom = "40px";
  toast.style.left = "50%";
  toast.style.transform = "translateX(-50%)";
  toast.style.backgroundColor = isSuccess ? "#0f3d1f" : "#ff4444";
  toast.style.color = isSuccess ? "#4ade80" : "#fff";
  toast.style.border = isSuccess ? "1px solid #4ade80" : "1px solid #5a1a1a";
  toast.style.padding = "10px 20px";
  toast.style.borderRadius = "6px";
  toast.style.fontSize = "11px";
  toast.style.fontFamily = "var(--font-mono)";
  toast.style.zIndex = "1000";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// Initialize page
document.addEventListener("DOMContentLoaded", () => {
  fetchStatus();
  loadHomeGreeting();
  loadSidebar();
  pollErrorConsole();
  
  // Status check loop
  let lastStatusOnline = null;
  setInterval(async () => {
    const isOnline = await fetchStatusQuiet();
    if (lastStatusOnline === true && isOnline === false) {
      showToast("ollama went offline");
    }
    lastStatusOnline = isOnline;
  }, 30000);

  // Error check loop
  setInterval(pollErrorConsole, 10000);

  // Shortcut hints for Mac/Windows
  const isMac = navigator.userAgent.toUpperCase().indexOf('MAC') >= 0;
  document.querySelector(".shortcut-hint").textContent = isMac ? "⌘K" : "Ctrl+K";
  
  setMode('ai');

  // Sidebar Toggle Event
  sidebarToggle.addEventListener("click", () => {
    sidebar.classList.toggle("open");
  });

  // New Chat Event
  newChatBtn.addEventListener("click", () => {
    activeConversationId = null;
    conversationActions.style.display = "none";
    clearSearchAndResults(true);
    document.querySelectorAll(".conv-item").forEach(el => el.classList.remove("active"));
  });

  // Open Source Filter Buttons
  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
      e.target.classList.add("active");
      openSourceGroup = e.target.dataset.group;
      openSourceOffset = 0;
      performOpenSourceSearch(searchInput.value.trim(), false);
    });
  });

  // Load More Button
  loadMoreBtn.addEventListener("click", () => {
    performOpenSourceSearch(searchInput.value.trim(), true);
  });

  // Slider Depth Listener
  if (kSlider && kValueLabel) {
    kSlider.addEventListener("input", (e) => {
      currentK = parseInt(e.target.value);
      kValueLabel.textContent = currentK;
      
      // Update active live search immediately if user is adjusting slider while typing
      const query = searchInput.value.trim();
      if (query) {
        if (currentMode === 'source') {
          openSourceOffset = 0;
          performOpenSourceSearch(query, false);
        } else {
          performLiveSearch(query);
        }
      }
    });
  }

  // Export Thread Listener
  if (exportThreadBtn) {
    exportThreadBtn.addEventListener("click", () => {
      exportThreadMarkdown();
    });
  }

  // Re-ingest Button Listener
  if (reingestBtn) {
    reingestBtn.addEventListener("click", () => {
      triggerReingest();
    });
  }

  // Error Console Toggle
  if (consoleToggleBtn) {
    consoleToggleBtn.addEventListener("click", () => {
      const isHidden = consoleContent.style.display === "none";
      consoleContent.style.display = isHidden ? "block" : "none";
      consoleToggleBtn.classList.toggle("open", isHidden);
    });
  }

  // Clear Error Console
  if (consoleClearBtn) {
    consoleClearBtn.addEventListener("click", async () => {
      try {
        const response = await fetch("/errors", { method: "DELETE" });
        if (response.ok) {
          pollErrorConsole();
        }
      } catch (err) {
        console.error(err);
      }
    });
  }

  // Modal Next/Prev pagination
  modalPrev.addEventListener("click", () => {
    if (modalCurrentIndex > 0) {
      navigateModalPassage(modalCurrentIndex - 1);
    }
  });

  modalNext.addEventListener("click", () => {
    if (modalCurrentIndex < modalChunksList.length - 1) {
      navigateModalPassage(modalCurrentIndex + 1);
    }
  });

  // Modal actions
  document.getElementById("modalAskAI").addEventListener("click", () => {
    if (currentModalItem) {
      const text = currentModalItem.text || currentModalItem.snippet;
      closeModal();
      searchInput.value = text;
      setMode('ai');
      askAI();
    }
  });

  document.getElementById("modalCopy").addEventListener("click", function() {
    if (currentModalItem) {
      const text = currentModalItem.text || currentModalItem.snippet;
      navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById("modalCopy");
        const originalText = btn.textContent;
        btn.textContent = "copied!";
        setTimeout(() => {
          btn.textContent = originalText;
        }, 1500);
      }).catch(err => {
        console.error("Failed to copy text: ", err);
      });
    }
  });

  document.getElementById("modalOpenOriginal").addEventListener("click", () => {
    if (currentModalItem && currentModalItem.url) {
      window.open(currentModalItem.url, "_blank");
    }
  });
});

// Mode switcher
function setMode(mode) {
  currentMode = mode;
  document.getElementById("modeAI").classList.toggle("active", mode === 'ai');
  document.getElementById("modeVerbatim").classList.toggle("active", mode === 'verbatim');
  document.getElementById("modeSource").classList.toggle("active", mode === 'source');

  const query = searchInput.value.trim();

  if (mode === 'source') {
    emptyState.style.display = 'none';
    conversationContainer.style.display = 'none';
    liveSearchContainer.style.display = 'none';
    openSourceContainer.style.display = 'block';
    conversationActions.style.display = 'none';
    if (query) {
      openSourceOffset = 0;
      performOpenSourceSearch(query, false);
    } else {
      openSourceList.innerHTML = "";
      paginationContainer.style.display = "none";
    }
  } else {
    openSourceContainer.style.display = 'none';
    if (query) {
      emptyState.style.display = 'none';
      liveSearchContainer.style.display = 'block';
      conversationContainer.style.display = 'none';
      conversationActions.style.display = 'none';
      performLiveSearch(query);
    } else {
      liveSearchContainer.style.display = 'none';
      if (activeConversationId) {
        emptyState.style.display = 'none';
        conversationContainer.style.display = 'flex';
        conversationActions.style.display = 'block';
      } else {
        emptyState.style.display = 'flex';
        conversationContainer.style.display = 'none';
        conversationActions.style.display = 'none';
      }
    }
  }
  searchInput.focus();
}

// Fetch home screen greeting details
async function loadHomeGreeting() {
  try {
    const response = await fetch("/greeting");
    if (!response.ok) throw new Error("Greeting load failed");
    const data = await response.json();
    
    document.getElementById("greeting-title").textContent = data.greeting;
    document.getElementById("greeting-subline").textContent = data.subline;
    
    const chipsContainer = document.getElementById("suggested-chips");
    chipsContainer.innerHTML = "";
    if (data.suggestions) {
      data.suggestions.forEach(suggestion => {
        const chip = document.createElement("button");
        chip.className = "prompt-chip";
        chip.textContent = suggestion;
        chip.addEventListener("click", () => {
          searchInput.value = suggestion;
          if (currentMode === 'source') {
            openSourceOffset = 0;
            performOpenSourceSearch(suggestion, false);
          } else {
            askAI();
          }
        });
        chipsContainer.appendChild(chip);
      });
    }
  } catch (err) {
    console.error("Error loading home greeting: ", err);
  }
}

// Load sidebar history conversations list
async function loadSidebar() {
  try {
    const response = await fetch("/conversations");
    if (!response.ok) throw new Error("Conversations load failed");
    const list = await response.json();
    
    listToday.innerHTML = "";
    listYesterday.innerHTML = "";
    listEarlier.innerHTML = "";
    
    let hasToday = false;
    let hasYesterday = false;
    let hasEarlier = false;
    
    const now = new Date();
    const todayStr = now.toDateString();
    
    const yesterday = new Date();
    yesterday.setDate(now.getDate() - 1);
    const yesterdayStr = yesterday.toDateString();

    list.forEach(c => {
      const convDate = new Date(c.updated_at);
      const convDateStr = convDate.toDateString();
      
      const itemEl = document.createElement("div");
      itemEl.className = "conv-item";
      if (c.id === activeConversationId) {
        itemEl.classList.add("active");
      }
      itemEl.dataset.id = c.id;
      
      const titleSpan = document.createElement("span");
      titleSpan.className = "conv-title-text";
      titleSpan.textContent = c.title || "New Conversation";
      
      // Inline rename on double click
      titleSpan.addEventListener("dblclick", () => {
        const input = document.createElement("input");
        input.type = "text";
        input.className = "rename-input";
        input.value = titleSpan.textContent;
        
        itemEl.replaceChild(input, titleSpan);
        input.focus();
        input.select();
        
        let finished = false;
        async function finishRename() {
          if (finished) return;
          finished = true;
          const newTitle = input.value.trim() || "New Conversation";
          titleSpan.textContent = newTitle;
          itemEl.replaceChild(titleSpan, input);
          
          if (newTitle !== c.title) {
            c.title = newTitle;
            try {
              const response = await fetch(`/conversations/${c.id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ title: newTitle })
              });
              if (!response.ok) throw new Error("Rename failed");
              loadSidebar();
            } catch (e) {
              console.error(e);
            }
          }
        }
        
        input.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            finishRename();
          } else if (e.key === "Escape") {
            e.preventDefault();
            input.value = c.title || "New Conversation";
            finishRename();
          }
        });
        
        input.addEventListener("blur", () => {
          finishRename();
        });
      });

      titleSpan.addEventListener("click", () => {
        selectConversation(c.id);
      });
      
      const deleteBtn = document.createElement("button");
      deleteBtn.className = "delete-conv-btn";
      deleteBtn.innerHTML = "✕";
      deleteBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteConversation(c.id);
      });
      
      itemEl.appendChild(titleSpan);
      itemEl.appendChild(deleteBtn);
      
      if (convDateStr === todayStr) {
        listToday.appendChild(itemEl);
        hasToday = true;
      } else if (convDateStr === yesterdayStr) {
        listYesterday.appendChild(itemEl);
        hasYesterday = true;
      } else {
        listEarlier.appendChild(itemEl);
        hasEarlier = true;
      }
    });
    
    sectionToday.style.display = hasToday ? "block" : "none";
    sectionYesterday.style.display = hasYesterday ? "block" : "none";
    sectionEarlier.style.display = hasEarlier ? "block" : "none";
    
  } catch (err) {
    console.error("Error loading sidebar list: ", err);
  }
}

// Select a conversation from sidebar
async function selectConversation(id) {
  activeConversationId = id;
  clearSearchAndResults(true);
  
  document.querySelectorAll(".conv-item").forEach(el => {
    el.classList.toggle("active", el.dataset.id === id);
  });
  
  emptyState.style.display = "none";
  liveSearchContainer.style.display = "none";
  openSourceContainer.style.display = "none";
  conversationContainer.style.display = "flex";
  conversationActions.style.display = "block";
  conversationContainer.innerHTML = `<div class="no-results">loading history...</div>`;
  
  try {
    const response = await fetch(`/conversations/${id}`);
    if (!response.ok) throw new Error("Load conversation failed");
    const data = await response.json();
    
    conversationContainer.innerHTML = "";
    
    if (!data.turns || data.turns.length === 0) {
      conversationContainer.innerHTML = `<div class="no-results">empty conversation</div>`;
      return;
    }
    
    data.turns.forEach(turn => {
      renderTurn(turn);
    });
    
    conversationContainer.scrollIntoView({ block: "end", behavior: "smooth" });
  } catch (err) {
    console.error(err);
    conversationContainer.innerHTML = `<div class="no-results" style="color: var(--accent-offline)">error loading conversation</div>`;
  }
}

// Delete a conversation
async function deleteConversation(id) {
  if (confirm("Are you sure you want to delete this conversation? This cannot be undone.")) {
    try {
      const response = await fetch(`/conversations/${id}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Delete failed");
      
      if (activeConversationId === id) {
        activeConversationId = null;
        conversationActions.style.display = "none";
        clearSearchAndResults(true);
      }
      loadSidebar();
    } catch (err) {
      console.error(err);
    }
  }
}

// Fetch status (active healthcheck details)
async function fetchStatus() {
  try {
    const response = await fetch("/status");
    if (!response.ok) throw new Error("API error");
    const data = await response.json();
    
    updateStatusIndicator(data);
    return data.ollama_running;
  } catch (err) {
    updateStatusIndicatorOffline("local server offline — run: start_app.bat");
    return false;
  }
}

async function fetchStatusQuiet() {
  try {
    const response = await fetch("/status");
    if (!response.ok) return false;
    const data = await response.json();
    updateStatusIndicator(data);
    return data.ollama_running;
  } catch (err) {
    updateStatusIndicatorOffline("local server offline");
    return false;
  }
}

function updateStatusIndicator(data) {
  if (data.ollama_running && data.model_available) {
    statusDot.className = "status-dot online";
    statusText.className = "status-text online";
    const docCountFormatted = data.documents_indexed.toLocaleString();
    statusText.textContent = `${docCountFormatted} memories · ${data.model}`;
  } else if (!data.ollama_running) {
    statusDot.className = "status-dot offline";
    statusText.className = "status-text offline";
    statusText.textContent = "ollama offline";
  } else if (!data.model_available) {
    statusDot.className = "status-dot offline";
    statusText.className = "status-text offline";
    statusText.textContent = "model missing";
  }
}

function updateStatusIndicatorOffline(msg) {
  statusDot.className = "status-dot offline";
  statusText.className = "status-text offline";
  statusText.textContent = msg;
}

// Ingestion Trigger handler
async function triggerReingest() {
  const syncIcon = reingestBtn.querySelector(".sync-icon");
  const syncText = reingestBtn.querySelector(".sync-text");
  
  syncIcon.classList.add("spinning");
  syncText.textContent = "Syncing...";
  reingestBtn.disabled = true;
  
  try {
    const response = await fetch("/ingest", { method: "POST" });
    if (!response.ok) throw new Error("Sync failed to trigger");
    
    const interval = setInterval(async () => {
      try {
        const res = await fetch("/ingest/status");
        if (res.ok) {
          const data = await res.json();
          if (data.status === "success") {
            clearInterval(interval);
            syncIcon.classList.remove("spinning");
            syncText.textContent = "Sync Notes";
            reingestBtn.disabled = false;
            showToast("Sync completed successfully!", true);
            fetchStatus();
          } else if (data.status === "failed") {
            clearInterval(interval);
            syncIcon.classList.remove("spinning");
            syncText.textContent = "Sync Notes";
            reingestBtn.disabled = false;
            showToast("Sync failed: " + data.error);
          }
        }
      } catch (err) {
        clearInterval(interval);
        syncIcon.classList.remove("spinning");
        syncText.textContent = "Sync Notes";
        reingestBtn.disabled = false;
      }
    }, 3000);
    
  } catch (err) {
    syncIcon.classList.remove("spinning");
    syncText.textContent = "Sync Notes";
    reingestBtn.disabled = false;
    showToast("Sync failed: " + err.message);
  }
}

// Error Console Monitor
async function pollErrorConsole() {
  try {
    const response = await fetch("/errors");
    if (!response.ok) return;
    const errors = await response.json();
    
    consoleErrorCount.textContent = `(${errors.length})`;
    consoleErrorCount.style.color = errors.length > 0 ? "var(--accent-offline)" : "#555";
    
    if (errors.length === 0) {
      consoleLogsList.innerHTML = `<div class="console-no-errors">No errors captured.</div>`;
      return;
    }
    
    consoleLogsList.innerHTML = "";
    errors.forEach(err => {
      const item = document.createElement("div");
      item.className = "console-error-item";
      
      const title = document.createElement("div");
      title.className = "console-error-title";
      title.textContent = `[${err.timestamp}] ${err.error_type} in ${err.path}`;
      
      const trace = document.createElement("pre");
      trace.className = "console-error-trace";
      trace.textContent = err.traceback;
      
      item.appendChild(title);
      item.appendChild(trace);
      consoleLogsList.appendChild(item);
    });
  } catch (err) {
    console.error("Failed to fetch errors:", err);
  }
}

// Export Chat history as clean markdown
function exportThreadMarkdown() {
  if (!activeConversationId) return;
  
  // Find current active conversation title in list
  const activeConvEl = document.querySelector(".conv-item.active .conv-title-text");
  const title = activeConvEl ? activeConvEl.textContent : "Exported Thread";
  
  let markdown = `# ${title}\n\n`;
  
  const turns = conversationContainer.querySelectorAll(".turn-block");
  if (turns.length === 0) {
    showToast("Cannot export empty thread");
    return;
  }
  
  turns.forEach(tEl => {
    const query = tEl.querySelector(".turn-query").textContent.replace("› ", "").trim();
    
    // Check if error turn or normal turn
    const isError = tEl.querySelector(".error-block") !== null;
    let answerText = "";
    
    if (isError) {
      answerText = tEl.querySelector(".error-content").textContent;
    } else {
      const ansCont = tEl.querySelector(".answer-content");
      // For verbatim mode, strip HTML formatting to raw text
      answerText = ansCont.textContent || ansCont.innerText;
    }
    
    markdown += `### Query\n> ${query}\n\n`;
    markdown += `### Answer\n${answerText}\n\n`;
    markdown += `---\n\n`;
  });
  
  navigator.clipboard.writeText(markdown).then(() => {
    showToast("Thread markdown copied to clipboard!", true);
  }).catch(err => {
    showToast("Export failed: " + err.message);
  });
}

// Focus input shortcut
document.addEventListener("keydown", (e) => {
  const isMac = navigator.userAgent.toUpperCase().indexOf('MAC') >= 0;
  const isFocusKey = isMac ? (e.metaKey && e.key.toLowerCase() === 'k') : (e.ctrlKey && e.key.toLowerCase() === 'k');
  
  if (isFocusKey) {
    e.preventDefault();
    searchInput.focus();
    searchInput.select();
  }
});

// Input handling (Debounced Search)
searchInput.addEventListener("input", (e) => {
  const query = e.target.value.trim();
  
  if (searchTimeout) clearTimeout(searchTimeout);
  
  if (!query) {
    clearSearchAndResults(false);
    return;
  }
  
  searchTimeout = setTimeout(() => {
    if (currentMode === 'source') {
      openSourceOffset = 0;
      performOpenSourceSearch(query, false);
    } else {
      performLiveSearch(query);
    }
  }, 200);
});

// Clear screen state
function clearSearchAndResults(clearInput = true) {
  if (clearInput) searchInput.value = "";
  resultsList.innerHTML = "";
  openSourceList.innerHTML = "";
  paginationContainer.style.display = "none";
  activeIndex = -1;
  currentResults = [];
  
  if (activeConversationId) {
    emptyState.style.display = "none";
    liveSearchContainer.style.display = "none";
    openSourceContainer.style.display = "none";
    conversationContainer.style.display = "flex";
    selectConversation(activeConversationId);
  } else {
    emptyState.style.display = "flex";
    liveSearchContainer.style.display = "none";
    openSourceContainer.style.display = "none";
    conversationContainer.style.display = "none";
    conversationContainer.innerHTML = "";
    loadHomeGreeting();
  }
}

// Live Search Preview (hybrid retrieval)
async function performLiveSearch(query) {
  if (currentMode === 'source') return;
  
  emptyState.style.display = "none";
  conversationContainer.style.display = "none";
  liveSearchContainer.style.display = "block";
  conversationActions.style.display = "none";
  
  try {
    const response = await fetch(`/search?q=${encodeURIComponent(query)}&limit=${currentK}`);
    if (!response.ok) throw new Error("Search failed");
    const results = await response.json();
    
    renderResultsGrid(results, query, resultsList);
  } catch (err) {
    console.error(err);
    resultsList.innerHTML = `<div class="no-results">search error</div>`;
  }
}

// Perform Open Source Search (FTS-only with pagination)
async function performOpenSourceSearch(query, append = false) {
  if (!append) {
    openSourceList.innerHTML = `<div class="no-results">searching...</div>`;
    openSourceOffset = 0;
  }
  
  try {
    const response = await fetch(`/search/source?q=${encodeURIComponent(query)}&limit=${openSourceLimit}&offset=${openSourceOffset}&source_group=${openSourceGroup}`);
    if (!response.ok) throw new Error("FTS Search failed");
    const data = await response.json();
    
    if (!append) {
      openSourceList.innerHTML = "";
    }
    
    if (data.results.length === 0 && !append) {
      openSourceList.innerHTML = `<div class="no-results">no matches for "${escapeHtml(query)}"</div>`;
      paginationContainer.style.display = "none";
      return;
    }
    
    renderResultsGrid(data.results, query, openSourceList, append);
    
    openSourceOffset = data.next_offset;
    paginationInfo.textContent = `showing ${openSourceList.children.length} of ${data.total} results`;
    paginationContainer.style.display = data.has_more ? "flex" : "none";
    
  } catch (err) {
    console.error(err);
    openSourceList.innerHTML = `<div class="no-results" style="color: var(--accent-offline)">search error: ${err.message}</div>`;
    paginationContainer.style.display = "none";
  }
}

// Render results into a target container (card grid)
function renderResultsGrid(results, query, targetEl, append = false) {
  if (!append) {
    targetEl.innerHTML = "";
    currentResults = [];
  }
  
  const startIdx = currentResults.length;
  currentResults = currentResults.concat(results);
  
  results.forEach((item, index) => {
    const actualIdx = startIdx + index;
    const cardEl = document.createElement("div");
    cardEl.className = "card";
    cardEl.dataset.index = actualIdx;
    if (item.url) cardEl.dataset.url = item.url;
    
    const topEl = document.createElement("div");
    topEl.className = "card-top";
    
    const titleEl = document.createElement("span");
    titleEl.className = "card-title";
    titleEl.textContent = item.title;
    
    const tagEl = document.createElement("span");
    tagEl.className = `src-tag src-${item.source}`;
    tagEl.textContent = item.source;
    
    topEl.appendChild(titleEl);
    topEl.appendChild(tagEl);
    
    const bodyEl = document.createElement("div");
    bodyEl.className = "card-body";
    bodyEl.innerHTML = item.snippet;
    
    const footerEl = document.createElement("div");
    footerEl.className = "card-footer";
    
    const timeEl = document.createElement("span");
    timeEl.className = "card-time";
    timeEl.textContent = item.timestamp || "";
    
    footerEl.appendChild(timeEl);
    
    cardEl.appendChild(topEl);
    cardEl.appendChild(bodyEl);
    if (item.timestamp) cardEl.appendChild(footerEl);
    
    cardEl.addEventListener("mouseenter", () => {
      setActiveItem(actualIdx, targetEl);
    });
    
    cardEl.addEventListener("click", () => {
      openModal(item);
    });
    
    targetEl.appendChild(cardEl);
  });
}

// Highlight cards
function setActiveItem(index, targetEl = resultsList) {
  const items = targetEl.querySelectorAll(".card");
  if (items.length === 0) return;
  
  if (activeIndex >= 0 && activeIndex < items.length) {
    items[activeIndex].classList.remove("active");
  }
  
  activeIndex = index;
  
  if (activeIndex < 0) activeIndex = items.length - 1;
  if (activeIndex >= items.length) activeIndex = 0;
  
  items[activeIndex].classList.add("active");
  items[activeIndex].scrollIntoView({ block: "nearest" });
}

// Modal handling with pagination
async function openModal(item) {
  currentModalItem = item;
  document.getElementById("modalTitle").textContent = item.title;
  document.getElementById("modalBody").textContent = item.text || item.snippet;
  
  const modal = document.getElementById("modal");
  modal.style.display = "flex";
  
  const openOriginalBtn = document.getElementById("modalOpenOriginal");
  if (item.url) {
    openOriginalBtn.style.opacity = "1";
    openOriginalBtn.style.cursor = "pointer";
    openOriginalBtn.disabled = false;
  } else {
    openOriginalBtn.style.opacity = "0.4";
    openOriginalBtn.style.cursor = "not-allowed";
    openOriginalBtn.disabled = true;
  }

  // Fetch passages (chunks) for breadcrumb navigation
  modalBreadcrumbs.style.display = "none";
  modalChunksList = [];
  modalCurrentIndex = -1;

  const sourceId = item.source_id || (item.metadata && item.metadata.source_id);
  if (sourceId) {
    try {
      const response = await fetch(`/notes/${encodeURIComponent(sourceId)}/chunks`);
      if (response.ok) {
        modalChunksList = await response.json();
        if (modalChunksList.length > 1) {
          // Find matching index in list
          const curId = item.id || item.chunk_id;
          modalCurrentIndex = modalChunksList.findIndex(c => c.id === curId);
          if (modalCurrentIndex === -1) {
            modalCurrentIndex = 0;
          }
          modalBreadcrumbs.style.display = "flex";
          updateModalBreadcrumbsUI();
        }
      }
    } catch (err) {
      console.error(err);
    }
  }
}

function updateModalBreadcrumbsUI() {
  modalBreadcrumbLabel.textContent = `passage ${modalCurrentIndex + 1} of ${modalChunksList.length}`;
  modalPrev.disabled = (modalCurrentIndex === 0);
  modalNext.disabled = (modalCurrentIndex === modalChunksList.length - 1);
  modalPrev.style.opacity = (modalCurrentIndex === 0) ? "0.3" : "1";
  modalNext.style.opacity = (modalCurrentIndex === modalChunksList.length - 1) ? "0.3" : "1";
}

function navigateModalPassage(idx) {
  modalCurrentIndex = idx;
  const targetChunk = modalChunksList[modalCurrentIndex];
  
  document.getElementById("modalBody").textContent = targetChunk.text;
  
  // If the target chunk has a unique URL, update Open Original button
  const openOriginalBtn = document.getElementById("modalOpenOriginal");
  if (targetChunk.url) {
    openOriginalBtn.style.opacity = "1";
    openOriginalBtn.style.cursor = "pointer";
    openOriginalBtn.disabled = false;
  } else {
    openOriginalBtn.style.opacity = "0.4";
    openOriginalBtn.style.cursor = "not-allowed";
    openOriginalBtn.disabled = true;
  }
  
  // Update internal item pointer
  currentModalItem = {
    title: targetChunk.title,
    text: targetChunk.text,
    snippet: targetChunk.text,
    url: targetChunk.url,
    source_id: modalChunksList[0].source_id
  };
  
  updateModalBreadcrumbsUI();
}

function closeModal() {
  document.getElementById("modal").style.display = "none";
  currentModalItem = null;
  searchInput.focus();
}

// Keyboard interactions
document.addEventListener("keydown", (e) => {
  const modal = document.getElementById("modal");
  if (modal.style.display === "flex") {
    if (e.key === "Escape") {
      e.preventDefault();
      closeModal();
    } else if (e.key === "ArrowLeft" && modalCurrentIndex > 0) {
      navigateModalPassage(modalCurrentIndex - 1);
    } else if (e.key === "ArrowRight" && modalCurrentIndex < modalChunksList.length - 1) {
      navigateModalPassage(modalCurrentIndex + 1);
    }
    return;
  }

  if (isStreaming) return;
  
  const targetGrid = currentMode === 'source' ? openSourceList : resultsList;
  
  if (e.key === "ArrowDown") {
    e.preventDefault();
    setActiveItem(activeIndex + 1, targetGrid);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    setActiveItem(activeIndex - 1, targetGrid);
  } else if (e.key === " ") {
    if (document.activeElement !== searchInput && activeIndex >= 0 && activeIndex < currentResults.length) {
      e.preventDefault();
      openModal(currentResults[activeIndex]);
    }
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (document.activeElement === searchInput) {
      if (currentMode !== 'source') {
        askAI();
      }
    } else if (activeIndex >= 0 && activeIndex < currentResults.length) {
      openModal(currentResults[activeIndex]);
    }
  } else if (e.key === "Escape") {
    e.preventDefault();
    clearSearchAndResults(true);
  }
});

// Render a turn (turn object has query, answer, mode, sources)
function renderTurn(turn, isNew = false) {
  const turnId = turn.id || Math.random().toString(36).substring(7);
  
  const turnEl = document.createElement("div");
  turnEl.className = "turn-block";
  turnEl.dataset.id = turnId;
  
  const queryEl = document.createElement("div");
  queryEl.className = "turn-query";
  queryEl.textContent = `› ${turn.query}`;
  
  let blockEl;
  
  if (turn.is_error) {
    blockEl = document.createElement("div");
    blockEl.className = "error-block";
    
    const errHeader = document.createElement("div");
    errHeader.className = "error-header";
    errHeader.textContent = "▸ ERROR";
    
    const errContent = document.createElement("div");
    errContent.className = "error-content";
    errContent.textContent = turn.answer;
    
    blockEl.appendChild(errHeader);
    blockEl.appendChild(errContent);
  } else {
    blockEl = document.createElement("div");
    blockEl.className = "answer-block";
    
    const headerRow = document.createElement("div");
    headerRow.className = "answer-header-row";
    
    const ansHeader = document.createElement("div");
    ansHeader.className = "answer-header";
    ansHeader.textContent = turn.mode === 'verbatim' ? "▸ VERBATIM" : "▸ ANSWER";
    
    // Copy Answer and Retry Actions
    const actionsGroup = document.createElement("div");
    actionsGroup.className = "answer-actions-group";
    
    const copyAnsBtn = document.createElement("button");
    copyAnsBtn.className = "answer-action-icon-btn";
    copyAnsBtn.innerHTML = "📋 copy";
    copyAnsBtn.title = "Copy answer to clipboard";
    copyAnsBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(ansContent.textContent || ansContent.innerText).then(() => {
        copyAnsBtn.innerHTML = "copied!";
        setTimeout(() => copyAnsBtn.innerHTML = "📋 copy", 1500);
      });
    });
    
    const retryBtn = document.createElement("button");
    retryBtn.className = "answer-action-icon-btn";
    retryBtn.innerHTML = "⟳ retry";
    retryBtn.title = "Regenerate AI response";
    retryBtn.addEventListener("click", () => {
      askAI(turn.query, turnId);
    });
    
    actionsGroup.appendChild(copyAnsBtn);
    if (turn.mode === 'ai') {
      actionsGroup.appendChild(retryBtn);
    }
    
    headerRow.appendChild(ansHeader);
    headerRow.appendChild(actionsGroup);
    
    const ansContent = document.createElement("div");
    ansContent.className = "answer-content";
    
    if (turn.mode === 'verbatim') {
      ansContent.innerHTML = turn.answer;
    } else {
      ansContent.textContent = turn.answer;
    }
    
    const ansSources = document.createElement("div");
    ansSources.className = "answer-sources";
    ansSources.style.display = "none";
    
    blockEl.appendChild(headerRow);
    blockEl.appendChild(ansContent);
    blockEl.appendChild(ansSources);
    
    // Thumbs Feedback buttons
    const feedbackContainer = document.createElement("div");
    feedbackContainer.className = "feedback-container";
    
    const thumbsUp = document.createElement("span");
    thumbsUp.className = "thumb-btn";
    thumbsUp.innerHTML = "👍";
    thumbsUp.title = "Good response";
    if (turn.feedback === "thumb_up") thumbsUp.classList.add("active");
    
    const thumbsDown = document.createElement("span");
    thumbsDown.className = "thumb-btn";
    thumbsDown.innerHTML = "👎";
    thumbsDown.title = "Bad response / poor retrieval";
    if (turn.feedback === "thumb_down") thumbsDown.classList.add("active");
    
    async function submitFeedback(fbValue) {
      const isRemoving = (fbValue === "thumb_up" && thumbsUp.classList.contains("active")) ||
                         (fbValue === "thumb_down" && thumbsDown.classList.contains("active"));
      const finalFb = isRemoving ? "" : fbValue;
      
      thumbsUp.classList.toggle("active", finalFb === "thumb_up");
      thumbsDown.classList.toggle("active", finalFb === "thumb_down");
      
      try {
        await fetch(`/turns/${turnId}/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feedback: finalFb })
        });
      } catch (err) {
        console.error("Failed to save feedback:", err);
      }
    }
    
    thumbsUp.addEventListener("click", () => submitFeedback("thumb_up"));
    thumbsDown.addEventListener("click", () => submitFeedback("thumb_down"));
    
    feedbackContainer.appendChild(thumbsUp);
    feedbackContainer.appendChild(thumbsDown);
    blockEl.appendChild(feedbackContainer);
    
    // Manage sources
    const sources = turn.sources || [];
    turnSourcesData[turnId] = sources;
    
    if (sources.length > 0) {
      if (turn.mode === 'ai') {
        const toggleBtn = document.createElement("button");
        toggleBtn.className = "toggle-sources-btn";
        
        const gridEl = document.createElement("div");
        gridEl.className = "turn-card-grid card-grid";
        gridEl.style.display = "none";
        
        const expanded = shownTurnSources[turnId] || false;
        toggleBtn.textContent = expanded ? "[ hide sources ]" : `[ show sources (${sources.length}) ]`;
        gridEl.style.display = expanded ? "grid" : "none";
        
        toggleBtn.addEventListener("click", () => {
          const isCurrentlyShown = gridEl.style.display === "grid";
          gridEl.style.display = isCurrentlyShown ? "none" : "grid";
          toggleBtn.textContent = isCurrentlyShown ? `[ show sources (${sources.length}) ]` : "[ hide sources ]";
          shownTurnSources[turnId] = !isCurrentlyShown;
        });
        
        sources.forEach(src => {
          const pill = document.createElement("span");
          pill.className = `source-pill ${src.source}`;
          pill.textContent = `${src.source} · ${src.created_at || "recent"}`;
          pill.title = src.title || src.source;
          pill.addEventListener("click", () => {
            openModal(src);
          });
          ansSources.appendChild(pill);
        });
        ansSources.style.display = "flex";
        
        renderResultsGrid(sources, "", gridEl);
        
        blockEl.appendChild(toggleBtn);
        blockEl.appendChild(gridEl);
      } else {
        sources.forEach(src => {
          const pill = document.createElement("span");
          pill.className = `source-pill ${src.source}`;
          pill.textContent = `${src.source} · ${src.created_at || "recent"}`;
          pill.title = src.title || src.source;
          pill.addEventListener("click", () => {
            openModal(src);
          });
          ansSources.appendChild(pill);
        });
        ansSources.style.display = "flex";
      }
    }
  }
  
  turnEl.appendChild(queryEl);
  turnEl.appendChild(blockEl);
  
  conversationContainer.appendChild(turnEl);
  
  if (isNew) {
    turnEl.scrollIntoView({ block: "end", behavior: "smooth" });
  }
}

// Trigger RAG Q&A query
async function askAI(forcedQuery = null, targetTurnId = null) {
  const query = forcedQuery !== null ? forcedQuery : searchInput.value.trim();
  if (!query) return;
  
  isStreaming = true;
  if (forcedQuery === null) {
    searchInput.blur();
  }
  
  emptyState.style.display = "none";
  liveSearchContainer.style.display = "none";
  openSourceContainer.style.display = "none";
  conversationContainer.style.display = "flex";
  conversationActions.style.display = "block";
  
  let turnEl, ansContent, ansSources, blockEl, turnId;
  
  if (targetTurnId) {
    turnId = targetTurnId;
    turnEl = conversationContainer.querySelector(`.turn-block[data-id="${targetTurnId}"]`);
    if (turnEl) {
      blockEl = turnEl.querySelector(".answer-block");
      ansContent = turnEl.querySelector(".answer-content");
      ansSources = turnEl.querySelector(".answer-sources");
      
      const oldToggle = turnEl.querySelector(".toggle-sources-btn");
      if (oldToggle) oldToggle.remove();
      const oldGrid = turnEl.querySelector(".turn-card-grid");
      if (oldGrid) oldGrid.remove();
      const oldFeedback = turnEl.querySelector(".feedback-container");
      if (oldFeedback) oldFeedback.remove();
      
      ansContent.innerHTML = `<span style="color: #555">thinking</span><span class="cursor"></span>`;
      ansSources.innerHTML = "";
      ansSources.style.display = "none";
    }
  }
  
  if (!turnEl) {
    turnId = "turn_" + Math.random().toString(36).substring(7);
    turnEl = document.createElement("div");
    turnEl.className = "turn-block";
    turnEl.dataset.id = turnId;
    
    const queryEl = document.createElement("div");
    queryEl.className = "turn-query";
    queryEl.textContent = `› ${query}`;
    
    blockEl = document.createElement("div");
    blockEl.className = "answer-block";
    
    const headerRow = document.createElement("div");
    headerRow.className = "answer-header-row";
    
    const ansHeader = document.createElement("div");
    ansHeader.className = "answer-header";
    ansHeader.textContent = currentMode === 'verbatim' ? "▸ VERBATIM" : "▸ ANSWER";
    
    headerRow.appendChild(ansHeader);
    
    ansContent = document.createElement("div");
    ansContent.className = "answer-content";
    ansContent.innerHTML = `<span style="color: #555">thinking</span><span class="cursor"></span>`;
    
    ansSources = document.createElement("div");
    ansSources.className = "answer-sources";
    ansSources.style.display = "none";
    
    blockEl.appendChild(headerRow);
    blockEl.appendChild(ansContent);
    blockEl.appendChild(ansSources);
    
    turnEl.appendChild(queryEl);
    turnEl.appendChild(blockEl);
    conversationContainer.appendChild(turnEl);
  }
  
  turnEl.scrollIntoView({ block: "end", behavior: "smooth" });

  try {
    const response = await fetch("/query", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        question: query,
        conversation_id: activeConversationId,
        mode: currentMode,
        k: currentK,
        turn_id: turnId.startsWith("stream_") ? null : turnId
      })
    });
    
    if (!response.ok) {
      let errorMsg = "something went wrong (500) — check the terminal for errors";
      if (response.status === 503) {
        const detail = await response.text();
        const cleanedDetail = detail.replace(/"/g, "").trim();
        
        if (cleanedDetail === "ollama_not_running") {
          errorMsg = "ollama isn't running — start it with: ollama serve";
        } else if (cleanedDetail.includes("not_pulled")) {
          errorMsg = "model not found — run: ollama pull llama3.2:3b";
        } else if (cleanedDetail === "ollama_timeout") {
          errorMsg = "ollama timed out — it may be loading the model, try again in 5s";
        }
      }
      throw new Error(errorMsg);
    }
    
    const newConvId = response.headers.get("X-Conversation-Id");
    if (newConvId && !activeConversationId) {
      activeConversationId = newConvId;
      loadSidebar();
    }
    
    ansContent.innerHTML = "";
    const textNode = document.createTextNode("");
    ansContent.appendChild(textNode);
    
    const cursor = document.createElement("span");
    cursor.className = "cursor";
    ansContent.appendChild(cursor);
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let fullText = "";
    let finalSources = [];
    
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      
      fullText += decoder.decode(value, { stream: true });
      
      const sentinelIndex = fullText.indexOf("__SOURCES__");
      if (sentinelIndex !== -1) {
        const answerText = fullText.substring(0, sentinelIndex);
        
        if (currentMode === 'verbatim') {
          ansContent.innerHTML = answerText;
        } else {
          textNode.textContent = answerText.trim();
        }
        
        const sourcesJson = fullText.substring(sentinelIndex + 11);
        try {
          finalSources = JSON.parse(sourcesJson);
          cursor.remove();
          
          ansSources.innerHTML = "";
          finalSources.forEach(src => {
            const pill = document.createElement("span");
            pill.className = `source-pill ${src.source}`;
            pill.textContent = `${src.source} · ${src.created_at || "recent"}`;
            pill.title = src.title || src.source;
            pill.addEventListener("click", () => {
              openModal(src);
            });
            ansSources.appendChild(pill);
          });
          ansSources.style.display = "flex";
          
          // Render Copy / Retry Action buttons dynamically on header row
          const headerRow = blockEl.querySelector(".answer-header-row") || document.createElement("div");
          if (!headerRow.parentNode) {
            headerRow.className = "answer-header-row";
            const oldHeader = blockEl.querySelector(".answer-header");
            blockEl.insertBefore(headerRow, ansContent);
            headerRow.appendChild(oldHeader);
          }
          
          let oldActions = headerRow.querySelector(".answer-actions-group");
          if (oldActions) oldActions.remove();
          
          const actionsGroup = document.createElement("div");
          actionsGroup.className = "answer-actions-group";
          
          const copyAnsBtn = document.createElement("button");
          copyAnsBtn.className = "answer-action-icon-btn";
          copyAnsBtn.innerHTML = "📋 copy";
          copyAnsBtn.title = "Copy answer to clipboard";
          copyAnsBtn.addEventListener("click", () => {
            navigator.clipboard.writeText(ansContent.textContent || ansContent.innerText).then(() => {
              copyAnsBtn.innerHTML = "copied!";
              setTimeout(() => copyAnsBtn.innerHTML = "📋 copy", 1500);
            });
          });
          
          const retryBtn = document.createElement("button");
          retryBtn.className = "answer-action-icon-btn";
          retryBtn.innerHTML = "⟳ retry";
          retryBtn.title = "Regenerate AI response";
          retryBtn.addEventListener("click", () => {
            askAI(query, turnId);
          });
          
          actionsGroup.appendChild(copyAnsBtn);
          if (currentMode === 'ai') {
            actionsGroup.appendChild(retryBtn);
          }
          headerRow.appendChild(actionsGroup);

          // Append Thumbs Feedback
          const feedbackContainer = document.createElement("div");
          feedbackContainer.className = "feedback-container";
          
          const thumbsUp = document.createElement("span");
          thumbsUp.className = "thumb-btn";
          thumbsUp.innerHTML = "👍";
          thumbsUp.title = "Good response";
          
          const thumbsDown = document.createElement("span");
          thumbsDown.className = "thumb-btn";
          thumbsDown.innerHTML = "👎";
          thumbsDown.title = "Bad response / poor retrieval";
          
          async function submitFeedback(fbValue) {
            const isRemoving = (fbValue === "thumb_up" && thumbsUp.classList.contains("active")) ||
                               (fbValue === "thumb_down" && thumbsDown.classList.contains("active"));
            const finalFb = isRemoving ? "" : fbValue;
            
            thumbsUp.classList.toggle("active", finalFb === "thumb_up");
            thumbsDown.classList.toggle("active", finalFb === "thumb_down");
            
            try {
              await fetch(`/turns/${turnId}/feedback`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ feedback: finalFb })
              });
            } catch (err) {
              console.error("Failed to save feedback:", err);
            }
          }
          
          thumbsUp.addEventListener("click", () => submitFeedback("thumb_up"));
          thumbsDown.addEventListener("click", () => submitFeedback("thumb_down"));
          
          feedbackContainer.appendChild(thumbsUp);
          feedbackContainer.appendChild(thumbsDown);
          blockEl.appendChild(feedbackContainer);
          
          // Render source grid collapsible
          if (currentMode === 'ai' && finalSources.length > 0) {
            const toggleBtn = document.createElement("button");
            toggleBtn.className = "toggle-sources-btn";
            toggleBtn.textContent = `[ show sources (${finalSources.length}) ]`;
            
            const gridEl = document.createElement("div");
            gridEl.className = "turn-card-grid card-grid";
            gridEl.style.display = "none";
            
            toggleBtn.addEventListener("click", () => {
              const isCurrentlyShown = gridEl.style.display === "grid";
              gridEl.style.display = isCurrentlyShown ? "none" : "grid";
              toggleBtn.textContent = isCurrentlyShown ? `[ show sources (${finalSources.length}) ]` : "[ hide sources ]";
              shownTurnSources[turnId] = !isCurrentlyShown;
            });
            
            renderResultsGrid(finalSources, "", gridEl);
            
            blockEl.appendChild(toggleBtn);
            blockEl.appendChild(gridEl);
          }
        } catch (e) {
          // incomplete JSON chunk
        }
      } else {
        let cleanText = fullText;
        for (let i = 1; i < 11; i++) {
          if (fullText.endsWith("__SOURCES__".substring(0, i))) {
            cleanText = fullText.substring(0, fullText.length - i);
            break;
          }
        }
        
        if (currentMode === 'verbatim') {
          ansContent.innerHTML = cleanText;
        } else {
          textNode.textContent = cleanText;
        }
      }
      
      turnEl.scrollIntoView({ block: "end", behavior: "smooth" });
    }
    
    loadSidebar();
    pollErrorConsole();
    
  } catch (err) {
    console.error(err);
    pollErrorConsole();
    
    // Render error turn
    blockEl.className = "error-block";
    
    const errHeader = blockEl.querySelector(".answer-header-row") || blockEl.querySelector(".answer-header");
    if (errHeader) {
      if (errHeader.className === "answer-header-row") {
        errHeader.className = "error-header";
        errHeader.innerHTML = "▸ ERROR";
      } else {
        errHeader.className = "error-header";
        errHeader.textContent = "▸ ERROR";
      }
    }
    ansContent.className = "error-content";
    ansContent.textContent = err.message || "local server offline — run: start_app.bat";
    ansSources.remove();
  } finally {
    isStreaming = false;
    if (forcedQuery === null) {
      searchInput.value = "";
    }
    
    setTimeout(() => {
      searchInput.focus();
    }, 100);
  }
}

// Helpers
function escapeHtml(text) {
  const map = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#039;'
  };
  return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}
