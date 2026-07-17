import { apiFetch } from './api.js';
import { showToast } from './ui.js';

const form = document.querySelector('[data-login-form]');

form?.addEventListener('submit', async event => {
  event.preventDefault();
  const formData = new FormData(form);
  try {
    await apiFetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        username: formData.get('username'),
        password: formData.get('password')
      })
    });
    window.location.href = '/';
  } catch (error) {
    showToast(error.message);
  }
});
