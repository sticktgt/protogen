import { apiFetch } from '/base/js/api.js';

export function loadModuleConfig() {
  return apiFetch('/api/config/modules/ui_schema');
}

export function loadSummary(workspaceId) {
  return apiFetch(`/api/ui-schema?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function createPage(workspaceId, payload) {
  return apiFetch('/api/ui-schema/pages', {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function updatePage(workspaceId, pageId, payload) {
  return apiFetch(`/api/ui-schema/pages/${encodeURIComponent(pageId)}`, {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deletePage(workspaceId, pageId) {
  return apiFetch(`/api/ui-schema/pages/${encodeURIComponent(pageId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}

export function addElement(workspaceId, pageId, payload) {
  return apiFetch(`/api/ui-schema/pages/${encodeURIComponent(pageId)}/elements`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function updateElement(workspaceId, pageId, elementId, payload) {
  return apiFetch(`/api/ui-schema/pages/${encodeURIComponent(pageId)}/elements/${encodeURIComponent(elementId)}`, {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteElement(workspaceId, pageId, elementId) {
  return apiFetch(`/api/ui-schema/pages/${encodeURIComponent(pageId)}/elements/${encodeURIComponent(elementId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}

export function addRequirementLink(workspaceId, payload) {
  return apiFetch('/api/ui-schema/requirement-links', {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteRequirementLink(workspaceId, linkId) {
  return apiFetch(`/api/ui-schema/requirement-links/${encodeURIComponent(linkId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}


export function addCodeLink(workspaceId, payload) {
  return apiFetch('/api/ui-schema/code-links', {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteCodeLink(workspaceId, linkId) {
  return apiFetch(`/api/ui-schema/code-links/${encodeURIComponent(linkId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}


export function updateApp(workspaceId, payload) {
  return apiFetch('/api/ui-schema/app', {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function addAppElement(workspaceId, payload) {
  return apiFetch('/api/ui-schema/app/elements', {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function updateAppElement(workspaceId, elementId, payload) {
  return apiFetch(`/api/ui-schema/app/elements/${encodeURIComponent(elementId)}`, {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteAppElement(workspaceId, elementId) {
  return apiFetch(`/api/ui-schema/app/elements/${encodeURIComponent(elementId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}

export function addUiLink(workspaceId, payload) {
  return apiFetch('/api/ui-schema/ui-links', {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteUiLink(workspaceId, linkId) {
  return apiFetch(`/api/ui-schema/ui-links/${encodeURIComponent(linkId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}
