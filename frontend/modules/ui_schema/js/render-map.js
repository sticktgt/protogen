import {
  APP_SCOPE,
  appSchema,
  codeLinks,
  elementTypeIcon,
  elementTypeLabel,
  flattenAppElements,
  flattenElements,
  links,
  pages,
  requirements,
  requirementsSource,
  state,
  targetTitle,
  uiLinks
} from './state.js';
import { renderAll } from './main.js';
import { escapeAttr, escapeHtml } from './html-utils.js';
import { renderChangeBadge, renderScopeChangeCounts } from './preview-diff.js';

const CARD_ELEMENT_LIMIT = 5;

export function renderMapView() {
  renderStats();
  renderCreateButton();
  renderAppRootPreview();
  renderPageGrid();
}

function renderStats() {
  const container = document.querySelector('[data-schema-stats]');
  if (!container) return;
  const allElements = pages().flatMap(page => flattenElements(page.details));
  const appElements = flattenAppElements();
  const linkedTargets = new Set(links().map(link => link.target_id));
  const implemented = links().filter(link => link.implementation_status === 'implemented').length;
  const withReqs = allElements.concat(appElements).filter(element => linkedTargets.has(element.id)).length;
  const empty = Math.max(0, allElements.length + appElements.length - withReqs);
  const requirementIds = new Set(requirements().map(item => item.id).filter(Boolean));
  const linkedRequirementIds = new Set(links().map(link => link.requirement_id).filter(Boolean));
  const unlinkedRequirements = [...requirementIds].filter(id => !linkedRequirementIds.has(id)).length;
  const unresolvedLinks = [...linkedRequirementIds].filter(id => !requirementIds.has(id)).length;
  const source = requirementsSource();
  container.innerHTML = `
    <div class="schema-nav-title">Статистика</div>
    <div class="schema-stat-row"><span class="schema-stat-label">Страниц</span><span class="schema-stat-value">${pages().length}</span></div>
    <div class="schema-stat-row"><span class="schema-stat-label">Элементов</span><span class="schema-stat-value">${allElements.length + appElements.length}</span></div>
    <div class="schema-stat-row"><span class="schema-stat-label">Корневых</span><span class="schema-stat-value">${appElements.length}</span></div>
    <div class="schema-stat-row"><span class="schema-stat-label">С требованиями</span><span class="schema-stat-value success">${withReqs}</span></div>
    <div class="schema-stat-row"><span class="schema-stat-label">Без требований</span><span class="schema-stat-value warning">${empty}</span></div>
    <div class="schema-stat-row"><span class="schema-stat-label">Реализовано</span><span class="schema-stat-value success">${implemented}</span></div>
    <div class="schema-stat-row"><span class="schema-stat-label">Без прямых UI-связей</span><span class="schema-stat-value">${unlinkedRequirements}</span></div>
    <div class="schema-stat-row"><span class="schema-stat-label">Неразрешённых связей</span><span class="schema-stat-value${unresolvedLinks ? ' warning' : ''}">${unresolvedLinks}</span></div>
    <div class="schema-requirements-source ${escapeAttr(source.status || '')}">
      <strong>Источник требований</strong>
      <span>${escapeHtml(source.path || 'не настроен')}</span>
      ${source.changed_since_sync ? '<span class="warning-text">Файл изменён после последней синхронизации</span>' : ''}
      ${source.error ? `<span class="warning-text">${escapeHtml(source.error)}</span>` : ''}
    </div>
  `;
}

function renderCreateButton() {
  const button = document.querySelector('[data-start-page-create]');
  if (!button) return;
  button.onclick = () => {
    state.createPageMode = true;
    state.selectedElementId = null;
    state.activeTab = 'structure';
    renderAll();
  };
}

function renderAppRootPreview() {
  const container = document.querySelector('[data-app-root-preview]');
  if (!container) return;
  const app = appSchema();
  const roots = app.root_elements || [];
  container.innerHTML = `
    <div class="app-root-card" data-open-app-root>
      <div class="app-root-header">
        <span>🧭</span>
        <strong>${escapeHtml(app.title || 'Приложение')}</strong>
        ${renderChangeBadge('application', 'app')}
        ${renderScopeChangeCounts(APP_SCOPE)}
        <span class="ui-screen-count">${flattenAppElements().length} элементов</span>
      </div>
      <div class="app-root-body">
        ${roots.map(renderRootElement).join('') || '<div class="empty-state compact">Корневых элементов нет.</div>'}
      </div>
    </div>
  `;
  container.querySelector('[data-open-app-root]')?.addEventListener('click', event => {
    const elementTarget = event.target.closest('[data-open-app-element]');
    state.selectedPageId = APP_SCOPE;
    state.selectedElementId = elementTarget ? elementTarget.dataset.openAppElement : null;
    state.createPageMode = false;
    state.selectedDeletedChange = null;
    state.elementEditorTab = 'info';
    state.activeTab = 'structure';
    renderAll();
  });
}

function renderRootElement(element) {
  const childCount = countNested(element);
  return `
    <div class="root-widget-card" data-open-app-element="${escapeAttr(element.id)}">
      <div class="ui-widget-card-top">
        <div class="ui-widget-card-name">${escapeHtml(elementTypeIcon(element.type))} ${escapeHtml(element.label || element.id)} ${renderChangeBadge('ui_element', element.id)}</div>
        <div class="ui-widget-card-type">${escapeHtml(elementTypeLabel(element.type))}</div>
      </div>
      <div class="ui-widget-card-desc">${escapeHtml(element.description || '')}</div>
      <div class="item-meta">${childCount} вложенных элементов</div>
    </div>
  `;
}

function renderPageGrid() {
  const container = document.querySelector('[data-page-grid]');
  if (!container) return;
  container.innerHTML = pages().map(pageWrapper => renderPageCard(pageWrapper.details || pageWrapper)).join('') || '<div class="empty-state">Страниц нет.</div>';

  container.querySelectorAll('[data-select-page]').forEach(item => {
    item.addEventListener('click', event => {
      const elementTarget = event.target.closest('[data-open-element]');
      state.selectedPageId = item.dataset.selectPage;
      state.selectedElementId = elementTarget ? elementTarget.dataset.openElement : null;
      state.createPageMode = false;
      state.elementEditorTab = 'info';
      state.showRequirementLinkForm = false;
      state.showElementCreateForm = false;
      state.showUiLinkForm = false;
      state.activeTab = 'structure';
      renderAll();
    });
  });
}

function renderPageCard(page) {
  const pageLinks = links().filter(link => link.target_type === 'page' && link.target_id === page.id);
  const pageCodeLinks = codeLinks().filter(link => link.target_type === 'page' && link.target_id === page.id);
  const incomingUiLinks = uiLinks().filter(link => link.target_type === 'page' && link.target_id === page.id);
  const selected = page.id === state.selectedPageId ? ' selected' : '';
  const allElements = flattenElements(page);
  return `
    <div class="ui-screen-card${selected}" data-select-page="${escapeAttr(page.id)}">
      <div class="ui-screen-card-header">
        <span>📄</span>
        <span>${escapeHtml(page.title || page.id)}</span>
        ${renderChangeBadge('page', page.id)}
        ${renderScopeChangeCounts(page.id)}
        <span class="ui-screen-count">${allElements.length} элементов</span>
      </div>
      <div class="ui-screen-badges">
        ${incomingUiLinks.some(link => link.source_id.startsWith('app.main_menu')) ? '<span class="schema-badge success">в меню</span>' : '<span class="schema-badge muted">не в меню</span>'}
      </div>
      <div class="ui-screen-desc">${escapeHtml(page.description || 'Описание не задано')}</div>
      <div class="ui-screen-card-body">
        ${renderPageElementsPreview(page, allElements.length)}
      </div>
      ${incomingUiLinks.length ? `<div class="ui-screen-links">${incomingUiLinks.slice(0, 3).map(link => `↳ ${escapeHtml(targetTitle('ui_element', link.source_id))}`).join('<br>')}</div>` : ''}
      <div class="ui-screen-footer">
        <span>${pageLinks.length} требований</span>
        <span>${pageCodeLinks.length} файлов кода</span>
      </div>
    </div>
  `;
}

function renderPageElementsPreview(page, totalCount) {
  const visible = (page.elements || []).slice(0, CARD_ELEMENT_LIMIT);
  const hiddenCount = Math.max(0, totalCount - visible.length);
  const cards = visible.map(renderElementPreview).join('');
  const overflow = hiddenCount
    ? `<div class="ui-widget-overflow">Еще ${hiddenCount} вложенных элементов</div>`
    : '';
  return (cards || '<div class="empty-state compact">На странице нет элементов</div>') + overflow;
}

function renderElementPreview(element) {
  const count = links().filter(link => link.target_id === element.id).length;
  return `
    <div class="ui-widget-card${count ? ' has-reqs' : ''}" data-open-element="${escapeAttr(element.id)}">
      <div class="ui-widget-card-top">
        <div class="ui-widget-card-name">${escapeHtml(element.label || element.id)} ${renderChangeBadge('ui_element', element.id)}</div>
        <div class="ui-widget-card-type">${escapeHtml(elementTypeIcon(element.type))} ${escapeHtml(elementTypeLabel(element.type))}</div>
      </div>
      <div class="ui-widget-card-desc">${escapeHtml(element.description || element.purpose || '')}</div>
    </div>
  `;
}

function countNested(element) {
  let count = 0;
  for (const child of element.children || []) {
    count += 1 + countNested(child);
  }
  return count;
}
