import { getContext, currentWorkspaceId } from './context.js';

export async function getPage(pageId) {
  const context = await getContext();
  return context.pages.find(page => page.id === pageId) || null;
}

export async function navigateToPage(pageId, params = {}) {
  const context = await getContext();
  const page = context.pages.find(item => item.id === pageId);
  if (!page) {
    throw new Error(`Page is not registered: ${pageId}`);
  }
  const url = new URL(`/${page.path}`, window.location.origin);
  const workspaceId = params.workspace_id || currentWorkspaceId(context);
  if (workspaceId) {
    url.searchParams.set('workspace_id', workspaceId);
  }
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null) {
      url.searchParams.set(key, value);
    }
  });
  window.location.href = url.toString();
}

export function getQueryParam(name) {
  return new URLSearchParams(window.location.search).get(name);
}
