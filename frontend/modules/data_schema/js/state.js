export const state = {
  workspaceId: null,
  previewRunId: null,
  previewActive: false,
  readOnly: false,
  writeLocked: false,
  agentRun: null,
  agentChanges: null,
  agentRequirementsResult: null,
  agentEvents: [],
  agentMetrics: null,
  agentEventCursor: 0,
  agentHistory: null,
  agentInitialAvailable: false,
  agentLoaded: false,
  agentLlmTest: null,
  agentStartError: '',
  agentRequirementsPath: '',
  agentUserRequest: '',
  agentBaseMode: 'current',
  agentPollIntervalMs: null,
  agentEventPageSize: null,
  agentEventBufferSize: null,
  agentEventDisplayLimit: null,
  agentIdleWarningSeconds: null,
  summary: null,
  activeTab: 'graph',
  selectedEntityId: null,
  selectedFieldId: null,
  activeEditorTab: 'fields',
  createEntityMode: false,
  createRelationMode: false,
  mapEntityFilter: '',
  structureEntityFilter: '',
  requirementFilter: '',
  uiSchemaSummary: null,
  uiLinkPageId: '',
  uiLinkTypeFilter: '',
  uiLinkTextFilter: '',
  graphSelectedEntityId: null,
  graphSelectedRelationId: null
};

export function configureAgentDefaults(moduleConfig) {
  const config = moduleConfig?.config || moduleConfig?.module_config || moduleConfig;
  const defaultPath = config?.agent?.requirements?.default_workspace_path;
  if (!state.agentRequirementsPath && typeof defaultPath === 'string') {
    state.agentRequirementsPath = defaultPath;
  }
  const ui = config?.agent?.ui || {};
  state.agentPollIntervalMs = requiredPositiveNumber(ui, 'poll_interval_ms');
  state.agentEventPageSize = requiredPositiveNumber(ui, 'event_page_size');
  state.agentEventBufferSize = requiredPositiveNumber(ui, 'event_buffer_size');
  state.agentEventDisplayLimit = requiredPositiveNumber(ui, 'event_display_limit');
  state.agentIdleWarningSeconds = requiredPositiveNumber(ui, 'idle_warning_seconds');
}

function requiredPositiveNumber(config, name) {
  const value = Number(config?.[name]);
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`agent.ui.${name} must be configured`);
  }
  return value;
}

export function entities() {
  return state.summary?.entities || [];
}

export function entityDetails(entityId = state.selectedEntityId) {
  return entities().find(item => item.id === entityId)?.details || null;
}

export function selectedField() {
  const entity = entityDetails();
  return entity?.fields?.find(item => item.id === state.selectedFieldId) || null;
}

export function relations() {
  return state.summary?.relations || [];
}

export function dictionaries() {
  return state.summary?.dictionaries || [];
}

export function requirements() {
  return state.summary?.requirements || [];
}

export function requirementGroups() {
  return state.summary?.requirement_groups || state.summary?.groups || [];
}

export function targetInfo() {
  if (state.selectedFieldId) {
    return {
      type: 'field',
      id: `${state.selectedEntityId}.${state.selectedFieldId}`,
      title: selectedField()?.title || state.selectedFieldId
    };
  }
  if (state.selectedEntityId) {
    return {
      type: 'entity',
      id: state.selectedEntityId,
      title: entityDetails()?.title || state.selectedEntityId
    };
  }
  return null;
}

export function relationTitle(relation) {
  return relation.title || relation.id;
}

export function entityTitle(entityId) {
  return entityDetails(entityId)?.title || entityId;
}

export function selectEntity(entityId) {
  state.selectedEntityId = entityId;
  state.selectedFieldId = null;
  state.createEntityMode = false;
  state.createRelationMode = false;
}

export function selectField(entityId, fieldId) {
  state.selectedEntityId = entityId;
  state.selectedFieldId = fieldId;
  state.createEntityMode = false;
  state.createRelationMode = false;
}
