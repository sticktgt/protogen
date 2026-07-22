import { createRelation, deleteRelation } from './api.js';
import { escapeHtml, formValue, toast } from './html-utils.js';
import { renderAll } from './main.js';
import { entityTitle, relations, state, targetInfo } from './state.js';

const cardinalityOptions = [
  ['one_to_one', '1:1 — один к одному'],
  ['one_to_many', '1:N — один ко многим'],
  ['many_to_one', 'N:1 — многие к одному'],
  ['many_to_many', 'N:M — многие ко многим']
];

export function renderRelationsTab() {
  const target = targetInfo();
  if (target.type === 'field') {
    return '<div class="empty-state compact-empty">Логические связи описываются между сущностями. Для полей используйте вкладки Требования, UI, API и Код.</div>';
  }
  const entityRelations = relations().filter(item => item.source_entity === target.id || item.target_entity === target.id);
  return `
    <section class="editor-section">
      <h3 class="section-title">Добавить связь</h3>
      <form data-add-relation class="compact-form relation-add-form">
        <div class="form-row"><label>Название</label><input name="title" placeholder="Счета клиента"></div>
        <div class="form-row"><label>От сущности</label><select name="source_entity">${entityOptions(target.id)}</select></div>
        <div class="form-row"><label>К сущности</label><select name="target_entity">${entityOptions('')}</select></div>
        <div class="form-row"><label>Кардинальность</label><select name="cardinality">
          ${cardinalityOptions.map(([id, title]) => `<option value="${id}" ${id === 'one_to_many' ? 'selected' : ''}>${title}</option>`).join('')}
        </select></div>
        <div class="form-row form-row-wide"><label>Описание</label><input name="description"></div>
        <div class="form-actions compact-form-actions"><button class="btn btn-primary" type="submit">Добавить связь</button></div>
      </form>
    </section>
    <section class="editor-section">
      <h3 class="section-title">Связи сущности</h3>
      <div class="link-list left-link-list">${entityRelations.map(renderRelation).join('') || '<div class="empty-state compact-empty">Связей с другими сущностями нет.</div>'}</div>
    </section>
  `;
}

export function bindRelationForms(container) {
  container.querySelector('[data-add-relation]')?.addEventListener('submit', async event => {
    event.preventDefault();
    await createRelation(state.workspaceId, {
      title: formValue(event.target, 'title'),
      source_entity: formValue(event.target, 'source_entity'),
      target_entity: formValue(event.target, 'target_entity'),
      cardinality: formValue(event.target, 'cardinality'),
      description: formValue(event.target, 'description')
    });
    toast('Связь добавлена');
    await renderAll({ reload: true });
  });
  container.querySelectorAll('[data-delete-relation]').forEach(button => button.addEventListener('click', async () => {
    if (!confirm('Удалить связь?')) return;
    await deleteRelation(state.workspaceId, button.dataset.deleteRelation);
    toast('Связь удалена');
    await renderAll({ reload: true });
  }));
}

function renderRelation(relation) {
  return `
    <div class="link-item relation-link-item">
      <div>
        <strong>${escapeHtml(relation.title)}</strong><br>
        <span class="muted">${escapeHtml(entityTitle(relation.source_entity))} → ${escapeHtml(entityTitle(relation.target_entity))} · ${escapeHtml(relation.cardinality)}</span>
        ${relation.description ? `<div class="relation-description">${escapeHtml(relation.description)}</div>` : ''}
      </div>
      <div class="inline-actions relation-actions">
        <span class="badge">${escapeHtml(relation.id)}</span>
        <button class="btn btn-sm btn-danger" type="button" data-delete-relation="${escapeHtml(relation.id)}">Удалить</button>
      </div>
    </div>
  `;
}

function entityOptions(selectedId) {
  return (state.summary?.entities || []).map(item => `
    <option value="${escapeHtml(item.id)}" ${item.id === selectedId ? 'selected' : ''}>${escapeHtml(item.details?.title || item.title)}</option>
  `).join('');
}
