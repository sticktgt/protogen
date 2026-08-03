import { apiFetch } from './api.js';
import { initLayout } from './layout.js';
import { showToast } from './ui.js';

await initLayout('base.admin');

let accessState = {
  users: [],
  workspaces: [],
  selectedUsername: null,
  filter: '',
  deleteFilter: '',
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function selectedUser() {
  return accessState.users.find(user => user.username === accessState.selectedUsername) || null;
}

function workspaceIds(user, accessType) {
  return new Set(user?.workspaces?.[accessType] || []);
}

async function loadAdminData() {
  const payload = await apiFetch('/api/admin/workspace-access');
  accessState.users = payload.users || [];
  accessState.workspaces = payload.workspaces || [];
  if (!accessState.selectedUsername && accessState.users.length) {
    accessState.selectedUsername = accessState.users[0].username;
  }
  if (accessState.selectedUsername && !selectedUser()) {
    accessState.selectedUsername = accessState.users[0]?.username || null;
  }
  renderAdminPage();
}

function renderAdminPage() {
  renderUsers();
  renderUserEditor();
  renderWorkspaceAccess();
  renderWorkspaceDeletion();
}

function renderUsers() {
  const container = document.querySelector('[data-users]');
  if (!container) return;
  if (!accessState.users.length) {
    container.innerHTML = '<p class="muted">Пользователи не найдены.</p>';
    return;
  }
  container.innerHTML = accessState.users.map(user => {
    const active = user.username === accessState.selectedUsername ? ' active' : '';
    const adminLabel = user.is_admin ? ' · admin' : '';
    return `
      <button class="admin-user-row${active}" data-select-user="${escapeHtml(user.username)}" type="button">
        <strong>${escapeHtml(user.display_name || user.username)}</strong>
        <span class="muted">${escapeHtml(user.username)}${adminLabel}</span>
      </button>
    `;
  }).join('');
  container.querySelectorAll('[data-select-user]').forEach(button => {
    button.addEventListener('click', () => {
      accessState.selectedUsername = button.dataset.selectUser;
      renderAdminPage();
    });
  });
}

function renderUserEditor() {
  const container = document.querySelector('[data-user-editor]');
  if (!container) return;
  const user = selectedUser();
  if (!user) {
    container.innerHTML = '<p class="muted">Выберите пользователя.</p>';
    return;
  }
  container.innerHTML = `
    <form data-edit-user-form="${escapeHtml(user.username)}">
      <div class="admin-user-editor-grid">
        <div class="form-row">
          <label>username</label>
          <input value="${escapeHtml(user.username)}" disabled>
        </div>
        <div class="form-row">
          <label>display name</label>
          <input name="display_name" value="${escapeHtml(user.display_name || user.username)}">
        </div>
        <div class="form-row">
          <label>новый password</label>
          <input name="password" type="password" placeholder="Оставьте пустым, чтобы не менять">
        </div>
        <div class="form-row">
          <label>тип пользователя</label>
          <input value="${user.is_admin ? 'admin' : 'user'}" disabled>
        </div>
      </div>
      <button class="btn btn-primary" type="submit">Сохранить пользователя</button>
    </form>
  `;
  container.querySelector('[data-edit-user-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const response = await apiFetch(`/api/admin/users/${encodeURIComponent(user.username)}`, {
      method: 'PUT',
      body: JSON.stringify({
        display_name: form.get('display_name') ?? '',
        password: form.get('password') || null,
      }),
    });
    updateUserInState(response.user);
    showToast('Пользователь сохранен');
    renderAdminPage();
  });
}

function updateUserInState(updatedUser) {
  const index = accessState.users.findIndex(user => user.username === updatedUser.username);
  if (index >= 0) {
    accessState.users[index] = updatedUser;
  } else {
    accessState.users.push(updatedUser);
  }
}

function renderWorkspaceAccess() {
  renderAccessUsers();
  renderAccessWorkspaces();
}

function renderAccessUsers() {
  const container = document.querySelector('[data-access-users]');
  if (!container) return;
  if (!accessState.users.length) {
    container.innerHTML = '<p class="muted">Пользователи не найдены.</p>';
    return;
  }
  container.innerHTML = accessState.users.map(user => {
    const active = user.username === accessState.selectedUsername ? ' active' : '';
    const ownedCount = user.workspaces?.owned?.length || 0;
    const sharedCount = user.workspaces?.shared?.length || 0;
    return `
      <button class="workspace-access-user${active}" data-select-access-user="${escapeHtml(user.username)}" type="button">
        <strong>${escapeHtml(user.display_name || user.username)}</strong>
        <span class="muted">${escapeHtml(user.username)}${user.is_admin ? ' · admin' : ''}</span>
        <span class="text-sm muted">owned: ${ownedCount} · shared: ${sharedCount}</span>
      </button>
    `;
  }).join('');
  container.querySelectorAll('[data-select-access-user]').forEach(button => {
    button.addEventListener('click', () => {
      accessState.selectedUsername = button.dataset.selectAccessUser;
      renderAdminPage();
    });
  });
}

function renderAccessWorkspaces() {
  const container = document.querySelector('[data-access-workspaces]');
  if (!container) return;
  const user = selectedUser();
  if (!user) {
    container.innerHTML = '<p class="muted">Выберите пользователя.</p>';
    return;
  }
  const owned = workspaceIds(user, 'owned');
  const shared = workspaceIds(user, 'shared');
  const filter = accessState.filter.trim().toLowerCase();
  const workspaces = accessState.workspaces.filter(workspace => {
    if (!filter) return true;
    return `${workspace.name || ''} ${workspace.id || ''}`.toLowerCase().includes(filter);
  });
  if (!workspaces.length) {
    container.innerHTML = '<p class="muted">Workspace не найдены.</p>';
    return;
  }
  container.innerHTML = workspaces.map(workspace => {
    const isOwned = owned.has(workspace.id);
    const isShared = shared.has(workspace.id);
    const checked = isOwned || isShared ? ' checked' : '';
    const disabled = isOwned ? ' disabled' : '';
    const rowClass = isOwned ? ' workspace-access-row-owned' : '';
    const accessLabel = isOwned ? 'owned' : (isShared ? 'shared' : 'нет доступа');
    return `
      <label class="workspace-access-row${rowClass}">
        <input type="checkbox" data-workspace-access-checkbox value="${escapeHtml(workspace.id)}"${checked}${disabled}>
        <span>
          <strong>${escapeHtml(workspace.name || workspace.id)}</strong>
          <span class="muted">id: ${escapeHtml(workspace.id)}</span>
          <span class="text-sm muted">Владелец: ${escapeHtml(workspace.owner || '')}</span>
        </span>
        <span class="badge">${accessLabel}</span>
      </label>
    `;
  }).join('');
  container.querySelectorAll('[data-workspace-access-checkbox]').forEach(input => {
    input.addEventListener('change', () => {
      const currentUser = selectedUser();
      if (!currentUser) return;
      const currentOwned = workspaceIds(currentUser, 'owned');
      if (currentOwned.has(input.value)) return;
      const nextShared = new Set(currentUser.workspaces?.shared || []);
      if (input.checked) {
        nextShared.add(input.value);
      } else {
        nextShared.delete(input.value);
      }
      currentUser.workspaces = currentUser.workspaces || { owned: [], shared: [] };
      currentUser.workspaces.shared = Array.from(nextShared);
      renderWorkspaceAccess();
    });
  });
}

function renderWorkspaceDeletion() {
  const container = document.querySelector('[data-delete-workspaces]');
  if (!container) return;
  const filter = accessState.deleteFilter.trim().toLowerCase();
  const workspaces = accessState.workspaces.filter(workspace => {
    if (!filter) return true;
    return `${workspace.name || ''} ${workspace.id || ''}`.toLowerCase().includes(filter);
  });
  if (!workspaces.length) {
    container.innerHTML = '<p class="muted">Workspace не найдены.</p>';
    return;
  }
  container.innerHTML = workspaces.map(workspace => `
    <div class="workspace-delete-row">
      <div>
        <strong>${escapeHtml(workspace.name || workspace.id)}</strong>
        <div class="muted">id: ${escapeHtml(workspace.id)} · владелец: ${escapeHtml(workspace.owner || '')}</div>
      </div>
      <button class="btn btn-danger" data-admin-delete-workspace="${escapeHtml(workspace.id)}" type="button">Удалить</button>
    </div>
  `).join('');
  container.querySelectorAll('[data-admin-delete-workspace]').forEach(button => {
    button.addEventListener('click', async () => {
      const workspaceId = button.dataset.adminDeleteWorkspace;
      const message = `Удалить workspace ${workspaceId}?\n\nПеред удалением содержимое workspace, кроме папки .protoarchitect, будет сохранено в ZIP-архив в data/workspaces.`;
      if (!window.confirm(message)) {
        return;
      }
      const response = await apiFetch(`/api/admin/workspaces/${encodeURIComponent(workspaceId)}`, { method: 'DELETE' });
      showToast(`Workspace удален. Архив: ${response.archive}`);
      await loadAdminData();
    });
  });
}

async function saveWorkspaceAccess() {
  const user = selectedUser();
  if (!user) return;
  const response = await apiFetch(`/api/admin/users/${encodeURIComponent(user.username)}/shared-workspaces`, {
    method: 'PUT',
    body: JSON.stringify({ workspace_ids: user.workspaces?.shared || [] }),
  });
  updateUserInState(response.user);
  showToast('Shared-доступ сохранен');
  renderAdminPage();
}

await loadAdminData();

document.querySelector('[data-create-user]')?.addEventListener('submit', async event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const response = await apiFetch('/api/admin/users', {
    method: 'POST',
    body: JSON.stringify({
      username: form.get('username'),
      display_name: form.get('display_name') || null,
      password: form.get('password'),
      is_admin: form.get('is_admin') === 'on',
    }),
  });
  event.currentTarget.reset();
  accessState.selectedUsername = response.user.username;
  showToast('Пользователь добавлен');
  await loadAdminData();
});

document.querySelector('[data-workspace-filter]')?.addEventListener('input', event => {
  accessState.filter = event.target.value;
  renderAccessWorkspaces();
});

document.querySelector('[data-delete-workspace-filter]')?.addEventListener('input', event => {
  accessState.deleteFilter = event.target.value;
  renderWorkspaceDeletion();
});

document.querySelector('[data-save-workspace-access]')?.addEventListener('click', async () => {
  try {
    await saveWorkspaceAccess();
  } catch (error) {
    showToast(error.message);
  }
});
