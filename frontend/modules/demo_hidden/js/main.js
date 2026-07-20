import { getContext, currentWorkspaceId } from '/base/js/context.js';
import { initLayout } from '/base/js/layout.js';
import { navigateToPage } from '/base/js/navigation.js';
import { showToast } from '/base/js/ui.js';
import { getStatus, getUserSettings, saveNote } from './api.js';

await initLayout('demo_hidden.main');
const context = await getContext();
const workspaceId = currentWorkspaceId(context);

async function loadStatus() {
  const status = await getStatus(workspaceId);
  document.querySelector('[data-status]').textContent = JSON.stringify(status, null, 2);
  document.querySelector('[data-note]').value = status.note || '';
}

async function loadUserLlmSettings() {
  const data = await getUserSettings();
  const llm = data.settings?.llm || {};
  document.querySelector('[data-llm-provider-view]').textContent = llm.provider || '—';
  document.querySelector('[data-llm-model-view]').textContent = llm.model || llm.default_model || '—';
}

await loadStatus();
await loadUserLlmSettings();

document.querySelector('[data-note-form]')?.addEventListener('submit', async event => {
  event.preventDefault();
  const note = document.querySelector('[data-note]').value;
  await saveNote(workspaceId, note);
  showToast('Заметка сохранена');
  await loadStatus();
});

document.querySelector('[data-open-links]')?.addEventListener('click', () => {
  navigateToPage('demo_links.main');
});
