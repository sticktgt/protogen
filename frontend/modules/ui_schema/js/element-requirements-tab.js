import { addRequirementLink, deleteRequirementLink } from './api.js';
import { renderAll } from './main.js';
import { links, requirementById, requirementTitle, requirements, state } from './state.js';
import { escapeAttr, escapeHtml, statusLabel } from './html-utils.js';
import { showToast } from '/base/js/ui.js';

const implementationStatuses = [
  ['planned', 'Запланировано'],
  ['in_progress', 'В работе'],
  ['implemented', 'Реализовано'],
  ['not_applicable', 'Не применимо']
];

export function renderRequirementsTab(container, target, targetType = 'ui_element') {
  const targetLinks = links().filter(link => link.target_type === targetType && link.target_id === target.id);
  container.innerHTML = `
    <div class="detail-section-row">
      <div class="detail-section-title">Связанные требования</div>
      <button class="btn btn-primary btn-sm" type="button" data-show-requirement-form>Связать с требованием</button>
    </div>
    <div class="linked-list">
      ${targetLinks.map(renderRequirementLinkRow).join('') || '<div class="empty-state compact">Связанных требований нет.</div>'}
    </div>
    <div data-requirement-form-container>${state.showRequirementLinkForm ? renderRequirementForm() : ''}</div>
  `;
  bindRequirementsTab(container, target, targetType);
}

function bindRequirementsTab(container, target, targetType) {
  container.querySelector('[data-show-requirement-form]')?.addEventListener('click', () => {
    state.showRequirementLinkForm = true;
    renderAll();
  });

  container.querySelectorAll('[data-unlink-requirement]').forEach(button => {
    button.addEventListener('click', async () => {
      await deleteRequirementLink(state.workspaceId, button.dataset.unlinkRequirement);
      showToast('Связь удалена');
      await renderAll({ reload: true });
    });
  });

  container.querySelectorAll('[data-open-requirement]').forEach(button => {
    button.addEventListener('click', () => showToast('Переход к требованию будет доступен после подключения модуля требований.'));
  });

  container.querySelector('[data-element-requirement-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    await addRequirementLink(state.workspaceId, {
      requirement_id: form.get('requirement_id'),
      target_type: targetType,
      target_id: target.id,
      relation: form.get('relation') || 'implemented_by',
      implementation_status: form.get('implementation_status') || 'planned'
    });
    state.showRequirementLinkForm = false;
    showToast(targetType === 'page' ? 'Требование связано со страницей' : 'Требование связано с элементом');
    await renderAll({ reload: true });
  });

  container.querySelector('[data-cancel-requirement-form]')?.addEventListener('click', () => {
    state.showRequirementLinkForm = false;
    renderAll();
  });
}

function renderRequirementForm() {
  const options = requirements().map(req => `<option value="${escapeAttr(req.id)}">${escapeHtml(req.code || req.id)} — ${escapeHtml(req.name || '')}</option>`).join('');
  return `
    <form class="schema-form linked-form" data-element-requirement-form>
      <div class="form-row">
        <label>Требование</label>
        <select name="requirement_id">${options}</select>
      </div>
      <div class="form-row">
        <label>Тип связи</label>
        <input name="relation" value="implemented_by">
      </div>
      <div class="form-row">
        <label>Статус реализации</label>
        <select name="implementation_status">${implementationStatuses.map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select>
      </div>
      <div class="page-actions-row">
        <button class="btn btn-primary" type="submit">Связать</button>
        <button class="btn" type="button" data-cancel-requirement-form>Отмена</button>
      </div>
    </form>
  `;
}

function renderRequirementLinkRow(link) {
  const req = requirementById(link.requirement_id);
  const types = (req?.types || []).join(', ');
  return `
    <div class="linked-row">
      <div>
        <div class="linked-row-title">${escapeHtml(requirementTitle(link.requirement_id))}</div>
        <div class="item-meta">${escapeHtml(types || 'тип не указан')} · ${escapeHtml(req?.status || '-')} · ${escapeHtml(statusLabel(link.implementation_status))}</div>
      </div>
      <div class="linked-row-actions">
        <button class="btn btn-sm" type="button" data-open-requirement="${escapeAttr(link.requirement_id)}">Перейти</button>
        <button class="btn btn-danger btn-sm" type="button" data-unlink-requirement="${escapeAttr(link.id)}">Отвязать</button>
      </div>
    </div>
  `;
}
