import { apiFetch } from '/base/js/api.js';

const root = '/api/data-schema';

export function loadModuleConfig() {
  return apiFetch('/api/config/modules/data_schema');
}

export function loadSummary(workspaceId, previewRunId = null) {
  const preview = previewRunId ? `&preview_run_id=${encodeURIComponent(previewRunId)}` : '';
  return apiFetch(`${root}?workspace_id=${encodeURIComponent(workspaceId)}${preview}`);
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


export function testAgentLlm(workspaceId) {
  return apiFetch(`${root}/agent/llm/test`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}

export function loadActiveAgentRun(workspaceId) {
  return apiFetch(`${root}/agent-runs/active?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function loadAgentRun(workspaceId, runId) {
  return apiFetch(`${root}/agent-runs/${encodeURIComponent(runId)}?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function loadAgentChanges(workspaceId, runId) {
  return apiFetch(`${root}/agent-runs/${encodeURIComponent(runId)}/changes?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function loadAgentFileDiff(workspaceId, runId) {
  return apiFetch(`${root}/agent-runs/${encodeURIComponent(runId)}/file-diff?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function loadAgentRequirementsResult(workspaceId, runId) {
  return apiFetch(`${root}/agent-runs/${encodeURIComponent(runId)}/requirements-data-result?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function loadAgentEvents(workspaceId, runId, after = 0, limit) {
  const query = new URLSearchParams({
    workspace_id: workspaceId,
    after: String(after || 0),
    limit: String(limit)
  });
  return apiFetch(`${root}/agent-runs/${encodeURIComponent(runId)}/events?${query.toString()}`);
}

export function startAgentRun(workspaceId, requirementsPath, userRequest, baseMode) {
  return apiFetch(`${root}/agent-runs`, {
    method: 'POST',
    body: JSON.stringify({
      workspace_id: workspaceId,
      requirements_path: requirementsPath,
      user_request: userRequest || '',
      base_mode: baseMode || 'current'
    })
  });
}

export function regenerateAgentRun(workspaceId, runId, comment) {
  return apiFetch(`${root}/agent-runs/${encodeURIComponent(runId)}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, comment: comment || '' })
  });
}

export function applyAgentRun(workspaceId, runId) {
  return apiFetch(`${root}/agent-runs/${encodeURIComponent(runId)}/apply`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}

export function rejectAgentRun(workspaceId, runId) {
  return apiFetch(`${root}/agent-runs/${encodeURIComponent(runId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}

export function cancelAgentRun(workspaceId, runId) {
  return apiFetch(`${root}/agent-runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}

export function loadLatestAgentSnapshot(workspaceId) {
  return apiFetch(`${root}/history/latest?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function restoreLatestAgentSnapshot(workspaceId) {
  return apiFetch(`${root}/history/restore-latest`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}
