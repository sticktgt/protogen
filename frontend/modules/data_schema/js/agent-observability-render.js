import { escapeAttr, escapeHtml } from './html-utils.js';
import { state } from './state.js';

export function renderRunObservability(run, metricsValue, eventsValue, running) {
  const metrics = metricsValue || {};
  const limits = metrics.limits || {};
  const events = Array.isArray(eventsValue) ? eventsValue : [];
  const tokenAvailable = metrics.token_usage_available === true;
  const lastActivity = metrics.last_event_at || run.updated_at;
  const idleSeconds = secondsSince(lastActivity);
  const timeout = Number(limits.request_timeout_seconds || 0);
  const idleWarning = running && idleSeconds >= state.agentIdleWarningSeconds
    ? `<div class="agent-idle-warning">Новых событий нет ${escapeHtml(formatDuration(idleSeconds))}. Возможно, агент ожидает ответ LLM. Таймаут одного запроса: ${escapeHtml(formatDuration(timeout))}.</div>`
    : '';
  return `
    <div class="agent-observability">
      <div class="agent-resource-grid">
        ${resourceCard('Время', `${formatDuration(executionDurationSeconds(run, metrics, running))} / ${formatDuration(limits.max_duration_seconds)}`)}
        ${resourceCard('Вызовы LLM', formatLimit(metrics.llm_calls, limits.max_llm_calls))}
        ${resourceCard('Токены', tokenAvailable ? formatLimit(metrics.total_tokens, limits.max_total_tokens) : 'нет данных')}
        ${resourceCard('Инструменты', formatLimit(metrics.tool_calls, limits.max_tool_calls))}
        ${resourceCard('Повторы tool call', formatLimit(metrics.max_repeat_streak, limits.max_repeated_tool_calls))}
        ${resourceCard('Последнее событие', formatRelative(lastActivity))}
      </div>
      ${tokenAvailable ? `<div class="agent-token-details">Вход: ${escapeHtml(formatNumber(metrics.input_tokens))} · выход: ${escapeHtml(formatNumber(metrics.output_tokens))}</div>` : '<div class="agent-token-details muted-text">Статистика токенов появится, если провайдер возвращает usage metadata.</div>'}
      <div class="muted-text">Оставшееся время не прогнозируется: показываются фактическая активность и настроенные пределы.</div>
      ${idleWarning}
      <details class="agent-event-log" ${running ? 'open' : ''}>
        <summary>Журнал выполнения · ${events.length}</summary>
        <div class="agent-event-list" data-agent-event-list>
          ${events.length ? events.slice(-state.agentEventDisplayLimit).map(renderEvent).join('') : '<div class="muted-text">События ещё не получены.</div>'}
        </div>
      </details>
    </div>
  `;
}

function resourceCard(label, value) {
  return `<div class="agent-resource-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function renderEvent(event) {
  const level = ['warning', 'error'].includes(event?.level) ? event.level : 'info';
  return `
    <div class="agent-event-item ${escapeAttr(level)}">
      <time>${escapeHtml(formatTime(event?.timestamp))}</time>
      <span>${escapeHtml(event?.message || event?.type || 'Событие')}</span>
    </div>
  `;
}

function formatLimit(value, maximum) {
  const current = formatNumber(value || 0);
  return Number(maximum) > 0 ? `${current} / ${formatNumber(maximum)}` : current;
}

function formatNumber(value) {
  return new Intl.NumberFormat('ru-RU').format(Number(value || 0));
}

function executionDurationSeconds(run, metrics, running) {
  const startedAt = new Date(run?.started_at || '').getTime();
  if (Number.isNaN(startedAt)) return 0;
  const finishedValue = metrics?.last_event_at || run?.updated_at || run?.started_at;
  const finishedAt = running ? Date.now() : new Date(finishedValue).getTime();
  if (Number.isNaN(finishedAt)) return 0;
  return Math.max(0, Math.floor((finishedAt - startedAt) / 1000));
}

function secondsSince(value) {
  if (!value) return 0;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
}

function formatDuration(secondsValue) {
  const seconds = Math.max(0, Number(secondsValue || 0));
  if (seconds < 60) return `${Math.floor(seconds)} сек`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} мин ${Math.floor(seconds % 60)} сек`;
  return `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`;
}

function formatRelative(value) {
  if (!value) return '—';
  const seconds = secondsSince(value);
  return seconds < 5 ? 'только что' : `${formatDuration(seconds)} назад`;
}

function formatTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString('ru-RU');
}

export function scrollAgentEventLogToLatest(container) {
  const list = container?.querySelector?.('[data-agent-event-list]');
  if (!list) return;
  window.requestAnimationFrame(() => {
    list.scrollTop = list.scrollHeight;
  });
}
