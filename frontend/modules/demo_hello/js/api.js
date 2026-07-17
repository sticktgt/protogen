import { apiFetch } from '/base/js/api.js';

export function getMessage(workspaceId) {
  return apiFetch(`/api/hello/message?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function saveMessage(workspaceId, message) {
  return apiFetch('/api/hello/message', {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, message })
  });
}
