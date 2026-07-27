import { apiFetch } from '/base/js/api.js';

export function loadModuleConfig() {
  return apiFetch('/api/config/modules/ui_schema');
}

export function loadSummary(workspaceId, previewRunId = null) {
  const preview = previewRunId ? `&preview_run_id=${encodeURIComponent(previewRunId)}` : '';
  return apiFetch(`/api/ui-schema?workspace_id=${encodeURIComponent(workspaceId)}${preview}`);
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

export function testAgentLlm(workspaceId) {
  return apiFetch('/api/ui-schema/agent/llm/test', {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}

export function loadActiveAgentRun(workspaceId) {
  return apiFetch(`/api/ui-schema/agent-runs/active?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function loadAgentRun(workspaceId, runId) {
  return apiFetch(`/api/ui-schema/agent-runs/${encodeURIComponent(runId)}?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function loadAgentChanges(workspaceId, runId) {
  return apiFetch(`/api/ui-schema/agent-runs/${encodeURIComponent(runId)}/changes?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function loadAgentEvents(workspaceId, runId, after = 0) {
  const query = new URLSearchParams({
    workspace_id: workspaceId,
    after: String(after || 0),
    limit: '200'
  });
  return apiFetch(`/api/ui-schema/agent-runs/${encodeURIComponent(runId)}/events?${query.toString()}`);
}

export function startAgentRun(workspaceId, requirementsPath, userRequest, baseMode) {
  return apiFetch('/api/ui-schema/agent-runs', {
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
  return apiFetch(`/api/ui-schema/agent-runs/${encodeURIComponent(runId)}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId, comment: comment || '' })
  });
}

export function applyAgentRun(workspaceId, runId) {
  return apiFetch(`/api/ui-schema/agent-runs/${encodeURIComponent(runId)}/apply`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}

export function rejectAgentRun(workspaceId, runId) {
  return apiFetch(`/api/ui-schema/agent-runs/${encodeURIComponent(runId)}/reject`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}

export function cancelAgentRun(workspaceId, runId) {
  return apiFetch(`/api/ui-schema/agent-runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}

export function loadLatestAgentSnapshot(workspaceId) {
  return apiFetch(`/api/ui-schema/history/latest?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function restoreLatestAgentSnapshot(workspaceId) {
  return apiFetch('/api/ui-schema/history/restore-latest', {
    method: 'POST',
    body: JSON.stringify({ workspace_id: workspaceId })
  });
}
