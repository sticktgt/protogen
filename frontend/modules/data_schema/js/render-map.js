import { state, entities, entityTitle, relations, selectEntity, selectField } from './state.js';
import { escapeHtml } from './html-utils.js';
import { renderTypeBadge } from './data-types.js';
import { renderAll } from './main.js';

const cardinalityLabels = {
  one_to_one: '1:1',
  one_to_many: '1:N',
  many_to_one: 'N:1',
  many_to_many: 'N:M'
};

const CARD_FIELD_LIMIT = 5;
const CARD_RELATION_LIMIT = 4;

export function renderMapView() {
  renderStats();
  bindMapFilter();
  const container = document.querySelector('[data-data-map]');
  if (!container) return;
  container.innerHTML = renderCardsMap();
  bindMapEvents(container);
}

function renderStats() {
  const stats = state.summary?.stats || {};
  const container = document.querySelector('[data-schema-stats]');
  if (!container) return;
  container.innerHTML = [
    ['Сущностей', stats.entity_count || 0],
    ['Полей', stats.field_count || 0],
    ['Связей', stats.relation_count || 0],
    ['Требований', stats.requirement_link_count || 0],
    ['UI-связей', stats.ui_link_count || 0],
    ['API-связей', stats.api_link_count || 0]
  ].map(([label, value]) => `
    <div class="data-stat"><span>${label}</span><span class="data-stat-value">${value}</span></div>
  `).join('');
}

function bindMapFilter() {
  const input = document.querySelector('[data-map-entity-filter]');
  if (!input) return;
  input.value = state.mapEntityFilter || '';
  input.oninput = () => {
    state.mapEntityFilter = input.value;
    renderMapView();
    input.focus();
  };
}

function filteredEntities() {
  const query = state.mapEntityFilter.trim().toLowerCase();
  if (!query) return entities();
  return entities().filter(item => {
    const entity = item.details || item;
    return [entity.title, entity.id].some(value => String(value || '').toLowerCase().includes(query));
  });
}

function renderCardsMap() {
  const items = filteredEntities();
  if (!items.length) {
    return '<div class="empty-state">Сущности по фильтру не найдены.</div>';
  }
  return `<div class="entity-card-grid">${items.map(renderEntityCard).join('')}</div>`;
}

function renderEntityCard(item) {
  const entity = item.details || {};
  const fields = entity.fields || [];
  const visibleFields = fields.slice(0, CARD_FIELD_LIMIT);
  const hiddenFieldCount = Math.max(0, fields.length - visibleFields.length);
  const entityRelations = relations().filter(relation => relation.source_entity === entity.id || relation.target_entity === entity.id);
  const visibleRelations = entityRelations.slice(0, CARD_RELATION_LIMIT);
  const hiddenRelationCount = Math.max(0, entityRelations.length - visibleRelations.length);

  return `
    <article class="entity-card" data-open-entity="${escapeHtml(entity.id)}">
      <div class="entity-card-header">
        <div>
          <div class="entity-title">${escapeHtml(entity.title)}</div>
          <div class="entity-id">${escapeHtml(entity.id)}</div>
        </div>
        <span class="badge">${fields.length} полей</span>
      </div>
      <div class="field-list compact-field-list">
        ${visibleFields.map(field => `
          <div class="field-row" data-open-field="${escapeHtml(field.id)}">
            <span class="field-row-title">${escapeHtml(field.title)} ${field.required ? '<span class="required-mark">*</span>' : ''}</span>
            ${renderTypeBadge(field.type)}
          </div>
        `).join('')}
      </div>
      ${hiddenFieldCount ? `<div class="more-fields-note">Показаны первые ${visibleFields.length} из ${fields.length}. Еще ${hiddenFieldCount} полей.</div>` : ''}
      <div class="entity-card-relations">
        <div class="entity-card-section-title">Связи</div>
        ${visibleRelations.length ? visibleRelations.map(relation => renderCardRelation(relation, entity.id)).join('') : '<div class="muted compact-muted">Связей нет.</div>'}
        ${hiddenRelationCount ? `<div class="more-fields-note">Еще ${hiddenRelationCount} связей.</div>` : ''}
      </div>
    </article>
  `;
}

function renderCardRelation(relation, entityId) {
  const outgoing = relation.source_entity === entityId;
  const otherEntityId = outgoing ? relation.target_entity : relation.source_entity;
  const direction = outgoing ? '→' : '←';
  return `
    <div class="card-relation-row" data-open-entity-relations="${escapeHtml(entityId)}" data-related-entity="${escapeHtml(otherEntityId)}">
      <span class="relation-direction">${direction}</span>
      <span class="field-row-title">${escapeHtml(entityTitle(otherEntityId))}</span>
      <span class="badge">${escapeHtml(cardinalityLabels[relation.cardinality] || relation.cardinality)}</span>
    </div>
  `;
}

function bindMapEvents(container) {
  container.querySelectorAll('[data-open-entity-relations]').forEach(node => {
    node.addEventListener('click', event => {
      event.stopPropagation();
      selectEntity(node.dataset.openEntityRelations);
      state.activeTab = 'structure';
      state.activeEditorTab = 'relations';
      renderAll();
    });
  });
  container.querySelectorAll('[data-open-entity]').forEach(node => {
    node.addEventListener('click', event => {
      event.stopPropagation();
      selectEntity(node.dataset.openEntity);
      state.activeTab = 'structure';
      state.activeEditorTab = 'fields';
      renderAll();
    });
  });
  container.querySelectorAll('[data-open-field]').forEach(node => {
    node.addEventListener('click', event => {
      event.stopPropagation();
      const entityId = node.closest('[data-open-entity]')?.dataset.openEntity;
      selectField(entityId, node.dataset.openField);
      state.activeTab = 'structure';
      state.activeEditorTab = 'fields';
      renderAll();
    });
  });
}
