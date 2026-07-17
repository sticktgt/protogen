import { getContext, currentWorkspaceId } from '/base/js/context.js';
import { initLayout } from '/base/js/layout.js';
import { navigateToPage } from '/base/js/navigation.js';
import { showToast } from '/base/js/ui.js';
import { getMessage, saveMessage } from './api.js';

await initLayout('demo_hello.main');
const context = await getContext();
const workspaceId = currentWorkspaceId(context);

const textarea = document.querySelector('[data-message]');
const meta = document.querySelector('[data-meta]');
const form = document.querySelector('[data-message-form]');
const linkButton = document.querySelector('[data-open-links]');

async function load() {
  const data = await getMessage(workspaceId);
  textarea.value = data.message || '';
  meta.textContent = `updated_by: ${data.updated_by || '-'}`;
}

form?.addEventListener('submit', async event => {
  event.preventDefault();
  const data = await saveMessage(workspaceId, textarea.value);
  meta.textContent = `updated_by: ${data.updated_by || '-'}`;
  showToast('Сообщение сохранено в workspace');
});

linkButton?.addEventListener('click', () => navigateToPage('demo_links.main'));

await load();
