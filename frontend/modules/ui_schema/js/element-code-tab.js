import { codeLinks } from './state.js';
import { escapeAttr, escapeHtml } from './html-utils.js';
import { showToast } from '/base/js/ui.js';

export function renderCodeTab(container, target, targetType = 'ui_element') {
  const targetLinks = codeLinks().filter(link => link.target_type === targetType && link.target_id === target.id);
  container.innerHTML = `
    <div class="detail-section-title">Связанные файлы кода прототипа</div>
    <div class="linked-list">
      ${targetLinks.map(renderCodeLinkRow).join('') || '<div class="empty-state compact">Связанных файлов нет.</div>'}
    </div>
  `;

  container.querySelectorAll('[data-open-code]').forEach(button => {
    button.addEventListener('click', () => showToast('Переход к файлу будет доступен после подключения модуля работы с кодом.'));
  });
}

function renderCodeLinkRow(link) {
  return `
    <div class="linked-row code-link-row">
      <div class="code-link-line">
        <span class="badge">${escapeHtml(link.kind || 'frontend_file')}</span>
        <span class="code-link-path">${escapeHtml(link.path || 'путь не задан')}</span>
      </div>
      <div class="linked-row-actions">
        ${link.path ? `<button class="btn btn-sm" type="button" data-open-code="${escapeAttr(link.id)}">Открыть</button>` : ''}
      </div>
    </div>
  `;
}
