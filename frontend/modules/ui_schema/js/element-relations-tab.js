import { addUiLink, deleteUiLink } from './api.js';
import {
  APP_SCOPE,
  elementTitle,
  elementTypeIcon,
  findAppParentElement,
  findParentElement,
  isLinkSourceElement,
  pages,
  pageTitle,
  state,
  targetTitle,
  uiLinks,
  allModalElements
} from './state.js';
import { renderAll } from './main.js';
import { escapeAttr, escapeHtml } from './html-utils.js';
import { showToast } from '/base/js/ui.js';

export function renderRelationsTab(container, page, target, appMode = false, targetType = 'ui_element') {
  const isPageTarget = targetType === 'page';
  const parent = isPageTarget ? null : (appMode ? findAppParentElement(target.id) : findParentElement(page, target.id));
  const children = isPageTarget ? (page?.elements || []) : (target.children || []);
  const outgoing = uiLinks().filter(link => link.source_type === targetType && link.source_id === target.id);
  const incoming = uiLinks().filter(link => link.target_type === targetType && link.target_id === target.id);
  container.innerHTML = `
    <div class="detail-section-title">Связи</div>
    <div class="relation-block">
      <div class="relation-label">Элемент верхнего уровня</div>
      ${parent ? renderRelationButton(parent, appMode) : renderRootButton(page, appMode, isPageTarget)}
    </div>
    <div class="relation-block">
      <div class="relation-label">Входящие элементы ниже уровнем</div>
      <div class="relation-buttons">
        ${children.map(child => renderRelationButton(child, appMode)).join('') || '<span class="text-muted text-sm">Дочерних элементов нет.</span>'}
      </div>
    </div>
    <div class="relation-block">
      <div class="relation-label">Исходящие связи</div>
      <div class="link-list">
        ${outgoing.map(renderUiLink).join('') || '<span class="text-muted text-sm">Исходящих связей нет.</span>'}
      </div>
      ${!isPageTarget ? renderAddLinkPanel(target) : ''}
    </div>
    <div class="relation-block">
      <div class="relation-label">Входящие связи</div>
      <div class="link-list">
        ${incoming.map(renderIncomingLink).join('') || '<span class="text-muted text-sm">Входящих связей нет.</span>'}
      </div>
    </div>
  `;

  bindStructureNavigation(container, appMode);
  bindUiLinkActions(container, target);
}

function renderRootButton(page, appMode, isPageTarget = false) {
  if (appMode) {
    return `<button class="btn btn-sm" type="button" data-select-app-root>🧭 Приложение</button>`;
  }
  if (isPageTarget) {
    return '<span class="text-muted text-sm">Страница является верхним уровнем.</span>';
  }
  return `<button class="btn btn-sm" type="button" data-select-page-root>📄 ${escapeHtml(page.title || page.id)}</button>`;
}

function renderRelationButton(element, appMode) {
  return `<button class="btn btn-sm" type="button" data-select-related-element="${escapeAttr(element.id)}" data-related-app="${appMode ? '1' : '0'}">${escapeHtml(elementTypeIcon(element.type))} ${escapeHtml(elementTitle(element))}</button>`;
}

function renderUiLink(link) {
  return `
    <div class="ui-link-row">
      <span>${escapeHtml(relationLabel(link.relation))}</span>
      <strong>${escapeHtml(targetTitle(link.target_type, link.target_id))}</strong>
      <button class="btn btn-sm" type="button" data-open-ui-link-target="${escapeAttr(link.target_type)}:${escapeAttr(link.target_id)}">Перейти</button>
      <button class="btn btn-sm btn-danger" type="button" data-delete-ui-link="${escapeAttr(link.id)}">Удалить</button>
    </div>
  `;
}

function renderIncomingLink(link) {
  return `
    <div class="ui-link-row">
      <span>${escapeHtml(relationLabel(link.relation))}</span>
      <strong>${escapeHtml(sourceTitle(link.source_type, link.source_id))}</strong>
      <button class="btn btn-sm" type="button" data-open-ui-link-source="${escapeAttr(link.source_type)}:${escapeAttr(link.source_id)}">Перейти</button>
    </div>
  `;
}

function renderAddLinkPanel(element) {
  if (!isLinkSourceElement(element)) {
    return '<div class="form-hint">Для этого типа элемента переходы не задаются.</div>';
  }
  if (!state.showUiLinkForm) {
    return `<div class="relation-actions"><button class="btn btn-primary btn-sm" type="button" data-show-ui-link-form>Добавить переход</button></div>`;
  }

  const targetOptions = buildTargetOptions(element);
  if (!targetOptions.length) {
    return '<div class="form-hint">Нет доступных целей для перехода.</div>';
  }

  return `
    <form class="schema-form inline-link-form" data-ui-link-form>
      <div class="form-row">
        <label>Переход</label>
        <select name="target_value">
          ${targetOptions.join('')}
        </select>
      </div>
      <div class="page-actions-row">
        <button class="btn btn-primary" type="submit">Связать</button>
        <button class="btn" type="button" data-cancel-ui-link-form>Отмена</button>
      </div>
    </form>
  `;
}

function buildTargetOptions(element) {
  const pageOptions = pages().map(page => `
    <option value="page:${escapeAttr(page.id)}:navigates_to">📄 ${escapeHtml(page.details?.title || page.title || page.id)}</option>
  `);
  if (element.type === 'menu_item') return pageOptions;
  const modalOptions = allModalElements().map(modal => `
    <option value="ui_element:${escapeAttr(modal.id)}:opens_modal">◫ ${escapeHtml(modal.label || modal.id)}</option>
  `);
  return pageOptions.concat(modalOptions);
}

function bindStructureNavigation(container, appMode) {
  container.querySelectorAll('[data-select-related-element]').forEach(button => {
    button.addEventListener('click', () => {
      state.selectedPageId = button.dataset.relatedApp === '1' ? APP_SCOPE : state.selectedPageId;
      state.selectedElementId = button.dataset.selectRelatedElement;
      state.elementEditorTab = 'info';
      renderAll();
    });
  });

  container.querySelector('[data-select-page-root]')?.addEventListener('click', () => {
    state.selectedElementId = null;
    state.elementEditorTab = 'info';
    renderAll();
  });

  container.querySelector('[data-select-app-root]')?.addEventListener('click', () => {
    state.selectedPageId = APP_SCOPE;
    state.selectedElementId = null;
    state.elementEditorTab = 'info';
    renderAll();
  });
}

function bindUiLinkActions(container, element) {
  container.querySelector('[data-show-ui-link-form]')?.addEventListener('click', () => {
    state.showUiLinkForm = true;
    renderAll();
  });

  container.querySelector('[data-cancel-ui-link-form]')?.addEventListener('click', () => {
    state.showUiLinkForm = false;
    renderAll();
  });

  container.querySelector('[data-ui-link-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const [targetType, targetId, relation] = String(form.get('target_value')).split(':');
    await addUiLink(state.workspaceId, {
      source_type: 'ui_element',
      source_id: element.id,
      target_type: targetType,
      target_id: targetId,
      relation
    });
    state.showUiLinkForm = false;
    showToast('Связь добавлена');
    await renderAll({ reload: true });
  });

  container.querySelectorAll('[data-delete-ui-link]').forEach(button => {
    button.addEventListener('click', async () => {
      await deleteUiLink(state.workspaceId, button.dataset.deleteUiLink);
      showToast('Связь удалена');
      await renderAll({ reload: true });
    });
  });

  container.querySelectorAll('[data-open-ui-link-target]').forEach(button => {
    button.addEventListener('click', () => openTarget(button.dataset.openUiLinkTarget));
  });

  container.querySelectorAll('[data-open-ui-link-source]').forEach(button => {
    button.addEventListener('click', () => openTarget(button.dataset.openUiLinkSource));
  });
}

function openTarget(value) {
  const [type, id] = value.split(':');
  if (type === 'page') {
    state.selectedPageId = id;
    state.selectedElementId = null;
  } else {
    state.selectedElementId = id;
    if (id.startsWith('app.')) state.selectedPageId = APP_SCOPE;
  }
  state.elementEditorTab = 'info';
  renderAll();
}

function sourceTitle(sourceType, sourceId) {
  if (sourceType === 'page') return pageTitle(sourceId);
  return elementTitle(sourceId);
}

function relationLabel(relation) {
  return {
    navigates_to: 'переход',
    opens_modal: 'открывает',
    links_to: 'связь'
  }[relation] || relation || 'связь';
}
