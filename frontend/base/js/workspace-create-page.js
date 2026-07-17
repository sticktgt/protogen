import { apiFetch } from './api.js';
import { clearContextCache } from './context.js';
import { initLayout } from './layout.js';
import { showToast } from './ui.js';

await initLayout('base.workspace_create');

const form = document.querySelector('[data-create-workspace]');
form?.addEventListener('submit', async event => {
  event.preventDefault();
  const formData = new FormData(form);
  const response = await apiFetch('/api/workspaces', {
    method: 'POST',
    body: JSON.stringify({
      name: formData.get('name'),
      description: formData.get('description') || ''
    })
  });
  clearContextCache();
  showToast(`Workspace создан: ${response.workspace.id}`);
  setTimeout(() => window.location.href = '/', 500);
});
