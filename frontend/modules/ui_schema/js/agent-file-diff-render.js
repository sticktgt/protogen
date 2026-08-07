import { escapeAttr, escapeHtml } from './html-utils.js';

const GROUPS = [
  ['added', 'Новые файлы'],
  ['modified', 'Изменённые файлы'],
  ['deleted', 'Удалённые файлы']
];

export function renderFileDiff(value) {
  const files = Array.isArray(value?.files) ? value.files : [];
  const summary = value?.summary || {};
  const total = Number(summary.files || files.length || 0);
  return `
    <section class="card agent-collapsible-card">
      <details class="agent-file-diff-root">
        <summary>Diff файлов · ${escapeHtml(total)}</summary>
        <div class="agent-file-diff-body">
          <p class="muted-text">Построчное сравнение базовой и временной UI-схемы. Этот diff не влияет на работу агента и предназначен только для проверки результата.</p>
          ${renderSummary(summary)}
          ${total ? GROUPS.map(([type, label]) => renderGroup(label, type, files)).join('') : '<div class="empty-state">Изменения файлов не обнаружены.</div>'}
        </div>
      </details>
    </section>
  `;
}

function renderSummary(summary) {
  return `
    <div class="agent-file-diff-summary" aria-label="Статистика diff файлов">
      <span>Файлы: <strong>${escapeHtml(summary.files || 0)}</strong></span>
      <span class="added">+${escapeHtml(summary.additions || 0)} строк</span>
      <span class="deleted">−${escapeHtml(summary.deletions || 0)} строк</span>
    </div>
  `;
}

function renderGroup(label, changeType, files) {
  const group = files.filter(item => item?.change_type === changeType);
  if (!group.length) return '';
  return `
    <details class="agent-file-diff-group">
      <summary>${escapeHtml(label)} · ${group.length}</summary>
      <div class="agent-file-diff-list">${group.map(renderFile).join('')}</div>
    </details>
  `;
}

function renderFile(file) {
  const path = String(file?.path || '');
  const changeType = String(file?.change_type || 'modified');
  return `
    <details class="agent-file-diff-file ${escapeAttr(changeType)}">
      <summary>
        <code>${escapeHtml(path)}</code>
        <span class="agent-file-diff-counts"><span class="added">+${escapeHtml(file?.additions || 0)}</span><span class="deleted">−${escapeHtml(file?.deletions || 0)}</span></span>
      </summary>
      ${renderDiff(file?.diff)}
    </details>
  `;
}

function renderDiff(diff) {
  const lines = String(diff || '').split('\n');
  return `
    <div class="agent-file-diff-code" role="region" aria-label="Построчные изменения">
      ${lines.map(line => `<span class="${escapeAttr(lineClass(line))}">${escapeHtml(line || ' ')}</span>`).join('')}
    </div>
  `;
}

function lineClass(line) {
  if (line.startsWith('+++') || line.startsWith('---')) return 'file-header';
  if (line.startsWith('@@')) return 'hunk-header';
  if (line.startsWith('+')) return 'added';
  if (line.startsWith('-')) return 'deleted';
  return 'context';
}
