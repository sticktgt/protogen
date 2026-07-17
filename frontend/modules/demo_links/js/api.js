import { apiFetch } from '/base/js/api.js';

export function getInfo(workspaceId) {
  return apiFetch(`/api/links/info?workspace_id=${encodeURIComponent(workspaceId)}`);
}
