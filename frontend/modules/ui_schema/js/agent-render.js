import { escapeAttr, escapeHtml } from './html-utils.js';
import { renderRunObservability } from './agent-observability-render.js';

export function renderAgentStart({ snapshot, initialAvailable, actionInProgress, llmTest, requirementsPath, userRequest, baseMode }) {
  return `
    <div class="agent-layout">
      <div class="agent-start-column">
        ${renderLlmConnection(llmTest, actionInProgress)}
        <section class="card agent-start-card">
          <div class="card-title">Синхронизация требований и UI-схемы</div>
          <p class="muted-text">Агент использует файл требований целиком и подготавливает временную версию схемы. Изменения применяются только после подтверждения.</p>
          <form data-agent-start-form class="agent-form">
            <div class="form-row">
              <label for="agent-requirements-path">Путь к файлу требований в workspace</label>
              <input id="agent-requirements-path" type="text" required data-agent-requirements-path value="${escapeAttr(requirementsPath || '')}" placeholder="requirements/requirements.json">
              <div class="field-help">Укажите путь относительно корня workspace к каноническому файлу модуля требований, например <code>requirements/requirements.json</code>. После принятия результата UI Schema сохранит только ссылку на этот файл.</div>
            </div>
            <div class="form-row">
              <label for="agent-user-request">Дополнительные указания агенту</label>
              <textarea id="agent-user-request" rows="5" data-agent-user-request placeholder="Например: сохрани существующую структуру меню; форму перевода сделай пошаговой.">${escapeHtml(userRequest || '')}</textarea>
            </div>
            ${initialAvailable ? `
              <details class="agent-advanced">
                <summary>Дополнительные параметры</summary>
                <div class="agent-radio-list">
                  <label><input type="radio" name="agent-base-mode" value="current" ${baseMode !== 'initial' ? 'checked' : ''}> Продолжить с текущей UI-схемой</label>
                  <label><input type="radio" name="agent-base-mode" value="initial" ${baseMode === 'initial' ? 'checked' : ''}> Начать заново со схемы до первого запуска AI-синхронизации</label>
                </div>
                <p class="muted-text">Непринятый preview не используется как основа. Перегенерация начинается заново от выбранной базы текущего запуска.</p>
              </details>
            ` : ''}
            <div class="agent-actions">
              <button class="btn btn-primary" type="submit" ${actionInProgress ? 'disabled' : ''}>Синхронизировать схему</button>
            </div>
          </form>
        </section>
      </div>
      <aside class="card agent-history-card">
        <div class="card-title">Восстановление</div>
        ${snapshot ? `
          <p>Доступен предыдущий снимок UI-схемы:</p>
          <div class="agent-snapshot-meta">${escapeHtml(formatDate(snapshot.created_at))}</div>
          <button class="btn" type="button" data-restore-latest ${actionInProgress ? 'disabled' : ''}>Восстановить предыдущую схему</button>
        ` : '<p class="muted-text">Снимки появятся после первого принятия изменений агента.</p>'}
      </aside>
    </div>
  `;
}

export function renderAgentRunning(run, metrics, events) {
  return `
    <div class="card agent-status-card">
      <div class="agent-status-heading">
        <div>
          <div class="card-title">Синхронизация UI-схемы</div>
          <div class="muted-text">Запуск ${escapeHtml(run.run_id)}</div>
        </div>
        <span class="agent-status-badge ${run.status === 'cancelling' ? 'cancelling' : 'running'}">${escapeHtml(statusLabel(run.status))}</span>
      </div>
      <div class="agent-progress-line"><span></span></div>
      <dl class="agent-run-meta">
        <div><dt>Этап</dt><dd>${escapeHtml(phaseLabel(run.phase))}</dd></div>
        <div><dt>Попытка</dt><dd>${escapeHtml(run.attempt || 1)}</dd></div>
        <div><dt>Начато</dt><dd>${escapeHtml(formatDate(run.started_at))}</dd></div>
        <div><dt>Основа</dt><dd>${run.base_mode === 'initial' ? 'схема до первого запуска AI-синхронизации' : 'текущая схема'}</dd></div>
        <div><dt>Требования</dt><dd>${escapeHtml(run.requirements_source_path || run.requirements_file_name || '—')}</dd></div>
      </dl>
      ${renderRunObservability(run, metrics, events, true)}
      ${run.status === 'running' ? '<button class="btn" type="button" data-cancel-agent-run>Отменить задачу</button>' : ''}
      ${run.status === 'cancelling' ? '<p class="agent-cancelling-note">Запрошена отмена. Ожидается завершение текущего вызова LLM или инструмента.</p>' : ''}
    </div>
  `;
}

export function renderAgentPreview(run, changes, actionInProgress, metrics, events) {
  return `
    <div class="agent-result-stack">
      <section class="card agent-result-header">
        <div class="agent-status-heading">
          <div>
            <div class="card-title">Результат синхронизации</div>
            <div class="muted-text">Попытка ${escapeHtml(run.attempt || 1)} · ${escapeHtml(formatDate(run.updated_at))}</div>
          </div>
          <span class="agent-status-badge ready">Готово к просмотру</span>
        </div>
        ${run.agent_report ? `<p class="agent-report">${escapeHtml(run.agent_report)}</p>` : ''}
        ${renderAgentNote(run.agent_note)}
        ${renderWarnings(run.validation_warnings)}
        ${renderDeletionWarning(changes.statistics || run.statistics || {})}
        ${renderRunObservability(run, metrics, events, false)}
      </section>
      ${renderStatistics(changes.statistics || run.statistics || {})}
      ${renderChanges(changes, run)}
      <section class="card agent-decision-card">
        <div class="agent-actions primary-actions">
          <button class="btn btn-primary" type="button" data-apply-agent-run ${actionInProgress ? 'disabled' : ''}>Принять все изменения</button>
          <button class="btn" type="button" data-open-agent-preview>Открыть визуальный preview</button>
          <a class="btn" href="${escapeAttr(diagnosticsHref(run))}">Скачать отчёт по запуску</a>
          <button class="btn btn-danger" type="button" data-reject-agent-run ${actionInProgress ? 'disabled' : ''}>Отклонить</button>
        </div>
        <div class="agent-regenerate-box">
          <label for="agent-regenerate-comment">Комментарий для перегенерации</label>
          <textarea id="agent-regenerate-comment" rows="3" data-regenerate-comment placeholder="Например: не удаляй существующие элементы; объедини шаги в одну форму."></textarea>
          <button class="btn" type="button" data-regenerate-agent-run ${actionInProgress ? 'disabled' : ''}>Перегенерировать</button>
        </div>
      </section>
    </div>
  `;
}

export function renderAgentFailed(run, actionInProgress, metrics, events) {
  const errors = Array.isArray(run.validation_errors) ? run.validation_errors : [];
  return `
    <div class="agent-result-stack">
      <section class="card agent-failed-card">
        <div class="agent-status-heading">
          <div>
            <div class="card-title">Синхронизация не завершена</div>
            <div class="muted-text">Попытка ${escapeHtml(run.attempt || 1)}</div>
          </div>
          <span class="agent-status-badge failed">Ошибка</span>
        </div>
        ${run.error ? `<p>${escapeHtml(run.error)}</p>` : ''}
        ${run.phase === 'stopped_by_limit' ? '<p class="agent-limit-note">Лимит является защитой от лишних расходов. Повышать его без анализа журнала не рекомендуется.</p>' : ''}
        ${errors.length ? `<ul class="agent-error-list">${errors.map(error => `<li>${escapeHtml(error)}</li>`).join('')}</ul>` : ''}
        ${renderRunObservability(run, metrics, events, false)}
      </section>
      <section class="card agent-decision-card">
        <div class="agent-regenerate-box">
          <label for="agent-regenerate-comment">Комментарий для новой генерации</label>
          <textarea id="agent-regenerate-comment" rows="4" data-regenerate-comment></textarea>
          <div class="agent-actions">
            <button class="btn btn-primary" type="button" data-regenerate-agent-run ${actionInProgress ? 'disabled' : ''}>Перегенерировать</button>
            <a class="btn" href="${escapeAttr(diagnosticsHref(run))}">Скачать отчёт по запуску</a>
            <button class="btn btn-danger" type="button" data-reject-agent-run ${actionInProgress ? 'disabled' : ''}>Отклонить</button>
          </div>
        </div>
      </section>
    </div>
  `;
}

function renderLlmConnection(test, actionInProgress) {
  const status = test?.status || 'idle';
  const result = test?.result || {};
  const message = test?.message || '';
  let details = '<span class="muted-text">Используются LLM-настройки текущего пользователя.</span>';
  if (status === 'testing') details = '<span class="muted-text">Проверяется соединение и вызов инструментов…</span>';
  if (status === 'success') {
    const llm = result.llm || {};
    details = `<span class="agent-llm-ok">${escapeHtml(result.message || 'Соединение работает')}</span>
      <span class="muted-text">${escapeHtml(llm.provider || '')} · ${escapeHtml(llm.model || '')}${llm.base_url ? ` · ${escapeHtml(llm.base_url)}` : ''}</span>`;
  }
  if (status === 'error') details = `<span class="agent-llm-error">${escapeHtml(message || 'Ошибка соединения')}</span>`;
  return `
    <section class="card agent-llm-card">
      <div>
        <div class="card-title">Соединение с LLM</div>
        <div class="agent-llm-details">${details}</div>
      </div>
      <button class="btn btn-sm" type="button" data-test-agent-llm ${actionInProgress || status === 'testing' ? 'disabled' : ''}>Проверить соединение</button>
    </section>
  `;
}

function renderDeletionWarning(statistics) {
  const deletedPages = Number(statistics.pages?.deleted || 0);
  const deletedElements = Number(statistics.elements?.deleted || 0);
  if (!deletedPages && !deletedElements) return '';
  return `
    <div class="agent-deletion-warning">
      <strong>Обнаружены удаления существующей схемы</strong>
      <span>Страницы: ${escapeHtml(deletedPages)} · UI-элементы: ${escapeHtml(deletedElements)}. Не применяйте результат, если эти удаления не были явно ожидаемы.</span>
    </div>
  `;
}

function renderStatistics(statistics) {
  const groups = [
    ['Приложение', statistics.application],
    ['Страницы', statistics.pages],
    ['UI-элементы', statistics.elements],
    ['Связи UI', statistics.ui_links],
    ['Связи с требованиями', statistics.requirement_links],
    ['Файлы', statistics.files]
  ];
  const assessments = statistics.assessments || {};
  return `
    <section class="card">
      <div class="card-title">Статистика изменений</div>
      <div class="agent-stat-grid">
        ${groups.map(([label, value]) => renderStatCard(label, value || {})).join('')}
        <div class="agent-stat-card assessment-card">
          <div class="agent-stat-title">Анализ требований</div>
          <div><strong>${escapeHtml(assessments.linked || 0)}</strong> с прямой UI-трассировкой</div>
          <div><strong>${escapeHtml(assessments.cross_cutting_ui || 0)}</strong> сквозных UI-правил</div>
          <div><strong>${escapeHtml(assessments.no_ui || 0)}</strong> без UI</div>
          <div><strong>${escapeHtml(assessments.unclear || 0)}</strong> требуют уточнения</div>
          <div><strong>${escapeHtml(assessments.unclassified || 0)}</strong> без классификации</div>
        </div>
        ${renderTraceabilityCard(statistics.traceability || {})}
      </div>
    </section>
  `;
}

function renderStatCard(label, value) {
  return `
    <div class="agent-stat-card">
      <div class="agent-stat-title">${escapeHtml(label)}</div>
      <div class="agent-stat-values">
        <span class="added">+ ${escapeHtml(value.added || 0)}</span>
        <span class="modified">~ ${escapeHtml(value.modified || 0)}</span>
        <span class="deleted">− ${escapeHtml(value.deleted || 0)}</span>
      </div>
    </div>
  `;
}

function renderChanges(changes, run) {
  const items = Array.isArray(changes.changes) ? changes.changes : [];
  const groups = groupChanges(items);
  const changedFiles = changes.changed_files || {};
  return `
    <section class="card">
      <details class="agent-changes-root">
        <summary>Перечень изменений · ${items.length}</summary>
        <div class="agent-changes-root-body">
          ${items.length ? Object.entries(groups).map(([key, group]) => `
            <details class="agent-change-group">
              <summary>${escapeHtml(changeGroupLabel(key))} · ${group.length}</summary>
              <div class="agent-change-list">${group.map(item => renderChangeItem(item, run)).join('')}</div>
            </details>
          `).join('') : '<div class="empty-state">Структурные изменения не обнаружены.</div>'}
          ${renderRequirementAssessments(changes.requirement_assessments)}
          ${renderTraceabilityWarnings(changes.traceability_warnings)}
          <details class="agent-change-group">
            <summary>Изменённые файлы</summary>
            ${renderFileList('Добавлены', changedFiles.added)}
            ${renderFileList('Изменены', changedFiles.modified)}
            ${renderFileList('Удалены', changedFiles.deleted)}
          </details>
        </div>
      </details>
    </section>
  `;
}

function renderChangeItem(item, run) {
  const title = item.title || item.label || item.object_id || '';
  const context = item.page_id ? ` · ${item.page_id}` : '';
  const href = previewChangeHref(run, item);
  return `
    <div class="agent-change-item ${escapeAttr(item.action || '')}">
      <span class="agent-change-action">${escapeHtml(actionSymbol(item.action))}</span>
      <div class="agent-change-content">
        <div>${escapeHtml(title)}</div>
        <div class="muted-text">${escapeHtml(item.object_id || '')}${escapeHtml(context)}</div>
      </div>
      ${href ? `<a class="btn btn-sm" href="${escapeAttr(href)}">Показать</a>` : ''}
    </div>
  `;
}

function previewChangeHref(run, item) {
  if (!run?.run_id) return '';
  const params = new URLSearchParams({
    preview_run_id: run.run_id,
    tab: 'structure'
  });
  if (item.action === 'deleted') {
    params.set('deleted_type', item.object_type || '');
    params.set('deleted_id', item.object_id || '');
    if (item.page_id) params.set('select_page_id', item.page_id);
    return `?${params.toString()}`;
  }
  if (item.object_type === 'application') {
    params.set('select_page_id', '__app__');
  } else if (item.object_type === 'page') {
    params.set('select_page_id', item.object_id);
  } else if (item.object_type === 'ui_element') {
    params.set('select_page_id', item.page_id || '__app__');
    params.set('select_element_id', item.object_id);
  } else if (item.object_type === 'requirement_link') {
    params.set('select_page_id', item.page_id || '__app__');
    if (item.target_type === 'page') params.set('select_page_id', item.target_id);
    if (item.target_type === 'ui_element') params.set('select_element_id', item.target_id);
  } else if (item.object_type === 'ui_link') {
    params.set('select_page_id', item.page_id || item.target_page_id || item.source_page_id || '__app__');
    if (item.target_type === 'ui_element') params.set('select_element_id', item.target_id);
    else if (item.source_type === 'ui_element') params.set('select_element_id', item.source_id);
  } else {
    return '';
  }
  return `?${params.toString()}`;
}

function renderTraceabilityCard(value) {
  return `
    <div class="agent-stat-card assessment-card">
      <div class="agent-stat-title">Качество трассировки</div>
      <div><strong>${escapeHtml(value.links_total || 0)}</strong> записей связей</div>
      <div><strong>${escapeHtml(value.requirements_with_elements || 0)}</strong> с конечными элементами</div>
      <div><strong>${escapeHtml(value.requirements_page_only || 0)}</strong> только со страницами</div>
      <div><strong>${escapeHtml(value.requirements_multi_target || 0)}</strong> с несколькими целями</div>
      <div><strong>${escapeHtml(value.requirements_cross_cutting_ui || 0)}</strong> сквозных UI-правил</div>
      <div><strong>${escapeHtml(value.average_targets_per_traced_requirement ?? value.average_targets_per_linked_requirement ?? 0)}</strong> целей в среднем</div>
    </div>
  `;
}

function renderAgentNote(note) {
  if (!note) return '';
  return `
    <details class="agent-note-box">
      <summary>Комментарий агента</summary>
      <p>${escapeHtml(note)}</p>
      <div class="muted-text">Комментарий не используется для машинной проверки; итоговая сводка выше рассчитана backend по фактическим данным.</div>
    </details>
  `;
}

function renderRequirementAssessments(groups) {
  if (!groups || typeof groups !== 'object') return '';
  const definitions = [
    ['cross_cutting_ui', 'Сквозные UI-правила'],
    ['no_ui', 'Без UI'],
    ['unclear', 'Требуют уточнения'],
    ['unclassified', 'Без классификации']
  ];
  const total = definitions.reduce((sum, [key]) => sum + (Array.isArray(groups[key]) ? groups[key].length : 0), 0);
  if (!total) return '';
  return `
    <details class="agent-requirement-assessments">
      <summary>Классификация требований · ${total}</summary>
      <div class="agent-requirement-assessment-groups">
        ${definitions.map(([key, label]) => renderRequirementAssessmentGroup(label, groups[key])).join('')}
      </div>
    </details>
  `;
}

function renderRequirementAssessmentGroup(label, items) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) return '';
  return `
    <details class="agent-change-group">
      <summary>${escapeHtml(label)} · ${list.length}</summary>
      <div class="agent-change-list">
        ${list.map(item => `
          <div class="agent-change-item">
            <div class="agent-change-content">
              <div><strong>${escapeHtml(item.requirement_id || '')}</strong>${item.name ? ` · ${escapeHtml(item.name)}` : ''}</div>
              <div class="muted-text">${escapeHtml(item.reason || '')}${item.scope ? ` · область: ${escapeHtml(item.scope)}` : ''}${Number.isFinite(Number(item.targets_count)) ? ` · целей: ${escapeHtml(item.targets_count)}` : ''}</div>
            </div>
          </div>
        `).join('')}
      </div>
    </details>
  `;
}

function renderTraceabilityWarnings(warnings) {
  if (!Array.isArray(warnings) || !warnings.length) return '';
  return `<details class="agent-warning-box" open><summary>Предупреждения трассировки · ${warnings.length}</summary><ul>${warnings.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></details>`;
}

function renderFileList(label, files) {
  const list = Array.isArray(files) ? files : [];
  if (!list.length) return '';
  return `<div class="agent-file-group"><strong>${escapeHtml(label)}</strong><ul>${list.map(file => `<li><code>${escapeHtml(file)}</code></li>`).join('')}</ul></div>`;
}

function renderWarnings(warnings) {
  if (!Array.isArray(warnings) || !warnings.length) return '';
  return `<details class="agent-warning-box"><summary>Предупреждения проверки · ${warnings.length}</summary><ul>${warnings.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></details>`;
}

function groupChanges(items) {
  return items.reduce((result, item) => {
    const key = item.object_type || 'other';
    (result[key] ||= []).push(item);
    return result;
  }, {});
}

function diagnosticsHref(run) {
  const runId = encodeURIComponent(run?.run_id || '');
  const workspaceId = encodeURIComponent(run?.workspace_id || '');
  return `/api/ui-schema/agent-runs/${runId}/diagnostics?workspace_id=${workspaceId}`;
}

function statusLabel(status) {
  return { running: 'Выполняется', cancelling: 'Отменяется', applying: 'Применяется' }[status] || status;
}

function phaseLabel(phase) {
  return {
    preparing: 'Подготовка',
    analyzing_requirements: 'Анализ требований и изменение схемы',
    validating: 'Проверка результата',
    building_preview: 'Подготовка статистики и preview',
    applying: 'Применение результата',
    cancelling: 'Ожидание остановки',
    stopped_by_limit: 'Остановлено по лимиту',
    completed: 'Завершено'
  }[phase] || phase || 'Подготовка';
}

function changeGroupLabel(type) {
  return {
    application: 'Приложение',
    page: 'Страницы',
    ui_element: 'UI-элементы',
    ui_link: 'Связи UI',
    requirement_link: 'Связи с требованиями'
  }[type] || type;
}

function actionSymbol(action) {
  return { added: '+', modified: '~', deleted: '−' }[action] || '•';
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU');
}
