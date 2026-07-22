import { bindTabs, renderTabs } from './editor-tabs.js';
import { bindExternalLinkForms, renderExternalLinksTab } from './external-links-tab.js';
import { bindRelationForms, renderRelationsTab } from './relations-tab.js';
import { bindRequirementForms, renderRequirementTab } from './requirements-tab.js';
import { renderCodeTab } from './code-tab.js';

export { renderCodeTab, renderExternalLinksTab, renderRelationsTab, renderRequirementTab, renderTabs };

export function bindSharedForms(container) {
  bindTabs(container);
  bindRequirementForms(container);
  bindRelationForms(container);
  bindExternalLinkForms(container);
}
