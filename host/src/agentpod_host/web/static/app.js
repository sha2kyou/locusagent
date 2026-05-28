/**
 * 极简 SPA：根据 GWZZ_PAGE 切换 section，调 /api/* 完成数据交互。
 * 包含会话管理（列表分组 / 新建 / 切换 / 加载历史）。
 */
(() => {
  const PAGE = window.GWZZ_PAGE || 'chat';
  const WS_PAGES = new Set(['skills', 'mcp', 'memory']);
  const PAGE_TITLES = { chat: '对话', skills: '技能', mcp: 'MCP', memory: '记忆' };
  const PROMPT_CHIPS = [
    '帮我总结当前项目结构',
    '搜索记忆里的重要信息',
    '写一段 Python 脚本处理 CSV',
    '解释这段代码在做什么',
  ];
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const STATUS_BADGE = {
    running: 'badge-success',
    creating: 'badge-warning',
    paused: 'badge-warning',
    stopped: 'badge-muted',
    absent: 'badge-muted',
    pending: 'badge-warning',
    ready: 'badge-success',
    failed: 'badge-danger',
  };

  // memory 条目的 embedding 状态（与容器状态分开映射，避免吓人）
  const EMBED_BADGE = {
    pending: 'badge-warning',
    ready: 'badge-success',
    failed: 'badge-muted',
  };
  const EMBED_LABEL = {
    pending: '排队中',
    ready: '已索引',
    failed: '仅关键词',
  };

  const parseApiError = (data, status, statusText) => {
    if (data?.error?.message) {
      const err = new Error(data.error.message);
      err.code = data.error.code;
      err.detail = data.error.detail;
      return err;
    }
    if (typeof data?.detail === 'string') {
      return new Error(data.detail);
    }
    if (Array.isArray(data?.detail)) {
      return new Error('request validation failed');
    }
    return new Error(`${status} ${statusText}`);
  };

  const redirectToLogin = () => {
    if (window.location.pathname !== '/') {
      window.location.href = '/';
    }
  };

  const j = async (url, opts = {}) => {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      ...opts,
    });
    if (res.status === 401) {
      redirectToLogin();
      throw new Error('session expired');
    }
    const ct = res.headers.get('content-type') || '';
    const data = ct.includes('json') ? await res.json().catch(() => null) : await res.text();
    if (!res.ok) {
      const err = parseApiError(data, res.status, res.statusText);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  };

  const copy = async (text, btn) => {
    try {
      await navigator.clipboard.writeText(text);
      const old = btn?.textContent;
      if (btn) { btn.textContent = '已复制'; setTimeout(() => (btn.textContent = old), 1200); }
    } catch {
      await uiPrompt('请手动复制以下内容：', { title: '复制', defaultValue: text, confirmText: '关闭' });
    }
  };

  /* ============= Toast & Dialogs ============= */
  let confirmResolve = null;
  let promptResolve = null;
  let pendingSettingsOnboarding = false;
  let statusPollTimer = null;
  let lastMeSnapshot = null;
  let lastFocusedBeforeModal = null;
  let chatStreamAbort = null;
  let stoppingStream = false;

  const MODAL_IDS = ['#apikey-modal', '#delete-account-modal', '#prompt-modal', '#confirm-modal', '#settings-modal'];

  function showToast(message, { type = 'info', duration = 3200 } = {}) {
    const host = $('#toast-host');
    if (!host || !message) return;
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    host.appendChild(el);
    requestAnimationFrame(() => el.classList.add('show'));
    setTimeout(() => {
      el.classList.remove('show');
      setTimeout(() => el.remove(), 220);
    }, duration);
  }

  function isModalOpen(sel) {
    const el = $(sel);
    return el && !el.hidden;
  }

  function syncBodyModalOpen() {
    document.body.classList.toggle('modal-open', MODAL_IDS.some(isModalOpen));
  }

  function focusableIn(root) {
    return Array.from(root.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
    )).filter((el) => el.offsetParent !== null || el === document.activeElement);
  }

  function trapModalFocus(modalSel) {
    const modal = $(modalSel);
    if (!modal || modal.hidden) return;
    const panel = $('.modal-panel', modal);
    if (!panel) return;
    const items = focusableIn(panel);
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const onKey = (e) => {
      if (e.key !== 'Tab' || !isModalOpen(modalSel)) return;
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    panel.dataset.focusTrap = '1';
    panel._focusTrapHandler = onKey;
    document.addEventListener('keydown', onKey);
  }

  function releaseModalFocus(modalSel) {
    const modal = $(modalSel);
    const panel = modal && $('.modal-panel', modal);
    if (panel?._focusTrapHandler) {
      document.removeEventListener('keydown', panel._focusTrapHandler);
      delete panel._focusTrapHandler;
    }
    if (lastFocusedBeforeModal && document.contains(lastFocusedBeforeModal)) {
      lastFocusedBeforeModal.focus();
    }
    lastFocusedBeforeModal = null;
  }

  function openModalFocus(modalSel, focusSel) {
    lastFocusedBeforeModal = document.activeElement;
    syncBodyModalOpen();
    trapModalFocus(modalSel);
    (focusSel ? $(focusSel) : null)?.focus();
  }

  function closeTopModalOnEscape() {
    if (isModalOpen('#apikey-modal')) { hideAgentApiKey(); return true; }
    if (isModalOpen('#delete-account-modal')) { closeDeleteAccountModal(); return true; }
    if (isModalOpen('#prompt-modal')) { closePromptModal(null); return true; }
    if (isModalOpen('#confirm-modal')) { closeConfirmModal(false); return true; }
    if (isModalOpen('#settings-modal')) { closeSettingsModal(); return true; }
    return false;
  }

  function uiConfirm(body, { title = '确认', confirmText = '确定', cancelText = '取消', danger = false } = {}) {
    return new Promise((resolve) => {
      confirmResolve = resolve;
      $('#confirm-modal-title').textContent = title;
      $('#confirm-modal-body').textContent = body;
      $('#confirm-modal-ok').textContent = confirmText;
      $('#confirm-modal-cancel').textContent = cancelText;
      $('#confirm-modal-ok').className = danger ? 'btn-danger' : 'btn-primary';
      $('#confirm-modal').hidden = false;
      openModalFocus('#confirm-modal', '#confirm-modal-ok');
    });
  }

  function closeConfirmModal(result) {
    $('#confirm-modal').hidden = true;
    releaseModalFocus('#confirm-modal');
    syncBodyModalOpen();
    if (confirmResolve) {
      confirmResolve(result);
      confirmResolve = null;
    }
  }

  function uiPrompt(body, { title = '输入', defaultValue = '', confirmText = '确定', cancelText = '取消' } = {}) {
    return new Promise((resolve) => {
      promptResolve = resolve;
      $('#prompt-modal-title').textContent = title;
      $('#prompt-modal-body').textContent = body;
      const input = $('#prompt-modal-input');
      if (input) {
        input.value = defaultValue;
        input.placeholder = '';
      }
      $('#prompt-modal-ok').textContent = confirmText;
      $('#prompt-modal-cancel').textContent = cancelText;
      $('#prompt-modal').hidden = false;
      openModalFocus('#prompt-modal', '#prompt-modal-input');
      input?.select();
    });
  }

  function closePromptModal(result) {
    $('#prompt-modal').hidden = true;
    releaseModalFocus('#prompt-modal');
    syncBodyModalOpen();
    if (promptResolve) {
      promptResolve(result);
      promptResolve = null;
    }
  }

  function maybeContinueOnboarding() {
    if (pendingSettingsOnboarding) {
      pendingSettingsOnboarding = false;
      openSettingsModal();
    }
  }

  function needsStatusPoll(me) {
    if (!me?.llm_configured) return false;
    if (me.provision_status === 'failed') return false;
    if (me.container_status === 'creating') return true;
    if (me.container_status === 'absent' && me.provision_status === 'pending') return true;
    return false;
  }

  function stopStatusPoll() {
    if (statusPollTimer) {
      clearInterval(statusPollTimer);
      statusPollTimer = null;
    }
  }

  function onAgentReady(me) {
    showToast('Agent 已就绪', { type: 'success' });
    if (PAGE !== 'chat') return;
    const tip = readinessTip(me);
    if (tip) return;
    loadSessions();
    const input = $('#chat-input');
    const btn = $('#chat-send');
    if (input) {
      input.disabled = false;
      input.placeholder = '给 Agent 发送消息…';
    }
    if (btn) btn.disabled = false;
    $('#btn-new-chat')?.removeAttribute('disabled');
    const emptyTitle = $('#chat-window .chat-empty h3')?.textContent || '';
    if (emptyTitle.includes('尚未配置') || emptyTitle.includes('未就绪') || emptyTitle.includes('启动中')) {
      showEmpty();
    }
  }

  async function refreshMeStatus() {
    try {
      const me = await j('/api/me');
      const prev = lastMeSnapshot;
      lastMeSnapshot = me;
      renderAgentStatus(me);
      if (prev && needsStatusPoll(prev) && !needsStatusPoll(me) && me.container_status === 'running') {
        onAgentReady(me);
      }
      if (!needsStatusPoll(me)) stopStatusPoll();
      return me;
    } catch {
      return null;
    }
  }

  function startStatusPollIfNeeded(me) {
    lastMeSnapshot = me;
    stopStatusPoll();
    if (!needsStatusPoll(me)) return;
    statusPollTimer = setInterval(refreshMeStatus, 3000);
  }

  function showPage() {
    $$('section.page').forEach((s) => (s.hidden = true));
    const target = document.getElementById(`page-${PAGE}`);
    if (target) target.hidden = false;
    $$('.nav-main a').forEach((a) => a.classList.toggle('active', a.dataset.page === PAGE));
    document.title = `${PAGE_TITLES[PAGE] || 'AgentPod'} · AgentPod`;
  }

  function enhanceCodeBlocks(root = document) {
    root.querySelectorAll('.msg-content pre').forEach((pre) => {
      if (pre.closest('.code-block-wrap')) return;
      const wrap = document.createElement('div');
      wrap.className = 'code-block-wrap';
      pre.parentNode.insertBefore(wrap, pre);
      wrap.appendChild(pre);
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'code-copy-btn';
      btn.textContent = '复制';
      btn.addEventListener('click', () => {
        const code = pre.querySelector('code')?.textContent || pre.textContent || '';
        copy(code, btn);
      });
      wrap.appendChild(btn);
    });
  }

  function badge(text, kind = 'badge-muted') {
    return `<span class="badge ${kind}">${text}</span>`;
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
  }

  function encodeBase64Utf8(input) {
    const bytes = new TextEncoder().encode(String(input || ''));
    let binary = '';
    for (let i = 0; i < bytes.length; i += 1) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }

  function decodeBase64Utf8(input) {
    const binary = atob(String(input || ''));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }

  function splitHtmlRenderBlocks(text) {
    const src = String(text || '');
    const regex = /\[HTML_RENDER\]([\s\S]*?)\[\/HTML_RENDER\]/gi;
    const parts = [];
    let pendingHtml = false;
    let last = 0;
    let m;
    while ((m = regex.exec(src)) !== null) {
      if (m.index > last) parts.push({ type: 'text', value: src.slice(last, m.index) });
      parts.push({ type: 'html', value: String(m[1] || '').trim() });
      last = regex.lastIndex;
    }
    if (last < src.length) {
      const rest = src.slice(last);
      const openIdx = rest.toLowerCase().indexOf('[html_render]');
      if (openIdx >= 0) {
        const visible = rest.slice(0, openIdx);
        if (visible) parts.push({ type: 'text', value: visible });
        pendingHtml = true;
      } else {
        parts.push({ type: 'text', value: rest });
      }
    }
    return { parts, pendingHtml };
  }

  let htmlRenderSeq = 0;
  let htmlRenderResizeBound = false;

  function nextHtmlRenderId() {
    htmlRenderSeq += 1;
    return `html-render-${Date.now()}-${htmlRenderSeq}`;
  }

  function ensureHtmlRenderResizeBridge() {
    if (htmlRenderResizeBound) return;
    htmlRenderResizeBound = true;
    window.addEventListener('message', (event) => {
      const data = event?.data;
      if (!data || data.type !== 'apod_html_render_height') return;
      const id = String(data.id || '');
      const height = Number(data.height || 0);
      if (!id || !Number.isFinite(height) || height <= 0) return;
      let frame = null;
      const direct = document.querySelectorAll('.html-render-frame[data-html-render-id]');
      for (const item of direct) {
        if (item.dataset.htmlRenderId === id) {
          frame = item;
          break;
        }
      }
      if (!frame) return;
      const next = Math.max(24, Math.ceil(height));
      const prev = Number(frame.dataset.htmlRenderHeight || 0);
      if (Math.abs(next - prev) < 2) return;
      frame.dataset.htmlRenderHeight = String(next);
      frame.style.height = `${next}px`;
    });
  }

  function renderHtmlRenderCard(html) {
    const id = nextHtmlRenderId();
    const b64 = encodeBase64Utf8(html || '');
    return `<div class="html-render-card" data-html-render-id="${escapeHtml(id)}" data-html-render-b64="${escapeHtml(b64)}">
      <iframe class="html-render-frame" data-html-render-id="${escapeHtml(id)}" sandbox="allow-scripts" loading="eager" referrerpolicy="no-referrer"></iframe>
    </div>`;
  }

  function renderHeightBridgeScript(renderId) {
    const id = JSON.stringify(String(renderId || ''));
    return `<script>(function(){const ID=${id};let raf=0;let last=0;function calc(){const de=document.documentElement;const b=document.body;return Math.max(de?de.scrollHeight:0,de?de.offsetHeight:0,b?b.scrollHeight:0,b?b.offsetHeight:0);}function post(){last=Date.now();parent.postMessage({type:'apod_html_render_height',id:ID,height:calc()},'*');}function schedule(force){const now=Date.now();if(!force&&now-last<100&&raf)return;if(raf)cancelAnimationFrame(raf);raf=requestAnimationFrame(()=>{raf=0;post();});}window.addEventListener('load',()=>schedule(true));window.addEventListener('resize',()=>schedule(false));if(window.ResizeObserver){const ro=new ResizeObserver(()=>schedule(false));if(document.documentElement)ro.observe(document.documentElement);if(document.body)ro.observe(document.body);}if(window.MutationObserver){const mo=new MutationObserver(()=>schedule(false));mo.observe(document.documentElement||document.body,{subtree:true,childList:true,characterData:true});}if(document.fonts&&document.fonts.ready){document.fonts.ready.then(()=>schedule(true)).catch(()=>{});}schedule(true);})();<\/script>`;
  }

  function normalizeHtmlRenderDoc(html, renderId) {
    const src = String(html || '').trim();
    if (!src) return '';
    const resetCss = '<style id="apod-html-render-reset">html,body{margin:0;padding:0;}*,*::before,*::after{box-sizing:border-box;}</style>';
    const bridge = renderHeightBridgeScript(renderId);
    if (/<head[\s>]/i.test(src)) {
      if (/<\/body>/i.test(src)) {
        return src.replace(/<head([^>]*)>/i, `<head$1>${resetCss}`).replace(/<\/body>/i, `${bridge}</body>`);
      }
      return `${src.replace(/<head([^>]*)>/i, `<head$1>${resetCss}`)}${bridge}`;
    }
    if (/<html[\s>]/i.test(src)) {
      if (/<\/body>/i.test(src)) {
        return src
          .replace(/<html([^>]*)>/i, `<html$1><head>${resetCss}</head>`)
          .replace(/<\/body>/i, `${bridge}</body>`);
      }
      return `${src.replace(/<html([^>]*)>/i, `<html$1><head>${resetCss}</head>`)}${bridge}`;
    }
    return `<!doctype html><html><head>${resetCss}</head><body>${src}${bridge}</body></html>`;
  }

  function hydrateHtmlRenderBlocks(root = document) {
    ensureHtmlRenderResizeBridge();
    root.querySelectorAll('.html-render-card[data-html-render-b64]').forEach((card) => {
      if (card.dataset.htmlRenderMounted === '1') return;
      const renderId = card.dataset.htmlRenderId || '';
      const b64 = card.dataset.htmlRenderB64 || '';
      const frame = card.querySelector('.html-render-frame');
      if (!frame) return;
      try {
        const html = normalizeHtmlRenderDoc(decodeBase64Utf8(b64), renderId);
        frame.style.height = '24px';
        frame.srcdoc = html;
        card.dataset.htmlRenderMounted = '1';
      } catch (e) {
        console.warn('html render failed', e);
        card.classList.add('is-error');
        frame.remove();
        const err = document.createElement('div');
        err.className = 'html-render-error';
        err.textContent = '渲染失败';
        card.appendChild(err);
      }
    });
  }

  function renderMarkdown(text) {
    if (!text) return '';
    if (window.marked && window.DOMPurify) {
      try {
        const html = window.marked.parse(text, { breaks: true, gfm: true });
        return window.DOMPurify.sanitize(html, {
          FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'link', 'meta', 'base', 'form'],
          FORBID_ATTR: ['style'],
        });
      } catch (e) {
        console.warn('markdown render failed', e);
      }
    }
    return escapeHtml(text).replace(/\n/g, '<br>');
  }

  function renderAssistantContent(text, { enableHtmlRender = false, renderHtmlNow = true } = {}) {
    const raw = String(text || '');
    const thinkingParts = [];
    let normal = raw;
    normal = normal.replace(/<thinking>([\s\S]*?)<\/thinking>/gi, (_m, p1) => {
      thinkingParts.push(String(p1 || '').trim());
      return '\n';
    });
    normal = normal.replace(/<think>([\s\S]*?)<\/think>/gi, (_m, p1) => {
      thinkingParts.push(String(p1 || '').trim());
      return '\n';
    });
    let normalHtml = '';
    if (enableHtmlRender) {
      const htmlState = splitHtmlRenderBlocks(normal.trim());
      normalHtml = htmlState.parts
        .map((part) => {
          if (part.type === 'html') {
            if (renderHtmlNow) return renderHtmlRenderCard(part.value);
            return '<div class="html-render-pending">HTML 渲染准备中…</div>';
          }
          return renderMarkdown(part.value);
        })
        .join('');
      if (htmlState.pendingHtml || (!renderHtmlNow && htmlState.parts.some((p) => p.type === 'html'))) {
        normalHtml += '<div class="html-render-pending">HTML 渲染中…</div>';
      }
    } else {
      normalHtml = renderMarkdown(normal.trim());
    }
    const thinkingHtml = thinkingParts
      .filter(Boolean)
      .map((t) => `<details class="thinking-block"><summary>Thinking</summary><div class="thinking-body">${renderMarkdown(t)}</div></details>`)
      .join('');
    return `${normalHtml}${thinkingHtml}`;
  }

  function detectToolKind(name) {
    const n = String(name || '').toLowerCase();
    if (!n) return 'tool';
    if (n.startsWith('skill_') || n.includes('skill')) return 'skill';
    if (n.startsWith('mcp_') || n.includes('mcp')) return 'mcp';
    if (n.includes('memory')) return 'memory';
    return 'tool';
  }

  function toolIcon(kind) {
    if (kind === 'mcp') return '🔌';
    if (kind === 'skill') return '🧩';
    if (kind === 'memory') return '🧠';
    return '⚙';
  }

  function displayToolName(toolName) {
    const raw = String(toolName || '').trim();
    if (!raw) return '工具';
    const key = raw.toLowerCase();
    const map = {
      web_extract: '网页提取',
      web_search: '网页搜索',
      skill_view: '查看技能',
      skill_manage: '管理技能',
      memory: '记忆',
      read_file: '读取文件',
      write_file: '写入文件',
      patch: '修改文件',
      search_files: '搜索文件',
      manage_workspace: '管理工作区',
    };
    return map[key] || raw;
  }

  function formatToolElapsed(ms) {
    const safe = Math.max(0, Math.floor(Number(ms) || 0));
    const totalSec = Math.floor(safe / 1000);
    if (totalSec < 60) {
      if (totalSec < 10) return `${(safe / 1000).toFixed(1)}s`;
      return `${totalSec}s`;
    }
    if (totalSec < 3600) {
      const m = Math.floor(totalSec / 60);
      const s = totalSec % 60;
      return `${m}m ${String(s).padStart(2, '0')}s`;
    }
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    return `${h}h ${String(m).padStart(2, '0')}m`;
  }

  function renderToolEventHtml({ toolName, kind, preview, pending = false, elapsedMs = null }) {
    const icon = toolIcon(kind);
    const namePart = escapeHtml(displayToolName(toolName));
    const full = preview ? String(preview) : '';
    const elapsedPart = elapsedMs != null
      ? `<span class="tool-event-time">${escapeHtml(formatToolElapsed(elapsedMs))}</span>`
      : '';
    let tail = '';
    if (pending && !full) {
      tail = `<span class="tool-event-pending">执行中…</span>${elapsedPart}`;
    } else if (full) {
      const short = full.slice(0, 120);
      if (full.length > 120) {
        tail = `<span class="tool-event-sep">→</span><details class="tool-event-expand"><summary>${escapeHtml(short)}…</summary><pre class="tool-event-full">${escapeHtml(full)}</pre></details>${elapsedPart}`;
      } else {
        tail = `<span class="tool-event-sep">→</span><span class="tool-event-result">${escapeHtml(short)}</span>${elapsedPart}`;
      }
    }
    return `<div class="tool-event-line tool-event-${kind}">
      <span class="tool-event-icon">${icon}</span>
      <span class="tool-event-body">
        <span class="tool-event-call">${namePart}</span>${tail}
      </span>
    </div>`;
  }

  function ensureToolTimerTicker() {
    if (window.__apodToolTimerTicker) return;
    window.__apodToolTimerTicker = setInterval(() => {
      document.querySelectorAll('.msg.tool-event[data-tool-running="1"]').forEach((el) => {
        const startedAt = Number(el.dataset.toolStartedAt || 0);
        if (!startedAt) return;
        const timeEl = el.querySelector('.tool-event-time');
        if (!timeEl) return;
        timeEl.textContent = formatToolElapsed(Date.now() - startedAt);
      });
    }, 500);
  }

  function appendToolBlock({ toolCallId, toolName, kind, preview, pending = false }) {
    const empty = $('#chat-empty');
    if (empty) empty.remove();
    const inner = ensureInner();
    const el = document.createElement('div');
    el.className = 'msg tool-event';
    if (toolCallId) el.dataset.toolCallId = toolCallId;
    el.dataset.toolKind = kind || 'tool';
    const isPending = pending && !preview;
    if (isPending) {
      ensureToolTimerTicker();
      el.dataset.toolRunning = '1';
      el.dataset.toolStartedAt = String(Date.now());
    }
    el.innerHTML = renderToolEventHtml({
      toolName,
      kind: kind || 'tool',
      preview,
      pending: isPending,
      elapsedMs: isPending ? 0 : null,
    });
    inner.appendChild(el);
    const win = $('#chat-window');
    win.scrollTop = win.scrollHeight;
    return el;
  }

  function updateToolBlock(el, { preview, toolName }) {
    if (!el) return;
    const kind = el.dataset.toolKind || 'tool';
    const name = String(toolName || '').trim()
      || String(el.querySelector('.tool-event-call')?.textContent || '').trim();
    const startedAt = Number(el.dataset.toolStartedAt || 0);
    const hasResult = Boolean(preview);
    let elapsedMs = null;
    if (startedAt) {
      elapsedMs = Math.max(0, Date.now() - startedAt);
      if (hasResult) {
        el.dataset.toolRunning = '0';
        el.dataset.toolElapsedMs = String(elapsedMs);
      }
    }
    el.innerHTML = renderToolEventHtml({
      toolName: name,
      kind,
      preview,
      pending: !hasResult && el.dataset.toolRunning === '1',
      elapsedMs,
    });
    const win = $('#chat-window');
    win.scrollTop = win.scrollHeight;
  }

  function stopRunningToolBlocks(reason = '已停止') {
    const preview = String(reason || '').trim() || '已停止';
    document.querySelectorAll('.msg.tool-event[data-tool-running="1"]').forEach((el) => {
      updateToolBlock(el, { preview });
    });
  }

  function parseToolMessage(text, meta) {
    const m0 = Array.isArray(meta) ? meta[0] : null;
    if (m0 && (m0.event_type === 'tool_call' || m0.event_type === 'tool_result')) {
      const kind = m0.tool_kind || detectToolKind(m0.tool_name);
      if (m0.event_type === 'tool_call') {
        return { kind, toolName: m0.tool_name || 'unknown', preview: '' };
      }
      return {
        kind,
        toolName: m0.tool_name || '',
        preview: m0.preview ? String(m0.preview) : '结果已返回',
      };
    }
    let raw = String(text || '').trim();
    let kind = 'tool';
    for (let i = 0; i < 3; i++) {
      const m = raw.match(/^\[(tool|mcp|skill|memory)\]\s*(.*)$/i);
      if (!m) break;
      kind = m[1].toLowerCase();
      raw = (m[2] || '').trim();
    }
    const callMatch = raw.match(/^调用：(.+)$/);
    const resultMatch = raw.match(/^结果：([\s\S]+)$/);
    if (resultMatch) {
      const preview = resultMatch[1];
      return { kind, toolName: '', preview };
    }
    if (callMatch) return { kind, toolName: callMatch[1], preview: '' };
    return { kind, toolName: '', preview: raw };
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const sleepWithSignal = (ms, signal) => new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }
    const timer = setTimeout(() => {
      if (signal) signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      if (signal) signal.removeEventListener('abort', onAbort);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    if (signal) signal.addEventListener('abort', onAbort, { once: true });
  });

  function buildToolCallMeta(messages) {
    const meta = new Map();
    for (const m of messages) {
      if (m.role === 'assistant' && Array.isArray(m.tool_calls)) {
        for (const tc of m.tool_calls) {
          if (tc?.function) {
            const id = tc.id || '';
            const name = tc.function?.name || '';
            if (id) meta.set(id, { name, kind: detectToolKind(name) });
          }
        }
      }
      if (m.role !== 'tool') continue;
      const ev = Array.isArray(m.tool_calls) ? m.tool_calls[0] : null;
      if (ev?.event_type === 'tool_call') {
        const id = ev.tool_call_id || '';
        const name = ev.tool_name || '';
        if (id) meta.set(id, { name, kind: ev.tool_kind || detectToolKind(name) });
      }
    }
    return meta;
  }

  function coalesceToolMessages(messages) {
    const rows = [];
    const callIdx = new Map();
    const callMeta = buildToolCallMeta(messages);
    const findPendingRowIndex = ({ toolName = '', kind = '' } = {}) => {
      const preferredName = String(toolName || '').trim();
      const preferredKind = String(kind || '').trim();
      let fallback = -1;
      for (let i = rows.length - 1; i >= 0; i--) {
        const row = rows[i];
        if (row?.type !== 'tool') continue;
        if (row.preview) continue;
        if (preferredName && String(row.tool_name || '').trim() === preferredName) return i;
        if (preferredKind && String(row.kind || '').trim() === preferredKind) return i;
        if (fallback < 0) fallback = i;
      }
      return fallback;
    };

    for (const m of messages) {
      if (m.role === 'system') continue;
      if (m.role === 'user') {
        rows.push({ type: 'chat', role: 'user', content: m.content, meta: null });
        continue;
      }
      if (m.role === 'assistant') {
        const oaiCalls = Array.isArray(m.tool_calls) && m.tool_calls[0]?.function
          ? m.tool_calls
          : null;
        if (oaiCalls?.length) {
          if (m.content) {
            rows.push({ type: 'chat', role: 'assistant', content: m.content, meta: null });
          }
          for (const tc of oaiCalls) {
            const id = tc.id || '';
            const name = tc.function?.name || '';
            rows.push({
              type: 'tool',
              tool_call_id: id,
              tool_name: name,
              kind: detectToolKind(name),
              preview: '',
            });
            if (id) callIdx.set(id, rows.length - 1);
          }
          continue;
        }
        rows.push({ type: 'chat', role: m.role, content: m.content, meta: m.tool_calls });
        continue;
      }
      if (m.role !== 'tool') continue;

      const meta = Array.isArray(m.tool_calls) ? m.tool_calls[0] : null;
      if (meta?.event_type === 'tool_call') {
        const id = meta.tool_call_id || `orphan-${rows.length}`;
        rows.push({
          type: 'tool',
          tool_call_id: id,
          tool_name: meta.tool_name || '',
          kind: meta.tool_kind || detectToolKind(meta.tool_name),
          preview: '',
        });
        callIdx.set(id, rows.length - 1);
        continue;
      }
      if (meta?.event_type === 'tool_result') {
        const id = meta.tool_call_id || '';
        const preview = meta.preview || String(m.content || '').replace(/^\[tool\]\s*结果：/, '');
        if (id && callIdx.has(id)) {
          rows[callIdx.get(id)].preview = preview;
        } else {
          const info = id ? callMeta.get(id) : null;
          const toolName = meta.tool_name || info?.name || '';
          const kind = meta.tool_kind || info?.kind || detectToolKind(toolName);
          const pendingIdx = findPendingRowIndex({ toolName, kind });
          if (pendingIdx >= 0) {
            rows[pendingIdx].preview = preview || '结果已返回';
            if (!rows[pendingIdx].tool_name && toolName) rows[pendingIdx].tool_name = toolName;
          } else {
            rows.push({
              type: 'tool',
              tool_call_id: id,
              tool_name: toolName,
              kind,
              preview: preview || '结果已返回',
            });
            if (id) callIdx.set(id, rows.length - 1);
          }
        }
        continue;
      }
      const tcId = m.tool_call_id || '';
      const preview = String(m.content || '').slice(0, 200);
      if (tcId && callIdx.has(tcId)) {
        rows[callIdx.get(tcId)].preview = preview;
        continue;
      }
      if (tcId || preview) {
        const info = tcId ? callMeta.get(tcId) : null;
        const toolName = info?.name || '';
        const kind = info?.kind || detectToolKind(toolName);
        const pendingIdx = !tcId ? findPendingRowIndex({ toolName, kind }) : -1;
        if (pendingIdx >= 0) {
          rows[pendingIdx].preview = preview || '结果已返回';
          if (!rows[pendingIdx].tool_name && toolName) rows[pendingIdx].tool_name = toolName;
        } else {
          rows.push({
            type: 'tool',
            tool_call_id: tcId,
            tool_name: toolName,
            kind,
            preview: preview || '结果已返回',
          });
          if (tcId) callIdx.set(tcId, rows.length - 1);
        }
        continue;
      }
      const parsed = parseToolMessage(m.content, m.tool_calls);
      const pendingIdx = parsed.preview ? findPendingRowIndex({ toolName: parsed.toolName, kind: parsed.kind }) : -1;
      if (pendingIdx >= 0) {
        rows[pendingIdx].preview = parsed.preview || '结果已返回';
        if (!rows[pendingIdx].tool_name && parsed.toolName) rows[pendingIdx].tool_name = parsed.toolName;
      } else {
        rows.push({
          type: 'tool',
          tool_name: parsed.toolName,
          kind: parsed.kind,
          preview: parsed.preview,
        });
      }
    }
    return rows;
  }

  function openSettingsModal() {
    const modal = $('#settings-modal');
    if (!modal) return;
    modal.hidden = false;
    loadSettingsForm();
    openModalFocus('#settings-modal', '#btn-close-settings');
  }

  function closeSettingsModal() {
    const modal = $('#settings-modal');
    if (!modal) return;
    modal.hidden = true;
    releaseModalFocus('#settings-modal');
    syncBodyModalOpen();
  }

  function agentStatusMeta(me) {
    if (!me) return { label: '未就绪', hint: '正在获取 Agent 状态', kind: 'muted', pulse: false };
    if (me.provision_status === 'failed') {
      return { label: '未就绪', hint: '初始化失败，请检查设置后重试', kind: 'danger', pulse: false, openSettings: true };
    }
    const cs = me.container_status;
    if (cs === 'creating') {
      return { label: '未就绪', hint: '启动中，通常需要 30~60 秒', kind: 'warning', pulse: true };
    }
    if (cs === 'running') {
      return { label: '已就绪', hint: '可以开始对话', kind: 'success', pulse: false };
    }
    if (cs === 'paused') {
      return { label: '未就绪', hint: '已暂停，发送消息时将自动恢复', kind: 'warning', pulse: false };
    }
    if (cs === 'stopped') {
      return { label: '未就绪', hint: '已停止，发送消息时将自动启动', kind: 'muted', pulse: false };
    }
    if (!me.llm_configured) {
      return { label: '未就绪', hint: '请先配置 LLM', kind: 'muted', pulse: false, openSettings: true };
    }
    return { label: '未就绪', hint: 'Agent 暂不可用', kind: 'muted', pulse: false, openSettings: true };
  }

  function renderAgentStatus(me) {
    const el = $('#agent-status');
    if (!el) return;
    const meta = agentStatusMeta(me);
    el.className = `agent-status is-${meta.kind}${meta.pulse ? ' is-pulse' : ''}${meta.openSettings ? ' is-clickable' : ''}`;
    el.title = `${meta.label} · ${meta.hint}`;
    el.setAttribute('aria-label', `${meta.label}：${meta.hint}`);
    const label = $('.agent-status-label', el);
    if (label) label.textContent = meta.label;
    if (meta.openSettings) el.dataset.openSettings = '1';
    else delete el.dataset.openSettings;
    el.hidden = false;

    const menuStatus = $('#user-menu-status');
    if (menuStatus) {
      menuStatus.textContent = `${meta.label} · ${meta.hint}`;
    }
  }

  function setupAgentStatus() {
    const el = $('#agent-status');
    if (!el) return;
    el.addEventListener('click', () => {
      if (el.dataset.openSettings) openSettingsModal();
    });
  }

  function userAvatarHtml(me) {
    const initial = escapeHtml((me.username || '?').charAt(0).toUpperCase());
    let avatarUrl = '';
    try {
      const parsed = new URL(String(me.avatar_url || ''), window.location.origin);
      if (parsed.protocol === 'https:') avatarUrl = parsed.href;
    } catch {}
    if (avatarUrl) {
      return `<img src="${escapeHtml(avatarUrl)}" alt="" class="user-avatar-img" />`;
    }
    return `<span class="user-avatar-fallback">${initial}</span>`;
  }

  function bindAvatarFallback(root) {
    root.querySelectorAll('.user-avatar-img').forEach((img) => {
      img.addEventListener('error', () => {
        const span = document.createElement('span');
        span.className = 'user-avatar-fallback';
        span.textContent = (lastMeSnapshot?.username || '?').charAt(0).toUpperCase();
        img.replaceWith(span);
      }, { once: true });
    });
  }

  async function loadUser() {
    try {
      const me = await j('/api/me');
      lastMeSnapshot = me;
      cachedUsername = me.username || '';
      const avatarSlot = $('#user-avatar-slot');
      const meta = $('#user-meta');
      if (avatarSlot) {
        avatarSlot.innerHTML = userAvatarHtml(me);
        bindAvatarFallback(avatarSlot);
      }
      if (meta) {
        const uidEl = $('.uid', meta);
        const unameEl = $('.uname', meta);
        if (uidEl) uidEl.textContent = `#${me.id}`;
        if (unameEl) unameEl.textContent = me.username || '';
      }
      renderAgentStatus(me);
      return me;
    } catch (err) {
      console.error('loadUser failed', err);
      return null;
    }
  }

  async function hideAgentApiKey() {
    const modal = $('#apikey-modal');
    const code = $('#apikey-flash-value');
    if (!modal) return;
    modal.hidden = true;
    if (code) code.textContent = '';
    releaseModalFocus('#apikey-modal');
    syncBodyModalOpen();
    maybeContinueOnboarding();
  }

  async function showAgentApiKey(apiKey) {
    if (!apiKey || typeof apiKey !== 'string') return;
    const modal = $('#apikey-modal');
    const code = $('#apikey-flash-value');
    const copyBtn = $('#copy-apikey');
    if (!modal || !code) return;
    code.textContent = apiKey;
    modal.hidden = false;
    if (copyBtn) {
      copyBtn.onclick = () => copy(apiKey, copyBtn);
    }
    openModalFocus('#apikey-modal', '#copy-apikey');
  }

  function closeUserMenu() {
    const dd = $('#user-menu-dropdown');
    const btn = $('#btn-user-menu');
    if (dd) dd.hidden = true;
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function toggleUserMenu() {
    const dd = $('#user-menu-dropdown');
    const btn = $('#btn-user-menu');
    if (!dd || !btn) return;
    const open = dd.hidden;
    dd.hidden = !open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) {
      $$('.user-menu-item', dd)[0]?.focus();
    }
  }

  function setupUserMenu() {
    $('#btn-user-menu')?.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleUserMenu();
    });
    $$('.js-open-settings-menu').forEach((btn) => {
      btn.addEventListener('click', () => {
        closeUserMenu();
        openSettingsModal();
      });
    });
    document.addEventListener('click', (e) => {
      if (!e.target.closest('#user-menu')) closeUserMenu();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeUserMenu();
    });
  }

  function setupNetworkStatus() {
    const notify = () => {
      if (!navigator.onLine) {
        showToast('网络已断开', { type: 'error', duration: 5000 });
      } else {
        showToast('网络已恢复', { type: 'success' });
      }
    };
    window.addEventListener('offline', notify);
    window.addEventListener('online', notify);
  }

  function isMobileViewport() {
    return window.matchMedia('(max-width: 768px)').matches;
  }

  function openMobileChatSidebar() {
    if (!isMobileViewport()) return;
    document.documentElement.classList.add('apod-chat-sidebar-open');
    const backdrop = $('#chat-sidebar-backdrop');
    if (backdrop) {
      backdrop.hidden = false;
      backdrop.setAttribute('aria-hidden', 'false');
    }
  }

  function closeMobileChatSidebar() {
    document.documentElement.classList.remove('apod-chat-sidebar-open');
    const backdrop = $('#chat-sidebar-backdrop');
    if (backdrop) {
      backdrop.hidden = true;
      backdrop.setAttribute('aria-hidden', 'true');
    }
  }

  function setupGlobalShortcuts() {
    document.addEventListener('keydown', (e) => {
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.target.matches('input, textarea, select') && e.key !== 'k') return;
      if (e.key === 'n' && PAGE === 'chat') {
        e.preventDefault();
        newSession();
      }
      if (e.key === 'k' && PAGE === 'chat') {
        e.preventDefault();
        const search = $('#session-search');
        if (search) {
          openMobileChatSidebar();
          search.focus();
          search.select();
        }
      }
    });
  }

  function setupModals() {
    $('#dismiss-apikey')?.addEventListener('click', () => { hideAgentApiKey(); });
    $('.modal-backdrop', $('#apikey-modal'))?.addEventListener('click', () => { hideAgentApiKey(); });

    $('#btn-close-settings')?.addEventListener('click', () => { closeSettingsModal(); });
    $('.modal-backdrop', $('#settings-modal'))?.addEventListener('click', () => { closeSettingsModal(); });

    $('#btn-open-delete-account')?.addEventListener('click', () => { openDeleteAccountModal(); });
    $('#delete-account-cancel')?.addEventListener('click', () => { closeDeleteAccountModal(); });
    $('.modal-backdrop', $('#delete-account-modal'))?.addEventListener('click', () => { closeDeleteAccountModal(); });
    $('#delete-account-submit')?.addEventListener('click', () => { submitDeleteAccount(); });
    $('#delete-account-copy-username')?.addEventListener('click', () => {
      if (cachedUsername) copy(cachedUsername, $('#delete-account-copy-username'));
    });

    $('#confirm-modal-ok')?.addEventListener('click', () => { closeConfirmModal(true); });
    $('#confirm-modal-cancel')?.addEventListener('click', () => { closeConfirmModal(false); });
    $('.modal-backdrop', $('#confirm-modal'))?.addEventListener('click', () => { closeConfirmModal(false); });

    $('#prompt-modal-ok')?.addEventListener('click', () => {
      closePromptModal($('#prompt-modal-input')?.value ?? '');
    });
    $('#prompt-modal-cancel')?.addEventListener('click', () => { closePromptModal(null); });
    $('.modal-backdrop', $('#prompt-modal'))?.addEventListener('click', () => { closePromptModal(null); });
    $('#prompt-modal-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        closePromptModal($('#prompt-modal-input')?.value ?? '');
      }
    });

    document.addEventListener('click', (e) => {
      const trigger = e.target.closest('.js-open-settings');
      if (trigger) {
        e.preventDefault();
        openSettingsModal();
      }
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (closeTopModalOnEscape()) return;
      }
    });

    $('#chat-sidebar-backdrop')?.addEventListener('click', () => closeMobileChatSidebar());
  }

  function openDeleteAccountModal() {
    const err = $('#delete-account-error');
    const input = $('#delete-account-confirm-input');
    const nameEl = $('#delete-account-username-display');
    if (err) { err.hidden = true; err.textContent = ''; }
    if (input) input.value = '';
    if (nameEl) nameEl.textContent = cachedUsername || '—';
    $('#delete-account-modal').hidden = false;
    openModalFocus('#delete-account-modal', '#delete-account-confirm-input');
  }

  function closeDeleteAccountModal() {
    $('#delete-account-modal').hidden = true;
    releaseModalFocus('#delete-account-modal');
    syncBodyModalOpen();
  }

  async function submitDeleteAccount() {
    const btn = $('#delete-account-submit');
    const errEl = $('#delete-account-error');
    const input = $('#delete-account-confirm-input');
    if (!btn || !input) return;
    if (!cachedUsername) {
      try {
        const me = await j('/api/me');
        cachedUsername = me.username || '';
      } catch {
        showToast('无法获取用户信息，请刷新后重试', { type: 'error' });
        return;
      }
    }
    const typed = input.value.trim();
    if (typed !== cachedUsername) {
      if (errEl) {
        errEl.textContent = '用户名不匹配';
        errEl.hidden = false;
      }
      return;
    }
    btn.disabled = true;
    if (errEl) errEl.hidden = true;
    try {
      await j('/api/me', {
        method: 'DELETE',
        body: JSON.stringify({ confirm_username: typed }),
      });
      window.location.href = '/';
    } catch (err) {
      btn.disabled = false;
      if (errEl) {
        errEl.textContent = `删除失败：${err.message}`;
        errEl.hidden = false;
      } else {
        showToast(`删除失败：${err.message}`, { type: 'error' });
      }
    }
  }

  async function maybeShowApiKeyFlash() {
    try {
      const r = await j('/api/me/api-key/flash');
      if (r.api_key) {
        await showAgentApiKey(r.api_key);
        return true;
      }
    } catch {}
    return false;
  }

  function updateAgentApiKeyStatus(me) {
    const status = $('#agent-apikey-status');
    if (!status) return;
    if (me?.agent_api_key_configured) {
      status.textContent = '已签发';
      status.className = 'status-text success';
    } else {
      status.textContent = '未签发';
      status.className = 'status-text';
    }
  }

  let cachedUsername = '';
  let llmFormBaseline = null;

  function snapshotLlmForm(f, configured) {
    return {
      base_url: f.base_url.value.trim(),
      model: f.model.value.trim(),
      configured: !!configured,
    };
  }

  function llmFormDirty(f) {
    if (!llmFormBaseline) return false;
    const key = f.api_key.value.trim();
    if (!llmFormBaseline.configured) {
      return !!(f.base_url.value.trim() && f.model.value.trim() && key.length >= 8);
    }
    if (key) return true;
    return f.base_url.value.trim() !== llmFormBaseline.base_url
      || f.model.value.trim() !== llmFormBaseline.model;
  }

  function syncLlmSaveBtn() {
    const f = $('#llm-form');
    const btn = $('#llm-save-btn');
    if (!f || !btn) return;
    btn.disabled = !llmFormDirty(f);
  }

  async function loadSettingsForm() {
    let me = null;
    try {
      me = await j('/api/me');
      cachedUsername = me.username || '';
      updateAgentApiKeyStatus(me);
    } catch {}

    try {
      const cfg = await j('/api/settings/llm');
      const f = $('#llm-form');
      if (!f) return;
      if (cfg.base_url) f.base_url.value = cfg.base_url;
      if (cfg.model) f.model.value = cfg.model;
      f.api_key.value = '';
      llmFormBaseline = snapshotLlmForm(f, cfg.configured);
      const status = $('#llm-status');
      if (cfg.configured) {
        f.api_key.value = '';
        f.api_key.placeholder = '留空则不修改';
        f.api_key.removeAttribute('required');
        if (status) {
          status.textContent = '已配置';
          status.className = 'status-text success';
        }
      } else {
        f.api_key.placeholder = 'sk-...';
        f.api_key.setAttribute('required', '');
        if (status) {
          status.textContent = '';
          status.className = 'status-text';
        }
      }
      syncLlmSaveBtn();
    } catch {}
  }

  function setupSettings() {
    const f = $('#llm-form');
    if (!f) return;

    const onLlmInput = () => syncLlmSaveBtn();
    f.base_url.addEventListener('input', onLlmInput);
    f.model.addEventListener('input', onLlmInput);
    f.api_key.addEventListener('input', onLlmInput);

    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      const status = $('#llm-status');
      status.className = 'status-text';
      status.textContent = '保存中…';
      try {
        const body = {
          base_url: f.base_url.value,
          model: f.model.value,
        };
        const key = f.api_key.value.trim();
        if (key) body.api_key = key;
        const r = await j('/api/settings/llm', { method: 'PUT', body: JSON.stringify(body) });
        const msgs = {
          none: '已保存',
          starting: '已保存，Agent 初始化中（约 30~60 秒）',
          applying: '已保存，正在应用新配置…',
        };
        const msg = msgs[r.provision_action] || '已保存';
        status.textContent = msg;
        status.className = 'status-text success';
        showToast(msg, { type: 'success' });
        f.api_key.value = '';
        f.api_key.placeholder = '留空则不修改';
        f.api_key.removeAttribute('required');
        llmFormBaseline = snapshotLlmForm(f, true);
        syncLlmSaveBtn();
        pendingSettingsOnboarding = false;
        try {
          const me = await j('/api/me');
          renderAgentStatus(me);
          startStatusPollIfNeeded(me);
        } catch {}
      } catch (err) {
        status.textContent = `失败：${err.message}`;
        status.className = 'status-text error';
        showToast(`保存失败：${err.message}`, { type: 'error' });
      }
    });

    $('#rotate-apikey')?.addEventListener('click', async () => {
      const ok = await uiConfirm('旧的 API Key 将立即失效，确定重置？', {
        title: '重置外部 API Key',
        danger: true,
        confirmText: '重置',
      });
      if (!ok) return;
      try {
        const r = await j('/api/me/api-key/rotate', { method: 'POST', body: '{}' });
        await showAgentApiKey(r.api_key);
        const status = $('#agent-apikey-status');
        if (status) {
          status.textContent = '已签发（新 Key 见弹窗）';
          status.className = 'status-text success';
        }
      } catch (err) {
        showToast(`重置失败：${err.message}`, { type: 'error' });
      }
    });
  }

  /* ============= Chat with Sessions ============= */
  const ChatState = {
    sessions: [],
    currentId: null,
    activeRunPollId: 0,
    sessionQuery: '',
  };
  let setChatStreamingUi = () => {};

  function abortChatStream() {
    chatStreamAbort?.abort();
    stopRunningToolBlocks('已停止');
    chatStreamAbort = null;
    stoppingStream = false;
    setChatStreamingUi(false);
  }

  function messagesSnapshotKey(messages) {
    if (!messages?.length) return '0';
    const last = messages[messages.length - 1];
    return `${messages.length}:${last.id || ''}:${(last.content || '').length}`;
  }

  function renderSessionMessages(messages) {
    clearChatWindow();
    let visible = 0;
    coalesceToolMessages(messages).forEach((row) => {
      if (row.type === 'tool') {
        appendToolBlock({
          toolCallId: row.tool_call_id,
          toolName: row.tool_name,
          kind: row.kind,
          preview: row.preview,
          pending: !row.preview,
        });
        visible += 1;
        return;
      }
      appendMessage(row.role, row.content, { meta: row.meta });
      visible += 1;
    });
    return visible;
  }

  async function fetchSessionMessages(sessionId) {
    const r = await j(`/api/workspace/sessions/${sessionId}`);
    return r.items || [];
  }

  async function pollActiveRun(sessionId) {
    const pollId = ++ChatState.activeRunPollId;
    let lastKey = null;
    try {
      while (ChatState.currentId === sessionId && pollId === ChatState.activeRunPollId) {
        await sleep(2000);
        if (ChatState.currentId !== sessionId || pollId !== ChatState.activeRunPollId) break;
        let active;
        try {
          active = await j(`/api/workspace/sessions/${sessionId}/active-run`);
        } catch {
          break;
        }
        if (!active.run || active.run.status !== 'running') break;
        setChatStreamingUi(true);
        const messages = await fetchSessionMessages(sessionId);
        const key = messagesSnapshotKey(messages);
        if (key !== lastKey) {
          lastKey = key;
          const visible = renderSessionMessages(messages);
          $('#chat-meta').textContent = `${visible} 条消息 · 生成中…`;
        }
      }
      if (ChatState.currentId === sessionId && pollId === ChatState.activeRunPollId) {
        const messages = await fetchSessionMessages(sessionId);
        const key = messagesSnapshotKey(messages);
        if (key !== lastKey) {
          const visible = renderSessionMessages(messages);
          $('#chat-meta').textContent = `${visible} 条消息`;
        } else {
          const meta = $('#chat-meta').textContent || '';
          if (meta.includes('生成中')) {
            $('#chat-meta').textContent = meta.replace(/\s*·\s*生成中…$/, '');
          }
        }
        setChatStreamingUi(false);
      }
    } catch (err) {
      console.warn('pollActiveRun failed', err);
      setChatStreamingUi(false);
    }
  }

  function groupSessionsByTime(sessions) {
    const now = Date.now();
    const day = 86400000;
    const todayStart = new Date(); todayStart.setHours(0, 0, 0, 0);
    const yesterdayStart = todayStart.getTime() - day;
    const week = todayStart.getTime() - 7 * day;
    const month = todayStart.getTime() - 30 * day;

    const groups = { '今天': [], '昨天': [], '过去 7 天': [], '过去 30 天': [], '更早': [] };
    for (const s of sessions) {
      const ts = Date.parse(s.updated_at || s.created_at || '') || 0;
      if (ts >= todayStart.getTime()) groups['今天'].push(s);
      else if (ts >= yesterdayStart) groups['昨天'].push(s);
      else if (ts >= week) groups['过去 7 天'].push(s);
      else if (ts >= month) groups['过去 30 天'].push(s);
      else groups['更早'].push(s);
    }
    return groups;
  }

  async function loadSessions() {
    try {
      const r = await j('/api/workspace/sessions');
      const sorted = (r.items || []).slice().sort((a, b) => {
        const ta = Date.parse(a.updated_at || a.created_at || '') || 0;
        const tb = Date.parse(b.updated_at || b.created_at || '') || 0;
        return tb - ta;
      });
      ChatState.sessions = sorted;
      renderSessionList();
    } catch (err) {
      $('#session-list').innerHTML = `<div class="session-empty">${err.status === 503 ? 'Agent 未就绪<br><button type="button" class="btn-link js-open-settings">打开设置</button>' : escapeHtml(err.message)}</div>`;
    }
  }

  function upsertSessionPreview(sessionId, title = '新对话') {
    if (!sessionId) return;
    const now = new Date().toISOString();
    const idx = ChatState.sessions.findIndex((s) => s.id === sessionId);
    if (idx >= 0) {
      ChatState.sessions[idx] = {
        ...ChatState.sessions[idx],
        title: ChatState.sessions[idx].title || title,
        updated_at: now,
      };
    } else {
      ChatState.sessions.unshift({
        id: sessionId,
        title,
        status: 'running',
        total_tokens: 0,
        created_at: now,
        updated_at: now,
      });
    }
    ChatState.sessions.sort((a, b) => {
      const ta = Date.parse(a.updated_at || a.created_at || '') || 0;
      const tb = Date.parse(b.updated_at || b.created_at || '') || 0;
      return tb - ta;
    });
    renderSessionList();
  }

  async function deleteSession(sessionId) {
    await j(`/api/workspace/sessions/${sessionId}`, { method: 'DELETE' });
    ChatState.sessions = ChatState.sessions.filter((s) => s.id !== sessionId);
    if (ChatState.currentId === sessionId) {
      newSession();
    } else {
      renderSessionList();
    }
  }

  function renderSessionList() {
    const ul = $('#session-list');
    const q = ChatState.sessionQuery.trim().toLowerCase();
    const sessions = q
      ? ChatState.sessions.filter((s) => String(s.title || '新对话').toLowerCase().includes(q))
      : ChatState.sessions;
    if (!sessions.length) {
      ul.innerHTML = q
        ? '<div class="session-empty">无匹配会话</div>'
        : '<div class="session-empty">还没有会话<br>点左上角"新对话"开始</div>';
      return;
    }
    const groups = groupSessionsByTime(sessions);
    let html = '';
    for (const [label, items] of Object.entries(groups)) {
      if (!items.length) continue;
      html += `<div class="session-group-label">${label}</div>`;
      for (const s of items) {
        const active = s.id === ChatState.currentId ? 'active' : '';
        html += `<li class="session-item ${active}" data-id="${s.id}">
          <span class="session-title">${escapeHtml(s.title || '新对话')}</span>
          <button class="session-delete" data-id="${s.id}" title="删除会话" aria-label="删除会话">×</button>
        </li>`;
      }
    }
    ul.innerHTML = html;
    $$('.session-item').forEach((li) => {
      li.addEventListener('click', () => switchSession(li.dataset.id));
    });
    $$('.session-delete').forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const sid = btn.dataset.id;
        if (!sid) return;
        const ok = await uiConfirm('删除后不可恢复，确定删除该会话？', {
          title: '删除会话',
          danger: true,
          confirmText: '删除',
        });
        if (!ok) return;
        btn.disabled = true;
        try {
          await deleteSession(sid);
        } catch (err) {
          showToast(`删除失败：${err.message}`, { type: 'error' });
          btn.disabled = false;
        }
      });
    });
  }

  function clearChatWindow() {
    $('#chat-window').innerHTML = '<div class="chat-window-inner"></div>';
  }

  function ensureInner() {
    let inner = $('.chat-window-inner');
    if (!inner) {
      const win = $('#chat-window');
      win.innerHTML = '';
      inner = document.createElement('div');
      inner.className = 'chat-window-inner';
      win.appendChild(inner);
    }
    return inner;
  }

  function appendMessage(role, content, opts = {}) {
    const empty = $('#chat-empty');
    if (empty) empty.remove();
    const inner = ensureInner();

    const el = document.createElement('div');
    el.className = `msg ${role}`;
    if (role === 'user') {
      el.innerHTML = `<div class="msg-content">${escapeHtml(content)}</div>`;
    } else if (role === 'assistant') {
      const body = opts.loading ? '' : renderAssistantContent(content || '', { enableHtmlRender: true });
      el.innerHTML = `
        <div class="msg-row">
          <div class="msg-avatar">G</div>
          <div class="msg-content${opts.loading ? ' msg-loading' : ''}">${body}</div>
        </div>
      `;
    } else {
      const parsed = parseToolMessage(content, opts.meta);
      return appendToolBlock({
        toolName: parsed.toolName,
        kind: parsed.kind,
        preview: parsed.preview,
      });
    }

    inner.appendChild(el);
    if (role === 'assistant' && !opts.loading) {
      hydrateHtmlRenderBlocks(el);
      enhanceCodeBlocks(el);
    }
    const win = $('#chat-window');
    win.scrollTop = win.scrollHeight;
    return el;
  }

  function setChatTitle(title) {
    $('#chat-title').textContent = title || '新对话';
  }

  function isDefaultSessionTitle(title) {
    const t = String(title || '').trim();
    return !t || t === '新对话';
  }

  async function waitForGeneratedSessionTitle(sessionId, { attempts = 30, intervalMs = 2000 } = {}) {
    if (!sessionId) return;
    for (let i = 0; i < attempts; i += 1) {
      await sleep(intervalMs);
      await loadSessions();
      const session = ChatState.sessions.find((s) => s.id === sessionId);
      if (!session) return;
      if (!isDefaultSessionTitle(session.title)) {
        if (ChatState.currentId === sessionId) {
          setChatTitle(session.title);
        }
        return;
      }
    }
  }

  function showEmpty() {
    const chips = PROMPT_CHIPS.map(
      (p) => `<button type="button" class="chat-prompt-chip" data-prompt="${escapeHtml(p)}">${escapeHtml(p)}</button>`
    ).join('');
    $('#chat-window').innerHTML = `
      <div class="chat-empty" id="chat-empty">
        <h3>有什么可以帮你的？</h3>
        <p>Agent 可读写文件、调用工具、检索网页、记忆与回忆。</p>
        <div class="chat-prompts">${chips}</div>
      </div>
    `;
    $$('.chat-prompt-chip').forEach((btn) => {
      btn.addEventListener('click', () => {
        const input = $('#chat-input');
        if (!input || input.disabled) return;
        input.value = btn.dataset.prompt || '';
        autoGrow(input);
        input.focus();
      });
    });
  }

  function readinessTip(me) {
    if (!me) return { title: '加载失败', body: '请刷新页面或重新登录。' };
    if (!me.llm_configured) {
      return {
        title: 'Agent 未就绪',
        body: '请先配置对话模型（OpenAI 兼容接口地址与 API Key）。',
        linkText: '打开设置',
        linkAction: 'settings',
      };
    }
    const cs = me.container_status;
    if (cs === 'creating') {
      return { title: 'Agent 未就绪', body: '正在启动，通常需要 30~60 秒。' };
    }
    if (cs === 'absent' || me.provision_status === 'failed') {
      return {
        title: 'Agent 未就绪',
        body: me.provision_status === 'failed' ? '初始化失败，请检查设置后重试。' : '请完成对话模型配置。',
        linkText: '打开设置',
        linkAction: 'settings',
      };
    }
    return null;
  }

  function tipActionHtml(tip) {
    if (!tip.linkText) return '';
    if (tip.linkAction === 'settings') {
      return `<p class="tip-action"><button type="button" class="btn-secondary js-open-settings">${escapeHtml(tip.linkText)}</button></p>`;
    }
    if (tip.linkHref) {
      return `<p class="tip-action"><a class="btn-secondary" href="${escapeHtml(tip.linkHref)}">${escapeHtml(tip.linkText)}</a></p>`;
    }
    return '';
  }

  function renderChatTip(tip) {
    $('#chat-window').innerHTML = `
      <div class="chat-empty">
        <h3>${escapeHtml(tip.title)}</h3>
        <p>${escapeHtml(tip.body)}</p>
        ${tipActionHtml(tip)}
      </div>
    `;
  }

  function renderWsTip(tip) {
    const action = tip.linkAction === 'settings'
      ? ` · <button type="button" class="btn-link js-open-settings">${escapeHtml(tip.linkText)}</button>`
      : tip.linkHref
        ? ` · <a href="${escapeHtml(tip.linkHref)}">${escapeHtml(tip.linkText)}</a>`
        : '';
    const html = `<div class="ws-empty">${escapeHtml(tip.body)}${action}</div>`;
    const listMap = { skills: '#skills-list', mcp: '#mcp-list', memory: '#memory-list' };
    const countMap = { skills: '#skills-count', mcp: '#mcp-count', memory: '#memory-count' };
    const listSel = listMap[PAGE];
    const countSel = countMap[PAGE];
    if (listSel) {
      const el = $(listSel);
      if (el) el.innerHTML = html;
    }
    if (countSel) {
      const el = $(countSel);
      if (el) el.textContent = '-';
    }
  }

  async function switchSession(id) {
    if (id === ChatState.currentId) return;
    abortChatStream();
    ChatState.activeRunPollId += 1;
    ChatState.currentId = id;
    clearChatWindow();
    renderSessionList();
    closeMobileChatSidebar();

    const found = ChatState.sessions.find((s) => s.id === id);
    setChatTitle(found?.title || '会话');
    if (isDefaultSessionTitle(found?.title)) {
      waitForGeneratedSessionTitle(id).catch((err) => {
        console.warn('waitForGeneratedSessionTitle failed', err);
      });
    }
    $('#chat-meta').textContent = '加载中…';

    try {
      const messages = await fetchSessionMessages(id);
      const visible = renderSessionMessages(messages);
      $('#chat-meta').textContent = `${visible} 条消息`;
      try {
        const active = await j(`/api/workspace/sessions/${id}/active-run`);
        if (active.run?.status === 'running') {
          setChatStreamingUi(true);
          $('#chat-meta').textContent = `${visible} 条消息 · 生成中…`;
          pollActiveRun(id);
        } else {
          setChatStreamingUi(false);
        }
      } catch { setChatStreamingUi(false); }
    } catch (err) {
      $('#chat-meta').textContent = '';
      appendMessage('tool', `加载失败：${err.message}`);
      setChatStreamingUi(false);
    }
  }

  function newSession() {
    abortChatStream();
    ChatState.activeRunPollId += 1;
    ChatState.currentId = null;
    setChatTitle('新对话');
    $('#chat-meta').textContent = '';
    showEmpty();
    renderSessionList();
    $('#chat-input')?.focus();
  }

  function autoGrow(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
  }

  async function streamChatCompletion(body, handlers, { maxRetries = 5, signal } = {}) {
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      const res = await fetch('/api/workspace/chat/completions', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
        body: JSON.stringify({ ...body, stream: true }),
        signal,
      });
      if (res.status === 401) {
        redirectToLogin();
        throw new Error('session expired');
      }
      if (res.status === 503 && attempt < maxRetries) {
        const retryAfter = parseInt(res.headers.get('Retry-After') || '2', 10);
        handlers.onRetry?.(attempt + 1, retryAfter);
        await sleepWithSignal(Math.max(retryAfter, 1) * 1000, signal);
        continue;
      }
      if (!res.ok) {
        let err;
        try {
          const data = await res.json();
          err = parseApiError(data, res.status, res.statusText);
        } catch {
          try {
            err = new Error(await res.text() || res.statusText);
          } catch {
            err = new Error(res.statusText);
          }
        }
        err.status = res.status;
        throw err;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let sep;
        while ((sep = buffer.indexOf('\n\n')) >= 0) {
          const event = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const dataLines = event.split('\n')
            .filter((l) => l.startsWith('data:'))
            .map((l) => l.slice(5).trim());
          if (!dataLines.length) continue;
          const raw = dataLines.join('\n');
          if (raw === '[DONE]') { handlers.onDone?.(); return; }
          try {
            const obj = JSON.parse(raw);
            handlers.onMessage?.(obj);
          } catch (e) {
            console.warn('bad SSE chunk', raw);
          }
        }
      }
      handlers.onDone?.();
      return;
    }
  }

  function setupChat(me) {
    if (PAGE !== 'chat') return;

    const input = $('#chat-input');
    const form = $('#chat-form');
    const btn = $('#chat-send');
    const stopBtn = $('#chat-stop');

    const setStreaming = (active) => {
      if (btn) {
        btn.hidden = active;
        btn.disabled = active;
      }
      if (stopBtn) {
        stopBtn.hidden = !active;
        if (!active) {
          stopBtn.disabled = false;
          stopBtn.classList.remove('is-busy');
          stopBtn.title = '停止生成';
          stopBtn.setAttribute('aria-label', '停止生成');
        }
      }
      if (input) input.disabled = active;
    };
    setChatStreamingUi = setStreaming;
    setStreaming(false);

    stopBtn?.addEventListener('click', async () => {
      if (stoppingStream) return;
      stoppingStream = true;
      if (stopBtn) {
        stopBtn.disabled = true;
        stopBtn.classList.add('is-busy');
        stopBtn.title = '正在停止…';
        stopBtn.setAttribute('aria-label', '正在停止');
      }
      showToast('正在停止…', { type: 'info', duration: 1200 });
      chatStreamAbort?.abort();
      stopRunningToolBlocks('已停止');
      setStreaming(false);
      const sid = ChatState.currentId;
      if (!sid || !stopBtn) {
        stoppingStream = false;
        return;
      }
      try {
        await j(`/api/workspace/sessions/${encodeURIComponent(sid)}/cancel`, { method: 'POST', body: '{}' });
      } catch (err) {
        showToast(`停止失败：${err.message}`, { type: 'error' });
      } finally {
        stoppingStream = false;
      }
    });

    $('#session-search')?.addEventListener('input', (e) => {
      ChatState.sessionQuery = e.target.value || '';
      renderSessionList();
    });

    const tip = readinessTip(me);
    if (tip) {
      setStreaming(false);
      renderChatTip(tip);
      $('#session-list').innerHTML = `<div class="session-empty">${escapeHtml(tip.title)}</div>`;
      input.disabled = true;
      btn.disabled = true;
      input.placeholder = tip.title;
      $('#btn-new-chat')?.setAttribute('disabled', 'true');
      return;
    }

    loadSessions();

    $('#btn-new-chat')?.addEventListener('click', () => newSession());

    input.addEventListener('input', () => autoGrow(input));
    input.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      if (e.isComposing) return;
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      form.requestSubmit();
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;
      abortChatStream();

      appendMessage('user', text);
      input.value = '';
      autoGrow(input);
      setStreaming(true);

      let currentAssistant = appendMessage('assistant', '', { loading: true });
      let contentEl = currentAssistant.querySelector('.msg-content');
      let acc = '';
      let started = false;
      const streamToolEls = new Map();
      const streamPendingToolEls = [];
      let aborted = false;
      chatStreamAbort = new AbortController();

      const isPendingToolEl = (el) => Boolean(el && el.dataset?.toolRunning === '1');
      const rememberPendingToolEl = (el) => {
        if (!el) return;
        streamPendingToolEls.push(el);
      };
      const consumePendingToolEl = ({ toolName = '' } = {}) => {
        const preferredName = String(toolName || '').trim();
        for (let i = streamPendingToolEls.length - 1; i >= 0; i--) {
          const el = streamPendingToolEls[i];
          if (!isPendingToolEl(el)) {
            streamPendingToolEls.splice(i, 1);
            continue;
          }
          if (!preferredName) return el;
          const currentName = String(el.querySelector('.tool-event-call')?.textContent || '').trim();
          if (currentName && currentName === displayToolName(preferredName)) return el;
        }
        for (let i = streamPendingToolEls.length - 1; i >= 0; i--) {
          const el = streamPendingToolEls[i];
          if (!isPendingToolEl(el)) {
            streamPendingToolEls.splice(i, 1);
            continue;
          }
          return el;
        }
        return null;
      };

      function resetAssistantBlock() {
        if (contentEl) contentEl.classList.remove('msg-loading');
        if (currentAssistant && !acc.trim()) {
          currentAssistant.remove();
        }
        currentAssistant = null;
        contentEl = null;
        acc = '';
        started = false;
      }

      function ensureAssistantBlock() {
        if (currentAssistant) return;
        currentAssistant = appendMessage('assistant', '', { loading: true });
        contentEl = currentAssistant.querySelector('.msg-content');
        acc = '';
        started = false;
      }

      const body = { messages: [{ role: 'user', content: text }] };
      if (ChatState.currentId) body.session_id = ChatState.currentId;

      try {
        await streamChatCompletion(body, {
          onRetry: (attempt, sec) => {
            ensureAssistantBlock();
            if (contentEl) {
              contentEl.classList.remove('msg-loading');
              contentEl.innerHTML = `<em>Agent 恢复中，${sec}s 后重试（${attempt}）…</em>`;
            }
          },
          onMessage: (chunk) => {
            if (chunk.session_id && !ChatState.currentId) {
              ChatState.currentId = chunk.session_id;
              upsertSessionPreview(chunk.session_id, '新对话');
              loadSessions().catch(() => {});
            }
            const xev = chunk.x_event;
            if (xev === 'tool_call') {
              resetAssistantBlock();
              const toolName = chunk.x_tool_name || 'unknown';
              const kind = chunk.x_tool_kind || detectToolKind(toolName);
              const toolId = chunk.x_tool_id || '';
              const el = appendToolBlock({
                toolCallId: toolId,
                toolName,
                kind,
                preview: '',
                pending: true,
              });
              rememberPendingToolEl(el);
              if (toolId) streamToolEls.set(toolId, el);
              return;
            }
            if (xev === 'tool_result') {
              const toolId = chunk.x_tool_call_id || '';
              const toolName = chunk.x_tool_name || '';
              const preview = chunk.x_preview || '';
              const el = (toolId ? streamToolEls.get(toolId) : null) || consumePendingToolEl({ toolName });
              if (el) {
                updateToolBlock(el, { preview, toolName });
              } else if (preview) {
                appendToolBlock({ toolName, kind: 'tool', preview });
              }
              return;
            }
            if (xev === 'error') {
              ensureAssistantBlock();
              if (!started) contentEl.classList.remove('msg-loading');
              contentEl.innerHTML = `<em>Error: ${escapeHtml(chunk.x_message || 'unknown')}</em>`;
              return;
            }
            const delta = chunk.choices?.[0]?.delta?.content;
            if (delta) {
              ensureAssistantBlock();
              if (!started) {
                contentEl.classList.remove('msg-loading');
                started = true;
              }
              acc += delta;
              contentEl.innerHTML = renderAssistantContent(acc, { enableHtmlRender: true, renderHtmlNow: false });
              enhanceCodeBlocks(contentEl);
              const win = $('#chat-window');
              win.scrollTop = win.scrollHeight;
            }
          },
        }, { signal: chatStreamAbort.signal });
        if (contentEl && acc) {
          contentEl.innerHTML = renderAssistantContent(acc, { enableHtmlRender: true, renderHtmlNow: true });
          hydrateHtmlRenderBlocks(contentEl);
          enhanceCodeBlocks(contentEl);
        }
        await loadSessions();
        if (ChatState.currentId) {
          const current = ChatState.sessions.find((s) => s.id === ChatState.currentId);
          if (isDefaultSessionTitle(current?.title)) {
            waitForGeneratedSessionTitle(ChatState.currentId).catch((err) => {
              console.warn('waitForGeneratedSessionTitle failed', err);
            });
          } else {
            setChatTitle(current.title);
          }
        }
      } catch (err) {
        if (err.name === 'AbortError') {
          aborted = true;
          ensureAssistantBlock();
          if (contentEl) {
            contentEl.classList.remove('msg-loading');
            if (acc.trim()) {
              contentEl.innerHTML = renderAssistantContent(acc, { enableHtmlRender: true });
              hydrateHtmlRenderBlocks(contentEl);
              enhanceCodeBlocks(contentEl);
            } else {
              contentEl.innerHTML = '<em>已停止生成</em>';
            }
          }
        } else {
          ensureAssistantBlock();
          if (contentEl) {
            contentEl.classList.remove('msg-loading');
            if (err.status === 409 && err.data?.error?.code === 'run_in_progress') {
              contentEl.innerHTML = '<em>该会话仍在生成中，请稍候…</em>';
              if (ChatState.currentId) pollActiveRun(ChatState.currentId);
            } else {
              contentEl.innerHTML = `<em>Error: ${escapeHtml(err.message)}</em>`;
            }
          }
        }
      } finally {
        chatStreamAbort = null;
        stoppingStream = false;
        if (ChatState.currentId) {
          try {
            const active = await j(`/api/workspace/sessions/${ChatState.currentId}/active-run`);
            setStreaming(active.run?.status === 'running');
            if (active.run?.status === 'running') {
              pollActiveRun(ChatState.currentId);
            } else {
              stopRunningToolBlocks('已停止');
            }
          } catch {
            setStreaming(false);
            stopRunningToolBlocks('已停止');
          }
        } else {
          setStreaming(false);
          stopRunningToolBlocks('已停止');
        }
        if (!aborted) input.focus();
      }
    });
  }

  /* ============= Skills / MCP / Memory ============= */
  async function setupWorkspace(me) {
    if (!WS_PAGES.has(PAGE)) return;

    const tip = readinessTip(me);
    if (tip) {
      renderWsTip(tip);
      return;
    }

    const renderList = (sel, items, render, empty) => {
      const el = $(sel);
      if (!items.length) { el.innerHTML = `<div class="ws-empty">${empty}</div>`; return; }
      el.innerHTML = items.map(render).join('');
    };
    const showErr = (sel, err) => {
      const msg = err.status === 503
        ? (err.code === 'starting' ? 'Agent 未就绪，正在启动' : 'Agent 未就绪')
        : escapeHtml(err.message);
      $(sel).innerHTML = `<div class="ws-empty">${msg}</div>`;
    };
    const parseCommand = (raw) => String(raw || '').trim().split(/\s+/).filter(Boolean);
    const parseTriggers = (raw) => String(raw || '').split(/[,，\n]/).map((x) => x.trim()).filter(Boolean);
    let editingMcpName = null;
    let cachedMcpItems = [];
    let editingSkillName = null;
    let cachedSkillItems = [];
    let skillSearchKeyword = '';
    let editingMemoryId = null;
    let cachedMemoryItems = [];
    let memorySearchKeyword = '';
    let activeMemoryAnchor = 'identity';
    let updateMcpInputs = () => {};
    let memoryAutoRefreshTimer = null;
    let memoryAutoRefreshInFlight = false;
    const sectionVersion = { skills: 0, mcp: 0, memory: 0 };
    const nextVersion = (k) => { sectionVersion[k] += 1; return sectionVersion[k]; };
    const isLatest = (k, v) => sectionVersion[k] === v;
    const errText = (err, fallback = '操作失败') => escapeHtml(err?.message || fallback);
    const stopMemoryAutoRefresh = () => {
      if (!memoryAutoRefreshTimer) return;
      clearInterval(memoryAutoRefreshTimer);
      memoryAutoRefreshTimer = null;
    };
    const startMemoryAutoRefresh = () => {
      if (memoryAutoRefreshTimer || PAGE !== 'memory') return;
      memoryAutoRefreshTimer = setInterval(async () => {
        if (memoryAutoRefreshInFlight) return;
        memoryAutoRefreshInFlight = true;
        try {
          await refreshMemoryList({ silent: true });
        } finally {
          memoryAutoRefreshInFlight = false;
        }
      }, 3000);
    };
    const withButtonBusy = async (btn, fn) => {
      if (btn) btn.disabled = true;
      try {
        return await fn();
      } finally {
        if (btn) btn.disabled = false;
      }
    };

    const isPrivateSkill = (s) => s.source === 'private';

    const renderSkillItem = (s) => {
      const isPrivate = isPrivateSkill(s);
      const sourceLabel = isPrivate ? '私有' : '公共';
      const triggers = s.triggers?.length ? s.triggers.join(', ') : '无';
      const actions = isPrivate
        ? `<div class="ws-item-actions">
            <button class="btn-icon skill-edit-btn" data-name="${encodeURIComponent(s.name || '')}" title="编辑技能">✎</button>
            <button class="btn-icon skill-delete-btn" data-name="${encodeURIComponent(s.name || '')}" title="删除技能">×</button>
          </div>`
        : `<div class="ws-item-actions"><span class="badge badge-muted ws-readonly-badge">只读</span></div>`;
      const bodyHtml = s.body
        ? `<details class="ws-skill-body"><summary>查看正文</summary><pre>${escapeHtml(s.body)}</pre></details>`
        : '';
      return `<div class="ws-item ${isPrivate ? '' : 'ws-item-readonly'}">
        <div class="ws-item-head">
          <div class="ws-item-title">${escapeHtml(s.name || '')}</div>
          ${actions}
        </div>
        <div class="ws-item-meta">${sourceLabel} · 触发词：${escapeHtml(triggers)}</div>
        <div class="ws-item-meta">${escapeHtml(s.description || '')}</div>
        ${bodyHtml}
      </div>`;
    };

    const renderSkills = (items) => {
      cachedSkillItems = items;
      const filtered = !skillSearchKeyword
        ? items
        : items.filter((s) => {
            const q = skillSearchKeyword.toLowerCase();
            return String(s.name || '').toLowerCase().includes(q)
              || String(s.description || '').toLowerCase().includes(q)
              || String(s.body || '').toLowerCase().includes(q);
          });
      const el = $('#skills-list');
      if (!filtered.length) {
        el.innerHTML = `<div class="ws-empty">${skillSearchKeyword ? '无匹配技能' : '暂无技能'}</div>`;
        return;
      }
      const publicItems = filtered.filter((s) => !isPrivateSkill(s));
      const privateItems = filtered.filter(isPrivateSkill);
      let html = '';
      if (publicItems.length) {
        html += '<div class="session-group-label">公共技能</div>';
        html += publicItems.map(renderSkillItem).join('');
      }
      if (privateItems.length) {
        html += '<div class="session-group-label">私有技能</div>';
        html += privateItems.map(renderSkillItem).join('');
      }
      el.innerHTML = html;
      $$('.skill-edit-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const encoded = btn.dataset.name;
          if (!encoded) return;
          const name = decodeURIComponent(encoded);
          const item = cachedSkillItems.find((it) => it.name === name);
          if (!item || !isPrivateSkill(item)) return;
          editingSkillName = name;
          $('#skill-name').value = item.name || '';
          $('#skill-name').disabled = true;
          $('#skill-desc').value = item.description || '';
          $('#skill-triggers').value = (item.triggers || []).join(', ');
          $('#skill-body').value = item.body || '';
          $('#skill-save-btn').textContent = '保存';
          $('#skill-cancel-edit-btn').hidden = false;
          $('#skill-form')?.closest('details')?.setAttribute('open', '');
        });
      });
      $$('.skill-delete-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const encoded = btn.dataset.name;
          if (!encoded) return;
          const name = decodeURIComponent(encoded);
          if (!await uiConfirm(`确定删除技能「${name}」？`, { title: '删除技能', danger: true, confirmText: '删除' })) return;
          await withButtonBusy(btn, async () => {
            try {
              await j(`/api/workspace/skills/${encodeURIComponent(name)}`, { method: 'DELETE' });
              await refreshSkillsList();
            } catch (err) {
              showToast(`删除失败：${errText(err)}`, { type: 'error' });
            }
          });
        });
      });
    };
    const refreshSkillsList = async () => {
      const v = nextVersion('skills');
      try {
        const skills = await j('/api/workspace/skills');
        if (!isLatest('skills', v)) return;
        const items = skills.items || [];
        const pub = items.filter((s) => !isPrivateSkill(s)).length;
        const priv = items.filter(isPrivateSkill).length;
        $('#skills-count').textContent = `公共 ${pub} / 私有 ${priv}`;
        renderSkills(items);
      } catch (err) {
        if (!isLatest('skills', v)) return;
        showErr('#skills-list', err);
      }
    };

    const renderMcpItems = (items) => {
      cachedMcpItems = items;
      renderList(
        '#mcp-list',
        items,
        (m) => {
          const endpoint = m.transport === 'http' ? (m.url || '-') : (m.command || []).concat(m.args || []).join(' ');
          const tools = Array.isArray(m.tools) ? m.tools : [];
          const renderParam = (p) => {
            const required = p.required ? '必填' : '可选';
            const enumTxt = Array.isArray(p.enum) && p.enum.length ? ` 枚举(${p.enum.join('|')})` : '';
            return `<span class="ws-tool-param">${escapeHtml(`${p.name}:${p.type} ${required}${enumTxt}`)}</span>`;
          };
          const toolsHtml = tools.length
            ? `<div class="ws-item-tools">${tools.map((t) => {
                const params = Array.isArray(t.schema_summary) ? t.schema_summary : [];
                const desc = t.description || '';
                const descHtml = desc
                  ? `<span class="ws-tool-desc">${escapeHtml(desc)}</span>`
                  : '';
                const descFullHtml = desc
                  ? `<div class="ws-tool-desc-full">${escapeHtml(desc)}</div>`
                  : '';
                return `<details class="ws-tool-chip">
                  <summary class="ws-tool-row">
                    <span class="ws-tool-name">${escapeHtml(t.name || '')}</span>${descHtml}
                  </summary>
                  ${descFullHtml}
                  <div class="ws-tool-params">${params.length ? params.map(renderParam).join('') : '<span class="ws-item-meta">无入参</span>'}</div>
                </details>`;
              }).join('')}</div>`
            : '<div class="ws-item-meta ws-tools-empty">暂无工具</div>';
          const status = m.connected ? badge('在线', 'badge-success') : badge('离线', 'badge-muted');
          const warn = m.runtime_error ? `<div class="ws-item-warn">连接失败：${escapeHtml(m.runtime_error)}</div>` : '';
          return `<div class="ws-item">
            <div class="ws-item-head">
              <div class="ws-item-title">${escapeHtml(m.name)}</div>
              <div class="ws-item-actions">
                ${status}
                <button class="btn-icon mcp-reconnect-btn" data-name="${encodeURIComponent(m.name || '')}" title="重连服务">↻</button>
                <button class="btn-icon mcp-edit-btn" data-name="${encodeURIComponent(m.name || '')}" title="编辑服务">✎</button>
                <button class="btn-icon mcp-delete-btn" data-name="${encodeURIComponent(m.name || '')}" title="删除服务">×</button>
              </div>
            </div>
            <div class="ws-item-meta">[${escapeHtml(m.transport)}] ${escapeHtml(endpoint)}</div>
            ${toolsHtml}
            ${warn}
          </div>`;
        },
        '暂无 MCP 服务'
      );
      $$('.mcp-delete-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const encoded = btn.dataset.name;
          if (!encoded) return;
          const name = decodeURIComponent(encoded);
          if (!await uiConfirm(`确定删除服务「${name}」？`, { title: '删除服务', danger: true, confirmText: '删除' })) return;
          await withButtonBusy(btn, async () => {
            try {
              await j(`/api/workspace/mcp/${encodeURIComponent(name)}`, { method: 'DELETE' });
              await refreshMcpList();
            } catch (err) {
              showToast(`删除失败：${errText(err)}`, { type: 'error' });
            }
          });
        });
      });
      $$('.mcp-edit-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const encoded = btn.dataset.name;
          if (!encoded) return;
          const name = decodeURIComponent(encoded);
          const item = cachedMcpItems.find((it) => it.name === name);
          if (!item) return;
          editingMcpName = name;
          $('#mcp-name').value = item.name || '';
          $('#mcp-name').disabled = true;
          $('#mcp-transport').value = item.transport || 'stdio';
          $('#mcp-command').value = (item.command || []).concat(item.args || []).join(' ');
          $('#mcp-url').value = item.url || '';
          $('#mcp-add-btn').textContent = '保存';
          $('#mcp-cancel-edit-btn').hidden = false;
          updateMcpInputs();
          $('#mcp-form')?.closest('details')?.setAttribute('open', '');
        });
      });
      $$('.mcp-reconnect-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const encoded = btn.dataset.name;
          if (!encoded) return;
          const name = decodeURIComponent(encoded);
          await withButtonBusy(btn, async () => {
            try {
              await j(`/api/workspace/mcp/${encodeURIComponent(name)}`, { method: 'POST', body: '{}' });
              await refreshMcpList();
            } catch (err) {
              showToast(`重连失败：${errText(err)}`, { type: 'error' });
            }
          });
        });
      });
    };

    const refreshMcpList = async () => {
      const v = nextVersion('mcp');
      try {
        const mcp = await j('/api/workspace/mcp');
        if (!isLatest('mcp', v)) return;
        const items = mcp.items || [];
        $('#mcp-count').textContent = items.length;
        renderMcpItems(items);
      } catch (err) {
        if (!isLatest('mcp', v)) return;
        showErr('#mcp-list', err);
      }
    };

    const renderMemories = (items) => {
      cachedMemoryItems = items;
      const filteredByAnchor = items.filter((m) => String(m.anchor || 'experience') === activeMemoryAnchor);
      const filtered = !memorySearchKeyword
        ? filteredByAnchor
        : filteredByAnchor.filter((m) => String(m.content || '').toLowerCase().includes(memorySearchKeyword.toLowerCase()));
      const identityCount = items.filter((m) => String(m.anchor || 'experience') === 'identity').length;
      const expCount = items.filter((m) => String(m.anchor || 'experience') === 'experience').length;
      $('#memory-count').textContent = `常驻记忆 ${identityCount} / 按需检索 ${expCount}`;
      renderList(
        '#memory-list',
        filtered,
        (it) => `<div class="ws-item">
          <div class="ws-item-head">
            <div class="ws-item-title">#${it.id}
              <span class="badge ${EMBED_BADGE[it.embedding_state] || 'badge-muted'}" title="${escapeHtml(it.embedding_state)}">${EMBED_LABEL[it.embedding_state] || it.embedding_state}</span>
            </div>
            <div class="ws-item-actions">
              <button class="btn-icon memory-toggle-anchor-btn" data-id="${it.id}" data-anchor="${it.anchor || 'experience'}" title="${it.anchor === 'identity' ? '降级为按需检索记忆' : '升级为常驻记忆'}" aria-label="${it.anchor === 'identity' ? '降级为按需检索记忆' : '升级为常驻记忆'}">${it.anchor === 'identity' ? '↓' : '↑'}</button>
              <button class="btn-icon memory-edit-btn" data-id="${it.id}" title="编辑记忆">✎</button>
              <button class="btn-icon memory-delete-btn" data-id="${it.id}" title="删除记忆">×</button>
            </div>
          </div>
          <div class="ws-item-meta">${escapeHtml(it.content || '')}</div>
        </div>`,
        memorySearchKeyword ? '无匹配记忆' : `暂无 ${activeMemoryAnchor === 'identity' ? '常驻记忆' : '按需检索记忆'}`
      );
      $$('#memory-anchor-tabs .ws-tab').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.anchor === activeMemoryAnchor);
      });
      $$('.memory-edit-btn').forEach((btn) => {
        btn.addEventListener('click', () => {
          const id = Number(btn.dataset.id || 0);
          if (!id) return;
          const item = cachedMemoryItems.find((it) => Number(it.id) === id);
          if (!item) return;
          editingMemoryId = id;
          $('#memory-content').value = item.content || '';
          $('#memory-save-btn').textContent = '保存';
          $('#memory-cancel-edit-btn').hidden = false;
          const contentEl = $('#memory-content');
          if (contentEl) contentEl.placeholder = '编辑记忆内容';
          $('#memory-form')?.closest('details')?.setAttribute('open', '');
        });
      });
      $$('.memory-toggle-anchor-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = Number(btn.dataset.id || 0);
          if (!id) return;
          const currentAnchor = btn.dataset.anchor === 'identity' ? 'identity' : 'experience';
          const nextAnchor = currentAnchor === 'identity' ? 'experience' : 'identity';
          const actionText = nextAnchor === 'identity' ? '升级为常驻记忆' : '降级为按需检索记忆';
          await withButtonBusy(btn, async () => {
            try {
              await j(`/api/workspace/memory/${id}`, {
                method: 'PUT',
                body: JSON.stringify({ anchor: nextAnchor }),
              });
              await refreshMemoryList();
              showToast(`${actionText}成功`);
            } catch (err) {
              showToast(`${actionText}失败：${errText(err)}`, { type: 'error' });
            }
          });
        });
      });
      $$('.memory-delete-btn').forEach((btn) => {
        btn.addEventListener('click', async () => {
          const id = Number(btn.dataset.id || 0);
          if (!id) return;
          if (!await uiConfirm(`确定删除记忆 #${id}？`, { title: '删除记忆', danger: true, confirmText: '删除' })) return;
          await withButtonBusy(btn, async () => {
            try {
              await j(`/api/workspace/memory/${id}`, { method: 'DELETE' });
              await refreshMemoryList();
            } catch (err) {
              showToast(`删除失败：${errText(err)}`, { type: 'error' });
            }
          });
        });
      });
    };
    const refreshMemoryList = async ({ silent = false } = {}) => {
      const v = nextVersion('memory');
      try {
        const mem = await j('/api/workspace/memory?limit=100');
        if (!isLatest('memory', v)) return;
        const items = mem.items || [];
        renderMemories(items);
        const hasPending = items.some((it) => String(it.embedding_state || '') === 'pending');
        if (hasPending) startMemoryAutoRefresh();
        else stopMemoryAutoRefresh();
      } catch (err) {
        if (!isLatest('memory', v)) return;
        if (!silent) showErr('#memory-list', err);
      }
    };
    await Promise.all([
      PAGE === 'skills' ? refreshSkillsList() : Promise.resolve(),
      PAGE === 'mcp' ? refreshMcpList() : Promise.resolve(),
      PAGE === 'memory' ? refreshMemoryList() : Promise.resolve(),
    ]);

    if (PAGE === 'mcp') {
    const mcpForm = $('#mcp-form');
    const transportEl = $('#mcp-transport');
    const commandEl = $('#mcp-command');
    const urlEl = $('#mcp-url');
    const nameEl = $('#mcp-name');
    const addBtn = $('#mcp-add-btn');
    const testBtn = $('#mcp-test-btn');
    const cancelEditBtn = $('#mcp-cancel-edit-btn');
    const exitEditMode = () => {
      editingMcpName = null;
      mcpForm.reset();
      nameEl.disabled = false;
      transportEl.value = 'stdio';
      addBtn.textContent = '添加';
      cancelEditBtn.hidden = true;
      updateMcpInputs();
    };
    updateMcpInputs = () => {
      const transport = transportEl.value;
      const isHttp = transport === 'http';
      commandEl.disabled = isHttp;
      commandEl.required = !isHttp;
      urlEl.disabled = !isHttp;
      urlEl.required = isHttp;
      const stdioField = $('#mcp-field-stdio');
      const httpField = $('#mcp-field-http');
      if (stdioField) stdioField.hidden = isHttp;
      if (httpField) httpField.hidden = !isHttp;
    };
    updateMcpInputs();
    transportEl?.addEventListener('change', updateMcpInputs);
    cancelEditBtn?.addEventListener('click', () => exitEditMode());

    const buildPayloadFromForm = () => {
      const name = nameEl.value.trim();
      const transport = transportEl.value;
      const commandText = commandEl.value.trim();
      const url = urlEl.value.trim();
      return {
        name,
        transport,
        command: transport === 'stdio' ? parseCommand(commandText) : [],
        args: [],
        env: {},
        url: transport === 'http' ? url : null,
      };
    };

    testBtn?.addEventListener('click', async () => {
      const payload = buildPayloadFromForm();
      if (!payload.name) {
        showToast('请先填写 MCP 名称', { type: 'error' });
        return;
      }
      await withButtonBusy(testBtn, async () => {
        try {
          const r = await j('/api/workspace/mcp/test', {
            method: 'POST',
            body: JSON.stringify(payload),
          });
          if (r.connected) {
            showToast(`连接成功，可用工具数：${r.tool_count}`, { type: 'success' });
          } else {
            showToast(`连接失败：${r.runtime_error || 'unknown'}`, { type: 'error' });
          }
        } catch (err) {
          showToast(`测试失败：${errText(err)}`, { type: 'error' });
        }
      });
    });

    mcpForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = buildPayloadFromForm();
      if (!payload.name) return;
      await withButtonBusy(addBtn, async () => {
        try {
          await j(editingMcpName ? `/api/workspace/mcp/${encodeURIComponent(editingMcpName)}` : '/api/workspace/mcp', {
            method: editingMcpName ? 'PUT' : 'POST',
            body: JSON.stringify(payload),
          });
          exitEditMode();
          await refreshMcpList();
        } catch (err) {
          showToast(`${editingMcpName ? '保存' : '添加'}失败：${errText(err)}`, { type: 'error' });
        }
      });
    });
    }

    if (PAGE === 'skills') {
    const skillForm = $('#skill-form');
    const skillNameEl = $('#skill-name');
    const skillDescEl = $('#skill-desc');
    const skillTriggersEl = $('#skill-triggers');
    const skillBodyEl = $('#skill-body');
    const skillSaveBtn = $('#skill-save-btn');
    const skillCancelBtn = $('#skill-cancel-edit-btn');
    const skillSearchEl = $('#skill-search');
    const exitSkillEditMode = () => {
      editingSkillName = null;
      skillForm.reset();
      skillNameEl.disabled = false;
      skillSaveBtn.textContent = '添加';
      skillCancelBtn.hidden = true;
    };
    skillCancelBtn?.addEventListener('click', () => exitSkillEditMode());
    skillSearchEl?.addEventListener('input', () => {
      skillSearchKeyword = skillSearchEl.value.trim();
      renderSkills(cachedSkillItems);
    });
    skillForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const payload = {
        name: skillNameEl.value.trim(),
        description: skillDescEl.value.trim(),
        body: skillBodyEl.value,
        triggers: parseTriggers(skillTriggersEl.value),
      };
      if (!payload.name) return;
      await withButtonBusy(skillSaveBtn, async () => {
        try {
          if (editingSkillName) {
            await j(`/api/workspace/skills/${encodeURIComponent(editingSkillName)}`, {
              method: 'PUT',
              body: JSON.stringify({
                description: payload.description,
                body: payload.body,
                triggers: payload.triggers,
              }),
            });
          } else {
            await j('/api/workspace/skills', {
              method: 'POST',
              body: JSON.stringify(payload),
            });
          }
          exitSkillEditMode();
          await refreshSkillsList();
        } catch (err) {
          showToast(`${editingSkillName ? '保存' : '添加'}技能失败：${errText(err)}`, { type: 'error' });
        }
      });
    });
    }

    if (PAGE === 'memory') {
    const memoryForm = $('#memory-form');
    const memoryContentEl = $('#memory-content');
    const memorySaveBtn = $('#memory-save-btn');
    const memoryCancelBtn = $('#memory-cancel-edit-btn');
    const memorySearchEl = $('#memory-search');
    const updateMemoryFormHint = () => {
      if (!memoryContentEl || editingMemoryId) return;
      memoryContentEl.placeholder = activeMemoryAnchor === 'identity'
        ? '添加到「常驻记忆」…'
        : '添加到「按需检索」…';
    };
    const exitMemoryEditMode = () => {
      editingMemoryId = null;
      memoryForm.reset();
      memorySaveBtn.textContent = '添加';
      memoryCancelBtn.hidden = true;
      updateMemoryFormHint();
    };
    memoryCancelBtn?.addEventListener('click', () => exitMemoryEditMode());
    memorySearchEl?.addEventListener('input', () => {
      memorySearchKeyword = memorySearchEl.value.trim();
      renderMemories(cachedMemoryItems);
    });
    $$('#memory-anchor-tabs .ws-tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        activeMemoryAnchor = btn.dataset.anchor || 'identity';
        if (editingMemoryId) exitMemoryEditMode();
        updateMemoryFormHint();
        renderMemories(cachedMemoryItems);
      });
    });
    updateMemoryFormHint();
    memoryForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const content = memoryContentEl.value.trim();
      if (!content) return;
      await withButtonBusy(memorySaveBtn, async () => {
        try {
          if (editingMemoryId) {
            await j(`/api/workspace/memory/${editingMemoryId}`, {
              method: 'PUT',
              body: JSON.stringify({ content }),
            });
          } else {
            await j('/api/workspace/memory', {
              method: 'POST',
              body: JSON.stringify({ content, anchor: activeMemoryAnchor }),
            });
          }
          exitMemoryEditMode();
          await refreshMemoryList();
        } catch (err) {
          showToast(`${editingMemoryId ? '保存' : '添加'} 记忆失败：${errText(err)}`, { type: 'error' });
        }
      });
    });
    }
  }

  function setupSidebarCollapse() {
    const root = document.documentElement;
    const shell = $('.app-shell');
    const navKey = 'apod-nav-collapsed';
    const chatKey = 'apod-chat-sidebar-collapsed';

    const navCollapsed = () => root.classList.contains('apod-nav-collapsed');

    const syncNavToggle = () => {
      const btn = $('#btn-nav-collapse');
      if (!btn) return;
      const collapsed = navCollapsed();
      btn.title = collapsed ? '展开导航' : '收起导航';
      btn.setAttribute('aria-label', btn.title);
    };

    const navBtn = $('#btn-nav-collapse');
    if (navBtn && shell) {
      syncNavToggle();
      navBtn.addEventListener('click', () => {
        root.classList.toggle('apod-nav-collapsed');
        localStorage.setItem(navKey, navCollapsed() ? '1' : '0');
        syncNavToggle();
      });
    }

    const chatPage = $('#page-chat');
    const chatBtn = $('#btn-chat-sidebar-toggle');
    const chatCollapsed = () => root.classList.contains('apod-chat-sidebar-collapsed');

    const syncChatToggle = () => {
      if (!chatBtn || !chatPage) return;
      const collapsed = chatCollapsed();
      chatBtn.title = collapsed ? '展开会话列表' : '收起会话列表';
      chatBtn.setAttribute('aria-label', chatBtn.title);
    };

    if (chatPage && chatBtn) {
      syncChatToggle();
      chatBtn.addEventListener('click', () => {
        if (isMobileViewport()) {
          if (document.documentElement.classList.contains('apod-chat-sidebar-open')) {
            closeMobileChatSidebar();
          } else {
            openMobileChatSidebar();
          }
          return;
        }
        root.classList.toggle('apod-chat-sidebar-collapsed');
        localStorage.setItem(chatKey, chatCollapsed() ? '1' : '0');
        syncChatToggle();
      });
    }
  }

  async function init() {
    document.documentElement.removeAttribute('data-theme');
    try { localStorage.removeItem('apod-theme'); } catch (_) {}
    showPage();
    setupSidebarCollapse();
    setupUserMenu();
    setupNetworkStatus();
    setupGlobalShortcuts();
    setupAgentStatus();
    setupModals();
    setupSettings();
    const me = await loadUser();
    updateAgentApiKeyStatus(me);
    startStatusPollIfNeeded(me);
    pendingSettingsOnboarding = !!(me && !me.llm_configured);

    const urlSettings = new URLSearchParams(window.location.search).get('settings') === '1';
    if (urlSettings) {
      history.replaceState(null, '', window.location.pathname);
      pendingSettingsOnboarding = false;
      openSettingsModal();
    }

    const showedKey = await maybeShowApiKeyFlash();
    if (pendingSettingsOnboarding && !showedKey) {
      pendingSettingsOnboarding = false;
      openSettingsModal();
    }

    setupChat(me);
    await setupWorkspace(me);
  }
  init();
})();
