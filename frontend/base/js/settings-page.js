import { apiFetch } from './api.js';
import { initLayout } from './layout.js';
import { showToast } from './ui.js';

await initLayout('base.settings');

const textarea = document.querySelector('[data-settings]');
const form = document.querySelector('[data-settings-form]');
const data = await apiFetch('/api/users/me/settings');
textarea.value = JSON.stringify(data.settings, null, 2);

form?.addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const settings = JSON.parse(textarea.value || '{}');
    await apiFetch('/api/users/me/settings', {
      method: 'PUT',
      body: JSON.stringify({ settings })
    });
    showToast('Настройки сохранены');
  } catch (error) {
    showToast(error.message);
  }
});
