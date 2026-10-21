/**
 * app.js — Frontend Client for Karpathy Knowledge Wiki
 * Handles:
 *  - Tab navigation
 *  - Q&A synthesis and keyword search with Azure OpenAI (gpt-5-mini-2)
 *  - Drag-and-drop document upload and real-time ingestion monitoring
 *  - Interactive Wiki knowledge graph reader and wikilink navigation
 *  - SkillOpt diagnostics view
 */

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initStats();
  initQueryTab();
  initIngestionTab();
  initWikiExplorerTab();
  initSkilloptTab();
  initModal();
});

// ── 1. Tab Navigation ─────────────────────────────────────────────────────────

function initTabs() {
  const tabs = document.querySelectorAll('.nav-tab');
  const panels = document.querySelectorAll('.tab-panel');

  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetId = tab.getAttribute('data-tab');
      tabs.forEach(t => t.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));

      tab.classList.add('active');
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) targetPanel.classList.add('active');

      // Refresh data on tab switch
      if (targetId === 'tabWiki') loadWikiPages();
      if (targetId === 'tabSkillopt') loadSkilloptData();
    });
  });
}

// ── 2. Real-Time Stats Loader ─────────────────────────────────────────────────

async function initStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) return;
    const data = await res.json();

    const totalPagesEl = document.getElementById('totalPagesCount');
    const totalDocsEl = document.getElementById('totalDocsCount');
    const modelNameEl = document.getElementById('modelName');
    const diagModelEl = document.getElementById('diagModel');

    if (totalPagesEl) totalPagesEl.textContent = data.total_pages;
    if (totalDocsEl) totalDocsEl.textContent = data.processed_docs;
    if (modelNameEl) modelNameEl.textContent = data.azure_deployment || 'gpt-5-mini-2';
    if (diagModelEl) diagModelEl.textContent = `Azure OpenAI (${data.azure_deployment || 'gpt-5-mini-2'})`;

    const allCount = document.getElementById('typeCountAll');
    const entityCount = document.getElementById('typeCountEntity');
    const conceptCount = document.getElementById('typeCountConcept');
    const themeCount = document.getElementById('typeCountTheme');

    if (allCount) allCount.textContent = data.total_pages;
    if (entityCount) entityCount.textContent = data.page_types?.entity || 0;
    if (conceptCount) conceptCount.textContent = data.page_types?.concept || 0;
    if (themeCount) themeCount.textContent = data.page_types?.theme || 0;
  } catch (err) {
    console.warn('Failed to load stats:', err);
  }
}

// ── 3. Query Tab (Q&A & Synthesis) ────────────────────────────────────────────

function initQueryTab() {
  const queryInput = document.getElementById('queryInput');
  const sendBtn = document.getElementById('sendQueryBtn');
  const answersStream = document.getElementById('answersStream');
  const welcomePlaceholder = document.getElementById('welcomePlaceholder');

  // Suggested chips
  document.querySelectorAll('.chip-query').forEach(chip => {
    chip.addEventListener('click', () => {
      const q = chip.getAttribute('data-q');
      if (queryInput) {
        queryInput.value = q;
        sendQuery();
      }
    });
  });

  if (sendBtn) {
    sendBtn.addEventListener('click', sendQuery);
  }

  if (queryInput) {
    queryInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendQuery();
      }
    });
  }

  async function sendQuery() {
    const q = (queryInput.value || '').trim();
    if (!q) return;

    const mode = document.querySelector('input[name="queryMode"]:checked')?.value || 'ai';

    // Hide welcome
    if (welcomePlaceholder) welcomePlaceholder.style.display = 'none';

    // Disable input while running
    sendBtn.disabled = true;
    const originalBtnHtml = sendBtn.innerHTML;
    sendBtn.innerHTML = `
      <span class="btn-text">Reasoning...</span>
      <span class="status-dot pulsing" style="background:#fff;"></span>
    `;

    // Create placeholder answer card
    const cardId = 'ans_' + Date.now();
    const cardEl = document.createElement('div');
    cardEl.className = 'answer-card glass-panel';
    cardEl.id = cardId;
    cardEl.innerHTML = `
      <div class="answer-header">
        <div class="question-text">
          <span class="question-icon">💬</span>
          <span>${escapeHtml(q)}</span>
        </div>
        <div class="answer-meta">
          <span class="badge-accent">${mode === 'ai' ? 'Reasoning Synthesis' : 'Keyword Search'}</span>
        </div>
      </div>
      <div class="answer-body">
        <p class="log-dim">Searching 265+ wiki pages & synthesizing with Azure gpt-5-mini-2...</p>
      </div>
    `;
    answersStream.prepend(cardEl);
    queryInput.value = '';

    try {
      const res = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, mode: mode })
      });
      const data = await res.json();

      if (data.error) {
        cardEl.querySelector('.answer-body').innerHTML = `
          <div class="log-error">Error: ${escapeHtml(data.error)}</div>
        `;
      } else {
        renderAnswerCard(cardEl, data, q);
      }
    } catch (err) {
      cardEl.querySelector('.answer-body').innerHTML = `
        <div class="log-error">Network request failed: ${escapeHtml(err.message)}</div>
      `;
    } finally {
      sendBtn.disabled = false;
      sendBtn.innerHTML = originalBtnHtml;
    }
  }

  function renderAnswerCard(cardEl, data, queryText) {
    let bodyHtml = '';
    if (data.mode === 'search') {
      bodyHtml = renderSearchResultsHtml(data.results);
    } else {
      const formattedAnswer = formatMarkdownText(data.answer || 'No answer generated.');
      bodyHtml = `<div>${formattedAnswer}</div>`;
    }

    // Render citations / retrieved pages
    let citationsHtml = '';
    const retrieved = data.retrieved || data.results || [];
    if (retrieved.length > 0) {
      const cards = retrieved.map(p => `
        <div class="citation-card" onclick="openWikilinkModal('${escapeHtml(p.title || p.filename.replace('.md',''))}')">
          <div class="citation-title-row">
            <span class="citation-title">${escapeHtml(p.title || p.filename.replace('.md',''))}</span>
            <span class="citation-score">score: ${p.score || 0}</span>
          </div>
          <p class="citation-snippet">${escapeHtml(p.preview || 'No preview available')}</p>
        </div>
      `).join('');

      citationsHtml = `
        <div class="answer-citations">
          <div class="citations-toggle">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/></svg>
            <span>Retrieved Wiki Sources (${retrieved.length})</span>
          </div>
          <div class="citations-grid">
            ${cards}
          </div>
        </div>
      `;
    }

    cardEl.querySelector('.answer-body').innerHTML = bodyHtml + citationsHtml;

    // Attach click handlers to any [[wikilinks]] inside the answer body
    cardEl.querySelectorAll('.wikilink-badge').forEach(badge => {
      badge.addEventListener('click', (e) => {
        e.preventDefault();
        const pageName = badge.getAttribute('data-wiki');
        if (pageName) openWikilinkModal(pageName);
      });
    });
  }

  function renderSearchResultsHtml(results) {
    if (!results || results.length === 0) {
      return '<p class="log-dim">No matching wiki pages found.</p>';
    }
    return `
      <p style="margin-bottom:12px; color:var(--text-muted);">Found <strong>${results.length}</strong> matching pages:</p>
      <div class="citations-grid" style="grid-template-columns:1fr;">
        ${results.map(r => `
          <div class="citation-card" onclick="openWikilinkModal('${escapeHtml(r.title)}')">
            <div class="citation-title-row">
              <span class="citation-title" style="font-size:1rem;">📄 ${escapeHtml(r.title)}</span>
              <span class="citation-score">relevance: ${r.score}</span>
            </div>
            <p class="citation-snippet" style="font-size:0.86rem;">${escapeHtml(r.preview || '')}</p>
            ${r.wikilinks && r.wikilinks.length ? `
              <div style="margin-top:6px; display:flex; gap:6px; flex-wrap:wrap;">
                ${r.wikilinks.slice(0, 5).map(l => `<span class="wikilink-badge" data-wiki="${escapeHtml(l)}">[[${escapeHtml(l)}]]</span>`).join('')}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    `;
  }
}

// ── 4. Ingestion Tab (Drag & Drop & Pipeline) ──────────────────────────────────

function initIngestionTab() {
  const dropZone = document.getElementById('documentDropZone');
  const filePicker = document.getElementById('filePickerInput');
  const selectedSection = document.getElementById('selectedFilesSection');
  const queueList = document.getElementById('filesQueueList');
  const queueCount = document.getElementById('queueCount');
  const clearBtn = document.getElementById('clearQueueBtn');
  const startBtn = document.getElementById('startIngestionBtn');
  const forceCheckbox = document.getElementById('forceReprocessCheckbox');

  const statusBadge = document.getElementById('pipelineStatusBadge');
  const progressFill = document.getElementById('pipelineProgressFill');
  const terminalBody = document.getElementById('terminalLogsBody');
  const clearLogsBtn = document.getElementById('clearLogsBtn');
  const terminalActiveFile = document.getElementById('terminalActiveFile');
  const summaryBanner = document.getElementById('ingestSummaryBanner');
  const summaryText = document.getElementById('summaryText');

  let queuedFiles = [];
  let pollInterval = null;

  // Dropzone click
  dropZone.addEventListener('click', () => filePicker.click());

  // Drag & drop events
  ['dragenter', 'dragover'].forEach(name => {
    dropZone.addEventListener(name, (e) => {
      e.preventDefault();
      dropZone.classList.add('drag-active');
    });
  });

  ['dragleave', 'drop'].forEach(name => {
    dropZone.addEventListener(name, (e) => {
      e.preventDefault();
      dropZone.classList.remove('drag-active');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    const files = Array.from(e.dataTransfer.files);
    addFilesToQueue(files);
  });

  filePicker.addEventListener('change', () => {
    const files = Array.from(filePicker.files);
    addFilesToQueue(files);
    filePicker.value = '';
  });

  clearBtn.addEventListener('click', () => {
    queuedFiles = [];
    updateQueueUi();
  });

  clearLogsBtn.addEventListener('click', () => {
    terminalBody.innerHTML = '<div class="log-entry log-dim">[Console cleared.]</div>';
  });

  function addFilesToQueue(files) {
    const allowed = ['.docx', '.pdf', '.txt', '.md'];
    files.forEach(f => {
      const ext = '.' + f.name.split('.').pop().toLowerCase();
      if (allowed.includes(ext) && !queuedFiles.some(q => q.name === f.name)) {
        queuedFiles.push(f);
      }
    });
    updateQueueUi();
  }

  function updateQueueUi() {
    queueCount.textContent = queuedFiles.length;
    if (queuedFiles.length === 0) {
      selectedSection.style.display = 'none';
      queueList.innerHTML = '';
      return;
    }

    selectedSection.style.display = 'flex';
    queueList.innerHTML = queuedFiles.map((f, idx) => {
      const ext = f.name.split('.').pop().toUpperCase();
      const sizeKb = (f.size / 1024).toFixed(1) + ' KB';
      return `
        <div class="file-queue-item">
          <div class="file-info">
            <span class="file-ext-badge">${ext}</span>
            <span class="file-name-text" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
            <span class="file-size-text">${sizeKb}</span>
          </div>
          <button class="remove-file-btn" data-idx="${idx}" title="Remove file">&times;</button>
        </div>
      `;
    }).join('');

    queueList.querySelectorAll('.remove-file-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.getAttribute('data-idx'));
        queuedFiles.splice(idx, 1);
        updateQueueUi();
      });
    });
  }

  // Start Ingestion
  startBtn.addEventListener('click', async () => {
    if (queuedFiles.length === 0) return;

    startBtn.disabled = true;
    startBtn.innerHTML = `
      <span class="status-dot pulsing" style="background:#fff;"></span>
      <span>Running Ingestion Pipeline...</span>
    `;

    const formData = new FormData();
    queuedFiles.forEach(f => formData.append('files', f));
    formData.append('force', forceCheckbox.checked ? 'true' : 'false');

    try {
      summaryBanner.style.display = 'none';
      setPipelineStatus('running', 'Processing');

      const res = await fetch('/api/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();

      if (data.error) {
        appendLog(`[ERROR] ${data.error}`, 'error');
        setPipelineStatus('error', 'Error');
        startBtn.disabled = false;
        startBtn.innerHTML = '<span>Start Autonomous Ingestion Pipeline</span>';
        return;
      }

      appendLog(`[STAGE] Uploaded ${data.files_count} file(s). Pipeline worker spawned.`, 'stage');
      startPollingIngestStatus();
    } catch (err) {
      appendLog(`[ERROR] Upload failed: ${err.message}`, 'error');
      setPipelineStatus('error', 'Error');
      startBtn.disabled = false;
      startBtn.innerHTML = '<span>Start Autonomous Ingestion Pipeline</span>';
    }
  });

  function startPollingIngestStatus() {
    if (pollInterval) clearInterval(pollInterval);
    const activeTabIndicator = document.getElementById('ingestActiveIndicator');
    if (activeTabIndicator) activeTabIndicator.style.display = 'inline-block';

    pollInterval = setInterval(async () => {
      try {
        const res = await fetch('/api/ingest-status');
        const state = await res.json();

        // Update progress bar
        progressFill.style.width = (state.progress_pct || 0) + '%';
        if (state.current_file) {
          terminalActiveFile.textContent = state.current_file;
        }

        // Render logs
        renderLogs(state.logs || []);

        // Update Stage tracker
        updateStageSteps(state.logs || []);

        if (state.status === 'completed') {
          clearInterval(pollInterval);
          setPipelineStatus('completed', 'Completed');
          if (activeTabIndicator) activeTabIndicator.style.display = 'none';

          startBtn.disabled = false;
          startBtn.innerHTML = '<span>Start Autonomous Ingestion Pipeline</span>';

          // Show summary
          if (state.summary) {
            summaryBanner.style.display = 'flex';
            summaryText.textContent = `Processed ${state.summary.total_documents} document(s) | Updated: ${state.summary.pages_updated} pages | Created: ${state.summary.pages_created} pages`;
          }

          // Refresh stats and pages
          initStats();
          loadWikiPages();
        } else if (state.status === 'error') {
          clearInterval(pollInterval);
          setPipelineStatus('error', 'Failed');
          if (activeTabIndicator) activeTabIndicator.style.display = 'none';
          startBtn.disabled = false;
          startBtn.innerHTML = '<span>Start Autonomous Ingestion Pipeline</span>';
        }
      } catch (err) {
        console.warn('Status poll failed:', err);
      }
    }, 1200);
  }

  function setPipelineStatus(stateClass, label) {
    statusBadge.className = `status-indicator-badge badge-${stateClass}`;
    statusBadge.textContent = label;
  }

  function renderLogs(logs) {
    if (!logs.length) return;
    terminalBody.innerHTML = logs.map(l => {
      let lvlClass = 'log-info';
      if (l.level === 'stage') lvlClass = 'log-stage';
      if (l.level === 'success') lvlClass = 'log-success';
      if (l.level === 'warn') lvlClass = 'log-warn';
      if (l.level === 'error') lvlClass = 'log-error';
      return `<div class="log-entry ${lvlClass}"><span style="color:var(--text-dim);">[${l.time}]</span> ${escapeHtml(l.message)}</div>`;
    }).join('');
    terminalBody.scrollTop = terminalBody.scrollHeight;
  }

  function appendLog(msg, level) {
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = `log-entry log-${level}`;
    entry.innerHTML = `<span style="color:var(--text-dim);">[${time}]</span> ${escapeHtml(msg)}`;
    terminalBody.appendChild(entry);
    terminalBody.scrollTop = terminalBody.scrollHeight;
  }

  function updateStageSteps(logs) {
    const stage1 = document.getElementById('stageStep1');
    const stage2 = document.getElementById('stageStep2');
    const stage3 = document.getElementById('stageStep3');
    const stage4 = document.getElementById('stageStep4');

    const logText = logs.map(l => l.message).join(' ');

    if (logText.includes('[Stage 1]')) stage1.className = 'stage-step active completed';
    if (logText.includes('[Stage 2]')) stage2.className = 'stage-step active completed';
    if (logText.includes('[Stage 3]')) stage3.className = 'stage-step active completed';
    if (logText.includes('[Stage 4]')) stage4.className = 'stage-step active completed';
  }
}

// ── 5. Wiki Explorer Tab ──────────────────────────────────────────────────────

let allWikiPages = [];
let currentFilterType = 'all';

function initWikiExplorerTab() {
  const searchInput = document.getElementById('wikiSearchInput');
  const filterChips = document.querySelectorAll('.filter-chip');
  const copyMdBtn = document.getElementById('copyMarkdownBtn');

  if (searchInput) {
    searchInput.addEventListener('input', () => filterAndRenderWikiPages());
  }

  filterChips.forEach(chip => {
    chip.addEventListener('click', () => {
      filterChips.forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      currentFilterType = chip.getAttribute('data-type');
      filterAndRenderWikiPages();
    });
  });

  if (copyMdBtn) {
    copyMdBtn.addEventListener('click', () => {
      const activeContent = copyMdBtn.getAttribute('data-content');
      if (activeContent) {
        navigator.clipboard.writeText(activeContent);
        copyMdBtn.textContent = 'Copied!';
        setTimeout(() => copyMdBtn.textContent = 'Copy Markdown', 1800);
      }
    });
  }
}

async function loadWikiPages() {
  const listEl = document.getElementById('wikiPagesList');
  if (!listEl) return;
  try {
    const res = await fetch('/api/pages');
    const data = await res.json();
    allWikiPages = data.pages || [];
    filterAndRenderWikiPages();
  } catch (err) {
    listEl.innerHTML = `<div class="log-error">Failed to load pages: ${err.message}</div>`;
  }
}

function filterAndRenderWikiPages() {
  const listEl = document.getElementById('wikiPagesList');
  const query = (document.getElementById('wikiSearchInput')?.value || '').toLowerCase().trim();

  const filtered = allWikiPages.filter(p => {
    if (currentFilterType !== 'all' && p.type !== currentFilterType) return false;
    if (query && !p.title.toLowerCase().includes(query) && !p.preview.toLowerCase().includes(query)) return false;
    return true;
  });

  if (filtered.length === 0) {
    listEl.innerHTML = '<div class="log-dim" style="padding:16px;">No matching pages found.</div>';
    return;
  }

  listEl.innerHTML = filtered.map(p => `
    <div class="wiki-page-item" data-filename="${escapeHtml(p.filename)}" onclick="loadWikiPageReader('${escapeHtml(p.filename)}')">
      <div class="page-item-header">
        <span class="page-item-title">${escapeHtml(p.title)}</span>
        <span class="page-item-badge badge-${p.type}">${p.type}</span>
      </div>
      <p class="page-item-preview">${escapeHtml(p.preview || 'No preview available')}</p>
    </div>
  `).join('');
}

async function loadWikiPageReader(filename) {
  const emptyState = document.getElementById('readerEmptyState');
  const contentWrapper = document.getElementById('readerContentWrapper');
  const titleEl = document.getElementById('readerTitle');
  const metaRow = document.getElementById('readerMetaRow');
  const bodyEl = document.getElementById('readerMarkdownBody');
  const copyBtn = document.getElementById('copyMarkdownBtn');
  const outboundCount = document.getElementById('readerOutboundCount');
  const inboundCount = document.getElementById('readerInboundCount');
  const backlinksList = document.getElementById('readerBacklinksList');

  // Highlight list item
  document.querySelectorAll('.wiki-page-item').forEach(item => {
    item.classList.toggle('active', item.getAttribute('data-filename') === filename);
  });

  try {
    const res = await fetch(`/api/page/${encodeURIComponent(filename)}`);
    const data = await res.json();
    if (data.error) return;

    emptyState.style.display = 'none';
    contentWrapper.style.display = 'flex';

    titleEl.textContent = data.title;
    copyBtn.setAttribute('data-content', data.content);

    outboundCount.textContent = data.wikilinks?.length || 0;
    inboundCount.textContent = data.backlinks?.length || 0;

    metaRow.innerHTML = `
      <span class="badge-subtle">File: wiki/${escapeHtml(data.filename)}</span>
      <span class="badge-accent">${(data.content.length / 1024).toFixed(1)} KB</span>
    `;

    bodyEl.innerHTML = formatMarkdownText(data.content);

    // Attach listeners to [[wikilinks]] inside page
    bodyEl.querySelectorAll('.wikilink-badge').forEach(badge => {
      badge.addEventListener('click', (e) => {
        e.preventDefault();
        const targetPage = badge.getAttribute('data-wiki');
        loadWikiPageReader(targetPage + '.md');
      });
    });

    // Render backlinks
    if (data.backlinks && data.backlinks.length > 0) {
      backlinksList.innerHTML = data.backlinks.map(b => `
        <button class="chip-query" onclick="loadWikiPageReader('${escapeHtml(b)}.md')">${escapeHtml(b)}</button>
      `).join('');
    } else {
      backlinksList.innerHTML = '<span class="log-dim">No incoming backlinks recorded.</span>';
    }

  } catch (err) {
    console.error('Error loading page:', err);
  }
}

// ── 6. SkillOpt Diagnostics Tab ───────────────────────────────────────────────

async function initSkilloptTab() {
  loadSkilloptData();
}

async function loadSkilloptData() {
  const promptPreview = document.getElementById('skillPromptPreview');
  const logsContainer = document.getElementById('skillOptLogsContainer');
  const logCountBadge = document.getElementById('skillOptLogCount');

  try {
    const res = await fetch('/api/skillopt');
    const data = await res.json();

    if (promptPreview) {
      promptPreview.textContent = data.skill_preview || 'No skill prompt available.';
    }

    if (logCountBadge) {
      logCountBadge.textContent = `${data.log_entries_count} runs`;
    }

    if (logsContainer) {
      if (!data.logs || data.logs.length === 0) {
        logsContainer.innerHTML = '<div class="log-dim" style="padding:16px;">No optimization runs found yet. Run <code>python main.py --skillopt</code> to train.</div>';
      } else {
        logsContainer.innerHTML = data.logs.map((log, i) => `
          <div class="skillopt-log-item">
            <div style="display:flex; justify-content:space-between; font-weight:700;">
              <span>Epoch #${log.epoch ?? i + 1}</span>
              <span class="log-success">Score: ${log.score ?? 'N/A'}</span>
            </div>
            <p style="color:var(--text-muted); font-size:0.78rem;">${escapeHtml(log.description || JSON.stringify(log))}</p>
          </div>
        `).join('');
      }
    }
  } catch (err) {
    console.warn('SkillOpt data error:', err);
  }
}

// ── 7. Wikilink Modal Preview ─────────────────────────────────────────────────

function initModal() {
  const backdrop = document.getElementById('wikilinkModalBackdrop');
  const closeBtn = document.getElementById('modalCloseBtn');

  if (closeBtn) {
    closeBtn.addEventListener('click', () => backdrop.style.display = 'none');
  }

  if (backdrop) {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) backdrop.style.display = 'none';
    });
  }
}

async function openWikilinkModal(pageTitle) {
  const backdrop = document.getElementById('wikilinkModalBackdrop');
  const modalTitle = document.getElementById('modalPageTitle');
  const modalBody = document.getElementById('modalPageContent');

  backdrop.style.display = 'flex';
  modalTitle.textContent = pageTitle;
  modalBody.innerHTML = '<div class="log-dim">Loading wiki page...</div>';

  try {
    const filename = pageTitle.endsWith('.md') ? pageTitle : pageTitle + '.md';
    const res = await fetch(`/api/page/${encodeURIComponent(filename)}`);
    const data = await res.json();

    if (data.error) {
      modalBody.innerHTML = `<div class="log-warn">Page "${escapeHtml(pageTitle)}" not yet created in the wiki.</div>`;
      return;
    }

    modalTitle.textContent = data.title;
    modalBody.innerHTML = formatMarkdownText(data.content);

    // Support nested link clicks inside modal
    modalBody.querySelectorAll('.wikilink-badge').forEach(badge => {
      badge.addEventListener('click', (e) => {
        e.preventDefault();
        const subPage = badge.getAttribute('data-wiki');
        openWikilinkModal(subPage);
      });
    });
  } catch (err) {
    modalBody.innerHTML = `<div class="log-error">Failed to load page: ${escapeHtml(err.message)}</div>`;
  }
}

// ── 8. Markdown & Text Formatting Helpers ─────────────────────────────────────

function formatMarkdownText(md) {
  if (!md) return '';

  let html = md;

  // Strip YAML frontmatter
  html = html.replace(/^---[\s\S]*?---\n*/, '');

  // Escape HTML tags to prevent XSS
  html = escapeHtml(html);

  // Headers
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
  html = html.replace(/\*(.*?)\*/gim, '<em>$1</em>');

  // Inline Code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Obsidian [[wikilinks]] -> clickable badges
  html = html.replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, (match, target, alias) => {
    const displayText = alias || target;
    return `<span class="wikilink-badge" data-wiki="${escapeHtml(target)}">[[${escapeHtml(displayText)}]]</span>`;
  });

  // Bullet Lists
  html = html.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/gms, '<ul>$1</ul>');
  html = html.replace(/<\/ul>\s*<ul>/g, '');

  // Paragraphs
  const lines = html.split('\n\n');
  html = lines.map(block => {
    block = block.trim();
    if (!block) return '';
    if (block.startsWith('<h') || block.startsWith('<ul') || block.startsWith('<li')) return block;
    return `<p>${block.replace(/\n/g, '<br>')}</p>`;
  }).join('\n');

  return html;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
