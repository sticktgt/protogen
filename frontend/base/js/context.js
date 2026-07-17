import { apiFetch } from './api.js';

let cachedContext = null;

export async function getContext({ refresh = false } = {}) {
  if (!cachedContext || refresh) {
    cachedContext = await apiFetch('/api/session/context');
  }
  return cachedContext;
}

export function clearContextCache() {
  cachedContext = null;
}

export function currentWorkspaceId(context) {
  return context?.workspace?.id || null;
}
