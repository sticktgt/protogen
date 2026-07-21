import { state, pages, requirements, links, requirementTitle, targetTitle, flattenElements } from './state.js';
import { renderAll } from './main.js';
import { deleteRequirementLink } from './api.js';
import { showToast } from '/base/js/ui.js';

export function renderTraceView() {
  renderRequirementList();
  renderLinkFormOptions();
  renderLinkTable();
}

function renderRequirementList() {
  const container = document.querySelector('[data-requirement-list]');
  const filter = (document.querySelector('[data-requirement-filter]')?.value || '').toLowerCase();
  if (!container) return;
  const visible = requirements().filter(req => {
    const text = `${req.id || ''} ${req.code || ''} ${req.name || ''}`.toLowerCase();
    return !filter || text.includes(filter);
  });
  container.innerHTML = visible.map(req => {
    const active = req.id === state.selectedRequirementId ? ' active' : '';
    const types = (req.types || []).join(', ');
    return `
      <div class="requirement-item${active}" data-select-requirement="${escapeAttr(req.id)}">
        <div class="item-title">${escapeHtml(req.code || req.id)} — ${escapeHtml(req.name || '')}</div>
        <div class="item-meta">${escapeHtml(types)} · ${escapeHtml(req.status || '-')}</div>
      </div>
    `;
  }).join('') || '<div class="empty-state">Требования не найдены.</div>';
  container.querySelectorAll('[data-select-requirement]').forEach(item => {
    item.addEventListener('click', () => {
      state.selectedRequirementId = item.dataset.selectRequirement;
      renderAll();
    });
  });
}

function renderLinkFormOptions() {
  const reqSelect = document.querySelector('[data-link-requirement-select]');
  const targetType = document.querySelector('[data-link-target-type]');
  const targetSelect = document.querySelector('[data-link-target-select]');
  if (reqSelect) {
    reqSelect.innerHTML = requirements().map(req => `
      <option value="${escapeAttr(req.id)}" ${req.id === state.selectedRequirementId ? 'selected' : ''}>${escapeHtml(req.code || req.id)} — ${escapeHtml(req.name || '')}</option>
    `).join('');
    reqSelect.onchange = () => {
      state.selectedRequirementId = reqSelect.value;
      renderAll();
    };
  }
  if (!targetSelect || !targetType) return;
  targetSelect.innerHTML = targetType.value === 'page'
    ? pages().map(page => `<option value="${escapeAttr(page.id)}">${escapeHtml(page.details?.title || page.title || page.id)}</option>`).join('')
    : pages().flatMap(page => flattenElements(page.details).map(element => `
        <option value="${escapeAttr(element.id)}">${escapeHtml(page.details?.title || page.title)} / ${'— '.repeat(element.depth)}${escapeHtml(element.label || element.id)}</option>
      `)).join('');
  targetType.onchange = () => renderLinkFormOptions();
}

function renderLinkTable() {
  const container = document.querySelector('[data-link-table]');
  if (!container) return;
  const visible = state.selectedRequirementId
    ? links().filter(link => link.requirement_id === state.selectedRequirementId)
    : links();
  container.innerHTML = visible.map(link => `
    <div class="link-row">
      <div><strong>${escapeHtml(link.requirement_id)}</strong></div>
      <div>${escapeHtml(requirementTitle(link.requirement_id))}</div>
      <div>${escapeHtml(targetTitle(link.target_type, link.target_id))}<br><span class="item-meta">${escapeHtml(link.target_type)} · ${escapeHtml(link.target_id)}</span></div>
      <div>
        <button class="btn btn-danger btn-sm" type="button" data-delete-link="${escapeAttr(link.id)}">Удалить</button>
      </div>
    </div>
  `).join('') || '<div class="empty-state">Связей нет.</div>';
  container.querySelectorAll('[data-delete-link]').forEach(button => {
    button.addEventListener('click', async () => {
      await deleteRequirementLink(state.workspaceId, button.dataset.deleteLink);
      showToast('Связь удалена');
      await renderAll({ reload: true });
    });
  });
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/'/g, '&#39;');
}
