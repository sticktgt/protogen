import { apiFetch } from './api.js';
import { initLayout } from './layout.js';
import { showToast } from './ui.js';

await initLayout('base.admin');

async function loadUsers() {
  const payload = await apiFetch('/api/admin/users');
  const container = document.querySelector('[data-users]');
  container.innerHTML = payload.users.map(user => `
    <div class="card">
      <strong>${user.display_name || user.username}</strong>
      <div class="muted">${user.username}${user.is_admin ? ' · admin' : ''}</div>
    </div>
  `).join('');
}

async function loadAppConfig() {
  const payload = await apiFetch('/api/admin/app-config');
  document.querySelector('[data-app-config]').value = JSON.stringify(payload.config, null, 2);
}

await loadUsers();
await loadAppConfig();

document.querySelector('[data-create-user]')?.addEventListener('submit', async event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  await apiFetch('/api/admin/users', {
    method: 'POST',
    body: JSON.stringify({
      username: form.get('username'),
      display_name: form.get('display_name') || null,
      password: form.get('password'),
      is_admin: form.get('is_admin') === 'on',
    }),
  });
  event.currentTarget.reset();
  showToast('Пользователь добавлен');
  await loadUsers();
});

document.querySelector('[data-app-config-form]')?.addEventListener('submit', async event => {
  event.preventDefault();
  const raw = document.querySelector('[data-app-config]').value;
  const config = JSON.parse(raw);
  await apiFetch('/api/admin/app-config', {
    method: 'PUT',
    body: JSON.stringify({ config }),
  });
  showToast('app config сохранен');
});
