import {
  bindAgentControls,
  initializeAgentController,
  isAgentActionInProgress,
  loadAgentPanelState as loadControllerState
} from './agent-controller.js';
import {
  renderAgentFailed,
  renderAgentPreview,
  renderAgentRunning,
  renderAgentStart
} from './agent-render.js';
import { state } from './state.js';

export function initializeAgentView({ onSchemaReload }) {
  initializeAgentController({ onSchemaReload, onRender: renderAgentView });
}

export async function loadAgentPanelState() {
  await loadControllerState();
}

export function renderAgentView() {
  const container = document.querySelector('[data-agent-view]');
  if (!container) return;
  if (state.previewActive) {
    container.innerHTML = '<div class="card">Завершите просмотр preview, чтобы управлять задачей синхронизации.</div>';
    return;
  }
  if (!state.agentLoaded) {
    container.innerHTML = '<div class="card">Загрузка состояния агента…</div>';
    return;
  }

  const run = state.agentRun;
  const busy = isAgentActionInProgress();
  if (!run) {
    container.innerHTML = renderAgentStart({
      snapshot: state.agentHistory,
      initialAvailable: state.agentInitialAvailable,
      actionInProgress: busy,
      llmTest: state.agentLlmTest,
      requirementsPath: state.agentRequirementsPath,
      userRequest: state.agentUserRequest,
      baseMode: state.agentBaseMode
    });
  } else if (['running', 'cancelling', 'applying'].includes(run.status)) {
    container.innerHTML = renderAgentRunning(run, state.agentMetrics, state.agentEvents);
  } else if (run.status === 'preview_ready') {
    container.innerHTML = renderAgentPreview(run, state.agentChanges || {}, busy, state.agentMetrics, state.agentEvents);
  } else if (run.status === 'failed') {
    container.innerHTML = renderAgentFailed(run, busy, state.agentMetrics, state.agentEvents);
  } else {
    container.innerHTML = renderAgentStart({
      snapshot: state.agentHistory,
      initialAvailable: state.agentInitialAvailable,
      actionInProgress: busy,
      llmTest: state.agentLlmTest,
      requirementsPath: state.agentRequirementsPath,
      userRequest: state.agentUserRequest,
      baseMode: state.agentBaseMode
    });
  }
  bindAgentControls(container);
}
