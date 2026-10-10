/* ═══════════════════════════════════════════════════════════════
   LeadPulse.ai Calling Platform — Frontend Application Logic
═══════════════════════════════════════════════════════════════ */

const API = '';  // Same origin (Flask serves frontend)
let AUTH_TOKEN = localStorage.getItem('fp_token');
let CURRENT_USER = null;
let CURRENT_PAGE = 'dashboard';
let leadsPage = 1;
let callsPage = 1;
let leadsSearch = '';
let leadsStatusFilter = '';
let callsSearch = '';
let callsStatusFilter = '';
let csvRows = [];
let searchDebounceTimer = null;

// ── API Helper ─────────────────────────────────────────────────

async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (AUTH_TOKEN) headers['Authorization'] = `Bearer ${AUTH_TOKEN}`;
  const res = await fetch(`${API}${path}`, { headers, ...opts });
  if (res.status === 401) {
    logout();
    return null;
  }
  try { return await res.json(); } catch { return null; }
}

async function apiGet(path) { return apiFetch(path); }
async function apiPost(path, body) {
  return apiFetch(path, { method: 'POST', body: JSON.stringify(body) });
}
async function apiPut(path, body) {
  return apiFetch(path, { method: 'PUT', body: JSON.stringify(body) });
}
async function apiDelete(path) {
  return apiFetch(path, { method: 'DELETE' });
}

// ── Toast ──────────────────────────────────────────────────────

function toast(msg, type = 'info', duration = 4000) {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(40px)'; el.style.transition = '0.3s'; setTimeout(() => el.remove(), 300); }, duration);
}

// ── Auth ───────────────────────────────────────────────────────

document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = document.getElementById('login-btn');
  const spinner = document.getElementById('login-spinner');
  const errEl = document.getElementById('login-error');
  btn.querySelector('.btn-text').classList.add('hidden');
  spinner.classList.remove('hidden');
  errEl.classList.add('hidden');

  const res = await apiPost('/api/auth/login', {
    email: document.getElementById('login-email').value,
    password: document.getElementById('login-password').value
  });

  btn.querySelector('.btn-text').classList.remove('hidden');
  spinner.classList.add('hidden');

  if (res && res.token) {
    AUTH_TOKEN = res.token;
    localStorage.setItem('fp_token', AUTH_TOKEN);
    CURRENT_USER = res.user;
    showApp();
  } else {
    errEl.textContent = res?.error || 'Login failed. Check credentials.';
    errEl.classList.remove('hidden');
  }
});

function logout() {
  AUTH_TOKEN = null;
  CURRENT_USER = null;
  localStorage.removeItem('fp_token');
  document.getElementById('app').classList.add('hidden');
  document.getElementById('login-screen').classList.remove('hidden');
}

async function showApp() {
  document.getElementById('login-screen').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  const res = await apiGet('/api/auth/me');
  if (res && res.user) {
    CURRENT_USER = res.user;
    document.getElementById('user-name').textContent = res.user.name;
    document.getElementById('user-role').textContent = res.user.role;
    document.getElementById('user-avatar').textContent = res.user.name[0].toUpperCase();
    if (!['owner', 'admin'].includes(res.user.role)) {
      document.getElementById('nav-team').style.display = 'none';
    }
  }
  navigateTo('dashboard');
}

// ── Navigation ─────────────────────────────────────────────────

function navigateTo(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.remove('hidden');

  const navEl = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');

  const titles = {
    dashboard: 'Dashboard', campaigns: 'Campaigns', leads: 'Lead Management',
    calls: 'Call History', agents: 'AI Agents', slots: 'Calling Slots',
    team: 'Team', plans: 'Plans & Billing', settings: 'Settings'
  };
  document.getElementById('page-title').textContent = titles[page] || page;
  CURRENT_PAGE = page;

  // Close mobile sidebar
  document.getElementById('sidebar').classList.remove('mobile-open');

  const loaders = {
    dashboard: loadDashboard,
    campaigns: loadCampaigns,
    leads: loadLeads,
    calls: loadCalls,
    agents: loadAgents,
    slots: loadSlots,
    team: loadTeam,
    plans: loadPlans,
    settings: loadSettings,
  };
  if (loaders[page]) loaders[page]();
}

// Setup nav click handlers
document.querySelectorAll('.nav-item[data-page]').forEach(item => {
  item.addEventListener('click', (e) => { e.preventDefault(); navigateTo(item.dataset.page); });
});

// Inline link navigation
document.addEventListener('click', (e) => {
  const link = e.target.closest('[data-page]');
  if (link && link.tagName === 'A') { e.preventDefault(); navigateTo(link.dataset.page); }
});

// Sidebar collapse
document.getElementById('sidebar-toggle').addEventListener('click', () => {
  const sidebar = document.getElementById('sidebar');
  const main = document.getElementById('main-content');
  sidebar.classList.toggle('collapsed');
  main.classList.toggle('sidebar-collapsed');
});

// Mobile sidebar
document.getElementById('mobile-menu-btn').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('mobile-open');
});

// ── Theme ──────────────────────────────────────────────────────

function toggleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute('data-theme');
  html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
}

// ── Dashboard ──────────────────────────────────────────────────

async function loadDashboard() {
  const data = await apiGet('/api/dashboard/stats');
  if (!data) return;

  document.getElementById('stat-total-leads').textContent = data.total_leads ?? '—';
  document.getElementById('stat-calls-today').textContent = data.calls_today ?? '—';
  document.getElementById('stat-completed').textContent = data.completed_today ?? '—';
  document.getElementById('stat-campaigns').textContent = data.active_campaigns ?? '—';
  document.getElementById('nav-leads-count').textContent = data.ready_leads ?? '0';

  // Balance
  const bal = data.telnyx_balance;
  document.getElementById('balance-amount').textContent = bal != null ? `$${parseFloat(bal).toFixed(2)}` : 'N/A';
  document.getElementById('balance-plan').textContent = (data.plan || 'Free').toUpperCase();
  if (data.plan_expires_at) {
    const exp = new Date(data.plan_expires_at);
    document.getElementById('balance-plan-expires').textContent = `Expires ${exp.toLocaleDateString('en-IN', {day:'numeric',month:'short',year:'numeric'})}`;
  }

  // Bar chart
  if (data.trend) renderBarChart(data.trend);

  // Recent calls
  renderRecentCalls(data.recent_calls || []);
}

function renderBarChart(trend) {
  const maxVal = Math.max(...trend.map(t => t.calls), 1);
  const container = document.getElementById('bar-chart');
  container.innerHTML = '';
  trend.forEach(t => {
    const pct = Math.max((t.calls / maxVal) * 100, 4);
    const dayLabel = new Date(t.date + 'T00:00:00').toLocaleDateString('en', {weekday: 'short'});
    container.innerHTML += `
      <div class="bar-col">
        <div class="bar" style="height:${pct}%" data-val="${t.calls}"></div>
        <span class="bar-label">${dayLabel}</span>
      </div>`;
  });
}

function renderRecentCalls(calls) {
  const body = document.getElementById('recent-calls-body');
  if (!calls.length) { body.innerHTML = '<tr><td colspan="5" class="empty">No call activity yet</td></tr>'; return; }
  body.innerHTML = calls.map(c => `
    <tr>
      <td class="name-cell">${escHtml(c.lead_name || '—')}</td>
      <td>${escHtml(c.phone || '—')}</td>
      <td>${directionPill(c.direction)}</td>
      <td>${statusPill(c.status)}</td>
      <td>${fmtDate(c.created_at)}</td>
    </tr>`).join('');
}

// ── Campaigns ─────────────────────────────────────────────────

async function loadCampaigns() {
  const data = await apiGet('/api/campaigns');
  const container = document.getElementById('campaigns-list');
  if (!data || !data.campaigns) { container.innerHTML = '<p class="empty">Failed to load</p>'; return; }
  if (!data.campaigns.length) {
    container.innerHTML = `<div class="glass-card" style="text-align:center;padding:60px">
      <p style="color:var(--text-muted);font-size:15px">No campaigns yet</p>
      <button class="btn btn-primary" style="margin-top:16px" onclick="openCreateCampaignModal()">Create First Campaign</button>
    </div>`;
    return;
  }
  container.innerHTML = data.campaigns.map(c => {
    const pct = c.total_leads > 0 ? Math.round((c.called_leads / c.total_leads) * 100) : 0;
    return `
    <div class="campaign-card">
      <div class="campaign-header">
        <div>
          <div class="campaign-name">${escHtml(c.name)}</div>
          <div class="campaign-desc">${escHtml(c.description || '')}</div>
        </div>
        ${statusPill(c.status)}
      </div>
      <div class="campaign-meta">
        <div class="campaign-stat"><span class="campaign-stat-val">${c.total_leads}</span><span class="campaign-stat-label">Total Leads</span></div>
        <div class="campaign-stat"><span class="campaign-stat-val" style="color:var(--green)">${c.called_leads}</span><span class="campaign-stat-label">Called</span></div>
        <div class="campaign-stat"><span class="campaign-stat-val" style="color:var(--red)">${c.failed_leads}</span><span class="campaign-stat-label">Failed</span></div>
      </div>
      <div class="progress-bar-wrap"><div class="progress-bar" style="width:${pct}%"></div></div>
      <div style="font-size:11px;color:var(--text-muted)">${pct}% complete · Created ${fmtDate(c.created_at)}</div>
      <div class="campaign-actions">
        ${c.status === 'draft' || c.status === 'paused' ? `<button class="btn btn-success btn-sm" onclick="launchCampaign('${c.id}')">▶ Launch</button>` : ''}
        ${c.status === 'running' ? `<button class="btn btn-ghost btn-sm" onclick="pauseCampaign('${c.id}')">⏸ Pause</button><button class="btn btn-danger btn-sm" onclick="stopCampaign('${c.id}')">■ Stop</button>` : ''}
        <button class="btn btn-danger btn-sm" onclick="deleteCampaign('${c.id}')">🗑</button>
      </div>
    </div>`;
  }).join('');
}

async function launchCampaign(id) {
  if (!confirm('Launch this campaign? All new leads will be called.')) return;
  const res = await apiPost(`/api/campaigns/${id}/launch`, {});
  if (res && !res.error) { toast(`${res.message}`, 'success'); loadCampaigns(); }
  else toast(res?.error || 'Failed to launch', 'error');
}
async function pauseCampaign(id) {
  const res = await apiPost(`/api/campaigns/${id}/pause`, {});
  if (res && !res.error) { toast('Campaign paused', 'info'); loadCampaigns(); }
  else toast(res?.error || 'Error', 'error');
}
async function stopCampaign(id) {
  if (!confirm('Stop this campaign?')) return;
  const res = await apiPost(`/api/campaigns/${id}/stop`, {});
  if (res && !res.error) { toast('Campaign stopped', 'info'); loadCampaigns(); }
  else toast(res?.error || 'Error', 'error');
}
async function deleteCampaign(id) {
  if (!confirm('Delete this campaign permanently?')) return;
  const res = await apiDelete(`/api/campaigns/${id}`);
  if (res && !res.error) { toast('Campaign deleted', 'success'); loadCampaigns(); }
  else toast(res?.error || 'Error', 'error');
}

function openCreateCampaignModal() { openModal('modal-create-campaign'); }
async function submitCreateCampaign() {
  const name = document.getElementById('camp-name').value.trim();
  if (!name) { toast('Name is required', 'error'); return; }
  const res = await apiPost('/api/campaigns', {
    name,
    description: document.getElementById('camp-desc').value,
    batch_size: parseInt(document.getElementById('camp-batch').value) || 2,
    delay_seconds: parseInt(document.getElementById('camp-delay').value) || 20
  });
  if (res && !res.error) { toast('Campaign created!', 'success'); closeModal('modal-create-campaign'); loadCampaigns(); }
  else toast(res?.error || 'Error', 'error');
}

// ── Leads ──────────────────────────────────────────────────────

async function loadLeads() {
  const params = new URLSearchParams({ page: leadsPage, per_page: 25 });
  if (leadsSearch) params.set('search', leadsSearch);
  if (leadsStatusFilter) params.set('status', leadsStatusFilter);
  const data = await apiGet(`/api/leads?${params}`);
  if (!data) return;

  document.getElementById('nav-leads-count').textContent = data.total || 0;
  renderLeadsTable(data.leads || []);
  renderPagination('leads-pagination', data.page, Math.ceil(data.total / data.per_page), (p) => { leadsPage = p; loadLeads(); });
}

function renderLeadsTable(leads) {
  const body = document.getElementById('leads-body');
  if (!leads.length) { body.innerHTML = '<tr><td colspan="8" class="empty">No leads found. Import or add some!</td></tr>'; return; }
  body.innerHTML = leads.map(l => `
    <tr>
      <td><input type="checkbox" class="lead-check" data-id="${l.id}"/></td>
      <td class="name-cell">${escHtml(l.name || '—')}</td>
      <td>${escHtml(l.phone)}</td>
      <td>${escHtml(l.email || '—')}</td>
      <td>${leadStatusPill(l.status)}</td>
      <td><span style="color:var(--text-muted);font-size:12px">${escHtml(l.lead_source || '—')}</span></td>
      <td style="text-align:center">${l.call_attempts || 0}</td>
      <td>
        <div style="display:flex;gap:6px">
          <button class="btn btn-primary btn-xs" onclick="testCallLead('${escHtml(l.phone)}','${escHtml(l.name || '')}')">📞</button>
          <button class="btn btn-danger btn-xs" onclick="deleteLead('${l.id}')">🗑</button>
        </div>
      </td>
    </tr>`).join('');
}

function testCallLead(phone, name) {
  document.getElementById('test-call-phone').value = phone;
  document.getElementById('test-call-name').value = name;
  openModal('modal-test-call');
}

async function deleteLead(id) {
  if (!confirm('Delete this lead?')) return;
  const res = await apiDelete(`/api/leads/${id}`);
  if (res && !res.error) { toast('Lead deleted', 'success'); loadLeads(); }
  else toast(res?.error || 'Error', 'error');
}

function toggleSelectAllLeads(cb) {
  document.querySelectorAll('.lead-check').forEach(c => c.checked = cb.checked);
}

function searchLeads(val) {
  leadsSearch = val;
  leadsPage = 1;
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(loadLeads, 350);
}
function filterLeads() {
  leadsStatusFilter = document.getElementById('leads-status-filter').value;
  leadsPage = 1;
  loadLeads();
}

function openAddLeadModal() { openModal('modal-add-lead'); }
async function submitAddLead() {
  const phone = document.getElementById('lead-phone').value.trim();
  if (!phone) { toast('Phone is required', 'error'); return; }
  const res = await apiPost('/api/leads', {
    name: document.getElementById('lead-name').value,
    phone,
    email: document.getElementById('lead-email').value,
    business_name: document.getElementById('lead-business').value,
    fitness_goal: document.getElementById('lead-goal').value,
    preferred_time: document.getElementById('lead-time').value,
    lead_source: document.getElementById('lead-source').value,
    status: document.getElementById('lead-status').value,
    notes: document.getElementById('lead-notes').value
  });
  if (res && !res.error) { toast('Lead added!', 'success'); closeModal('modal-add-lead'); loadLeads(); }
  else toast(res?.error || 'Error creating lead', 'error');
}

// ── CSV Import ─────────────────────────────────────────────────

function openImportModal() {
  csvRows = [];
  document.getElementById('csv-preview').classList.add('hidden');
  document.getElementById('import-result').classList.add('hidden');
  document.getElementById('import-btn').classList.add('hidden');
  document.getElementById('csv-file-input').value = '';
  openModal('modal-import');
}

function handleCsvFile(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const lines = text.split('\n').filter(l => l.trim());
    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, '').toLowerCase());
    csvRows = [];
    for (let i = 1; i < lines.length; i++) {
      const vals = lines[i].split(',').map(v => v.trim().replace(/^"|"$/g, ''));
      const row = {};
      headers.forEach((h, idx) => { row[h] = vals[idx] || ''; });
      if (row.phone) csvRows.push(row);
    }
    document.getElementById('csv-count').textContent = `✓ ${csvRows.length} valid rows found`;
    const previewBody = document.getElementById('csv-preview-body');
    previewBody.innerHTML = csvRows.slice(0, 5).map(r => `<tr><td>${escHtml(r.name||'')}</td><td>${escHtml(r.phone||'')}</td><td>${escHtml(r.email||'')}</td></tr>`).join('');
    document.getElementById('csv-preview').classList.remove('hidden');
    document.getElementById('import-btn').classList.remove('hidden');
  };
  reader.readAsText(file);
}

async function submitImport() {
  if (!csvRows.length) return;
  const res = await apiPost('/api/leads/import', {
    rows: csvRows,
    duplicate_policy: document.getElementById('import-dupe-policy').value
  });
  if (res) {
    const el = document.getElementById('import-result');
    el.className = `alert ${res.error ? 'alert-error' : 'alert-success'}`;
    el.textContent = res.error ? res.error : `✓ Imported ${res.accepted} leads. Duplicates: ${res.duplicates}. Rejected: ${res.rejected}.`;
    el.classList.remove('hidden');
    if (!res.error) { loadLeads(); csvRows = []; }
  }
}

// ── Call History ───────────────────────────────────────────────

async function loadCalls() {
  const params = new URLSearchParams({ page: callsPage, per_page: 25 });
  if (callsSearch) params.set('search', callsSearch);
  if (callsStatusFilter) params.set('status', callsStatusFilter);
  const data = await apiGet(`/api/calls?${params}`);
  if (!data) return;
  renderCallsTable(data.calls || []);
  renderPagination('calls-pagination', data.page, Math.ceil(data.total / data.per_page), (p) => { callsPage = p; loadCalls(); });
}

function renderCallsTable(calls) {
  const body = document.getElementById('calls-body');
  if (!calls.length) { body.innerHTML = '<tr><td colspan="7" class="empty">No call records yet</td></tr>'; return; }
  body.innerHTML = calls.map(c => `
    <tr>
      <td class="name-cell">${escHtml(c.lead_name || '—')}</td>
      <td>${escHtml(c.phone || '—')}</td>
      <td>${directionPill(c.direction)}</td>
      <td>${statusPill(c.status)}</td>
      <td><span style="color:var(--text-muted);font-size:12px">${escHtml(c.outcome || '—')}</span></td>
      <td><span style="color:var(--text-muted);font-size:12px">${escHtml(c.campaign_id ? c.campaign_id.slice(0,8) + '…' : '—')}</span></td>
      <td style="color:var(--text-muted);font-size:12px">${fmtDate(c.created_at)}</td>
    </tr>`).join('');
}

function searchCalls(val) {
  callsSearch = val;
  callsPage = 1;
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(loadCalls, 350);
}
function filterCalls() {
  callsStatusFilter = document.getElementById('calls-status-filter').value;
  callsPage = 1;
  loadCalls();
}

// ── Test Call Modal ────────────────────────────────────────────

function openTestCallModal() { openModal('modal-test-call'); }
async function submitTestCall() {
  const phone = document.getElementById('test-call-phone').value.trim();
  const name = document.getElementById('test-call-name').value.trim() || 'Test Contact';
  if (!phone) { toast('Phone number required', 'error'); return; }
  const res = await apiPost('/api/calls/test', { phone, name });
  const el = document.getElementById('test-call-result');
  if (res && !res.error) {
    el.className = 'alert alert-success';
    el.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
      Call scheduled! Event ID: <strong>${res.event_id}</strong>`;
    el.classList.remove('hidden');
    toast(`Call to ${phone} scheduled!`, 'success');
  } else {
    el.className = 'alert alert-error';
    el.textContent = res?.error || 'Failed to schedule call';
    el.classList.remove('hidden');
    toast(res?.error || 'Call failed', 'error');
  }
}

// ── AI Agents ──────────────────────────────────────────────────

async function loadAgents() {
  const container = document.getElementById('agents-list');
  container.innerHTML = '<p style="color:var(--text-muted)">Loading agents...</p>';
  const data = await apiGet('/api/agents');
  if (!data || data.error) {
    container.innerHTML = `<div class="glass-card"><p style="color:var(--red)">${data?.error || 'Failed to load agents'}</p></div>`;
    return;
  }
  if (!data.agents.length) {
    container.innerHTML = '<div class="glass-card" style="text-align:center;padding:60px"><p style="color:var(--text-muted)">No AI Agents found on your Telnyx account.</p></div>';
    return;
  }
  container.innerHTML = data.agents.map(a => `
    <div class="agent-card">
      <div class="agent-header">
        <div class="agent-avatar">🤖</div>
        <div>
          <div class="agent-info-name">${escHtml(a.name || 'Unnamed Agent')}</div>
          <div class="agent-info-model">${escHtml(a.model || 'Unknown Model')} · ${escHtml(a.id)}</div>
        </div>
      </div>
      ${a.greeting ? `<div class="agent-greeting">"${escHtml(a.greeting)}"</div>` : ''}
      <div style="display:flex;gap:8px;margin-top:4px">
        <button class="btn btn-ghost btn-sm" onclick="editAgent('${escHtml(a.id)}')">✏️ Edit</button>
        <button class="btn btn-primary btn-sm" onclick="openTestCallModalWithAgent('${escHtml(a.id)}')">📞 Test Call</button>
      </div>
    </div>`).join('');
}

async function editAgent(id) {
  const data = await apiGet(`/api/agents/${id}`);
  if (!data || data.error) { toast(data?.error || 'Failed to load agent', 'error'); return; }
  document.getElementById('edit-agent-id').value = id;
  document.getElementById('edit-agent-name').value = data.name || '';
  document.getElementById('edit-agent-greeting').value = data.greeting || '';
  document.getElementById('edit-agent-instructions').value = data.instructions || '';
  openModal('modal-edit-agent');
}

async function submitEditAgent() {
  const id = document.getElementById('edit-agent-id').value;
  const res = await apiPut(`/api/agents/${id}`, {
    name: document.getElementById('edit-agent-name').value,
    greeting: document.getElementById('edit-agent-greeting').value,
    instructions: document.getElementById('edit-agent-instructions').value
  });
  if (res && !res.error) { toast('Agent updated!', 'success'); closeModal('modal-edit-agent'); loadAgents(); }
  else toast(res?.error || 'Failed to update', 'error');
}

function openTestCallModalWithAgent(agentId) {
  openModal('modal-test-call');
}

// ── Calling Slots ──────────────────────────────────────────────

async function loadSlots() {
  const container = document.getElementById('slots-list');
  const data = await apiGet('/api/slots');
  if (!data || data.error) { container.innerHTML = '<p class="empty">Failed to load</p>'; return; }
  if (!data.slots.length) {
    container.innerHTML = `<div class="glass-card" style="text-align:center;padding:60px">
      <p style="color:var(--text-muted)">No calling slots configured</p>
      <button class="btn btn-primary" style="margin-top:16px" onclick="openAddSlotModal()">Add First Slot</button>
    </div>`;
    return;
  }
  container.innerHTML = data.slots.map(s => {
    const days = JSON.parse(s.days || '[]');
    return `<div class="slot-card">
      <div class="slot-header">
        <span class="slot-name">${escHtml(s.name)}</span>
        ${s.is_enabled ? '<span class="pill pill-green">Active</span>' : '<span class="pill pill-gray">Disabled</span>'}
      </div>
      <div class="slot-time">${escHtml(s.start_time)} – ${escHtml(s.end_time)}</div>
      <div class="slot-days">${days.map(d => `<span class="slot-day">${d}</span>`).join('')}</div>
      <div style="font-size:11px;color:var(--text-muted)">${escHtml(s.timezone)}</div>
      <button class="btn btn-danger btn-xs" style="align-self:flex-start;margin-top:4px" onclick="deleteSlot('${s.id}')">Delete</button>
    </div>`;
  }).join('');
}

function openAddSlotModal() { openModal('modal-add-slot'); }
async function submitAddSlot() {
  const activeDays = [...document.querySelectorAll('.day-btn.active')].map(b => b.dataset.day);
  const res = await apiPost('/api/slots', {
    name: document.getElementById('slot-name').value || 'Default Slot',
    days: activeDays,
    start_time: document.getElementById('slot-start').value,
    end_time: document.getElementById('slot-end').value,
    timezone: 'Asia/Kolkata'
  });
  if (res && !res.error) { toast('Slot created!', 'success'); closeModal('modal-add-slot'); loadSlots(); }
  else toast(res?.error || 'Error', 'error');
}
async function deleteSlot(id) {
  if (!confirm('Delete this slot?')) return;
  const res = await apiDelete(`/api/slots/${id}`);
  if (res && !res.error) { toast('Deleted', 'success'); loadSlots(); }
  else toast(res?.error || 'Error', 'error');
}

// Days picker toggle
document.getElementById('days-picker').addEventListener('click', (e) => {
  const btn = e.target.closest('.day-btn');
  if (btn) btn.classList.toggle('active');
});

// ── Team ───────────────────────────────────────────────────────

async function loadTeam() {
  const data = await apiGet('/api/team');
  const body = document.getElementById('team-body');
  if (!data || data.error) { body.innerHTML = `<tr><td colspan="6" class="empty">${data?.error || 'Failed to load'}</td></tr>`; return; }
  body.innerHTML = (data.members || []).map(m => `
    <tr>
      <td class="name-cell">${escHtml(m.name)}</td>
      <td>${escHtml(m.email)}</td>
      <td><span class="pill ${m.role === 'owner' ? 'pill-purple' : 'pill-blue'}">${m.role}</span></td>
      <td style="color:var(--text-muted);font-size:12px">${fmtDate(m.created_at)}</td>
      <td>${m.is_active ? '<span class="pill pill-green">Active</span>' : '<span class="pill pill-red">Inactive</span>'}</td>
      <td>${m.role !== 'owner' ? `<button class="btn btn-danger btn-xs" onclick="removeMember('${m.id}')">Remove</button>` : ''}</td>
    </tr>`).join('');
}

function openInviteModal() { openModal('modal-invite'); }
async function submitInvite() {
  const email = document.getElementById('invite-email').value.trim();
  if (!email) { toast('Email required', 'error'); return; }
  const res = await apiPost('/api/team/invite', {
    name: document.getElementById('invite-name').value,
    email,
    role: document.getElementById('invite-role').value
  });
  if (res && !res.error) { toast(res.message, 'success'); closeModal('modal-invite'); loadTeam(); }
  else toast(res?.error || 'Error', 'error');
}

async function removeMember(id) {
  if (!confirm('Remove this team member?')) return;
  const res = await apiDelete(`/api/team/${id}`);
  if (res && !res.error) { toast('Member removed', 'success'); loadTeam(); }
  else toast(res?.error || 'Error', 'error');
}

// ── Plans ──────────────────────────────────────────────────────

async function loadPlans() {
  const data = await apiGet('/api/plans');
  if (!data) return;
  const container = document.getElementById('plans-grid');
  const plans = data.plans || [];
  const current = data.current_plan;
  const exp = data.expires_at ? new Date(data.expires_at).toLocaleDateString('en-IN', {day:'numeric', month:'short', year:'numeric'}) : null;

  container.innerHTML = `
    <div class="glass-card" style="grid-column:1/-1;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:16px">
      <div>
        <div style="font-size:13px;color:var(--text-secondary)">Current Plan</div>
        <div style="font-size:22px;font-weight:800;text-transform:capitalize">${current || 'Free'}</div>
        ${exp ? `<div style="font-size:12px;color:var(--text-muted)">Expires ${exp}</div>` : ''}
      </div>
      <div class="plan-chip" style="font-size:13px;padding:6px 18px">${(current||'free').toUpperCase()}</div>
    </div>
    ${plans.map((p, i) => `
    <div class="plan-card ${i === 1 ? 'featured' : ''}" style="cursor:default">
      <div class="plan-name">${p.name}</div>
      <div class="plan-price"><sup>₹</sup>${p.price.toLocaleString('en-IN')}<sub>/plan</sub></div>
      <ul class="plan-features">${p.features.map(f => `<li>${f}</li>`).join('')}</ul>
      <button class="btn ${i === 1 ? 'btn-primary' : 'btn-ghost'}" onclick="selectPlan('${p.id}')">
        ${current === p.id ? 'Current Plan' : 'Upgrade →'}
      </button>
    </div>`).join('')}`;
}

function selectPlan(id) {
  toast(`To upgrade to the ${id} plan, please contact your account manager or use the billing portal.`, 'info', 5000);
}

// ── Settings ───────────────────────────────────────────────────

async function loadSettings() {
  const data = await apiGet('/api/settings');
  if (!data) return;
  document.getElementById('settings-workspace-name').value = data.workspace_name || '';
  document.getElementById('settings-phone').value = data.telnyx_phone_number || '';
  document.getElementById('settings-assistant-id').value = data.assistant_id || '';
  document.getElementById('settings-batch-size').value = data.batch_size || 2;
  document.getElementById('settings-batch-delay').value = data.batch_delay || 20;
  document.getElementById('settings-countries').value = data.call_countries || 'US,IN';
}

async function saveSettings() {
  const res = await apiPut('/api/settings', {
    workspace_name: document.getElementById('settings-workspace-name').value,
    batch_size: document.getElementById('settings-batch-size').value,
    batch_delay: document.getElementById('settings-batch-delay').value,
    call_countries: document.getElementById('settings-countries').value
  });
  if (res && !res.error) toast('Settings saved!', 'success');
  else toast(res?.error || 'Failed', 'error');
}

async function changePassword() {
  const cp = document.getElementById('settings-current-password').value;
  const np = document.getElementById('settings-new-password').value;
  if (!cp || !np) { toast('Both fields required', 'error'); return; }
  if (np.length < 6) { toast('New password must be at least 6 characters', 'error'); return; }
  const res = await apiPost('/api/auth/change-password', { current_password: cp, new_password: np });
  if (res && !res.error) {
    toast('Password changed!', 'success');
    document.getElementById('settings-current-password').value = '';
    document.getElementById('settings-new-password').value = '';
  } else toast(res?.error || 'Failed', 'error');
}

// ── Modals ─────────────────────────────────────────────────────

function openModal(id) { document.getElementById(id).classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id).classList.add('hidden'); }

// Close on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(overlay.id); });
});

// ── Helpers ────────────────────────────────────────────────────

function escHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function fmtDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
  } catch { return iso; }
}

function statusPill(status) {
  const map = {
    scheduled: 'pill-blue', running: 'pill-orange', completed: 'pill-green',
    failed: 'pill-red', paused: 'pill-orange', stopped: 'pill-gray',
    draft: 'pill-gray', new: 'pill-blue', called: 'pill-purple',
    interested: 'pill-green', booked: 'pill-green', not_interested: 'pill-red',
    no_answer: 'pill-gray', active: 'pill-green'
  };
  return `<span class="pill ${map[status] || 'pill-gray'}">${escHtml(status || '—')}</span>`;
}

function leadStatusPill(status) { return statusPill(status); }

function directionPill(dir) {
  return dir === 'inbound'
    ? `<span class="pill pill-blue">↓ In</span>`
    : `<span class="pill pill-purple">↑ Out</span>`;
}

function renderPagination(containerId, page, totalPages, onPage) {
  const el = document.getElementById(containerId);
  if (!totalPages || totalPages <= 1) { el.innerHTML = ''; return; }
  let html = `<span class="page-info">Page ${page} of ${totalPages}</span>`;
  if (page > 1) html += `<button class="btn btn-ghost btn-sm" onclick="${containerId}_onPage(${page - 1})">← Prev</button>`;
  if (page < totalPages) html += `<button class="btn btn-ghost btn-sm" onclick="${containerId}_onPage(${page + 1})">Next →</button>`;
  el.innerHTML = html;
  window[`${containerId}_onPage`] = onPage;
}

// ── Init ───────────────────────────────────────────────────────

async function checkHealth() {
  const data = await apiGet('/api/health').catch(() => null);
  const chip = document.getElementById('config-status-chip');
  if (chip) {
    if (data && data.telnyx_api_key && data.assistant_configured) {
      chip.innerHTML = '<div class="status-dot green pulse"></div><span>Connected</span>';
    } else {
      chip.innerHTML = '<div class="status-dot orange pulse"></div><span>Partial Config</span>';
    }
  }
}

window.addEventListener('DOMContentLoaded', async () => {
  if (AUTH_TOKEN) {
    showApp();
  }
  setInterval(checkHealth, 30000);
});
