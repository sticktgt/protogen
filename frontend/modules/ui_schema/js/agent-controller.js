import { showToast } from '/base/js/ui.js';
import {
  applyAgentRun,
  cancelAgentRun,
  loadActiveAgentRun,
  loadAgentChanges,
  loadAgentEvents,
  loadAgentRun,
  loadLatestAgentSnapshot,
  regenerateAgentRun,
  rejectAgentRun,
  restoreLatestAgentSnapshot,
  startAgentRun,
  testAgentLlm
} from './api.js';
import { state } from './state.js';
import { scrollAgentEventLogToLatest } from './agent-observability-render.js';

let reloadSchema = async () => {};
let renderView = () => {};
let pollingTimer = null;
let actionInProgress = false;

export function initializeAgentController({ onSchemaReload, onRender }) {
  reloadSchema = onSchemaReload || reloadSchema;
  renderView = onRender || renderView;
}

export function isAgentActionInProgress() {
  return actionInProgress;
}

export async function loadAgentPanelState() {
  if (!state.workspaceId || state.previewRunId) return;
  state.writeLocked = false;
  try {
    const [active, history] = await Promise.all([
      loadActiveAgentRun(state.workspaceId),
      loadLatestAgentSnapshot(state.workspaceId)
    ]);
    state.agentRun = active?.run || null;
    state.writeLocked = isLockingStatus(state.agentRun?.status);
    state.agentHistory = history?.snapshot || null;
    state.agentInitialAvailable = history?.initial_snapshot_available === true;
    state.agentChanges = state.agentRun?.status === 'preview_ready'
      ? await loadAgentChanges(state.workspaceId, state.agentRun.run_id)
      : null;
    resetAgentObservability();
    applyEmbeddedObservability(state.agentRun);
    if (state.agentRun?.run_id) await refreshRunEvents(state.agentRun.run_id);
    state.agentLoaded = true;
    configurePolling();
  } catch (error) {
    console.error(error);
    state.writeLocked = false;
    state.agentLoaded = true;
  }
}

export function bindAgentControls(container) {
  scrollAgentEventLogToLatest(container);
  const run = state.agentRun;
  if (!run) {
    bindStart(container);
    bindRestore(container);
    bindLlmTest(container);
    return;
  }
  if (['running', 'cancelling', 'applying'].includes(run.status)) {
    if (run.status === 'running') container.querySelector('[data-cancel-agent-run]')?.addEventListener('click', () => cancelRun(run));
    return;
  }
  if (run.status === 'preview_ready') {
    container.querySelector('[data-apply-agent-run]')?.addEventListener('click', () => applyRun(run));
    container.querySelector('[data-reject-agent-run]')?.addEventListener('click', () => rejectRun(run));
    container.querySelector('[data-open-agent-preview]')?.addEventListener('click', () => openPreview(run));
    bindRegeneration(container, run);
    return;
  }
  if (run.status === 'failed') {
    bindRegeneration(container, run);
    container.querySelector('[data-reject-agent-run]')?.addEventListener('click', () => rejectRun(run));
  }
}

function bindStart(container) {
  const pathInput = container.querySelector('[data-agent-requirements-path]');
  const requestInput = container.querySelector('[data-agent-user-request]');
  pathInput?.addEventListener('input', () => { state.agentRequirementsPath = pathInput.value; });
  requestInput?.addEventListener('input', () => { state.agentUserRequest = requestInput.value; });
  container.querySelectorAll('input[name="agent-base-mode"]').forEach(input => {
    input.addEventListener('change', () => {
      if (input.checked) state.agentBaseMode = input.value;
    });
  });

  container.querySelector('[data-agent-start-form]')?.addEventListener('submit', async event => {
    event.preventDefault();
    const requirementsPath = (pathInput?.value || '').trim();
    if (!requirementsPath) {
      showToast('Укажите относительный путь к файлу требований в workspace');
      pathInput?.focus();
      return;
    }
    const request = requestInput?.value || '';
    const baseMode = container.querySelector('input[name="agent-base-mode"]:checked')?.value || 'current';
    state.agentRequirementsPath = requirementsPath;
    state.agentUserRequest = request;
    state.agentBaseMode = baseMode;
    await runAction(async () => {
      state.agentRun = await startAgentRun(state.workspaceId, requirementsPath, request, baseMode);
      state.writeLocked = true;
      state.agentChanges = null;
      resetAgentObservability();
      configurePolling();
    }, 'Задача синхронизации запущена');
  });
}

function bindLlmTest(container) {
  container.querySelector('[data-test-agent-llm]')?.addEventListener('click', async () => {
    state.agentLlmTest = { status: 'testing' };
    renderView();
    try {
      const result = await testAgentLlm(state.workspaceId);
      state.agentLlmTest = { status: 'success', result };
    } catch (error) {
      console.error(error);
      state.agentLlmTest = { status: 'error', message: error?.message || 'Ошибка соединения с LLM' };
    }
    renderView();
  });
}

function bindRegeneration(container, run) {
  container.querySelector('[data-regenerate-agent-run]')?.addEventListener('click', async () => {
    const comment = container.querySelector('[data-regenerate-comment]')?.value || '';
    await runAction(async () => {
      state.agentRun = await regenerateAgentRun(state.workspaceId, run.run_id, comment);
      state.writeLocked = true;
      state.agentChanges = null;
      resetAgentObservability();
      configurePolling();
    }, 'Перегенерация запущена');
  });
}

function bindRestore(container) {
  container.querySelector('[data-restore-latest]')?.addEventListener('click', async () => {
    if (!window.confirm('Восстановить предыдущую версию UI-схемы? Текущее состояние также будет сохранено.')) return;
    await runAction(async () => {
      await restoreLatestAgentSnapshot(state.workspaceId);
      state.summary = null;
      await reloadSchema();
      await refreshSnapshotState();
    }, 'Предыдущая UI-схема восстановлена');
  });
}

async function applyRun(run) {
  if (!window.confirm('Применить все изменения к рабочей UI-схеме?')) return;
  await runAction(async () => {
    await applyAgentRun(state.workspaceId, run.run_id);
    stopPolling();
    state.agentRun = null;
    state.agentChanges = null;
    resetAgentObservability();
    state.writeLocked = false;
    state.summary = null;
    await refreshSnapshotState();
    await reloadSchema();
  }, 'Изменения UI-схемы применены');
}

async function rejectRun(run) {
  if (!window.confirm('Отклонить весь результат синхронизации?')) return;
  await runAction(async () => {
    await rejectAgentRun(state.workspaceId, run.run_id);
    stopPolling();
    state.agentRun = null;
    state.agentChanges = null;
    resetAgentObservability();
    state.writeLocked = false;
    await refreshSnapshotState();
    await reloadSchema();
  }, 'Изменения отклонены');
}

async function cancelRun(run) {
  if (!window.confirm('Запросить отмену выполняющейся задачи? Текущий вызов LLM может завершаться до таймаута.')) return;
  await runAction(async () => {
    state.agentRun = await cancelAgentRun(state.workspaceId, run.run_id);
    state.writeLocked = true;
    configurePolling();
  }, 'Запрошена отмена задачи');
}


async function refreshSnapshotState() {
  const history = await loadLatestAgentSnapshot(state.workspaceId);
  state.agentHistory = history?.snapshot || null;
  state.agentInitialAvailable = history?.initial_snapshot_available === true;
}

function openPreview(run) {
  const url = new URL(window.location.href);
  url.searchParams.set('preview_run_id', run.run_id);
  url.searchParams.set('tab', 'map');
  window.location.href = url.toString();
}

async function runAction(action, successMessage) {
  if (actionInProgress) return;
  actionInProgress = true;
  renderView();
  try {
    await action();
    if (successMessage) showToast(successMessage);
  } catch (error) {
    console.error(error);
    showToast(error?.message || 'Операция не выполнена');
  } finally {
    actionInProgress = false;
    renderView();
  }
}

function configurePolling() {
  const running = ['running', 'cancelling', 'applying'].includes(state.agentRun?.status);
  if (running && !pollingTimer) pollingTimer = window.setInterval(refreshRun, 2000);
  if (!running) stopPolling();
}

async function refreshRun() {
  const runId = state.agentRun?.run_id;
  if (!runId) return stopPolling();
  try {
    const [run] = await Promise.all([
      loadAgentRun(state.workspaceId, runId),
      refreshRunEvents(runId)
    ]);
    state.agentRun = run;
    applyEmbeddedObservability(run);
    state.writeLocked = isLockingStatus(run.status);
    if (run.status === 'preview_ready') {
      state.agentChanges = await loadAgentChanges(state.workspaceId, runId);
    }
    if (run.status === 'cancelled') {
      state.agentRun = null;
      state.writeLocked = false;
      stopPolling();
      await reloadSchema();
      showToast('Задача отменена');
    } else if (!['running', 'cancelling', 'applying'].includes(run.status)) {
      stopPolling();
    }
    renderView();
  } catch (error) {
    console.error(error);
    stopPolling();
  }
}

async function refreshRunEvents(runId) {
  const result = await loadAgentEvents(state.workspaceId, runId, state.agentEventCursor || 0);
  const incoming = Array.isArray(result?.events) ? result.events : [];
  if (incoming.length) {
    state.agentEvents = [...state.agentEvents, ...incoming].slice(-300);
  }
  state.agentMetrics = result?.metrics || state.agentMetrics;
  state.agentEventCursor = Number(result?.next_after || state.agentEventCursor || 0);
}

function applyEmbeddedObservability(run) {
  if (!run) return;
  if (run.metrics && typeof run.metrics === 'object') state.agentMetrics = run.metrics;
  if (Array.isArray(run.recent_events) && run.recent_events.length) {
    const bySeq = new Map(state.agentEvents.map(event => [Number(event.seq || 0), event]));
    run.recent_events.forEach(event => bySeq.set(Number(event.seq || 0), event));
    state.agentEvents = [...bySeq.values()].sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0)).slice(-300);
    state.agentEventCursor = Math.max(state.agentEventCursor || 0, ...state.agentEvents.map(event => Number(event.seq || 0)));
  }
}

function isLockingStatus(status) {
  return ['running', 'cancelling', 'preview_ready', 'applying', 'failed'].includes(status);
}

function resetAgentObservability() {
  state.agentEvents = [];
  state.agentMetrics = null;
  state.agentEventCursor = 0;
}

function stopPolling() {
  if (pollingTimer) window.clearInterval(pollingTimer);
  pollingTimer = null;
}
