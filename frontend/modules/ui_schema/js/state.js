export const APP_SCOPE = '__app__';

export const groupElementTypes = [];
export const atomicElementTypes = [];
export const pageElementTypes = [];
export const appElementTypes = [];
export const elementTypes = [];

const typeMeta = {};
const typeDefinitions = new Map();

function replaceArray(target, values) {
  target.splice(0, target.length, ...values);
}

export function configureElementTypes(moduleConfig) {
  const config = moduleConfig?.config || moduleConfig?.module_config || moduleConfig;
  const definitions = config?.ui?.element_types;
  if (!Array.isArray(definitions) || definitions.length === 0) {
    throw new Error('В config.yaml не задан ui.element_types');
  }

  typeDefinitions.clear();
  for (const key of Object.keys(typeMeta)) delete typeMeta[key];

  const seen = new Set();
  for (const definition of definitions) {
    const type = definition?.id;
    if (!type || seen.has(type)) throw new Error(`Некорректный тип UI-элемента: ${type || '<empty>'}`);
    if (!['page', 'app'].includes(definition.scope)) throw new Error(`Некорректная область типа ${type}`);
    if (!['group', 'atomic'].includes(definition.kind)) throw new Error(`Некорректный вид типа ${type}`);
    seen.add(type);
    typeDefinitions.set(type, definition);
    typeMeta[type] = [definition.icon || '□', definition.label || type];
  }

  replaceArray(groupElementTypes, definitions.filter(item => item.kind === 'group').map(item => item.id));
  replaceArray(atomicElementTypes, definitions.filter(item => item.kind === 'atomic').map(item => item.id));
  replaceArray(pageElementTypes, definitions.filter(item => item.scope === 'page').map(item => item.id));
  replaceArray(appElementTypes, definitions.filter(item => item.scope === 'app').map(item => item.id));
  replaceArray(elementTypes, definitions.map(item => item.id));
}

export const state = {
  workspaceId: null,
  previewRunId: null,
  previewActive: false,
  readOnly: false,
  writeLocked: false,
  agentRun: null,
  agentChanges: null,
  agentEvents: [],
  agentMetrics: null,
  agentEventCursor: 0,
  agentHistory: null,
  agentInitialAvailable: false,
  agentLoaded: false,
  agentLlmTest: null,
  agentStartError: "",
  agentRequirementsPath: "",
  agentUserRequest: "",
  agentBaseMode: "current",
  summary: null,
  activeTab: 'map',
  selectedPageId: null,
  selectedElementId: null,
  selectedRequirementId: null,
  selectedDeletedChange: null,
  elementEditorTab: 'info',
  createPageMode: false,
  showRequirementLinkForm: false,
  showElementCreateForm: false,
  showUiLinkForm: false
};

export function configureAgentDefaults(moduleConfig) {
  const config = moduleConfig?.config || moduleConfig?.module_config || moduleConfig;
  const defaultPath = config?.agent?.requirements?.default_workspace_path;
  if (!state.agentRequirementsPath && typeof defaultPath === 'string') {
    state.agentRequirementsPath = defaultPath;
  }
}

export function pages() {
  return state.summary?.pages || [];
}

export function appSchema() {
  return state.summary?.app || { id: 'app', title: 'Приложение', root_elements: [] };
}

export function requirements() {
  return state.summary?.requirements?.requirements || [];
}

export function requirementsSource() {
  return state.summary?.requirements_source || { status: 'not_configured' };
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
  if (!isAppScope()) {
    return parent && !isGroupElement(parent) ? [] : pageElementTypes;
  }
  if (!parent) {
    return appElementTypes.filter(type => {
      const definition = typeDefinitions.get(type);
      if (!definition?.root_allowed) return false;
      if (!definition.unique_root) return true;
      return !(appSchema().root_elements || []).some(element => element.type === type);
    });
  }
  const definition = typeDefinitions.get(parent.type);
  return Array.isArray(definition?.allowed_children) ? definition.allowed_children : [];
}


export function isLinkSourceElement(element) {
  return !!element && typeDefinitions.get(element.type)?.link_source === true;
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
