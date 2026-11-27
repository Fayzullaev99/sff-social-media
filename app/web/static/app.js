/* ==========================================================
   Social Agent — Dashboard logic (vanilla JS)
   ========================================================== */
const ICONS = {
  bot: '<rect x="3" y="8" width="18" height="12" rx="3"/><path d="M12 8V4M8 14h.01M16 14h.01M9 18h6"/><circle cx="12" cy="3" r="1"/>',
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3M12 17h.01"/>',
  check: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  megaphone: '<path d="M3 11v2a1 1 0 0 0 1 1h3l5 4V6L7 10H4a1 1 0 0 0-1 1z"/><path d="M16 8a5 5 0 0 1 0 8M19 5a9 9 0 0 1 0 14"/>',
  sparkles: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  activity: '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  plug: '<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>',
  zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9z"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/>',
  cloud: '<path d="M17.5 19a4.5 4.5 0 1 0-1.4-8.8A6 6 0 1 0 6 17.3"/><path d="M12 12v9M8.5 15.5 12 12l3.5 3.5"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
  save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
  inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"/>',
  reply: '<path d="M9 17 4 12l5-5"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  film: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M7 4v16M17 4v16M2 12h20M2 8h5M17 8h5M2 16h5M17 16h5"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
};
const svg = (name) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ''}</svg>`;
const hydrateIcons = (root = document) =>
  root.querySelectorAll('[data-icon]').forEach((el) => {
    if (!el.dataset.hydrated) { el.innerHTML = svg(el.dataset.icon) + el.innerHTML; el.dataset.hydrated = '1'; }
  });

/* ---------- helpers ---------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(path, opts = {}) {
  const init = { headers: {}, ...opts };
  if (opts.body && !(opts.body instanceof FormData)) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  let data = null;
  try { data = await res.json(); } catch { /* empty */ }
  if (!res.ok) throw new Error((data && (data.detail || data.message)) || `HTTP ${res.status}`);
  return data;
}

function toast(msg, type = 'ok') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${type === 'ok' ? '✅' : type === 'err' ? '⚠️' : 'ℹ️'}</span><div>${esc(msg)}</div>`;
  $('#toasts').appendChild(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 300); }, 4200);
}

async function withLoading(btn, fn) {
  btn.classList.add('loading'); btn.disabled = true;
  try { return await fn(); } catch (e) { toast(e.message, 'err'); } finally { btn.classList.remove('loading'); btn.disabled = false; }
}

function timeAgo(iso) {
  if (!iso) return '';
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z');
  const s = (Date.now() - d) / 1000;
  if (s < 60) return 'hozirgina';
  if (s < 3600) return `${Math.floor(s / 60)} daq. oldin`;
  if (s < 86400) return `${Math.floor(s / 3600)} soat oldin`;
  return d.toLocaleString('uz-UZ', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

const GRADS = ['#8b5cf6,#06b6d4', '#ec4899,#8b5cf6', '#f59e0b,#ef4444', '#10b981,#06b6d4', '#6366f1,#ec4899', '#14b8a6,#6366f1'];
const avatar = (name, id) => {
  const g = GRADS[Math.abs(Number(String(id).slice(-4)) || 0) % GRADS.length];
  return `<div class="avatar" style="background:linear-gradient(135deg,${g})">${esc((name || '?').trim().charAt(0).toUpperCase())}</div>`;
};
const KIND = { user: '👤 Kontakt', bot: '🤖 Bot', group: '👥 Guruh', channel: '📢 Kanal', discussion: '💬 Izohlar' };
const FEED_ICON = { telegram: '✈️', admin_bot: '🤖', knowledge: '📚', escalation: '❓', approval: '✅', content: '📢', video: '🎬', youtube: '📺', instagram: '📸', analytics: '📊', ads: '🎯', agent: '⚡', scheduler: '⏰' };

const feedHtml = (items) => items.length
  ? items.map((a) => `<div class="feed-item ${a.level}"><div class="ico">${FEED_ICON[a.kind] || '•'}</div><div class="txt">${esc(a.message)}</div><time>${timeAgo(a.created_at)}</time></div>`).join('')
  : '<div class="empty"><div class="big">🌙</div>Hozircha faollik yo\'q</div>';

/* ==========================================================
   APP
   ========================================================== */
const App = {
  page: 'overview',
  state: { chatTab: 'allowed', qTab: 'open', aTab: 'pending', dialogs: null, chats: [], settings: null, pg: [] },

  init() {
    hydrateIcons();
    $$('#nav .nav-item').forEach((b) => b.addEventListener('click', () => this.go(b.dataset.page)));
    $('#agent-toggle').addEventListener('change', (e) => this.toggleAgent(e.target.checked));
    const hash = location.hash.replace('#', '');
    this.go(hash && $(`#page-${hash}`) ? hash : 'overview');
    this.bindChats(); this.bindKnowledge(); this.bindTabs(); this.bindContent(); this.bindVideos(); this.bindAnalytics(); this.bindAds(); this.bindPlayground(); this.bindSettings();
    $('#modal').addEventListener('click', (e) => { if (e.target.id === 'modal') this.closeModal(); });
    setInterval(() => this.poll(), 8000);
  },

  go(page) {
    this.page = page;
    location.hash = page;
    $$('#nav .nav-item').forEach((b) => b.classList.toggle('active', b.dataset.page === page));
    $$('.page').forEach((p) => p.classList.toggle('active', p.id === `page-${page}`));
    this.refresh();
  },

  refresh() {
    const map = {
      overview: () => this.loadOverview(), chats: () => this.loadChats(), knowledge: () => this.loadKnowledge(),
      questions: () => this.loadQuestions(), approvals: () => this.loadApprovals(), content: () => this.loadContent(),
      videos: () => this.loadVideos(), analytics: () => this.loadAnalytics(), ads: () => this.loadAds(),
      activity: () => this.loadActivity(), settings: () => this.loadSettings(), playground: () => {},
    };
    (map[this.page] || (() => {}))();
    this.loadOverview(true);
  },

  async poll() {
    if (document.hidden) return;
    await this.loadOverview(true);
    if (['questions', 'approvals', 'overview'].includes(this.page)) this.refresh();
  },

  /* ---------------- overview ---------------- */
  async loadOverview(badgesOnly = false) {
    let d;
    try { d = await api('/api/overview'); } catch (e) { if (!badgesOnly) toast(e.message, 'err'); return; }
    const s = d.stats;
    $('#badge-questions').textContent = s.open_questions || '';
    $('#badge-approvals').textContent = s.pending_approvals || '';
    $('#agent-toggle').checked = !d.paused;
    $('#agent-state').textContent = d.paused ? 'Agent to‘xtatilgan' : 'Agent ishlamoqda';
    $('#agent-state-sub').textContent = d.paused ? 'yoqish uchun bosing' : (d.services.telegram ? 'Telegram ulangan' : 'Telegram ulanmagan');
    if (badgesOnly && this.page !== 'overview') return;

    const cards = [
      ['inbox', 'Kiruvchi xabarlar', s.messages_in_24h, `7 kunda: ${s.messages_in_7d}`, 'var(--cyan)'],
      ['send', 'Agent javoblari', s.replies_24h, `7 kunda: ${s.replies_7d}`, 'var(--violet)'],
      ['help', 'Javobsiz savollar', s.open_questions, s.open_questions ? 'Sizning javobingiz kerak' : 'Hammasi javob berilgan', 'var(--amber)'],
      ['check', 'Kutilayotgan tasdiqlar', s.pending_approvals, 'Postlar, javoblar, xarajatlar', 'var(--rose)'],
      ['chat', 'Faol chatlar', s.allowed_chats, 'ruxsat berilgan', 'var(--mint)'],
      ['book', 'Bilim bazasi', s.knowledge_docs, 'hujjat', 'var(--indigo)'],
      ['megaphone', 'Joylangan postlar', s.published_posts, 'jami', 'var(--cyan)'],
    ];
    $('#stats').innerHTML = cards.map(([ic, label, v, sub, color]) => `
      <div class="card stat" style="--accent:${color}">
        <div class="stat-icon">${svg(ic)}</div>
        <div class="stat-value">${v}</div>
        <div class="stat-label">${label}</div>
        <div class="stat-sub">${sub}</div>
      </div>`).join('') + `<div class="card stat" style="--accent:var(--mint)"><div class="stat-icon">${svg('zap')}</div>
        <div class="stat-value" style="font-size:22px">${d.paused ? '⏸ Pauza' : '▶ Faol'}</div><div class="stat-label">Agent holati</div>
        <div class="stat-sub"><button class="btn btn-sm" onclick="App.toggleAgent(${d.paused})">${d.paused ? 'Yoqish' : 'To‘xtatish'}</button></div></div>`;

    const sv = d.services;
    const row = (on, name, sub) => `<div class="service"><span class="dot ${on ? 'on' : ''}"></span><div class="name">${name}<small>${sub}</small></div><span class="badge ${on ? 'green' : 'rose'}">${on ? 'Ulangan' : 'O‘chiq'}</span></div>`;
    $('#services').innerHTML =
      row(sv.gemini, 'Gemini AI', sv.gemini ? 'Javob, video va strategiya' : '.env: GEMINI_API_KEY') +
      row(sv.telegram, 'Telegram akkaunt', sv.telegram_user || '.env: TG_API_ID + login.py') +
      row(sv.admin_bot, 'Admin-bot', sv.admin_bot ? 'Bildirishnomalar va tasdiqlar' : '.env: ADMIN_BOT_TOKEN, ADMIN_IDS') +
      row(sv.youtube, 'YouTube', sv.youtube_channel || 'youtube_auth.py') +
      row(sv.instagram, 'Instagram', sv.instagram_user || '.env: IG_ACCESS_TOKEN, IG_ACCOUNT_ID') +
      row(sv.meta_ads || sv.google_ads, 'Targetolog Ads', (sv.meta_ads ? 'Meta Ads ' : '') + (sv.google_ads ? 'Google Ads' : '') || '.env: META_ADS_* / GOOGLE_ADS_*');
    $('#overview-feed').innerHTML = feedHtml(d.activity);
  },

  async toggleAgent(on) {
    try { await api(`/api/agent/${on ? 'resume' : 'pause'}`, { method: 'POST' }); toast(on ? 'Agent yoqildi' : 'Agent to‘xtatildi'); }
    catch (e) { toast(e.message, 'err'); }
    this.loadOverview();
  },

  /* ---------------- chats ---------------- */
  bindChats() {
    $$('[data-chat-tab]').forEach((t) => t.addEventListener('click', () => {
      $$('[data-chat-tab]').forEach((x) => x.classList.toggle('active', x === t));
      this.state.chatTab = t.dataset.chatTab;
      this.loadChats();
    }));
    $('#chat-search').addEventListener('input', () => this.renderChats());
    $('#chat-kind').addEventListener('change', () => this.renderChats());
  },

  async loadChats() {
    try {
      this.state.chats = await api('/api/chats');
      if (this.state.chatTab === 'dialogs') {
        $('#chat-list').innerHTML = '<div class="empty"><div class="big">⏳</div>Telegram dialoglari yuklanmoqda…</div>';
        this.state.dialogs = await api('/api/dialogs');
      }
    } catch (e) {
      $('#chat-list').innerHTML = `<div class="empty"><div class="big">🔌</div>${esc(e.message)}<br><span style="font-size:12.5px">.env faylini to'ldiring va <code>login.py</code> ni ishga tushiring</span></div>`;
      return;
    }
    this.renderChats();
  },

  renderChats() {
    const q = $('#chat-search').value.toLowerCase();
    const kind = $('#chat-kind').value;
    let items = this.state.chatTab === 'dialogs' ? (this.state.dialogs || []) : this.state.chats.filter((c) => c.allowed);
    items = items.filter((c) => (!kind || c.kind === kind) && (!q || `${c.title} ${c.username || ''}`.toLowerCase().includes(q)));
    if (!items.length) {
      $('#chat-list').innerHTML = this.state.chatTab === 'allowed'
        ? '<div class="empty"><div class="big">🔒</div>Hali hech bir chatga ruxsat berilmagan.<br>«Telegram dialoglari» bo\'limidan kerakli chatlarni yoqing.</div>'
        : '<div class="empty"><div class="big">🔎</div>Hech narsa topilmadi</div>';
      return;
    }
    $('#chat-list').innerHTML = items.slice(0, 300).map((c) => `
      <div class="list-item" data-id="${c.id}">
        ${avatar(c.title, c.id)}
        <div class="meta"><b>${esc(c.title || 'Nomsiz')}</b><span>${KIND[c.kind] || c.kind}${c.username ? ' · @' + esc(c.username) : ''}${c.unread ? ` · <span class="badge cyan">${c.unread} yangi</span>` : ''}</span></div>
        ${c.kind === 'bot' ? '<span class="badge">bot</span>' : `
        <select class="input" style="width:auto;padding:7px 10px" data-mode ${c.kind === 'channel' ? 'disabled title="Kanal postlari doim tasdiq orqali"' : ''}>
          <option value="auto" ${c.mode === 'auto' ? 'selected' : ''}>⚡ Avto</option>
          <option value="approve" ${c.mode === 'approve' ? 'selected' : ''}>✋ Tasdiq</option>
        </select>
        <label class="toggle" title="Ruxsat"><input type="checkbox" data-allow ${c.allowed ? 'checked' : ''}><span></span></label>`}
      </div>`).join('');
    $$('#chat-list .list-item').forEach((el) => {
      const c = items.find((x) => String(x.id) === el.dataset.id);
      const save = async (patch) => {
        try {
          const r = await api('/api/chats', { method: 'POST', body: { id: c.id, title: c.title, username: c.username, kind: c.kind, ...patch } });
          Object.assign(c, r);
          toast(patch.allowed === undefined ? 'Rejim saqlandi' : (r.allowed ? `«${c.title}» ga ruxsat berildi` : `«${c.title}» o'chirildi`));
          this.state.chats = await api('/api/chats');
          if (this.state.chatTab === 'allowed') this.renderChats();
        } catch (e) { toast(e.message, 'err'); }
      };
      el.querySelector('[data-allow]')?.addEventListener('change', (e) => save({ allowed: e.target.checked }));
      el.querySelector('[data-mode]')?.addEventListener('change', (e) => save({ mode: e.target.value }));
    });
  },

  /* ---------------- knowledge ---------------- */
  bindKnowledge() {
    const dz = $('#dropzone'), input = $('#file-input');
    input.addEventListener('change', () => this.uploadFiles(input.files));
    ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
    ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
    dz.addEventListener('drop', (e) => this.uploadFiles(e.dataTransfer.files));
    $('#kb-add-btn').addEventListener('click', (e) => withLoading(e.currentTarget, async () => {
      const title = $('#kb-title').value.trim(), text = $('#kb-text').value.trim();
      if (!title || !text) throw new Error('Sarlavha va matnni kiriting');
      const r = await api('/api/knowledge/text', { method: 'POST', body: { title, text } });
      toast(`«${r.title}» qo'shildi (${r.chunks} bo'lak)`);
      $('#kb-title').value = ''; $('#kb-text').value = '';
      this.loadKnowledge();
    }));
    $('#url-btn').addEventListener('click', (e) => withLoading(e.currentTarget, async () => {
      const url = $('#url-input').value.trim();
      if (!url) throw new Error('URL kiriting');
      const r = await api('/api/knowledge/url', { method: 'POST', body: { url } });
      toast(`«${r.title}» qo'shildi`); $('#url-input').value = ''; this.loadKnowledge();
    }));
    const doSearch = (btn) => withLoading(btn, async () => {
      const q = $('#kb-search').value.trim(); if (!q) return;
      const hits = await api('/api/knowledge/search', { method: 'POST', body: { q } });
      $('#kb-search-results').innerHTML = hits.length ? hits.map((h) => `
        <div class="list-item" style="align-items:flex-start"><span class="badge ${h.score > .6 ? 'green' : h.score > .45 ? 'amber' : 'rose'}">${(h.score * 100).toFixed(0)}%</span>
        <div class="meta"><b>${esc(h.title)}</b><span style="white-space:pre-wrap">${esc(h.text.slice(0, 400))}${h.text.length > 400 ? '…' : ''}</span></div></div>`).join('')
        : '<div class="empty">Hech narsa topilmadi — agent bunday savolni sizga yuboradi</div>';
    });
    $('#kb-search-btn').addEventListener('click', (e) => doSearch(e.currentTarget));
    $('#kb-search').addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch($('#kb-search-btn')); });
  },

  async uploadFiles(files) {
    for (const f of files) {
      const fd = new FormData(); fd.append('file', f);
      toast(`«${f.name}» yuklanmoqda…`, 'info');
      try { const r = await api('/api/knowledge/upload', { method: 'POST', body: fd }); toast(`«${r.title}» qo'shildi (${r.chunks} bo'lak)`); }
      catch (e) { toast(`${f.name}: ${e.message}`, 'err'); }
    }
    $('#file-input').value = '';
    this.loadKnowledge();
  },

  async loadKnowledge() {
    let docs;
    try { docs = await api('/api/knowledge'); } catch (e) { toast(e.message, 'err'); return; }
    $('#kb-count').textContent = docs.length || '';
    const KB_KIND = { file: ['📄', 'Fayl', 'violet'], text: ['📝', 'Matn', 'cyan'], url: ['🌐', 'Sayt', 'amber'], admin_answer: ['🧠', 'Sizning javobingiz', 'green'] };
    $('#kb-list').innerHTML = docs.length ? docs.map((d) => {
      const [ic, label, color] = KB_KIND[d.kind] || ['📄', d.kind, ''];
      return `<div class="list-item"><div class="avatar" style="background:var(--surface-2);font-size:18px">${ic}</div>
        <div class="meta"><b>${esc(d.title)}</b><span>${d.chunks} bo'lak · ${(d.chars / 1000).toFixed(1)}k belgi · ${timeAgo(d.created_at)}</span></div>
        <span class="badge ${color}">${label}</span>
        <button class="btn btn-sm btn-ghost" title="O'chirish" onclick="App.deleteDoc(${d.id})">${svg('trash')}</button></div>`;
    }).join('') : '<div class="empty"><div class="big">📚</div>Baza bo\'sh. Kompaniya haqida ma\'lumot, narxlar, FAQ yuklang — agent shular asosida javob beradi.</div>';
  },

  async deleteDoc(id) {
    if (!confirm('Hujjat bazadan o\'chirilsinmi?')) return;
    try { await api(`/api/knowledge/${id}`, { method: 'DELETE' }); toast('O\'chirildi'); this.loadKnowledge(); } catch (e) { toast(e.message, 'err'); }
  },

  /* ---------------- tabs ---------------- */
  bindTabs() {
    $$('[data-q-tab]').forEach((t) => t.addEventListener('click', () => {
      $$('[data-q-tab]').forEach((x) => x.classList.toggle('active', x === t)); this.state.qTab = t.dataset.qTab; this.loadQuestions();
    }));
    $$('[data-a-tab]').forEach((t) => t.addEventListener('click', () => {
      $$('[data-a-tab]').forEach((x) => x.classList.toggle('active', x === t)); this.state.aTab = t.dataset.aTab; this.loadApprovals();
    }));
  },

  /* ---------------- questions ---------------- */
  async loadQuestions() {
    const box = $('#questions-list');
    if (box.querySelector('textarea:focus')) return; // don't wipe while typing
    let items;
    try { items = await api(`/api/escalations${this.state.qTab ? '?status=' + this.state.qTab : ''}`); } catch (e) { toast(e.message, 'err'); return; }
    const ST = { open: ['amber', 'Javob kutilmoqda'], answered: ['green', 'Javob berildi'], dismissed: ['', 'Yopildi'] };
    box.innerHTML = items.length ? items.map((q) => `
      <div class="card q-card">
        <div class="q-head">${avatar(q.sender_name, q.chat_id)}<div><b>${esc(q.sender_name)}</b><div class="muted" style="font-size:12.5px">${esc(q.chat_title)} · til: ${esc(q.language)}</div></div>
          <span class="badge ${ST[q.status][0]}">${ST[q.status][1]}</span><time>${timeAgo(q.created_at)}</time></div>
        <div class="quote">${esc(q.question)}</div>
        ${q.reason ? `<div class="reason">🧠 ${esc(q.reason)}</div>` : ''}
        ${q.status === 'open' ? `
          <textarea class="input" rows="3" id="ans-${q.id}" placeholder="Javobingizni yozing — agent uni mijoz tiliga moslab yuboradi va bazaga qo'shadi"></textarea>
          <div class="row mt"><button class="btn btn-primary" onclick="App.answer(${q.id}, this)">${svg('reply')}Javob yuborish</button>
          <button class="btn btn-ghost" onclick="App.dismiss(${q.id})">E'tiborsiz qoldirish</button></div>`
        : q.answer ? `<div class="quote" style="border-left-color:var(--mint)"><b>Sizning javobingiz:</b>\n${esc(q.answer)}</div>` : ''}
      </div>`).join('') : '<div class="card empty"><div class="big">🎉</div>Javobsiz savollar yo\'q. Agent hamma narsaga o\'zi javob bermoqda.</div>';
  },

  answer(id, btn) {
    return withLoading(btn, async () => {
      const answer = $(`#ans-${id}`).value.trim();
      if (!answer) throw new Error('Javob yozing');
      await api(`/api/escalations/${id}/answer`, { method: 'POST', body: { answer } });
      toast('Javob yuborildi va bazaga qo\'shildi'); $(`#ans-${id}`).blur(); this.loadQuestions(); this.loadOverview(true);
    });
  },
  async dismiss(id) {
    try { await api(`/api/escalations/${id}/dismiss`, { method: 'POST' }); this.loadQuestions(); this.loadOverview(true); } catch (e) { toast(e.message, 'err'); }
  },

  /* ---------------- approvals ---------------- */
  async loadApprovals() {
    const box = $('#approvals-list');
    let items;
    try { items = await api(`/api/approvals${this.state.aTab ? '?status=' + this.state.aTab : ''}`); } catch (e) { toast(e.message, 'err'); return; }
    const ST = { pending: ['amber', '⏳ Kutilmoqda'], approved: ['cyan', 'Tasdiqlandi'], executed: ['green', '✅ Bajarildi'], rejected: ['rose', '❌ Rad etildi'], failed: ['rose', '⚠️ Xato'] };
    box.innerHTML = items.length ? items.map((a) => {
      const p = a.payload || {};
      let body = '';
      if (a.kind === 'publish_post') body = `<div class="quote post">${esc(p.preview || '')}</div>`;
      else if (a.kind === 'publish_video') body = `
        <div class="row mb"><span class="badge cyan">🎬 ${esc(p.style || '')}</span><span class="badge">⏱ ${esc(p.duration_sec || 0)}s</span><span class="badge violet">📡 ${esc((p.targets || []).join(', '))}</span></div>
        <video src="/media/videos/${p.video_id}.mp4" controls style="width:100%;max-height:320px;border-radius:12px;background:#000;margin-bottom:10px"></video>
        <div class="quote post">${esc(p.description || '')}</div>`;
      else if (a.kind.startsWith('ad_')) {
        const cp = p.ad_copy || {}, aud = p.audience || {};
        body = `<div class="quote post">${cp.headline ? `<b>${esc(cp.headline)}</b>\n` : ''}${esc(cp.primary_text || p.rationale || JSON.stringify(p))}</div>
          ${aud.locations ? `<div class="row mb"><span class="badge">👥 ${aud.age_min || 18}–${aud.age_max || 45}</span><span class="badge cyan">📍 ${esc((aud.locations || []).join(', '))}</span></div>` : ''}
          ${p.rationale ? `<div class="reason">🎯 ${esc(p.rationale)}</div>` : ''}`;
      }
      else if (a.kind === 'send_reply') body = `<div class="quote">${esc(p.question || '')}</div><div class="quote post"><b>Tayyor javob:</b>\n${esc(p.text || '')}</div>`;
      else body = `<div class="quote">${esc(JSON.stringify(p, null, 2))}</div>`;
      return `<div class="card q-card">
        <div class="q-head"><span class="badge violet">${esc(a.kind_label)}</span><b>#${a.id} · ${esc(a.title)}</b><span class="badge ${ST[a.status]?.[0] || ''}">${ST[a.status]?.[1] || a.status}</span><time>${timeAgo(a.created_at)}</time></div>
        ${a.requires_money ? `<div class="money-alert">💰 Pul sarflanadi: ${a.amount ? esc(a.amount + ' ' + (a.currency || '')) : 'miqdor ko‘rsatilmagan'} — diqqat bilan tekshiring</div>` : ''}
        ${body}
        ${a.result && a.status !== 'pending' ? `<div class="reason">${esc(a.result)} ${a.decided_by ? '· ' + esc(a.decided_by) : ''}</div>` : ''}
        ${a.status === 'pending' ? `<div class="row">
          <button class="btn btn-success" onclick="App.decide(${a.id}, true, this)">${svg('check')}Tasdiqlash</button>
          <button class="btn btn-danger" onclick="App.decide(${a.id}, false, this)">${svg('x')}Rad etish</button>
          ${a.kind === 'publish_post' ? `<button class="btn btn-ghost" onclick="App.editPost(${p.post_id})">${svg('edit')}Tahrirlash</button>` : ''}
        </div>` : ''}
      </div>`;
    }).join('') : '<div class="card empty"><div class="big">✨</div>Tasdiq kutayotgan narsa yo\'q</div>';
  },

  decide(id, approve, btn) {
    if (!approve && !confirm('Rad etilsinmi?')) return;
    return withLoading(btn, async () => {
      const r = await api(`/api/approvals/${id}/decide`, { method: 'POST', body: { approve } });
      toast(approve ? (r.status === 'failed' ? `Xato: ${r.result}` : 'Tasdiqlandi') : 'Rad etildi', r.status === 'failed' ? 'err' : 'ok');
      this.loadApprovals(); this.loadOverview(true);
      if (this.page === 'content') this.loadContent();
      if (this.page === 'videos') this.loadVideos();
      if (this.page === 'ads') this.loadAds();
    });
  },

  /* ---------------- content ---------------- */
  bindContent() {
    $('#post-gen-btn').addEventListener('click', (e) => withLoading(e.currentTarget, async () => {
      const channel_id = Number($('#post-channel').value);
      if (!channel_id) throw new Error('Avval «Chatlar» bo\'limida kanalga ruxsat bering');
      const t = $('#post-time').value;
      await api('/api/posts', { method: 'POST', body: {
        channel_id, topic: $('#post-topic').value.trim() || null, instructions: $('#post-instr').value.trim(),
        scheduled_at: t ? new Date(t).toISOString() : null } });
      toast('Post tayyor — tasdiqlash uchun yuborildi');
      $('#post-topic').value = ''; $('#post-instr').value = ''; $('#post-time').value = '';
      this.loadContent(); this.loadOverview(true);
    }));
  },

  async loadContent() {
    let posts, chats;
    try { [posts, chats] = await Promise.all([api('/api/posts'), api('/api/chats')]); } catch (e) { toast(e.message, 'err'); return; }
    const channels = chats.filter((c) => c.allowed && c.kind === 'channel');
    $('#post-channel').innerHTML = channels.length ? channels.map((c) => `<option value="${c.id}">📢 ${esc(c.title)}</option>`).join('') : '<option value="">— ruxsat berilgan kanal yo\'q —</option>';
    const ST = { pending: ['amber', 'Tasdiq kutmoqda'], scheduled: ['cyan', 'Rejalashtirilgan'], published: ['green', 'Joylandi'], rejected: ['rose', 'Rad etilgan'], failed: ['rose', 'Xato'] };
    $('#posts-list').innerHTML = posts.length ? posts.map((p) => `
      <div class="list-item" style="align-items:flex-start;flex-direction:column;gap:10px">
        <div class="row" style="width:100%"><span class="badge ${ST[p.status]?.[0]}">${ST[p.status]?.[1] || p.status}</span>
          <b style="flex:1">${esc(p.topic)}</b><span class="muted" style="font-size:12px">📢 ${esc(p.channel_title)} · ${timeAgo(p.published_at || p.created_at)}</span></div>
        <div class="quote post" style="width:100%;margin:0">${esc(p.text)}</div>
        ${p.scheduled_at && p.status !== 'published' ? `<span class="muted" style="font-size:12.5px">⏰ ${new Date(p.scheduled_at).toLocaleString('uz-UZ')}</span>` : ''}
        ${p.error ? `<span class="badge rose">${esc(p.error)}</span>` : ''}
        ${p.status === 'pending' ? `<div class="row">
          <button class="btn btn-sm btn-success" onclick="App.decide(${p.approval_id}, true, this)">${svg('check')}Tasdiqlash</button>
          <button class="btn btn-sm" onclick="App.editPost(${p.id})">${svg('edit')}Tahrirlash</button>
          <button class="btn btn-sm" onclick="App.regenPost(${p.id}, this)">${svg('refresh')}Qayta yozish</button>
          <button class="btn btn-sm btn-danger" onclick="App.decide(${p.approval_id}, false, this)">${svg('x')}Rad etish</button></div>` : ''}
      </div>`).join('') : '<div class="empty"><div class="big">📝</div>Hali postlar yo\'q. O\'ng tomondagi forma orqali birinchi postni yarating.</div>';
  },

  async editPost(id) {
    const posts = await api('/api/posts');
    const p = posts.find((x) => x.id === id);
    if (!p) return;
    this.openModal(`
      <h3>${svg('edit')}Postni tahrirlash</h3>
      <div class="field"><textarea class="input" id="edit-text" rows="12">${esc(p.text)}</textarea><span class="hint">Telegram formatlash: **qalin**, __kursiv__</span></div>
      <div class="row" style="justify-content:flex-end"><button class="btn btn-ghost" onclick="App.closeModal()">Bekor qilish</button>
      <button class="btn btn-primary" id="edit-save">${svg('save')}Saqlash</button></div>`);
    $('#edit-save').addEventListener('click', (e) => withLoading(e.currentTarget, async () => {
      await api(`/api/posts/${id}`, { method: 'PATCH', body: { text: $('#edit-text').value } });
      toast('Saqlandi'); this.closeModal(); this.refresh();
    }));
  },

  regenPost(id, btn) {
    const instr = prompt('Qanday o\'zgartirish kerak? (ixtiyoriy)', '') ?? null;
    if (instr === null) return;
    return withLoading(btn, async () => {
      await api(`/api/posts/${id}/regenerate`, { method: 'POST', body: { instructions: instr } });
      toast('Qayta yozildi'); this.loadContent();
    });
  },

  openModal(html) { $('#modal-body').innerHTML = html; $('#modal').classList.add('open'); },
  closeModal() { $('#modal').classList.remove('open'); },

  /* ---------------- videos ---------------- */
  bindVideos() {
    $('#vid-gen-btn').addEventListener('click', (e) => withLoading(e.currentTarget, async () => {
      const targets = $$('.vid-target:checked').map((x) => x.value);
      toast('Video tayyorlanmoqda (ssenariy + ovoz + montaj)...', 'info');
      await api('/api/videos', { method: 'POST', body: {
        topic: $('#vid-topic').value.trim() || null,
        style: $('#vid-style').value,
        aspect_ratio: $('#vid-ratio').value,
        language: $('#vid-lang').value,
        targets,
        instructions: $('#vid-instr').value.trim(),
      } });
      toast('Video tayyor — tasdiqlashga yuborildi!');
      $('#vid-topic').value = ''; $('#vid-instr').value = '';
      this.loadVideos(); this.loadOverview(true);
    }));
  },

  async loadVideos() {
    let items;
    try { items = await api('/api/videos'); } catch (e) { toast(e.message, 'err'); return; }
    const ST = { rendering: ['cyan', '⏳ Montaj…'], pending: ['amber', 'Tasdiq kutmoqda'], published: ['green', '✅ Joylandi'], rejected: ['rose', 'Rad etildi'], failed: ['rose', '⚠️ Xato'], ready: ['violet', 'Tayyor'] };
    $('#videos-list').innerHTML = items.length ? items.map((v) => {
      const urls = Object.entries(v.published_urls || {}).map(([k, u]) => `<span class="badge green">${esc(k)}: ${esc(u)}</span>`).join('');
      return `<div class="list-item" style="flex-direction:column;align-items:stretch;gap:12px">
        <div class="row"><span class="badge ${ST[v.status]?.[0] || ''}">${ST[v.status]?.[1] || v.status}</span>
          <b style="flex:1">${esc(v.title || v.topic)}</b>
          <span class="badge violet">${esc(v.style)} · ${esc(v.aspect_ratio)} · ${v.duration_sec}s</span></div>
        ${v.video_path ? `<video src="/media/videos/${v.id}.mp4" poster="/media/thumbs/${v.id}.jpg" controls style="width:100%;max-height:340px;border-radius:12px;background:#000"></video>` : ''}
        <div class="muted" style="font-size:13px;white-space:pre-wrap">${esc((v.description || '').slice(0, 320))}</div>
        ${urls ? `<div class="row">${urls}</div>` : ''}
        ${v.error ? `<span class="badge rose">${esc(v.error)}</span>` : ''}
        <div class="row">
          ${v.status === 'pending' && v.approval_id ? `
            <button class="btn btn-sm btn-success" onclick="App.decide(${v.approval_id}, true, this)">${svg('check')}Tasdiqlash va joylash</button>
            <button class="btn btn-sm btn-danger" onclick="App.decide(${v.approval_id}, false, this)">${svg('x')}Rad etish</button>` : ''}
          <button class="btn btn-sm btn-ghost" onclick="App.deleteVideo(${v.id})">${svg('trash')}O'chirish</button>
        </div>
      </div>`;
    }).join('') : '<div class="empty"><div class="big">🎬</div>Hali videolar yo\'q. O\'ng tomondagi forma orqali birinchi Shorts/Reels videongizni yasang.</div>';
  },

  async deleteVideo(id) {
    if (!confirm('Video o\'chirilsinmi?')) return;
    try { await api(`/api/videos/${id}`, { method: 'DELETE' }); toast('O\'chirildi'); this.loadVideos(); } catch (e) { toast(e.message, 'err'); }
  },

  /* ---------------- analytics ---------------- */
  bindAnalytics() {
    $('#an-refresh-btn').addEventListener('click', (e) => withLoading(e.currentTarget, async () => {
      const r = await api('/api/analytics/refresh', { method: 'POST' });
      toast(`Tahlil tugadi (${r.new_comments} yangi izoh tekshirildi)`);
      this.loadAnalytics();
    }));
  },

  async loadAnalytics() {
    let d;
    try { d = await api('/api/analytics'); } catch (e) { toast(e.message, 'err'); return; }
    const sb = d.sentiment_breakdown || {};
    const total = (sb.positive || 0) + (sb.neutral || 0) + (sb.negative || 0) + (sb.spam || 0);
    const yt = d.platforms?.youtube, ig = d.platforms?.instagram;
    $('#an-stats').innerHTML = [
      ['sparkles', 'Sifat reytingi', `${d.quality_rating}/10`, `Kayfiyat indeksi: ${d.avg_sentiment >= 0 ? '+' : ''}${d.avg_sentiment}`, 'var(--mint)'],
      ['chat', 'Ijobiy izohlar', sb.positive || 0, `Jami ${total} izohdan · 😐 ${sb.neutral || 0}`, 'var(--cyan)'],
      ['help', 'Salbiy / Spam', `${sb.negative || 0} / ${sb.spam || 0}`, 'Shikoyatlar va yashirilgan spam', 'var(--rose)'],
      ['chart', 'YouTube / Instagram', `${yt ? yt.followers : '—'} / ${ig ? ig.followers : '—'}`, 'Obunachilar soni', 'var(--violet)'],
    ].map(([ic, label, v, sub, color]) => `<div class="card stat" style="--accent:${color}"><div class="stat-icon">${svg(ic)}</div><div class="stat-value">${v}</div><div class="stat-label">${label}</div><div class="stat-sub">${sub}</div></div>`).join('');

    $('#an-guidance').textContent = d.learned_guidance || 'Hali avtomatik tuzatish yozilmagan. «Hozir tahlil qilish» tugmasini bosing.';

    const SBADGE = { positive: ['green', '👍 Ijobiy'], neutral: ['', '😐 Neytral'], negative: ['rose', '👎 Salbiy'], spam: ['amber', '🛡 Spam'] };
    $('#an-comments').innerHTML = (d.comments || []).length ? d.comments.map((c) => `
      <div class="list-item" style="flex-direction:column;align-items:stretch;gap:6px">
        <div class="row"><span class="badge violet">${esc(c.platform)}</span><b>${esc(c.author)}</b>
          <span class="badge ${SBADGE[c.sentiment]?.[0] || ''}">${SBADGE[c.sentiment]?.[1] || c.sentiment}</span>
          <span class="badge">🌐 ${esc(c.language)}</span><span class="muted" style="margin-left:auto;font-size:12px">${timeAgo(c.created_at)}</span></div>
        <div style="font-size:13.5px">${esc(c.text)}</div>
        ${c.reply_text ? `<div class="quote" style="margin:4px 0 0;padding:8px 12px;border-left-color:var(--mint)"><b>Agent javobi:</b> ${esc(c.reply_text)}</div>` : ''}
      </div>`).join('') : '<div class="empty"><div class="big">💬</div>Hali tahlil qilingan izohlar yo\'q</div>';

    const SEVB = { info: 'green', warning: 'amber', critical: 'rose' };
    $('#an-insights').innerHTML = (d.insights || []).length ? d.insights.map((i) => `
      <div class="list-item" style="flex-direction:column;align-items:stretch;gap:6px">
        <div class="row"><span class="badge ${SEVB[i.severity] || ''}">${esc(i.severity)}</span>
          ${i.auto_applied ? '<span class="badge cyan">🛠 Avto-tuzatildi</span>' : ''}
          <span class="muted" style="margin-left:auto;font-size:12px">${timeAgo(i.created_at)}</span></div>
        <b>${esc(i.summary)}</b>
        <div class="muted" style="font-size:13px">${esc(i.action_taken)}</div>
      </div>`).join('') : '<div class="empty"><div class="big">📊</div>Hali sifat auditi o\'tkazilmagan</div>';
  },

  /* ---------------- targetolog (ads) ---------------- */
  bindAds() {
    $('#ad-propose-btn').addEventListener('click', (e) => withLoading(e.currentTarget, async () => {
      const goal = $('#ad-goal').value.trim();
      if (!goal) throw new Error('Reklama maqsadini kiriting');
      const daily = $('#ad-daily').value ? Number($('#ad-daily').value) : null;
      const total = $('#ad-total').value ? Number($('#ad-total').value) : null;
      await api('/api/ads/propose', { method: 'POST', body: {
        platform: $('#ad-platform').value, goal, daily_budget: daily, total_budget: total,
        currency: $('#ad-currency').value, extra_notes: $('#ad-notes').value.trim(),
      } });
      toast('Strategiya tayyor — pul sarfi uchun tasdiq so\'raldi!');
      $('#ad-goal').value = ''; $('#ad-notes').value = '';
      this.loadAds(); this.loadOverview(true);
    }));
  },

  async loadAds() {
    let items;
    try { items = await api('/api/ads'); } catch (e) { toast(e.message, 'err'); return; }
    const ST = { pending_approval: ['amber', '💰 Tasdiq kutmoqda'], active: ['green', '🚀 Faol'], paused: ['cyan', '⏸ To‘xtatilgan'], rejected: ['rose', '❌ Rad etilgan'], failed: ['rose', '⚠️ Xato'] };
    $('#ads-list').innerHTML = items.length ? items.map((c) => {
      const aud = c.target_audience || {}, cp = c.ad_copy || {}, m = c.metrics || {};
      return `<div class="list-item" style="flex-direction:column;align-items:stretch;gap:10px">
        <div class="row"><span class="badge violet">${esc(c.platform.toUpperCase())}</span><b>${esc(c.name)}</b>
          <span class="badge ${ST[c.status]?.[0] || ''}">${ST[c.status]?.[1] || c.status}</span>
          <span class="badge amber" style="margin-left:auto">💰 ${c.daily_budget} ${esc(c.currency)}/kun (jami ${c.total_budget})</span></div>
        <div class="quote post" style="margin:0"><b>${esc(cp.headline || '')}</b>\n${esc(cp.primary_text || '')}\n\n📣 CTA: ${esc(cp.call_to_action || '')}</div>
        <div class="row">
          <span class="badge">👥 ${aud.age_min || 18}–${aud.age_max || 45}</span>
          <span class="badge cyan">📍 ${esc((aud.locations || []).join(', '))}</span>
          ${(aud.interests || []).slice(0, 4).map((x) => `<span class="badge">${esc(x)}</span>`).join('')}
        </div>
        ${m.impressions ? `<div class="row"><span class="badge green">👁 ${m.impressions}</span><span class="badge">🖱 ${m.clicks} (CTR ${m.ctr}%)</span><span class="badge amber">💸 ${m.spend}</span></div>` : ''}
        ${c.ai_notes ? `<div class="reason" style="margin:0">🧠 ${esc(c.ai_notes)}</div>` : ''}
        <div class="row">
          ${c.status === 'pending_approval' && c.approval_id ? `
            <button class="btn btn-sm btn-success" onclick="App.decide(${c.approval_id}, true, this)">${svg('check')}Tasdiqlash (pul sarfi)</button>
            <button class="btn btn-sm btn-danger" onclick="App.decide(${c.approval_id}, false, this)">${svg('x')}Rad etish</button>` : ''}
          ${c.status === 'active' ? `
            <button class="btn btn-sm" onclick="App.adBudget(${c.id}, ${c.daily_budget})">💰 Byudjetni o'zgartirish</button>
            <button class="btn btn-sm btn-danger" onclick="App.adPause(${c.id}, this)">⏸ To'xtatish</button>` : ''}
          ${c.status === 'paused' ? `<button class="btn btn-sm btn-success" onclick="App.adResume(${c.id}, this)">▶ Qayta yoqish (tasdiq bilan)</button>` : ''}
        </div>
      </div>`;
    }).join('') : '<div class="empty"><div class="big">🎯</div>Hali reklama kampaniyalari yo\'q. O\'ng tomondan maqsadni yozing — Targetolog strategiya tuzib tasdiqqa yuboradi.</div>';
  },

  async adBudget(id, cur) {
    const val = prompt('Yangi kunlik byudjet:', String(cur));
    if (!val || isNaN(Number(val))) return;
    try { await api(`/api/ads/${id}/budget`, { method: 'POST', body: { daily_budget: Number(val) } }); toast('Byudjet o\'zgarishi tasdiqqa yuborildi!'); this.loadOverview(true); }
    catch (e) { toast(e.message, 'err'); }
  },
  adPause(id, btn) {
    return withLoading(btn, async () => { await api(`/api/ads/${id}/pause`, { method: 'POST' }); toast('Reklama to\'xtatildi'); this.loadAds(); });
  },
  adResume(id, btn) {
    return withLoading(btn, async () => { await api(`/api/ads/${id}/resume`, { method: 'POST' }); toast('Qayta yoqish tasdiqqa yuborildi!'); this.loadOverview(true); });
  },

  /* ---------------- playground ---------------- */
  bindPlayground() {
    const send = () => this.pgSend();
    $('#pg-send').addEventListener('click', send);
    $('#pg-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
    $('#pg-clear').addEventListener('click', () => { this.state.pg = []; this.renderPg(); });
  },

  renderPg(typing = false) {
    const box = $('#pg-msgs');
    if (!this.state.pg.length && !typing) {
      box.innerHTML = '<div class="empty"><div class="big">💬</div>Mijoz sifatida biror narsa yozing.<br>Masalan: «Assalomu alaykum, narxlaringiz qanday?» yoki «Привет, сколько стоит доставка?»</div>';
      return;
    }
    box.innerHTML = this.state.pg.map((m) => {
      if (m.role === 'user') return `<div class="bubble user">${esc(m.text)}</div>`;
      const meta = m.meta;
      const metaHtml = meta ? `<div class="bubble-meta">
        <span class="badge">🌐 ${esc(meta.language)}</span>
        <span class="badge ${meta.confidence >= .75 ? 'green' : meta.confidence >= .5 ? 'amber' : 'rose'}">ishonch ${(meta.confidence * 100).toFixed(0)}%</span>
        ${meta.escalate ? '<span class="badge amber">❓ adminga yuboriladi</span>' : ''}
        ${!meta.should_reply ? '<span class="badge">🤐 javob bermaydi</span>' : ''}
        ${(meta.sources || []).slice(0, 2).map((s) => `<span class="badge violet">📚 ${esc(s.title)}</span>`).join('')}
        </div>${meta.reason ? `<div class="reason" style="margin:6px 0 0">🧠 ${esc(meta.reason)}</div>` : ''}` : '';
      return `<div class="bubble agent">${esc(m.text || '—')}${metaHtml}</div>`;
    }).join('') + (typing ? '<div class="typing"><i></i><i></i><i></i></div>' : '');
    box.scrollTop = box.scrollHeight;
  },

  async pgSend() {
    const input = $('#pg-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    this.state.pg.push({ role: 'user', text });
    this.renderPg(true);
    try {
      const r = await api('/api/playground', { method: 'POST', body: {
        context: $('#pg-context').value,
        messages: this.state.pg.map((m) => ({ role: m.role, text: m.text })) } });
      this.state.pg.push({ role: 'agent', text: r.should_reply ? r.reply : '', meta: r });
    } catch (e) {
      this.state.pg.push({ role: 'agent', text: `⚠️ ${e.message}` });
    }
    this.renderPg();
  },

  /* ---------------- activity ---------------- */
  async loadActivity() {
    try { $('#activity-feed').innerHTML = feedHtml(await api('/api/activity')); } catch (e) { toast(e.message, 'err'); }
  },

  /* ---------------- settings ---------------- */
  bindSettings() {
    $('#settings-save').addEventListener('click', (e) => withLoading(e.currentTarget, async () => {
      const out = {};
      $$('[data-s]').forEach((el) => {
        const path = el.dataset.s.split('.');
        let v;
        if (el.type === 'checkbox') v = el.checked;
        else if (el.type === 'number') v = el.value === '' ? null : Number(el.value);
        else if (el.dataset.type === 'list') v = el.value.split(',').map((x) => x.trim()).filter(Boolean);
        else if (el.dataset.type === 'int') v = el.value ? Number(el.value) : null;
        else v = el.value;
        let node = out;
        path.slice(0, -1).forEach((k) => { node[k] = node[k] || {}; node = node[k]; });
        node[path.at(-1)] = v;
      });
      this.state.settings = await api('/api/settings', { method: 'PUT', body: out });
      toast('Sozlamalar saqlandi');
    }));
  },

  async loadSettings() {
    let s, chats;
    try { [s, chats] = await Promise.all([api('/api/settings'), api('/api/chats')]); } catch (e) { toast(e.message, 'err'); return; }
    this.state.settings = s;
    const channels = chats.filter((c) => c.allowed && c.kind === 'channel');
    $('#settings-channel').innerHTML = '<option value="">— birinchi kanal —</option>' + channels.map((c) => `<option value="${c.id}">${esc(c.title)}</option>`).join('');
    $$('[data-s]').forEach((el) => {
      const v = el.dataset.s.split('.').reduce((n, k) => (n == null ? n : n[k]), s);
      if (el.type === 'checkbox') el.checked = !!v;
      else if (el.dataset.type === 'list') el.value = (v || []).join(', ');
      else el.value = v ?? '';
    });
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
