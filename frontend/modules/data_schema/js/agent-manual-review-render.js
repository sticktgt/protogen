import { escapeHtml } from './html-utils.js';

export function renderManualReview(manualReview) {
  if (!manualReview || typeof manualReview !== 'object') return '';
  const inherited = Array.isArray(manualReview.inherited_requirement_links)
    ? manualReview.inherited_requirement_links
    : [];
  const cleanup = Array.isArray(manualReview.cleanup_candidates)
    ? manualReview.cleanup_candidates
    : [];
  if (!inherited.length && !cleanup.length) return '';

  const total = inherited.length + cleanup.length;
  return `
    <section class="card agent-semantic-review approved">
      <details>
        <summary>Ручная проверка · ${total}</summary>
        <div class="agent-semantic-review-body">
          <p>Информация сохранена для аналитика и не влияет на статус применения. Автоматические исправления и удаления по этим пунктам не выполняются.</p>
          ${renderInheritedLinks(inherited)}
          ${renderCleanupCandidates(cleanup)}
        </div>
      </details>
    </section>
  `;
}

function renderInheritedLinks(items) {
  if (!items.length) return '';
  return `
    <details class="agent-semantic-strengths">
      <summary>Связи отсутствующих требований · ${items.length}</summary>
      <div class="agent-semantic-issues">
        ${items.map(item => {
          const requirementId = String(item?.requirement_id || '');
          const links = Array.isArray(item?.links) ? item.links : [];
          const details = links.map(link => {
            const target = [link?.target_type, link?.target_id].filter(Boolean).join(':');
            const relation = link?.relation ? ` · ${link.relation}` : '';
            return `${target}${relation}`;
          }).filter(Boolean);
          return `
            <article class="agent-semantic-issue advisory">
              <div class="agent-semantic-issue-heading">
                <span>Сохранённая связь</span>
                <code>${escapeHtml(requirementId)}</code>
              </div>
              <p>Requirement ID отсутствует в актуальном наборе готовых требований. Связи сохранены без изменений.</p>
              ${details.length ? `<div class="muted-text">${escapeHtml(details.join(', '))}</div>` : ''}
            </article>
          `;
        }).join('')}
      </div>
    </details>
  `;
}

function renderCleanupCandidates(items) {
  if (!items.length) return '';
  return `
    <details class="agent-semantic-strengths">
      <summary>Кандидаты на очистку схемы · ${items.length}</summary>
      <div class="agent-semantic-issues">
        ${items.map(item => {
          const requirements = Array.isArray(item?.requirement_ids) ? item.requirement_ids : [];
          const targets = Array.isArray(item?.targets) ? item.targets : [];
          const references = [
            requirements.length ? `Требования: ${requirements.join(', ')}` : '',
            targets.length ? `Объекты: ${targets.join(', ')}` : ''
          ].filter(Boolean).join(' · ');
          return `
            <article class="agent-semantic-issue advisory">
              <div class="agent-semantic-issue-heading">
                <span>Проверить вручную</span>
                <code>${escapeHtml(item?.category || '')}</code>
              </div>
              <p>${escapeHtml(item?.message || '')}</p>
              ${item?.recommendation ? `<p><strong>Рекомендация:</strong> ${escapeHtml(item.recommendation)}</p>` : ''}
              ${references ? `<div class="muted-text">${escapeHtml(references)}</div>` : ''}
            </article>
          `;
        }).join('')}
      </div>
    </details>
  `;
}
