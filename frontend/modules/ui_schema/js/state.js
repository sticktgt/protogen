export const APP_SCOPE = '__app__';

export const groupElementTypes = [
  'section', 'form', 'filter_panel', 'toolbar', 'details_panel', 'tabs', 'modal',
  'wizard', 'grid', 'table_with_actions', 'card', 'list', 'main_menu', 'menu_group'
];

export const atomicElementTypes = [
  'text', 'image', 'input', 'textarea', 'select', 'checkbox', 'radio', 'button', 'link',
  'table', 'badge', 'date_picker', 'file_upload', 'menu_item'
];

export const pageElementTypes = groupElementTypes.concat(atomicElementTypes)
  .filter(type => !['main_menu', 'menu_group', 'menu_item'].includes(type));

export const appElementTypes = ['main_menu', 'menu_group', 'menu_item'];
export const elementTypes = groupElementTypes.concat(atomicElementTypes);

const typeMeta = {
  section: ['▦', 'section'],
  form: ['📝', 'form'],
  filter_panel: ['🔎', 'filter_panel'],
  toolbar: ['🧰', 'toolbar'],
  details_panel: ['📋', 'details_panel'],
  tabs: ['🗂️', 'tabs'],
  modal: ['◫', 'modal'],
  wizard: ['🪄', 'wizard'],
  grid: ['▦', 'grid'],
  table_with_actions: ['📊', 'table_with_actions'],
  main_menu: ['🧭', 'main_menu'],
  menu_group: ['📁', 'menu_group'],
  menu_item: ['➡️', 'menu_item'],
  text: ['T', 'text'],
  image: ['🖼️', 'image'],
  input: ['⌨️', 'input'],
  textarea: ['¶', 'textarea'],
  select: ['▾', 'select'],
  checkbox: ['☑', 'checkbox'],
  radio: ['◉', 'radio'],
  button: ['🔘', 'button'],
  link: ['🔗', 'link'],
  table: ['▤', 'table'],
  list: ['☰', 'list'],
  card: ['▣', 'card'],
  badge: ['🏷️', 'badge'],
  date_picker: ['📅', 'date_picker'],
  file_upload: ['📎', 'file_upload']
};

export const state = {
  workspaceId: null,
  summary: null,
  activeTab: 'map',
  selectedPageId: null,
  selectedElementId: null,
  selectedRequirementId: null,
  elementEditorTab: 'info',
  createPageMode: false,
  showRequirementLinkForm: false,
  showElementCreateForm: false,
  showUiLinkForm: false
};

export function pages() {
  return state.summary?.pages || [];
}

export function appSchema() {
  return state.summary?.app || { id: 'app', title: 'Приложение', root_elements: [] };
}

export function requirements() {
  return state.summary?.requirements?.requirements || [];
}

export function links() {
  return state.summary?.requirement_links?.links || [];
}

export function uiLinks() {
  return state.summary?.ui_links?.links || [];
}

export function codeLinks() {
  return state.summary?.code_links?.links || [];
}

export function selectedPage() {
  if (state.selectedPageId === APP_SCOPE) return null;
  return pages().find(item => item.id === state.selectedPageId)?.details || null;
}

export function selectedScopeElements() {
  if (state.selectedPageId === APP_SCOPE) return appSchema().root_elements || [];
  return selectedPage()?.elements || [];
}

export function findPageByElement(elementId) {
  for (const page of pages()) {
    if (findElement(page.details, elementId)) return page.details;
  }
  return null;
}

export function findAppElement(elementId) {
  return findElementInList(appSchema().root_elements || [], elementId);
}

export function findAnyElement(elementId) {
  return findAppElement(elementId) || findPageByElement(elementId)?.elements && findElement(findPageByElement(elementId), elementId);
}

export function findElement(page, elementId) {
  if (!page) return null;
  return findElementInList(page.elements || [], elementId);
}

function findElementInList(elements, elementId) {
  for (const element of elements || []) {
    if (element.id === elementId) return element;
    const nested = findElementInList(element.children || [], elementId);
    if (nested) return nested;
  }
  return null;
}

export function findParentElement(page, elementId) {
  if (!page || !elementId) return null;
  return findParentInList(page.elements || [], elementId, null);
}

export function findAppParentElement(elementId) {
  if (!elementId) return null;
  return findParentInList(appSchema().root_elements || [], elementId, null);
}

function findParentInList(elements, elementId, parent) {
  for (const element of elements || []) {
    if (element.id === elementId) return parent;
    const nested = findParentInList(element.children || [], elementId, element);
    if (nested) return nested;
  }
  return null;
}

export function flattenElements(page) {
  const result = [];
  function walk(elements, depth = 0) {
    for (const element of elements || []) {
      result.push({ ...element, depth });
      walk(element.children || [], depth + 1);
    }
  }
  walk(page?.elements || []);
  return result;
}

export function flattenAppElements() {
  const result = [];
  function walk(elements, depth = 0) {
    for (const element of elements || []) {
      result.push({ ...element, depth, scope: 'app' });
      walk(element.children || [], depth + 1);
    }
  }
  walk(appSchema().root_elements || []);
  return result;
}

export function isGroupElement(element) {
  return !!element && groupElementTypes.includes(element.type);
}

export function isAppScope() {
  return state.selectedPageId === APP_SCOPE;
}

export function allowedChildTypes(parent) {
  if (!isAppScope()) return pageElementTypes;
  if (!parent) {
    const hasMainMenu = (appSchema().root_elements || []).some(element => element.type === 'main_menu');
    return hasMainMenu ? [] : ['main_menu'];
  }
  if (parent.type === 'main_menu') return ['menu_group', 'menu_item'];
  if (parent.type === 'menu_group') return ['menu_item'];
  return [];
}


export function isLinkSourceElement(element) {
  return !!element && ['menu_item', 'button', 'link', 'card'].includes(element.type);
}

export function allModalElements() {
  const result = [];
  for (const page of pages()) {
    for (const element of flattenElements(page.details)) {
      if (element.type === 'modal') result.push({ ...element, page_id: page.id });
    }
  }
  return result;
}

export function elementTypeIcon(type) {
  return typeMeta[type]?.[0] || '□';
}

export function elementTypeLabel(type) {
  return typeMeta[type]?.[1] || type || '';
}

export function elementTypeText(type) {
  return `${elementTypeIcon(type)} ${elementTypeLabel(type)}`;
}

export function elementTitle(elementOrId) {
  if (typeof elementOrId !== 'string') {
    return elementOrId?.label || elementOrId?.title || elementOrId?.id || '';
  }
  const appElement = findAppElement(elementOrId);
  if (appElement) return elementTitle(appElement);
  for (const page of pages()) {
    const element = findElement(page.details, elementOrId);
    if (element) return elementTitle(element);
  }
  return elementOrId;
}

export function requirementTitle(id) {
  const req = requirements().find(item => item.id === id);
  return req ? `${req.code || req.id} — ${req.name || ''}` : id;
}

export function requirementById(id) {
  return requirements().find(item => item.id === id) || null;
}

export function pageTitle(id) {
  const page = pages().find(item => item.id === id);
  return page?.title || page?.details?.title || id;
}

export function targetTitle(targetType, targetId) {
  if (targetType === 'page') return pageTitle(targetId);
  return elementTitle(targetId);
}
