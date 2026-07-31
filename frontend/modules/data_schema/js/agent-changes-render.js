import { escapeAttr, escapeHtml } from './html-utils.js';

export const CHANGE_GROUP_LABELS = {
  entities: 'Сущности',
  fields: 'Поля',
  relations: 'Связи',
  dictionaries: 'Справочники',
  dictionary_values: 'Значения справочников',
  requirement_links: 'Связи с требованиями'
};

export function renderCompactChangeStatistics(statistics) {
  const groups = Object.entries(CHANGE_GROUP_LABELS);
  return `
    <section class="agent-change-stats" aria-label="Статистика изменений">
      <div class="agent-change-stats-title">Изменения</div>
      <div class="agent-stat-grid">
        ${groups.map(([key, label]) => renderStatCard(label, statistics?.[key] || {})).join('')}
      </div>
    </section>
  `;
}

export function renderChanges(value, run) {
  const groups = value?.changes && typeof value.changes === 'object' ? value.changes : {};
  const total = Object.values(groups).reduce(
    (sum, items) => sum + (Array.isArray(items) ? items.length : 0),
    0
  );
  const files = value?.files || {};
  return `
    <section class="card">
      <details class="agent-changes-root">
        <summary>Перечень изменений · ${total}</summary>
        <div class="agent-changes-root-body">
          ${total ? Object.entries(groups)
            .filter(([, items]) => Array.isArray(items) && items.length)
            .map(([key, items]) => `
              <details class="agent-change-group">
                <summary>${escapeHtml(CHANGE_GROUP_LABELS[key] || key)} · ${items.length}</summary>
                <div class="agent-change-list">${items.map(item => renderChangeItem(item, run)).join('')}</div>
              </details>
            `).join('') : '<div class="empty-state">Структурные изменения не обнаружены.</div>'}
          <details class="agent-change-group">
            <summary>Изменённые файлы</summary>
            ${renderFileList('Добавлены', files.added)}
            ${renderFileList('Изменены', files.modified)}
            ${renderFileList('Удалены', files.deleted)}
          </details>
        </div>
      </details>
    </section>
  `;
}

export function renderDeletionWarning(statistics) {
  const deleted = Object.values(statistics || {}).reduce(
    (sum, item) => sum + Number(item?.deleted || 0),
    0
  );
  return deleted
    ? `<div class="agent-warning-box"><strong>Удаления: ${deleted}.</strong> Проверьте их перед применением.</div>`
    : '';
}

function renderStatCard(label, value) {
  return `
    <div class="agent-stat-card">
      <div class="agent-stat-title">${escapeHtml(label)}</div>
      <div class="agent-stat-values">
        <span class="added">+${escapeHtml(value.added || 0)}</span>
        <span class="modified">~${escapeHtml(value.modified || 0)}</span>
        <span class="deleted">−${escapeHtml(value.deleted || 0)}</span>
      </div>
    </div>
  `;
}

function renderChangeItem(item, run) {
  const action = item.change_type || item.action || '';
  const id = item.id || item.object_id || '';
  const href = previewChangeHref(run, item.object_type, id, action);
  const properties = Array.isArray(item.field_changes) ? item.field_changes : [];
  return `
    <div class="agent-change-item ${escapeAttr(action)}">
      <span class="agent-change-action">${escapeHtml(actionSymbol(action))}</span>
      <div class="agent-change-content">
        <div>${escapeHtml(item.title || id)}</div>
        <div class="muted-text">${escapeHtml(id)}</div>
        ${renderPropertyChanges(properties)}
      </div>
      ${href ? `<a class="btn btn-sm" href="${escapeAttr(href)}">Показать</a>` : ''}
    </div>
  `;
}

function renderPropertyChanges(properties) {
  if (!properties.length) return '';
  return `
    <details class="agent-change-properties">
      <summary>Изменено свойств: ${properties.length}</summary>
      <div class="agent-change-property-list">
        ${properties.map(property => `
          <div class="agent-change-property">
            <code>${escapeHtml(property.field || '')}</code>
            <span class="agent-change-before">${escapeHtml(formatChangeValue(property.before))}</span>
            <span aria-hidden="true">→</span>
            <span class="agent-change-after">${escapeHtml(formatChangeValue(property.after))}</span>
          </div>
        `).join('')}
      </div>
    </details>
  `;
}

function previewChangeHref(run, objectType, id, action) {
  if (!run?.run_id || action === 'deleted') return '';
  const params = new URLSearchParams({ preview_run_id: run.run_id, tab: 'structure' });
  if (objectType === 'entities') params.set('select_entity_id', id);
  else if (objectType === 'fields') {
    const [entityId, ...fieldParts] = String(id).split('.');
    params.set('select_entity_id', entityId);
    params.set('select_field_id', fieldParts.join('.'));
  } else if (objectType === 'relations') {
    params.set('tab', 'graph');
    params.set('select_relation_id', id);
  } else return '';
  return `?${params.toString()}`;
}

function renderFileList(label, files) {
  const list = Array.isArray(files) ? files : [];
  return list.length
    ? `<div class="agent-file-group"><strong>${escapeHtml(label)}</strong><ul>${list.map(file => `<li><code>${escapeHtml(file)}</code></li>`).join('')}</ul></div>`
    : '';
}

function formatChangeValue(value) {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch (_error) {
      return String(value);
    }
  }
  return String(value);
}

function actionSymbol(action) {
  return { added: '+', modified: '~', deleted: '−' }[action] || '•';
}
