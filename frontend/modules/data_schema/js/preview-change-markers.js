import { state } from './state.js';

const LABELS = {
  added: 'Добавлено',
  modified: 'Изменено',
  deleted: 'Удалено'
};

export function entityPreviewChange(entityId) {
  const direct = changeFor('entities', entityId);
  if (direct) return direct;
  return changedFieldsForEntity(entityId).length ? 'modified' : '';
}

export function fieldPreviewChange(entityId, fieldId) {
  return changeFor('fields', `${entityId}.${fieldId}`);
}

export function relationPreviewChange(relationId) {
  return changeFor('relations', relationId);
}

export function previewChangeClass(action) {
  return action ? `preview-change-${action}` : '';
}

export function previewChangeBadge(action, { compact = false } = {}) {
  if (!action) return '';
  const symbol = { added: '+', modified: '~', deleted: '−' }[action] || '•';
  const label = LABELS[action] || action;
  return `<span class="schema-preview-change-badge ${previewChangeClass(action)}" title="${label}">${symbol}${compact ? '' : ` ${label}`}</span>`;
}

export function changedFieldsForEntity(entityId) {
  const prefix = `${entityId}.`;
  return changesOf('fields').filter(item => String(item?.id || '').startsWith(prefix));
}

function changeFor(group, id) {
  const item = changesOf(group).find(change => String(change?.id || '') === String(id || ''));
  return String(item?.change_type || '');
}

function changesOf(group) {
  const changes = state.summary?.preview_changes?.changes;
  return Array.isArray(changes?.[group]) ? changes[group] : [];
}
