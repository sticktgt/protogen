import { escapeAttr, escapeHtml } from './html-utils.js';
import { renderRunObservability } from './agent-observability-render.js';
import { renderManualReview } from './agent-manual-review-render.js';
import { renderSemanticReview } from './agent-semantic-review-render.js';
import {
  renderChanges,
  renderCompactChangeStatistics,
  renderDeletionWarning
} from './agent-changes-render.js';

export function renderAgentStart({ snapshot, initialAvailable, actionInProgress, llmTest, startError, requirementsPath, userRequest, baseMode }) {
  return `
    <div class="agent-layout">
      <div class="agent-start-column">
        ${renderLlmConnection(llmTest, actionInProgress)}
        <section class="card agent-start-card">
          <div class="card-title">Синхронизация требований и схемы данных</div>
          <p class="muted-text">Агент читает канонический файл требований, изменяет только временную копию логической схемы и формирует результат для review. Рабочая схема изменяется только после подтверждения.</p>
          ${startError ? `<div class="agent-inline-error" data-agent-start-error role="alert">${escapeHtml(startError)}</div>` : ''}
          <form data-agent-start-form class="agent-form">
            <div class="form-row">
              <label for="agent-requirements-path">Путь к каноническому файлу требований</label>
              <input id="agent-requirements-path" type="text" required data-agent-requirements-path value="${escapeAttr(requirementsPath || '')}" placeholder="requirements/requirements.json">
              <div class="field-help">Путь задаётся относительно корня workspace. После применения схема хранит ссылку в <code>requirements_source.json</code>, а не копию требований.</div>
            </div>
            <div class="form-row">
              <label for="agent-user-request">Дополнительные указания агенту</label>
              <textarea id="agent-user-request" rows="5" data-agent-user-request placeholder="Например: сохрани существующие сущности; добавь данные, необходимые для сценария согласования.">${escapeHtml(userRequest || '')}</textarea>
            </div>
            ${initialAvailable ? `
              <details class="agent-advanced">
                <summary>Дополнительные параметры</summary>
                <div class="agent-radio-list">
                  <label><input type="radio" name="agent-base-mode" value="current" ${baseMode !== 'initial' ? 'checked' : ''}> Продолжить с текущей схемой данных</label>
                  <label><input type="radio" name="agent-base-mode" value="initial" ${baseMode === 'initial' ? 'checked' : ''}> Начать со схемы до первого запуска AI-синхронизации</label>
                </div>
                <p class="muted-text">Непринятый preview не становится основой следующего запуска.</p>
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
          <p>Доступен предыдущий снимок схемы данных:</p>
          <div class="agent-snapshot-meta">${escapeHtml(formatDate(snapshot.created_at))}</div>
          <button class="btn" type="button" data-restore-latest ${actionInProgress ? 'disabled' : ''}>Восстановить предыдущую схему</button>
        ` : '<p class="muted-text">Снимки появятся после первого применения изменений агента.</p>'}
      </aside>
    </div>
  `;
}

export function renderAgentRunning(run, metrics, events) {
  return `
    <section class="card agent-status-card">
      <div class="agent-status-heading">
        <div>
          <div class="card-title">Синхронизация схемы данных</div>
          <div class="muted-text">Запуск ${escapeHtml(run.run_id)}</div>
        </div>
        <span class="agent-status-badge ${run.status === 'cancelling' ? 'cancelling' : 'running'}">${escapeHtml(statusLabel(run.status))}</span>
      </div>
      <div class="agent-progress-line"><span></span></div>
      <dl class="agent-run-meta">
        <div><dt>Этап</dt><dd>${escapeHtml(phaseLabel(run.phase))}</dd></div>
        <div><dt>Попытка</dt><dd>${escapeHtml(run.attempt || 1)}</dd></div>
        <div><dt>Начато</dt><dd>${escapeHtml(formatDate(run.started_at))}</dd></div>
        <div><dt>Основа</dt><dd>${run.base_mode === 'initial' ? 'исходная схема' : 'текущая схема'}</dd></div>
        <div><dt>Требования</dt><dd>${escapeHtml(run.requirements_source_path || run.requirements_file_name || '—')}</dd></div>
      </dl>
      ${renderRunObservability(run, metrics, events, true)}
      ${run.status === 'running' ? '<button class="btn" type="button" data-cancel-agent-run>Отменить задачу</button>' : ''}
      ${run.status === 'cancelling' ? '<p class="agent-cancelling-note">Отмена запрошена. Текущий вызов LLM или инструмента может завершаться до настроенного таймаута.</p>' : ''}
    </section>
  `;
}

export function renderAgentPreview(run, changes, requirementsResult, actionInProgress, metrics, events) {
  const statistics = changes?.statistics || run.statistics || {};
  const review = run.semantic_review && typeof run.semantic_review === 'object'
    ? run.semantic_review
    : {};
  const reviewContractValid = ['approved', 'needs_revision', 'skipped'].includes(review.status)
    && ['approve', 'revise'].includes(review.decision)
    && ['combined', 'correction_verification'].includes(review.review_kind)
    && review.coverage_complete === true;
  const reviewApproved = reviewContractValid
    && ['approved', 'skipped'].includes(review.status)
    && review.decision === 'approve'
    && !review.blocking
    && !review.correction_pending;
  const applyBlocked = Boolean(run.apply_blocked || !reviewApproved);
  const displayedWarnings = collectWarnings(run.validation_warnings, requirementsResult);
  const advisoryCount = Number(review.issue_counts?.advisory || 0);
  const warningCount = displayedWarnings.length + advisoryCount;
  const resultStatus = applyBlocked
    ? '<span class="agent-status-badge revision">Требует исправления</span>'
    : warningCount > 0
      ? '<span class="agent-status-badge warning">Готово с предупреждениями</span>'
      : '<span class="agent-status-badge ready">Готово к применению</span>';
  return `
    <div class="agent-result-stack">
      <section class="card agent-result-header">
        <div class="agent-status-heading">
          <div>
            <div class="card-title">Результат синхронизации</div>
            <div class="muted-text">Попытка ${escapeHtml(run.attempt || 1)} · ${escapeHtml(formatDate(run.updated_at))}</div>
          </div>
          ${resultStatus}
        </div>
        ${run.agent_report ? `<p class="agent-report">${escapeHtml(run.agent_report)}</p>` : ''}
        ${renderAgentNote(run.agent_note)}
        ${renderWarnings(displayedWarnings)}
        ${renderDeletionWarning(statistics)}
        ${renderSemanticReview(review)}
        ${renderManualReview(run.manual_review)}
        ${renderRunObservability(run, metrics, events, false)}
        ${renderCompactChangeStatistics(statistics)}
      </section>
      ${renderChanges(changes, run)}
      <section class="card agent-decision-card">
        <div class="agent-actions primary-actions">
          ${applyBlocked
            ? `<button class="btn btn-primary" type="button" data-regenerate-agent-run ${actionInProgress ? 'disabled' : ''}>Перегенерировать и исправить</button>`
            : `<button class="btn btn-primary" type="button" data-apply-agent-run ${actionInProgress ? 'disabled' : ''}>Принять все изменения</button>`}
          <button class="btn" type="button" data-open-agent-preview>Открыть визуальный preview</button>
          <a class="btn" href="${escapeAttr(diagnosticsHref(run))}">Скачать диагностику</a>
          <button class="btn btn-danger" type="button" data-reject-agent-run ${actionInProgress ? 'disabled' : ''}>Отклонить</button>
        </div>
        <div class="agent-regenerate-box">
          <label for="agent-regenerate-comment">Комментарий для перегенерации</label>
          <textarea id="agent-regenerate-comment" rows="3" data-regenerate-comment placeholder="Например: сохрани существующие сущности; исправь обязательные замечания review."></textarea>
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
          <div><div class="card-title">Синхронизация не завершена</div><div class="muted-text">Попытка ${escapeHtml(run.attempt || 1)}</div></div>
          <span class="agent-status-badge failed">Ошибка</span>
        </div>
        ${run.error ? `<p>${escapeHtml(run.error)}</p>` : ''}
        ${run.phase === 'stopped_by_limit' ? '<p class="agent-limit-note">Запуск остановлен защитным лимитом. Перед его увеличением проверьте журнал и диагностику.</p>' : ''}
        ${renderValidationErrors(errors, run.validation_error_count)}
        ${renderRunObservability(run, metrics, events, false)}
      </section>
      <section class="card agent-decision-card">
        <div class="agent-regenerate-box">
          <label for="agent-regenerate-comment">Комментарий для новой генерации</label>
          <textarea id="agent-regenerate-comment" rows="4" data-regenerate-comment></textarea>
          <div class="agent-actions">
            <button class="btn btn-primary" type="button" data-regenerate-agent-run ${actionInProgress ? 'disabled' : ''}>Перегенерировать</button>
            <a class="btn" href="${escapeAttr(diagnosticsHref(run))}">Скачать диагностику</a>
            <button class="btn btn-danger" type="button" data-reject-agent-run ${actionInProgress ? 'disabled' : ''}>Закрыть и удалить запуск</button>
          </div>
        </div>
      </section>
    </div>
  `;
}


function renderLlmConnection(test, busy) {
  let result = '<span class="muted-text">Соединение ещё не проверялось.</span>';
  if (test?.status === 'testing') result = '<span>Проверка соединения…</span>';
  if (test?.status === 'success') {
    const llm = test.result?.llm || {};
    result = `<span class="agent-test-success">${escapeHtml(test.result?.message || 'Соединение работает')} · ${escapeHtml(llm.provider || '')} ${escapeHtml(llm.model || '')}</span>`;
  }
  if (test?.status === 'error') result = `<span class="agent-test-error">${escapeHtml(test.message || 'Ошибка соединения')}</span>`;
  return `<section class="card agent-connection-card"><div><div class="card-title">Подключение LLM</div>${result}</div><button class="btn btn-sm" type="button" data-test-agent-llm ${busy || test?.status === 'testing' ? 'disabled' : ''}>Проверить</button></section>`;
}

function renderValidationErrors(errors, totalCount = null) {
  if (!errors.length && !totalCount) return '';
  const total = Number(totalCount || errors.length);
  return `<details class="agent-error-box" open><summary>Ошибки проверки · ${total}</summary><ul>${errors.slice(0, 100).map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>${total > errors.length ? `<p>Показано ${errors.length} из ${total}.</p>` : ''}</details>`;
}

function renderWarnings(warnings) {
  if (!Array.isArray(warnings) || !warnings.length) return '';
  return `<details class="agent-warning-box"><summary>Предупреждения · ${warnings.length}</summary><ul>${warnings.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></details>`;
}

function collectWarnings(runWarnings, requirementsResult) {
  const requirements = Array.isArray(requirementsResult?.requirements)
    ? requirementsResult.requirements
    : [];
  const detailed = [];
  requirements.forEach(item => {
    const assessment = item?.assessment || {};
    const type = assessment.type;
    if (type === 'unclear' || type === 'unclassified') {
      const prefix = type === 'unclear' ? 'Требует уточнения' : 'Не классифицировано';
      const identity = [item.requirement_id, item.name].filter(Boolean).join(' · ');
      const reason = assessment.reason ? ` — ${assessment.reason}` : '';
      detailed.push(`${prefix}: ${identity}${reason}`);
    }
    if (Array.isArray(item?.warnings)) {
      item.warnings.forEach(message => {
        if (!message) return;
        const identity = [item.requirement_id, item.name].filter(Boolean).join(' · ');
        detailed.push(`${identity} — ${message}`);
      });
    }
  });
  const genericPatterns = [
    /^Требуют уточнения:\s*\d+$/i,
    /^Не классифицировано:\s*\d+$/i
  ];
  const base = Array.isArray(runWarnings)
    ? runWarnings.filter(item => !detailed.length || !genericPatterns.some(pattern => pattern.test(String(item || '').trim())))
    : [];
  return [...new Set([...base, ...detailed].map(item => String(item || '').trim()).filter(Boolean))];
}

function renderAgentNote(note) {
  const text = humanAgentNote(note);
  return text ? `<details class="agent-note-box"><summary>Комментарий агента</summary><p>${escapeHtml(text)}</p></details>` : '';
}

function humanAgentNote(note) {
  const text = String(note || '').trim();
  if (!text) return '';
  try {
    const payload = JSON.parse(text);
    if (!payload || Array.isArray(payload) || typeof payload !== 'object') return text;
    const technicalKeys = new Set([
      'valid', 'errors', 'warnings', 'counts', 'preservation',
      'assessment_counts', 'completed', 'next_action'
    ]);
    const keys = Object.keys(payload);
    const technical = keys.length > 0
      && keys.every(key => technicalKeys.has(key))
      && ('valid' in payload || 'completed' in payload || 'counts' in payload);
    return technical ? '' : text;
  } catch {
    return text;
  }
}


function diagnosticsHref(run) {
  return `/api/data-schema/agent-runs/${encodeURIComponent(run?.run_id || '')}/diagnostics?workspace_id=${encodeURIComponent(run?.workspace_id || '')}`;
}

function statusLabel(status) {
  return { running: 'Выполняется', cancelling: 'Отменяется', applying: 'Применяется' }[status] || status;
}

function phaseLabel(phase) {
  return {
    preparing: 'Подготовка',
    synchronizing: 'Создание схемы и трассировки',
    validating: 'Техническая проверка результата',
    semantic_review: 'Смысловая проверка результата',
    semantic_correction: 'Исправление обязательных замечаний',
    semantic_verification: 'Проверка исправлений',
    building_preview: 'Подготовка diff и preview',
    applying: 'Применение результата',
    cancelling: 'Ожидание остановки',
    stopped_by_limit: 'Остановлено по лимиту',
    completed: 'Завершено'
  }[phase] || phase || 'Подготовка';
}


function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('ru-RU');
}
