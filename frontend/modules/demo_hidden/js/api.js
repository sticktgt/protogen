import { apiFetch } from '/base/js/api.js';

export function getStatus(workspaceId) {
  return apiFetch(`/api/hidden/status?workspace_id=${encodeURIComponent(workspaceId)}`);
}

export function saveNote(workspaceId, note) {
  return apiFetch('/api/hidden/note', {
    method: 'PUT',
    body: JSON.stringify({ workspace_id: workspaceId, note }),
  });
}
