import { addRequirementLink, deleteRequirementLink } from './api.js';
import { escapeHtml, formValue, toast } from './html-utils.js';
import { renderAll } from './main.js';
import { requirementGroups, requirements, state, targetInfo } from './state.js';

export function renderRequirementTab() {
  const target = targetInfo();
  const links = (state.summary?.requirement_links || []).filter(item => item.target_type === target.type && item.target_id === target.id);
  return `
    <div class="small-note">Связи идут на поле <code>requirements[].id</code>. Требования здесь не редактируются.</div>
    <section class="editor-section">
      <h3 class="section-title">Связанные требования</h3>
      <div class="link-list left-link-list">${links.map(link => renderRequirementLink(link)).join('') || '<div class="empty-state compact-empty">Связанных требований нет.</div>'}</div>
    </section>
    <section class="editor-section">
      <h3 class="section-title">Связать с требованием</h3>
      <form data-add-requirement-link class="requirement-link-form">
        <div class="form-row form-row-wide">
          <label>Фильтр требований</label>
          <input data-requirement-filter name="requirement_filter" placeholder="ID, название, тип, статус или группа" value="${escapeHtml(state.requirementFilter)}">
        </div>
        <div class="requirement-picker" data-requirement-options>
          ${renderRequirementOptions()}
        </div>
        <div class="compact-form requirement-link-meta">
          <div class="form-row">
            <label>Отношение</label>
            <input name="relation" value="defines">
          </div>
          <div class="form-row">
            <label>Статус связи</label>
            <select name="implementation_status">
              <option value="planned">planned</option>
              <option value="implemented">implemented</option>
              <option value="needs_review">needs_review</option>
            </select>
          </div>
          <div class="form-actions compact-form-actions">
            <button class="btn btn-primary" type="submit">Связать</button>
          </div>
        </div>
      </form>
    </section>
  `;
}

export function bindRequirementForms(container) {
  bindRequirementFilter(container);
  container.querySelector('[data-add-requirement-link]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const target = targetInfo();
    const requirementId = new FormData(event.target).get('requirement_id');
    if (!requirementId) {
      toast('Выберите требование');
      return;
    }
    await addRequirementLink(state.workspaceId, {
      requirement_id: requirementId,
      target_type: target.type,
      target_id: target.id,
      relation: formValue(event.target, 'relation') || 'defines',
      implementation_status: formValue(event.target, 'implementation_status') || 'planned'
    });
    toast('Требование связано');
    await renderAll({ reload: true });
  });
  container.querySelectorAll('[data-delete-requirement-link]').forEach(button => button.addEventListener('click', async () => {
    await deleteRequirementLink(state.workspaceId, button.dataset.deleteRequirementLink);
    await renderAll({ reload: true });
  }));
}

function bindRequirementFilter(container) {
  const input = container.querySelector('[data-requirement-filter]');
  const options = container.querySelector('[data-requirement-options]');
  if (!input || !options) return;
  input.oninput = () => {
    state.requirementFilter = input.value;
    options.innerHTML = renderRequirementOptions();
  };
}

function renderRequirementOptions() {
  const items = filteredRequirements();
  if (!requirements().length) {
    return '<div class="empty-state compact-empty">В локальном списке требований нет записей.</div>';
  }
  if (!items.length) {
    return '<div class="empty-state compact-empty">Требования по фильтру не найдены.</div>';
  }
  return items.map(req => `
    <label class="requirement-option">
      <input type="radio" name="requirement_id" value="${escapeHtml(req.id)}">
      <span>
        <strong>${escapeHtml(req.id)}</strong> — ${escapeHtml(req.title || req.text || '')}
        <span class="requirement-meta">${renderRequirementMeta(req)}</span>
      </span>
    </label>
  `).join('');
}

function filteredRequirements() {
  const query = state.requirementFilter.trim().toLowerCase();
  const all = requirements();
  if (!query) return all.slice(0, 30);
  return all.filter(req => requirementSearchText(req).includes(query)).slice(0, 50);
}

function requirementSearchText(req) {
  return [
    req.id,
    req.title,
    req.text,
    req.type,
    req.status,
    req.priority,
    req.group_id,
    groupTitle(req.group_id)
  ].map(value => String(value || '').toLowerCase()).join(' ');
}

function renderRequirementMeta(req) {
  const parts = [
    groupTitle(req.group_id),
    req.type,
    req.status,
    req.priority
  ].filter(Boolean);
  return parts.length ? parts.map(item => `<span class="badge">${escapeHtml(item)}</span>`).join('') : '<span class="muted">без типа и статуса</span>';
}

function groupTitle(groupId) {
  if (!groupId) return '';
  return requirementGroups().find(group => group.id === groupId)?.title || groupId;
}

function renderRequirementLink(link) {
  const req = requirements().find(item => item.id === link.requirement_id);
  return `
    <div class="link-item">
      <div><strong>${escapeHtml(link.requirement_id)}</strong> ${escapeHtml(req?.title || req?.text || '')}<br><span class="muted">${escapeHtml(link.relation)} · ${escapeHtml(link.implementation_status)}</span></div>
      <button class="btn btn-sm btn-danger" type="button" data-delete-requirement-link="${escapeHtml(link.id)}">Отвязать</button>
    </div>
  `;
}
