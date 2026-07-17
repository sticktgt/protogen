import { initLayout } from './layout.js';
import { getContext } from './context.js';

await initLayout('base.home');
const context = await getContext();

const moduleList = document.querySelector('[data-module-list]');
if (moduleList) {
  moduleList.innerHTML = context.menu.map(item => `
    <div class="card">
      <div class="card-title">${item.icon || ''} ${item.title}</div>
      <p class="muted">Модуль: ${item.module_name}</p>
      <a class="btn btn-primary" href="/${item.path}">Открыть</a>
    </div>
  `).join('');
}

const contextBox = document.querySelector('[data-context-json]');
if (contextBox) {
  contextBox.textContent = JSON.stringify(context, null, 2);
}
