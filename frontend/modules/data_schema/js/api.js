import { apiFetch } from '/base/js/api.js';

const root = '/api/data-schema';

export function loadSummary(workspaceId) {
  return apiFetch(`${root}?workspace_id=${encodeURIComponent(workspaceId)}`);
}


export function loadUiSchema(workspaceId) {
  return apiFetch(`/api/ui-schema?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function updateSchema(workspaceId, payload) {
  return apiFetch(`${root}/schema`, {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function createEntity(workspaceId, payload) {
  return apiFetch(`${root}/entities`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function updateEntity(workspaceId, entityId, payload) {
  return apiFetch(`${root}/entities/${encodeURIComponent(entityId)}`, {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteEntity(workspaceId, entityId) {
  return apiFetch(`${root}/entities/${encodeURIComponent(entityId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}

export function addField(workspaceId, entityId, payload) {
  return apiFetch(`${root}/entities/${encodeURIComponent(entityId)}/fields`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function updateField(workspaceId, entityId, fieldId, payload) {
  return apiFetch(`${root}/entities/${encodeURIComponent(entityId)}/fields/${encodeURIComponent(fieldId)}`, {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteField(workspaceId, entityId, fieldId) {
  return apiFetch(`${root}/entities/${encodeURIComponent(entityId)}/fields/${encodeURIComponent(fieldId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}

export function createRelation(workspaceId, payload) {
  return apiFetch(`${root}/relations`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function updateRelation(workspaceId, relationId, payload) {
  return apiFetch(`${root}/relations/${encodeURIComponent(relationId)}`, {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteRelation(workspaceId, relationId) {
  return apiFetch(`${root}/relations/${encodeURIComponent(relationId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}

export function addRequirementLink(workspaceId, payload) {
  return apiFetch(`${root}/requirement-links`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteRequirementLink(workspaceId, linkId) {
  return apiFetch(`${root}/requirement-links/${encodeURIComponent(linkId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}

export function addUiLink(workspaceId, payload) {
  return apiFetch(`${root}/ui-links`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteUiLink(workspaceId, linkId) {
  return apiFetch(`${root}/ui-links/${encodeURIComponent(linkId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}

export function addApiLink(workspaceId, payload) {
  return apiFetch(`${root}/api-links`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteApiLink(workspaceId, linkId) {
  return apiFetch(`${root}/api-links/${encodeURIComponent(linkId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}

export function addCodeLink(workspaceId, payload) {
  return apiFetch(`${root}/code-links`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, ...payload })
  });
}

export function deleteCodeLink(workspaceId, linkId) {
  return apiFetch(`${root}/code-links/${encodeURIComponent(linkId)}?workspace_id=${encodeURIComponent(workspaceId)}`, {
    method: 'DELETE'
  });
}
