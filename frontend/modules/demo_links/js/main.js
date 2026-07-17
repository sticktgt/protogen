import { getContext, currentWorkspaceId } from '/base/js/context.js';
import { initLayout } from '/base/js/layout.js';
import { navigateToPage } from '/base/js/navigation.js';
import { getInfo } from './api.js';

await initLayout('demo_links.main');
const context = await getContext();
const workspaceId = currentWorkspaceId(context);
const info = await getInfo(workspaceId);

const target = document.querySelector('[data-info]');
target.innerHTML = `
  <p class="summary-line">Этот модуль прочитал данные из <code>${info.hello_summary.source}</code>.</p>
  <pre>${JSON.stringify(info, null, 2)}</pre>
`;

document.querySelector('[data-open-hello]')?.addEventListener('click', () => {
  navigateToPage('demo_hello.main');
});

document.querySelector('[data-open-hidden]')?.addEventListener('click', () => {
  navigateToPage('demo_hidden.main', { source: 'demo_links' });
});
