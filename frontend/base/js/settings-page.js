import { apiFetch } from './api.js';
import { initLayout } from './layout.js';
import { showToast } from './ui.js';

const LLM_PROVIDERS = [
  'ollama-cloud',
  'ollama',
  'lmstudio',
  'openai',
  'anthropic',
  'gemini',
  'openrouter',
  'opencode',
  'openai-compatible',
];

const DEFAULT_PROVIDER = 'ollama-cloud';
const API_KEY_MASK = '********';

await initLayout('base.settings');

const form = document.querySelector('[data-settings-form]');
const providerSelect = document.querySelector('[data-llm-provider]');
const modelInput = document.querySelector('[data-llm-model]');
const baseUrlInput = document.querySelector('[data-llm-base-url]');
const apiKeyInput = document.querySelector('[data-llm-api-key]');
const cancelButton = document.querySelector('[data-cancel-settings]');

let currentSettings = {};
let currentApiKey = '';

function renderProviderOptions(selectedProvider) {
  providerSelect.innerHTML = LLM_PROVIDERS.map(provider => {
    const selected = provider === selectedProvider ? ' selected' : '';
    return `<option value="${provider}"${selected}>${provider}</option>`;
  }).join('');
}

function getLlmSettings(settings) {
  const llm = settings.llm || {};
  return {
    provider: llm.provider || DEFAULT_PROVIDER,
    model: llm.model || llm.default_model || '',
    base_url: llm.base_url || '',
    api_key: llm.api_key || '',
  };
}

function fillForm(settings) {
  const llm = getLlmSettings(settings);
  currentApiKey = llm.api_key;

  renderProviderOptions(llm.provider);
  modelInput.value = llm.model;
  baseUrlInput.value = llm.base_url;
  apiKeyInput.value = llm.api_key ? API_KEY_MASK : '';
}

function normalizeOptional(value) {
  const trimmed = String(value || '').trim();
  return trimmed || null;
}

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

function collectSettings() {
  const provider = providerSelect.value;
  const model = modelInput.value.trim();

  if (!provider) {
    throw new Error('Provider обязателен');
  }
  if (!model) {
    throw new Error('Model обязателен');
  }

  const nextSettings = structuredClone(currentSettings);
  const llm = { ...(nextSettings.llm || {}) };

  llm.provider = provider;
  llm.model = model;

  const baseUrl = normalizeOptional(baseUrlInput.value);
  if (baseUrl) {
    llm.base_url = baseUrl;
  } else {
    delete llm.base_url;
  }

  const apiKeyValue = apiKeyInput.value;
  if (apiKeyValue === API_KEY_MASK && currentApiKey) {
    llm.api_key = currentApiKey;
  } else if (apiKeyValue.trim()) {
    llm.api_key = apiKeyValue;
  } else {
    delete llm.api_key;
  }

  nextSettings.llm = llm;
  return nextSettings;
}

async function loadSettings() {
  const data = await apiFetch('/api/users/me/settings');
  currentSettings = data.settings || {};
  fillForm(currentSettings);
}

form?.addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const settings = collectSettings();
    await apiFetch('/api/users/me/settings', {
      method: 'PUT',
      body: JSON.stringify({ settings }),
    });
    showToast('Настройки сохранены');
    setTimeout(returnToPreviousPage, 250);
  } catch (error) {
    showToast(error.message);
  }
});

cancelButton?.addEventListener('click', () => {
  returnToPreviousPage();
});

await loadSettings();
