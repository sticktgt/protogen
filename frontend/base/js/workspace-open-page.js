import { apiFetch } from './api.js';
import { clearContextCache } from './context.js';
import { initLayout } from './layout.js';
import { showToast } from './ui.js';

await initLayout('base.workspace_open');

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function workspaceCard(workspace, currentWorkspaceId) {
  const isCurrent = workspace.id === currentWorkspaceId;
  const description = workspace.description || 'Комментарий не задан.';
  return `
    <div class="card workspace-card${isCurrent ? ' workspace-card-current' : ''}">
      <div class="workspace-card-header">
        <div>
          <div class="card-title">${escapeHtml(workspace.name)}</div>
          <p class="muted">id: ${escapeHtml(workspace.id)}</p>
        </div>
        ${isCurrent ? '<span class="badge">текущий</span>' : ''}
      </div>
      <p>${escapeHtml(description)}</p>
      <p class="muted">Владелец: ${escapeHtml(workspace.owner || '')} · Доступ: ${escapeHtml(workspace.access_type || '')}</p>
      <button class="btn btn-primary" data-open-workspace="${escapeHtml(workspace.id)}">Открыть</button>
    </div>
  `;
}

async function loadWorkspaces() {
  const data = await apiFetch('/api/workspaces');
  const container = document.querySelector('[data-workspaces]');
  if (!data.workspaces.length) {
    container.innerHTML = '<div class="card"><p class="muted">Доступных workspace пока нет.</p></div>';
    return;
  }
  container.innerHTML = data.workspaces
    .map(workspace => workspaceCard(workspace, data.current_workspace_id))
    .join('');
  container.querySelectorAll('[data-open-workspace]').forEach(button => {
    button.addEventListener('click', async () => {
      await apiFetch(`/api/workspaces/${button.dataset.openWorkspace}/open`, { method: 'POST' });
      clearContextCache();
      showToast('Workspace открыт');
      setTimeout(() => window.location.href = '/', 400);
    });
  });
}

await loadWorkspaces();
