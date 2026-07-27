import { APP_SCOPE, state } from './state.js';
import { escapeAttr, escapeHtml } from './html-utils.js';

const actionMeta = {
  added: ['+', 'Добавлено'],
  modified: ['~', 'Изменено'],
  deleted: ['−', 'Удалено']
};

export function previewChangeItems() {
  return Array.isArray(state.summary?.preview_changes?.changes)
    ? state.summary.preview_changes.changes
    : [];
}

export function objectChange(objectType, objectId) {
  return previewChangeItems().find(item =>
    item.object_type === objectType && item.object_id === objectId
  ) || null;
}

export function renderChangeBadge(objectType, objectId) {
  if (!state.previewActive) return '';
  const change = objectChange(objectType, objectId);
  if (!change) return '';
  const [symbol, label] = actionMeta[change.action] || ['•', 'Изменено'];
  return `<span class="preview-change-badge ${escapeAttr(change.action)}" title="${escapeAttr(label)}">${escapeHtml(symbol)} ${escapeHtml(label)}</span>`;
}

export function changesForScope(pageId) {
  if (!state.previewActive) return [];
  return previewChangeItems().filter(item => belongsToScope(item, pageId));
}

export function renderScopeChangeCounts(pageId) {
  const counts = countActions(changesForScope(pageId));
  const total = counts.added + counts.modified + counts.deleted;
  if (!total) return '';
  return `
    <span class="preview-scope-counts" title="Изменения страницы и связанных объектов">
      <span class="added">+${counts.added}</span>
      <span class="modified">~${counts.modified}</span>
      <span class="deleted">−${counts.deleted}</span>
    </span>
  `;
}

export function renderScopeChangesOverview(pageId) {
  const items = changesForScope(pageId);
  if (!items.length) return '';
  const counts = countActions(items);
  return `
    <details class="preview-scope-overview">
      <summary>
        Изменения ${pageId === APP_SCOPE ? 'приложения' : 'на странице'} ·
        <span class="added">+${counts.added}</span>
        <span class="modified">~${counts.modified}</span>
        <span class="deleted">−${counts.deleted}</span>
      </summary>
      <div class="preview-scope-change-list">
        ${items.map(renderScopeChangeRow).join('')}
      </div>
    </details>
  `;
}

export function deletedChangesForScope(pageId) {
  return changesForScope(pageId).filter(item =>
    item.action === 'deleted' && ['page', 'ui_element'].includes(item.object_type)
  );
}

export function renderDeletedChangesSection(pageId) {
  const items = deletedChangesForScope(pageId);
  if (!items.length) return '';
  return `
    <details class="preview-deleted-section">
      <summary>Удалённые объекты · ${items.length}</summary>
      <div class="preview-deleted-list">
        ${items.map(item => `
          <button type="button" class="preview-deleted-row" data-select-deleted-type="${escapeAttr(item.object_type)}" data-select-deleted-id="${escapeAttr(item.object_id)}">
            <span>− ${escapeHtml(item.title || item.label || item.object_id)}</span>
            <code>${escapeHtml(item.object_id)}</code>
          </button>
        `).join('')}
      </div>
    </details>
  `;
}

export function renderSelectedChangeDetails(objectType, objectId) {
  if (!state.previewActive) return '';
  const direct = objectChange(objectType, objectId);
  const related = relatedLinkChanges(objectType, objectId);
  if (!direct && !related.length) return '';
  return `
    <details class="preview-object-changes">
      <summary>Изменения объекта${direct ? ` · ${escapeHtml(actionMeta[direct.action]?.[1] || direct.action)}` : ''}</summary>
      ${direct ? renderDirectChange(direct) : ''}
      ${related.length ? `
        <div class="preview-related-changes">
          <div class="preview-change-subtitle">Связи</div>
          ${related.map(renderRelatedChange).join('')}
        </div>
      ` : ''}
    </details>
  `;
}

export function selectedDeletedChange() {
  const selected = state.selectedDeletedChange;
  if (!selected) return null;
  return objectChange(selected.objectType, selected.objectId);
}

export function renderDeletedChangeEditor(change) {
  if (!change) return '<div class="empty-state">Удалённый объект не найден в отчёте изменений.</div>';
  return `
    <div class="element-editor-header">
      <div>
        <div class="element-editor-title">− ${escapeHtml(change.title || change.label || change.object_id)}</div>
        <div class="item-meta">${escapeHtml(change.object_id)} · удалено</div>
      </div>
    </div>
    ${renderDirectChange(change)}
    <details class="preview-technical-diff">
      <summary>Полные данные удалённого объекта</summary>
      <pre>${escapeHtml(JSON.stringify(change.before || {}, null, 2))}</pre>
    </details>
  `;
}

function belongsToScope(item, pageId) {
  if (item.object_type === 'application') return pageId === APP_SCOPE;
  if (item.object_type === 'page') return item.object_id === pageId;
  if (item.object_type === 'ui_element' || item.object_type === 'requirement_link') {
    return pageId === APP_SCOPE ? !item.page_id : item.page_id === pageId;
  }
  if (item.object_type === 'ui_link') {
    if (pageId === APP_SCOPE) {
      const appSource = item.source_type === 'ui_element' && !item.source_page_id;
      const appTarget = item.target_type === 'ui_element' && !item.target_page_id;
      return appSource || appTarget;
    }
    return item.source_page_id === pageId || item.target_page_id === pageId || item.page_id === pageId;
  }
  return false;
}

function countActions(items) {
  const counts = { added: 0, modified: 0, deleted: 0 };
  for (const item of items) {
    if (Object.hasOwn(counts, item.action)) counts[item.action] += 1;
  }
  return counts;
}

function renderScopeChangeRow(item) {
  const [symbol, label] = actionMeta[item.action] || ['•', item.action || ''];
  const href = changeHref(item);
  return `
    <div class="preview-scope-change-row ${escapeAttr(item.action || '')}">
      <span class="preview-scope-change-symbol">${escapeHtml(symbol)}</span>
      <div>
        <div>${escapeHtml(changeTitle(item))}</div>
        <div class="item-meta">${escapeHtml(changeTypeLabel(item.object_type))} · ${escapeHtml(label)}</div>
      </div>
      ${href ? `<a class="btn btn-sm" href="${escapeAttr(href)}">Открыть</a>` : ''}
    </div>
  `;
}

function changeHref(item) {
  if (!state.previewRunId) return '';
  const params = new URLSearchParams({
    preview_run_id: state.previewRunId,
    tab: 'structure'
  });
  const pageId = item.page_id || item.target_page_id || item.source_page_id;
  if (pageId) params.set('select_page_id', pageId);
  if (item.action === 'deleted' && ['page', 'ui_element'].includes(item.object_type)) {
    params.set('deleted_type', item.object_type);
    params.set('deleted_id', item.object_id || '');
  } else if (item.object_type === 'application') {
    params.set('select_page_id', APP_SCOPE);
  } else if (item.object_type === 'page') {
    params.set('select_page_id', item.object_id || '');
  } else if (item.object_type === 'ui_element') {
    params.set('select_page_id', item.page_id || APP_SCOPE);
    params.set('select_element_id', item.object_id || '');
  } else if (item.object_type === 'requirement_link') {
    if (item.target_type === 'page') params.set('select_page_id', item.target_id || '');
    if (item.target_type === 'ui_element') params.set('select_element_id', item.target_id || '');
  } else if (item.object_type === 'ui_link') {
    const elementId = item.target_type === 'ui_element'
      ? item.target_id
      : item.source_type === 'ui_element' ? item.source_id : '';
    if (elementId) params.set('select_element_id', elementId);
  } else {
    return '';
  }
  return `?${params.toString()}`;
}

function changeTitle(item) {
  if (item.object_type === 'requirement_link') {
    return `${item.requirement_id || ''} → ${item.target_id || ''}`;
  }
  return item.title || item.label || item.object_id || '';
}

function changeTypeLabel(objectType) {
  return {
    application: 'приложение',
    page: 'страница',
    ui_element: 'UI-элемент',
    ui_link: 'UI-связь',
    requirement_link: 'связь с требованием'
  }[objectType] || objectType || 'объект';
}

function relatedLinkChanges(objectType, objectId) {
  return previewChangeItems().filter(item => {
    if (item.object_type === 'requirement_link') {
      return item.target_type === objectType && item.target_id === objectId;
    }
    if (item.object_type === 'ui_link') {
      return item.source_id === objectId || item.target_id === objectId;
    }
    return false;
  });
}

function renderDirectChange(change) {
  const fields = Array.isArray(change.field_changes) ? change.field_changes : [];
  return `
    <div class="preview-direct-change ${escapeAttr(change.action || '')}">
      ${fields.length ? `
        <div class="preview-field-diff-list">
          ${fields.map(item => `
            <div class="preview-field-diff">
              <code>${escapeHtml(item.field)}</code>
              <div><span>Было:</span> ${renderValue(item.before)}</div>
              <div><span>Стало:</span> ${renderValue(item.after)}</div>
            </div>
          `).join('')}
        </div>
      ` : `<div class="muted-text">${change.action === 'added' ? 'Новый объект.' : change.action === 'deleted' ? 'Объект удалён.' : 'Содержимое объекта изменено.'}</div>`}
      <details class="preview-technical-diff">
        <summary>Технические данные</summary>
        <div class="preview-json-pair">
          <div><strong>Было</strong><pre>${escapeHtml(JSON.stringify(change.before || null, null, 2))}</pre></div>
          <div><strong>Стало</strong><pre>${escapeHtml(JSON.stringify(change.after || null, null, 2))}</pre></div>
        </div>
      </details>
    </div>
  `;
}

function renderRelatedChange(change) {
  const [symbol, label] = actionMeta[change.action] || ['•', change.action || ''];
  const title = change.object_type === 'requirement_link'
    ? `${change.requirement_id} → ${change.target_id}`
    : change.title || change.object_id;
  return `
    <div class="preview-related-row ${escapeAttr(change.action || '')}">
      <span>${escapeHtml(symbol)}</span>
      <div>
        <div>${escapeHtml(title)}</div>
        <div class="item-meta">${escapeHtml(label)} · ${escapeHtml(change.relation || '')}</div>
      </div>
    </div>
  `;
}

function renderValue(value) {
  if (value === undefined) return '<em>отсутствует</em>';
  if (value === null) return '<em>null</em>';
  if (typeof value === 'object') return `<code>${escapeHtml(JSON.stringify(value))}</code>`;
  if (value === '') return '<em>пусто</em>';
  return `<span>${escapeHtml(String(value))}</span>`;
}
