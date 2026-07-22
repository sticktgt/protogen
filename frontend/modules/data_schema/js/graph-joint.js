import { dataTypeInfo } from './data-types.js';
import { escapeHtml } from './html-utils.js';
import { renderAll } from './main.js';
import { entities, entityDetails, entityTitle, relations, relationTitle, selectEntity, state } from './state.js';

const JOINT_CSS = 'https://cdn.jsdelivr.net/npm/@joint/core/dist/joint.css';
const JOINT_JS = 'https://cdn.jsdelivr.net/npm/@joint/core/dist/joint.js';
const MAX_FIELDS_IN_NODE = 6;
const NODE_WIDTH = 360;
const NODE_ROW_HEIGHT = 28;
const NODE_HEADER_HEIGHT = 54;
const NODE_PADDING_BOTTOM = 16;

let jointLoadPromise = null;
let entityShapeCtor = null;

export async function renderGraphView() {
  const container = document.querySelector('[data-joint-graph]');
  if (!container) return;
  container.innerHTML = '<div class="empty-state compact-empty">Загрузка JointJS...</div>';
  const joint = await ensureJointLoaded();
  if (!joint) {
    container.innerHTML = renderJointUnavailable();
    return;
  }
  drawGraph(container, joint);
}

function renderJointUnavailable() {
  return `
    <div class="joint-unavailable">
      <strong>JointJS не загружен.</strong>
      <div class="small-note">Экспериментальная вкладка использует <code>@joint/core</code> из CDN. Если приложение запущено без доступа к сети, граф недоступен, но остальные режимы модуля работают как раньше.</div>
    </div>
  `;
}

async function ensureJointLoaded() {
  if (window.joint) return window.joint;
  if (!jointLoadPromise) {
    jointLoadPromise = loadJointAssets();
  }
  try {
    await jointLoadPromise;
  } catch (error) {
    console.warn('JointJS load failed', error);
  }
  return window.joint || null;
}

function loadJointAssets() {
  ensureStylesheet(JOINT_CSS);
  return new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-jointjs-cdn]');
    if (existing) {
      existing.addEventListener('load', resolve, { once: true });
      existing.addEventListener('error', reject, { once: true });
      return;
    }
    const script = document.createElement('script');
    script.src = JOINT_JS;
    script.dataset.jointjsCdn = 'true';
    script.onload = resolve;
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

function ensureStylesheet(href) {
  if (document.querySelector(`link[href="${href}"]`)) return;
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = href;
  document.head.appendChild(link);
}

function drawGraph(container, joint) {
  const entityItems = entities().map(item => item.details || item);
  if (!entityItems.length) {
    container.innerHTML = '<div class="empty-state">Сущностей пока нет.</div>';
    return;
  }

  container.innerHTML = `
    <div class="joint-toolbar">
      <div class="small-note joint-toolbar-note">Клик выделяет сущность или связь. Двойной клик открывает существующий редактор. Координаты графа не сохраняются в логической схеме.</div>
      <button class="btn btn-sm" type="button" data-joint-autolayout>Разложить автоматически</button>
    </div>
    <div class="joint-graph-layout">
      <div class="joint-paper" data-joint-paper></div>
      <aside class="joint-details-panel" data-joint-details></aside>
    </div>
  `;
  const paperElement = container.querySelector('[data-joint-paper]');
  const detailsElement = container.querySelector('[data-joint-details]');
  const width = Math.max(container.clientWidth - 320 || 900, 900);
  const graph = new joint.dia.Graph({}, { cellNamespace: joint.shapes });
  const paper = new joint.dia.Paper({
    el: paperElement,
    model: graph,
    width,
    height: 640,
    gridSize: 10,
    drawGrid: true,
    background: { color: 'transparent' },
    interactive: { linkMove: false, elementMove: true, vertexAdd: false },
    cellViewNamespace: joint.shapes
  });

  const nodes = new Map();
  const relationLinks = new Map();
  const EntityShape = ensureEntityShape(joint);

  entityItems.forEach((entity, index) => {
    const node = makeEntityNode(EntityShape, entity, index, width);
    node.addTo(graph);
    nodes.set(entity.id, node);
  });

  for (const relation of relations()) {
    const source = nodes.get(relation.source_entity);
    const target = nodes.get(relation.target_entity);
    if (!source || !target) continue;
    const link = makeRelationLink(joint, relation, source, target);
    link.addTo(graph);
    link.toBack();
    relationLinks.set(relation.id, link);
  }

  applyAutomaticLayout(joint, graph, nodes, width);
  resizePaperToGraph(paper, graph);
  updateSelection(nodes, relationLinks, detailsElement);

  container.querySelector('[data-joint-autolayout]')?.addEventListener('click', () => {
    applyAutomaticLayout(joint, graph, nodes, width, { forceFallback: !hasDirectedGraphLayout(joint) });
    resizePaperToGraph(paper, graph);
    updateSelection(nodes, relationLinks, detailsElement);
  });

  paper.on('element:pointerclick', view => {
    const entityId = view.model.get('dataEntityId');
    if (!entityId) return;
    state.graphSelectedEntityId = entityId;
    state.graphSelectedRelationId = null;
    updateSelection(nodes, relationLinks, detailsElement);
  });

  paper.on('element:pointerdblclick', view => {
    const entityId = view.model.get('dataEntityId');
    if (!entityId) return;
    selectEntity(entityId);
    state.activeTab = 'structure';
    state.activeEditorTab = 'fields';
    renderAll();
  });

  paper.on('link:pointerclick', view => {
    const relationId = view.model.get('dataRelationId');
    if (!relationId) return;
    state.graphSelectedEntityId = null;
    state.graphSelectedRelationId = relationId;
    updateSelection(nodes, relationLinks, detailsElement);
  });

  paper.on('link:pointerdblclick', view => {
    openRelationInEditor(view.model.get('dataRelationId'));
  });

  paper.on('blank:pointerclick', () => {
    state.graphSelectedEntityId = null;
    state.graphSelectedRelationId = null;
    updateSelection(nodes, relationLinks, detailsElement);
  });
}

function ensureEntityShape(joint) {
  if (entityShapeCtor) return entityShapeCtor;
  const fieldMarkup = [];
  for (let index = 0; index < MAX_FIELDS_IN_NODE; index += 1) {
    fieldMarkup.push(
      { tagName: 'rect', selector: `fieldRow${index}` },
      { tagName: 'text', selector: `fieldName${index}` },
      { tagName: 'rect', selector: `typeBadge${index}` },
      { tagName: 'text', selector: `typeIcon${index}` },
      { tagName: 'text', selector: `typeText${index}` }
    );
  }
  entityShapeCtor = joint.dia.Element.define('dataSchema.EntityNode', {
    size: { width: NODE_WIDTH, height: 220 },
    attrs: {
      body: {
        refWidth: '100%',
        refHeight: '100%',
        fill: '#ffffff',
        stroke: '#dbe3ef',
        strokeWidth: 1.4,
        rx: 12,
        ry: 12
      },
      header: {
        refWidth: '100%',
        height: NODE_HEADER_HEIGHT,
        fill: '#f8fafc',
        stroke: '#dbe3ef',
        strokeWidth: 1.2,
        rx: 12,
        ry: 12
      },
      title: {
        text: '',
        x: 16,
        y: 20,
        fill: '#0f172a',
        fontSize: 15,
        fontWeight: 700,
        textAnchor: 'start',
        textVerticalAnchor: 'middle'
      },
      entityId: {
        text: '',
        x: 16,
        y: 40,
        fill: '#64748b',
        fontSize: 11,
        textAnchor: 'start',
        textVerticalAnchor: 'middle'
      },
      moreText: {
        text: '',
        x: 16,
        y: 0,
        fill: '#64748b',
        fontSize: 11,
        textAnchor: 'start',
        textVerticalAnchor: 'middle'
      }
    }
  }, {
    markup: [
      { tagName: 'rect', selector: 'body' },
      { tagName: 'rect', selector: 'header' },
      { tagName: 'text', selector: 'title' },
      { tagName: 'text', selector: 'entityId' },
      ...fieldMarkup,
      { tagName: 'text', selector: 'moreText' }
    ]
  });
  return entityShapeCtor;
}

function makeEntityNode(EntityShape, entity, index, width) {
  const columns = width >= 1280 ? 3 : 2;
  const column = index % columns;
  const row = Math.floor(index / columns);
  const x = 40 + column * (NODE_WIDTH + 56);
  const y = 40 + row * 250;
  const fields = entity.fields || [];
  const visibleFields = fields.slice(0, MAX_FIELDS_IN_NODE);
  const hiddenCount = Math.max(0, fields.length - visibleFields.length);
  const nodeHeight = NODE_HEADER_HEIGHT + 16 + visibleFields.length * NODE_ROW_HEIGHT + (hiddenCount ? 22 : 0) + NODE_PADDING_BOTTOM;

  const node = new EntityShape();
  node.position(x, y);
  node.resize(NODE_WIDTH, Math.max(156, nodeHeight));
  node.attr({
    title: { text: entity.title || entity.id },
    entityId: { text: entity.id }
  });

  for (let fieldIndex = 0; fieldIndex < MAX_FIELDS_IN_NODE; fieldIndex += 1) {
    const field = visibleFields[fieldIndex];
    if (field) {
      setFieldAttrs(node, field, fieldIndex);
    } else {
      hideFieldAttrs(node, fieldIndex);
    }
  }

  node.attr('moreText', {
    text: hiddenCount ? `... еще ${hiddenCount} полей` : '',
    y: NODE_HEADER_HEIGHT + 16 + visibleFields.length * NODE_ROW_HEIGHT + 10,
    opacity: hiddenCount ? 1 : 0
  });
  node.set('dataEntityId', entity.id);
  return node;
}

function setFieldAttrs(node, field, index) {
  const rowY = NODE_HEADER_HEIGHT + 10 + index * NODE_ROW_HEIGHT;
  const info = dataTypeInfo(field.type);
  const colors = typeColors(info.id);
  node.attr({
    [`fieldRow${index}`]: {
      x: 12,
      y: rowY,
      width: NODE_WIDTH - 24,
      height: 23,
      fill: '#f8fafc',
      stroke: '#e2e8f0',
      rx: 7,
      ry: 7,
      opacity: 1
    },
    [`fieldName${index}`]: {
      text: `${field.title || field.id}${field.required ? ' *' : ''}`,
      x: 22,
      y: rowY + 12,
      fill: '#0f172a',
      fontSize: 11,
      textAnchor: 'start',
      textVerticalAnchor: 'middle',
      textWrap: { width: 210, height: 16, ellipsis: true },
      opacity: 1
    },
    [`typeBadge${index}`]: {
      x: NODE_WIDTH - 118,
      y: rowY + 3,
      width: 96,
      height: 17,
      fill: colors.fill,
      stroke: colors.stroke,
      rx: 8,
      ry: 8,
      opacity: 1
    },
    [`typeIcon${index}`]: {
      text: info.icon,
      x: NODE_WIDTH - 108,
      y: rowY + 12,
      fill: colors.text,
      fontSize: 9,
      textAnchor: 'middle',
      textVerticalAnchor: 'middle',
      opacity: 1
    },
    [`typeText${index}`]: {
      text: info.id,
      x: NODE_WIDTH - 94,
      y: rowY + 12,
      fill: colors.text,
      fontSize: 10,
      fontWeight: 600,
      textAnchor: 'start',
      textVerticalAnchor: 'middle',
      opacity: 1
    }
  });
}

function hideFieldAttrs(node, index) {
  node.attr({
    [`fieldRow${index}`]: { opacity: 0 },
    [`fieldName${index}`]: { opacity: 0, text: '' },
    [`typeBadge${index}`]: { opacity: 0 },
    [`typeIcon${index}`]: { opacity: 0, text: '' },
    [`typeText${index}`]: { opacity: 0, text: '' }
  });
}

function typeColors(type) {
  const palette = {
    string: { fill: '#eff6ff', stroke: '#bfdbfe', text: '#1d4ed8' },
    text: { fill: '#f5f3ff', stroke: '#ddd6fe', text: '#6d28d9' },
    integer: { fill: '#ecfeff', stroke: '#a5f3fc', text: '#0e7490' },
    decimal: { fill: '#fff1f2', stroke: '#fecdd3', text: '#be123c' },
    boolean: { fill: '#f0fdf4', stroke: '#bbf7d0', text: '#15803d' },
    date: { fill: '#fffbeb', stroke: '#fde68a', text: '#b45309' },
    datetime: { fill: '#fefce8', stroke: '#fef08a', text: '#a16207' },
    uuid: { fill: '#f1f5f9', stroke: '#cbd5e1', text: '#475569' },
    dictionary: { fill: '#f0f9ff', stroke: '#bae6fd', text: '#0369a1' },
    json: { fill: '#faf5ff', stroke: '#e9d5ff', text: '#7e22ce' }
  };
  return palette[type] || { fill: '#f8fafc', stroke: '#cbd5e1', text: '#475569' };
}

function makeRelationLink(joint, relation, source, target) {
  const link = new joint.shapes.standard.Link();
  link.source(source);
  link.target(target);
  setLinkRouting(link);
  link.labels([{
    attrs: {
      text: {
        text: relationLabel(relation),
        fontSize: 11,
        fill: '#475569'
      },
      rect: {
        fill: '#f8fafc',
        stroke: '#dbe3ef',
        rx: 4,
        ry: 4
      }
    }
  }]);
  link.attr({
    line: {
      stroke: '#64748b',
      strokeWidth: 1.5,
      targetMarker: {
        type: 'path',
        d: 'M 10 -5 0 0 10 5 z'
      }
    }
  });
  link.set('dataRelationId', relation.id);
  link.set('dataSourceEntityId', relation.source_entity);
  link.set('dataTargetEntityId', relation.target_entity);
  return link;
}

function setLinkRouting(link) {
  if (typeof link.router === 'function') {
    link.router('manhattan', {
      padding: 24,
      step: 20,
      startDirections: ['right', 'bottom', 'top'],
      endDirections: ['left', 'top', 'bottom']
    });
  } else {
    link.set('router', { name: 'manhattan', args: { padding: 24, step: 20 } });
  }
  if (typeof link.connector === 'function') {
    link.connector('rounded', { radius: 10 });
  } else {
    link.set('connector', { name: 'rounded', args: { radius: 10 } });
  }
}

function applyAutomaticLayout(joint, graph, nodes, width, options = {}) {
  if (!options.forceFallback && hasDirectedGraphLayout(joint)) {
    try {
      joint.layout.DirectedGraph.layout(graph, {
        setLinkVertices: true,
        rankDir: 'LR',
        marginX: 48,
        marginY: 48,
        nodeSep: 80,
        edgeSep: 40,
        rankSep: 120
      });
      graph.getLinks().forEach(link => {
        setLinkRouting(link);
        link.toBack();
      });
      graph.getElements().forEach(element => element.toFront());
      return;
    } catch (error) {
      console.warn('JointJS DirectedGraph layout failed, using fallback layout', error);
    }
  }
  applyFallbackLayeredLayout(nodes, width);
  graph.getLinks().forEach(link => {
    setLinkRouting(link);
    link.toBack();
  });
  graph.getElements().forEach(element => element.toFront());
}

function hasDirectedGraphLayout(joint) {
  return Boolean(joint.layout?.DirectedGraph?.layout);
}

function applyFallbackLayeredLayout(nodes, width) {
  const levelByEntity = new Map();
  entities().forEach(entity => levelByEntity.set(entity.id, 0));
  for (let pass = 0; pass < entities().length; pass += 1) {
    for (const relation of relations()) {
      const sourceLevel = levelByEntity.get(relation.source_entity) || 0;
      const targetLevel = levelByEntity.get(relation.target_entity) || 0;
      if (targetLevel <= sourceLevel && relation.source_entity !== relation.target_entity) {
        levelByEntity.set(relation.target_entity, sourceLevel + 1);
      }
    }
  }
  const groups = new Map();
  for (const entity of entities()) {
    const level = Math.min(levelByEntity.get(entity.id) || 0, 4);
    const items = groups.get(level) || [];
    items.push(entity.id);
    groups.set(level, items);
  }
  const horizontalGap = width >= 1500 ? 470 : 430;
  const verticalGap = 238;
  for (const [level, entityIds] of groups.entries()) {
    entityIds.forEach((entityId, row) => {
      const node = nodes.get(entityId);
      if (!node) return;
      node.position(40 + level * horizontalGap, 40 + row * verticalGap);
    });
  }
}

function resizePaperToGraph(paper, graph) {
  const bbox = graph.getBBox();
  if (!bbox) return;
  const width = Math.max(900, Math.ceil(bbox.x + bbox.width + 80));
  const height = Math.max(620, Math.ceil(bbox.y + bbox.height + 80));
  paper.setDimensions(width, height);
}

function updateSelection(nodes, relationLinks, detailsElement) {
  nodes.forEach((node, entityId) => {
    const selected = entityId === state.graphSelectedEntityId;
    node.attr({
      body: {
        stroke: selected ? '#2563eb' : '#dbe3ef',
        strokeWidth: selected ? 2.4 : 1.4
      },
      header: {
        stroke: selected ? '#2563eb' : '#dbe3ef',
        fill: selected ? '#eff6ff' : '#f8fafc'
      }
    });
  });
  relationLinks.forEach((link, relationId) => {
    const selected = relationId === state.graphSelectedRelationId;
    link.attr('line/stroke', selected ? '#2563eb' : '#64748b');
    link.attr('line/strokeWidth', selected ? 3 : 1.5);
    link.label(0, {
      attrs: {
        text: { fill: selected ? '#1d4ed8' : '#475569', fontWeight: selected ? 700 : 400 },
        rect: { fill: selected ? '#eff6ff' : '#f8fafc', stroke: selected ? '#93c5fd' : '#dbe3ef' }
      }
    });
    if (selected) link.toFront();
  });
  renderDetails(detailsElement);
}

function renderDetails(detailsElement) {
  if (!detailsElement) return;
  const selectedRelation = relations().find(item => item.id === state.graphSelectedRelationId);
  const selectedEntity = entityDetails(state.graphSelectedEntityId);
  if (selectedRelation) {
    detailsElement.innerHTML = renderRelationDetails(selectedRelation);
    detailsElement.querySelector('[data-open-graph-relation]')?.addEventListener('click', () => openRelationInEditor(selectedRelation.id));
    return;
  }
  if (selectedEntity) {
    detailsElement.innerHTML = renderEntityDetails(selectedEntity);
    detailsElement.querySelector('[data-open-graph-entity]')?.addEventListener('click', () => {
      selectEntity(selectedEntity.id);
      state.activeTab = 'structure';
      state.activeEditorTab = 'fields';
      renderAll();
    });
    return;
  }
  detailsElement.innerHTML = `
    <div class="joint-details-title">Граф данных</div>
    <div class="small-note">${escapeHtml(renderGraphSummary())}</div>
    <div class="small-note">Выберите сущность или связь на графе, чтобы увидеть свойства. Для редактирования используйте двойной клик или кнопку открытия редактора.</div>
  `;
}

function renderEntityDetails(entity) {
  const entityRelations = relations().filter(item => item.source_entity === entity.id || item.target_entity === entity.id);
  return `
    <div class="joint-details-title">${escapeHtml(entity.title || entity.id)}</div>
    <div class="joint-details-subtitle">entity · ${escapeHtml(entity.id)}</div>
    <div class="joint-details-section">
      <div class="joint-details-label">Поля</div>
      <div>${escapeHtml(String((entity.fields || []).length))}</div>
    </div>
    <div class="joint-details-section">
      <div class="joint-details-label">Связи</div>
      ${entityRelations.length ? entityRelations.slice(0, 6).map(renderEntityRelationLine).join('') : '<div class="small-note">Связей нет.</div>'}
    </div>
    <button class="btn btn-primary btn-sm" type="button" data-open-graph-entity>Открыть редактор</button>
  `;
}

function renderEntityRelationLine(relation) {
  return `
    <div class="joint-details-line">
      <div>${escapeHtml(entityTitle(relation.source_entity))} → ${escapeHtml(entityTitle(relation.target_entity))}</div>
      <span class="type-badge">${escapeHtml(relation.cardinality || '')}</span>
    </div>
  `;
}

function renderRelationDetails(relation) {
  return `
    <div class="joint-details-title">${escapeHtml(relation.title || relation.id)}</div>
    <div class="joint-details-subtitle">relation · ${escapeHtml(relation.id)}</div>
    <div class="joint-details-section">
      <div class="joint-details-label">Сущности</div>
      <div>${escapeHtml(entityTitle(relation.source_entity))} → ${escapeHtml(entityTitle(relation.target_entity))}</div>
    </div>
    <div class="joint-details-section">
      <div class="joint-details-label">Кардинальность</div>
      <div>${escapeHtml(relation.cardinality || '')}</div>
    </div>
    ${relation.description ? `<div class="joint-details-section"><div class="joint-details-label">Описание</div><div>${escapeHtml(relation.description)}</div></div>` : ''}
    <button class="btn btn-primary btn-sm" type="button" data-open-graph-relation>Открыть связь</button>
  `;
}

function openRelationInEditor(relationId) {
  const relation = relations().find(item => item.id === relationId);
  const entityId = relation?.source_entity || relation?.target_entity;
  if (!entityId) return;
  selectEntity(entityId);
  state.activeTab = 'structure';
  state.activeEditorTab = 'relations';
  state.graphSelectedRelationId = relationId;
  renderAll();
}

function relationLabel(relation) {
  const labels = {
    one_to_one: '1:1',
    one_to_many: '1:N',
    many_to_one: 'N:1',
    many_to_many: 'N:M'
  };
  return `${labels[relation.cardinality] || relation.cardinality} ${relation.title || ''}`.trim();
}

export function renderGraphSummary() {
  return `Сущностей: ${escapeHtml(String(entities().length))}, связей: ${escapeHtml(String(relations().length))}`;
}
