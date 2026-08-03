import { apiFetch } from './api.js';
import { clearContextCache } from './context.js';
import { initLayout } from './layout.js';
import { showToast } from './ui.js';

await initLayout('base.workspace_create');

const form = document.querySelector('[data-create-workspace]');
const cancelButton = document.querySelector('[data-cancel-create-workspace]');

function returnToPreviousPage() {
  const params = new URLSearchParams(window.location.search);
  const returnTo = params.get('return_to');
  if (returnTo && returnTo.startsWith('/')) {
    const target = new URL(returnTo, window.location.origin);
    if (target.pathname !== window.location.pathname) {
      window.location.href = target.toString();
      return;
    }
  }
  if (document.referrer) {
    const referrer = new URL(document.referrer);
    if (referrer.origin === window.location.origin && referrer.pathname !== window.location.pathname) {
      window.location.href = referrer.toString();
      return;
    }
  }
  window.location.href = '/';
}

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

cancelButton?.addEventListener('click', () => {
  returnToPreviousPage();
});
