import { addApiLink, addUiLink, deleteApiLink, deleteUiLink, loadUiSchema } from './api.js';
import { escapeHtml, formValue, toast } from './html-utils.js';
import { renderAll } from './main.js';
import { state, targetInfo } from './state.js';

const uiRelationOptions = [
  ['displayed_by', 'Отображается элементом'],
  ['entered_by', 'Вводится элементом'],
  ['selected_by', 'Выбирается элементом'],
  ['represented_by', 'Представлено элементом'],
  ['uses', 'Используется элементом']
];

export function renderExternalLinksTab(kind) {
  if (kind === 'ui') return renderUiLinksTab();
  return renderGenericExternalLinksTab('api');
}

export function bindExternalLinkForms(container) {
  bindUiSchemaControls(container);
  container.querySelectorAll('[data-add-external-link]').forEach(form => {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const target = targetInfo();
      const payload = {
        data_target_type: target.type,
        data_target_id: target.id,
        external_target_type: formValue(form, 'external_target_type'),
        external_target_id: formValue(form, 'external_target_id'),
        relation: formValue(form, 'relation')
      };
      if (!payload.external_target_id) {
        toast('Выберите объект для связи');
        return;
      }
      if (form.dataset.addExternalLink === 'ui') await addUiLink(state.workspaceId, payload);
      if (form.dataset.addExternalLink === 'api') await addApiLink(state.workspaceId, payload);
      toast('Связь добавлена');
      await renderAll({ reload: true });
    });
  });
  container.querySelectorAll('[data-delete-ui-link]').forEach(button => button.addEventListener('click', async () => {
    await deleteUiLink(state.workspaceId, button.dataset.deleteUiLink);
    await renderAll({ reload: true });
  }));
  container.querySelectorAll('[data-delete-api-link]').forEach(button => button.addEventListener('click', async () => {
    await deleteApiLink(state.workspaceId, button.dataset.deleteApiLink);
    await renderAll({ reload: true });
  }));
}

export async function ensureUiSchemaLoaded() {
  if (state.uiSchemaSummary) return;
  try {
    state.uiSchemaSummary = await loadUiSchema(state.workspaceId);
  } catch (error) {
    toast('Не удалось загрузить UI-схему');
  }
}

function renderUiLinksTab() {
  const target = targetInfo();
  const links = (state.summary?.ui_links || []).filter(item => item.data_target_type === target.type && item.data_target_id === target.id);
  if (!state.uiSchemaSummary) {
    return `
      <div class="small-note">UI-схема будет загружена через API модуля <code>ui_schema</code>.</div>
      <button class="btn btn-primary btn-sm" type="button" data-load-ui-schema>Загрузить UI-схему</button>
      <section class="editor-section">
        <h3 class="section-title">Связанные UI-объекты</h3>
        <div class="link-list left-link-list">${links.map(link => renderExternalLink(link, 'ui')).join('') || '<div class="empty-state compact-empty">Связей с UI-схемой нет.</div>'}</div>
      </section>
    `;
  }
  const pages = uiPages();
  const selectedPage = selectedUiPage(pages);
  return `
    <section class="editor-section">
      <h3 class="section-title">Связанные UI-объекты</h3>
      <div class="link-list left-link-list">${links.map(link => renderExternalLink(link, 'ui')).join('') || '<div class="empty-state compact-empty">Связей с UI-схемой нет.</div>'}</div>
    </section>
    <section class="editor-section">
      <h3 class="section-title">Связать с элементом UI</h3>
      <form data-add-external-link="ui" class="ui-link-form">
        <input type="hidden" name="external_target_type" value="ui_element">
        <div class="compact-form ui-picker-filters">
          <div class="form-row">
            <label>Страница</label>
            <select data-ui-page-select name="ui_page">
              ${pages.map(page => `<option value="${escapeHtml(page.id)}" ${page.id === selectedPage?.id ? 'selected' : ''}>${escapeHtml(pageTitle(page))}</option>`).join('')}
            </select>
          </div>
          <div class="form-row">
            <label>Тип элемента</label>
            <select data-ui-type-filter name="ui_type_filter">
              <option value="">Все типы</option>
              ${uiElementTypes().map(type => `<option value="${escapeHtml(type)}" ${type === state.uiLinkTypeFilter ? 'selected' : ''}>${escapeHtml(type)}</option>`).join('')}
            </select>
          </div>
          <div class="form-row">
            <label>Фильтр</label>
            <input data-ui-text-filter name="ui_text_filter" placeholder="Название, ID или тип" value="${escapeHtml(state.uiLinkTextFilter)}">
          </div>
          <div class="form-row">
            <label>Отношение</label>
            <select name="relation">${uiRelationOptions.map(([id, title]) => `<option value="${id}" ${id === defaultUiRelation(target.type) ? 'selected' : ''}>${title}</option>`).join('')}</select>
          </div>
        </div>
        <div class="ui-element-picker" data-ui-element-picker>
          ${renderUiElementPicker(selectedPage)}
        </div>
        <div class="form-actions compact-form-actions"><button class="btn btn-primary" type="submit">Связать</button></div>
      </form>
    </section>
  `;
}

function renderGenericExternalLinksTab(kind) {
  const target = targetInfo();
  const listKey = kind === 'ui' ? 'ui_links' : 'api_links';
  const schema = kind === 'ui' ? 'ui_schema' : 'api_schema';
  const label = kind === 'ui' ? 'UI-объект' : 'API-объект';
  const links = (state.summary?.[listKey] || []).filter(item => item.data_target_type === target.type && item.data_target_id === target.id);
  return `
    <section class="editor-section">
      <h3 class="section-title">Связать с ${escapeHtml(schema)}</h3>
      <form data-add-external-link="${kind}" class="compact-form external-link-form ${kind}-link-form">
        <div class="form-row"><label>${label}: тип</label><input name="external_target_type" value="${kind === 'ui' ? 'ui_element' : 'operation'}"></div>
        <div class="form-row"><label>${label}: ID</label><input name="external_target_id" placeholder="accounts.list.balance_column"></div>
        <div class="form-row"><label>Отношение</label><input name="relation" value="${kind === 'ui' ? 'displayed_by' : 'used_by'}"></div>
        <div class="form-actions compact-form-actions"><button class="btn btn-primary" type="submit">Связать</button></div>
      </form>
    </section>
    <section class="editor-section">
      <h3 class="section-title">Связанные объекты</h3>
      <div class="link-list left-link-list">${links.map(link => renderExternalLink(link, kind)).join('') || `<div class="empty-state compact-empty">Связей с ${escapeHtml(schema)} нет.</div>`}</div>
    </section>
  `;
}

function renderExternalLink(link, kind) {
  return `
    <div class="link-item">
      <div><strong>${escapeHtml(link.external_target_id)}</strong><br><span class="muted">${escapeHtml(link.external_target_type)} · ${escapeHtml(link.relation)}</span></div>
      <button class="btn btn-sm btn-danger" type="button" data-delete-${kind}-link="${escapeHtml(link.id)}">Отвязать</button>
    </div>
  `;
}

function bindUiSchemaControls(container) {
  container.querySelector('[data-load-ui-schema]')?.addEventListener('click', async () => {
    await ensureUiSchemaLoaded();
    await renderAll();
  });
  container.querySelector('[data-ui-page-select]')?.addEventListener('change', async event => {
    state.uiLinkPageId = event.target.value;
    await renderAll();
  });
  container.querySelector('[data-ui-type-filter]')?.addEventListener('change', async event => {
    state.uiLinkTypeFilter = event.target.value;
    await renderAll();
  });
  container.querySelector('[data-ui-text-filter]')?.addEventListener('input', event => {
    state.uiLinkTextFilter = event.target.value;
    const selectedPage = selectedUiPage(uiPages());
    const picker = container.querySelector('[data-ui-element-picker]');
    if (picker) picker.innerHTML = renderUiElementPicker(selectedPage);
  });
}

function uiPages() {
  return state.uiSchemaSummary?.pages || [];
}

function pageTitle(page) {
  return page.details?.title || page.title || page.id;
}

function selectedUiPage(pages) {
  if (!pages.length) return null;
  const page = pages.find(item => item.id === state.uiLinkPageId) || pages[0];
  state.uiLinkPageId = page.id;
  return page;
}

function uiElementTypes() {
  const types = new Set();
  for (const page of uiPages()) {
    walkElements(page.details?.elements || [], element => types.add(element.type));
  }
  return [...types].filter(Boolean).sort();
}

function walkElements(elements, visit) {
  for (const element of elements || []) {
    visit(element);
    walkElements(element.children || [], visit);
  }
}

function renderUiElementPicker(page) {
  if (!page) return '<div class="empty-state compact-empty">В UI-схеме нет страниц.</div>';
  const rendered = renderUiElements(page.details?.elements || [], 0);
  return rendered || '<div class="empty-state compact-empty">Элементы по фильтру не найдены.</div>';
}

function renderUiElements(elements, level) {
  return (elements || []).map(element => renderUiElementOption(element, level)).filter(Boolean).join('');
}

function renderUiElementOption(element, level) {
  const childrenHtml = renderUiElements(element.children || [], level + 1);
  const matches = uiElementMatches(element);
  if (!matches && !childrenHtml) return '';
  const selectable = matches;
  return `
    <div class="ui-element-option ${selectable ? '' : 'ui-element-ancestor'}" style="--ui-level: ${level}">
      ${selectable ? `<label><input type="radio" name="external_target_id" value="${escapeHtml(element.id)}">` : '<div class="ui-element-ancestor-label">'}
        <span class="ui-element-title">${escapeHtml(element.label || element.title || element.id)}</span>
        <span class="type-badge">${escapeHtml(element.type || 'element')}</span>
        <span class="muted">${escapeHtml(element.id)}</span>
      ${selectable ? '</label>' : '</div>'}
    </div>
    ${childrenHtml}
  `;
}

function uiElementMatches(element) {
  const typeFilter = state.uiLinkTypeFilter;
  const textFilter = state.uiLinkTextFilter.trim().toLowerCase();
  const typeMatches = !typeFilter || element.type === typeFilter;
  const text = [element.id, element.label, element.title, element.type].map(value => String(value || '').toLowerCase()).join(' ');
  const textMatches = !textFilter || text.includes(textFilter);
  return typeMatches && textMatches;
}

function defaultUiRelation(targetType) {
  return targetType === 'field' ? 'displayed_by' : 'represented_by';
}
