import { apiFetch } from './api.js';
import { getContext } from './context.js';

export async function initLayout(activePageId = '') {
  const context = await getContext();
  renderSidebar(context, activePageId);
  renderTopbar(context, activePageId);
}

function renderSidebar(context, activePageId) {
  const container = document.querySelector('[data-sidebar]');
  if (!container) return;

  if (!context.menu.length) {
    container.innerHTML = '<div class="muted sidebar-empty">Нет модулей в меню</div>';
    return;
  }

  container.innerHTML = context.menu.map(link => {
    const href = `/${link.path}`;
    const active = link.id === activePageId ? ' active' : '';
    const icon = link.icon ? `${link.icon} ` : '';
    return `<a class="sidebar-link${active}" href="${href}">${icon}${link.title}</a>`;
  }).join('');
}

function renderTopbar(context, activePageId) {
  const container = document.querySelector('[data-topbar]');
  if (!container) return;

  const appName = context.app?.name || 'ProtoArchitect';
  const workspaceName = context.workspace?.name || 'workspace не выбран';
  const userName = context.user?.display_name || context.user?.username || '';
  const adminLink = context.user?.is_admin
    ? '<a class="topbar-link" href="/base/admin.html">Администрирование</a>'
    : '';

  container.innerHTML = `
    <div class="topbar-left">
      <a class="topbar-brand" href="/">${appName}</a>
      <span class="topbar-workspace">${workspaceName}</span>
    </div>
    <nav class="topbar-menu" aria-label="Системное меню">
      <a class="topbar-link${activePageId === 'base.workspace_open' ? ' active' : ''}" href="/base/workspace-open.html">Открыть workspace</a>
      <a class="topbar-link${activePageId === 'base.workspace_create' ? ' active' : ''}" href="/base/workspace-create.html">Создать workspace</a>
      <a class="topbar-link${activePageId === 'base.settings' ? ' active' : ''}" href="/base/settings.html">Настройки</a>
      ${adminLink}
      <span class="topbar-user">${userName}</span>
      <button class="btn" data-logout>Выйти</button>
    </nav>
  `;

  container.querySelector('[data-logout]')?.addEventListener('click', async () => {
    await apiFetch('/api/auth/logout', { method: 'POST' });
    window.location.href = '/login';
  });
}
