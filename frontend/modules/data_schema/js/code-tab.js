import { escapeHtml } from './html-utils.js';
import { state, targetInfo } from './state.js';

export function renderCodeTab() {
  const target = targetInfo();
  const links = (state.summary?.code_links || []).filter(item => item.target_type === target.type && item.target_id === target.id);
  return `
    <div class="small-note">Связи с кодом только отображаются. Ручное добавление ссылок на код в этом модуле не выполняется.</div>
    <div class="link-list left-link-list">${links.map(renderCodeLink).join('') || '<div class="empty-state compact-empty">Связей с кодом пока нет.</div>'}</div>
  `;
}

function renderCodeLink(link) {
  return `
    <div class="link-item readonly-link-item">
      <div><strong>${escapeHtml(link.path || 'Путь не указан')}</strong><br><span class="muted">${escapeHtml(link.code_type)} · ${escapeHtml(link.status)}</span></div>
    </div>
  `;
}
