import { escapeHtml } from './html-utils.js';
import { localizeAgentMessage } from './agent-message-localization.js';

const RELATION_LABELS = {
  implemented_by: 'реализуется объектом',
  supports: 'поддерживается объектом',
  triggers: 'запускает действие',
  starts_flow: 'начинает пользовательский сценарий',
  provides_access: 'предоставляет доступ',
  displays_result: 'показывает результат',
  displays_summary: 'показывает сводку'
};

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
    <section class="card agent-collapsible-card agent-manual-review">
      <details>
        <summary>Ручная проверка · ${total}</summary>
        <div class="agent-manual-review-body">
          <p>Здесь показаны прежние связи и рекомендации, которые требуют решения аналитика. Связи с отсутствующими в текущем полном файле требованиями уже удалены из временного результата; связанные UI-объекты автоматически не удаляются.</p>
          ${renderInheritedLinks(inherited)}
          ${renderCleanupCandidates(cleanup)}
        </div>
      </details>
    </section>
  `;
}

function renderInheritedLinks(items) {
  if (!items.length) return '';
  const issueCount = items.reduce((total, item) => total + inheritedIssueCount(item), 0);
  return `
    <details class="agent-manual-review-group">
      <summary>Прежние связи с удалёнными или переименованными требованиями · ${items.length}${issueCount ? ` · проблем ${issueCount}` : ''}</summary>
      <div class="agent-manual-review-guidance">
        <strong>Что это означает</strong>
        <p>Эти связи были в базовой схеме, но соответствующие ID отсутствуют в полном текущем наборе требований. Они удалены из временного результата.</p>
        <strong>Что делать</strong>
        <ol>
          <li>Если ID требования изменился — восстановите связь уже с новым <code>requirement_id</code>.</li>
          <li>Если требование удалено — проверьте, нужен ли целевой UI-объект другим актуальным требованиям.</li>
          <li>Если объект устарел или дублируется — удалите его вручную либо перегенерируйте с соответствующим указанием агенту.</li>
        </ol>
      </div>
      <div class="agent-manual-review-list">
        ${items.map(renderInheritedRequirement).join('')}
      </div>
    </details>
  `;
}

function renderInheritedRequirement(item) {
  const requirementId = String(item?.requirement_id || 'ID не указан');
  const links = Array.isArray(item?.links) ? item.links : [];
  const issueCount = inheritedIssueCount(item);
  return `
    <details class="agent-manual-review-item inherited">
      <summary>
        <code>${escapeHtml(requirementId)}</code>
        <span>${links.length} ${pluralize(links.length, 'связь', 'связи', 'связей')}</span>
        ${issueCount ? `<span class="agent-manual-review-problem-count">${issueCount} ${pluralize(issueCount, 'проблема', 'проблемы', 'проблем')}</span>` : '<span class="agent-manual-review-ok">без технических проблем</span>'}
      </summary>
      <div class="agent-manual-review-item-body">
        <p>${escapeHtml(item?.reason || 'Требование отсутствует в текущем входном файле.')}</p>
        ${links.length ? `<div class="agent-manual-review-link-list">${links.map(link => renderInheritedLink(requirementId, link)).join('')}</div>` : '<div class="muted-text">Прежние связи не найдены.</div>'}
      </div>
    </details>
  `;
}

function renderInheritedLink(requirementId, link) {
  const targetType = String(link?.target_type || '');
  const targetId = String(link?.target_id || '');
  const targetLabel = String(link?.target_label || targetId || 'Объект не указан');
  const targetKind = targetType === 'page' ? 'Страница' : 'UI-элемент';
  const relation = String(link?.relation || '');
  const relationLabel = String(link?.relation_label || RELATION_LABELS[relation] || relation || 'не указана');
  const linkId = String(link?.id || 'id отсутствует');
  const pageTitle = String(link?.page_title || '');
  const pageId = String(link?.page_id || '');
  const issues = normalizedLinkIssues(link);
  const exists = link?.target_exists !== false;
  return `
    <article class="agent-manual-review-link ${issues.length ? 'has-issues' : ''}">
      <div class="agent-manual-review-link-heading">
        <div>
          <span class="agent-manual-review-target-kind">${escapeHtml(targetKind)}</span>
          <strong>${escapeHtml(targetLabel)}</strong>
        </div>
        <span class="agent-manual-review-link-status ${issues.length ? 'warning' : 'ok'}">${issues.length ? 'нужно проверить' : (link?.status === 'removed' ? 'удалена из результата' : 'сохранена')}</span>
      </div>
      <dl class="agent-manual-review-link-meta">
        <div><dt>Требование</dt><dd><code>${escapeHtml(requirementId)}</code></dd></div>
        <div><dt>Целевой объект</dt><dd><code>${escapeHtml(`${targetType}:${targetId}`)}</code>${exists ? '' : ' · объект не найден'}</dd></div>
        ${pageTitle || pageId ? `<div><dt>Страница</dt><dd>${escapeHtml(pageTitle || pageId)}${pageTitle && pageId ? ` · <code>${escapeHtml(pageId)}</code>` : ''}</dd></div>` : ''}
        <div><dt>Тип связи</dt><dd>${escapeHtml(relationLabel)}${relation ? ` · <code>${escapeHtml(relation)}</code>` : ''}</dd></div>
        <div><dt>Технический ID связи</dt><dd><code>${escapeHtml(linkId)}</code></dd></div>
      </dl>
      ${issues.length ? `<div class="agent-manual-review-issues">${issues.map(renderLinkIssue).join('')}</div>` : ''}
    </article>
  `;
}

function renderLinkIssue(issue) {
  const title = String(issue?.title || 'Проблема связи');
  const message = localizeAgentMessage(issue?.message || '');
  const recommendation = String(issue?.recommendation || '');
  return `
    <div class="agent-manual-review-issue">
      <strong>${escapeHtml(title)}</strong>
      ${message ? `<p>${escapeHtml(message)}</p>` : ''}
      ${recommendation ? `<p><strong>Что сделать:</strong> ${escapeHtml(recommendation)}</p>` : ''}
    </div>
  `;
}

function normalizedLinkIssues(link) {
  if (Array.isArray(link?.issues) && link.issues.some(item => item && typeof item === 'object')) {
    return link.issues.filter(item => item && typeof item === 'object');
  }
  return [];
}

function inheritedIssueCount(item) {
  if (Array.isArray(item?.issue_details)) return item.issue_details.length;
  if (Array.isArray(item?.issues)) return item.issues.length;
  return 0;
}

function renderCleanupCandidates(items) {
  if (!items.length) return '';
  return `
    <details class="agent-manual-review-group">
      <summary>Кандидаты на ручную очистку · ${items.length}</summary>
      <div class="agent-manual-review-list">
        ${items.map(item => {
          const requirements = Array.isArray(item?.requirement_ids) ? item.requirement_ids : [];
          const targets = Array.isArray(item?.targets) ? item.targets : [];
          const references = [
            requirements.length ? `Требования: ${requirements.join(', ')}` : '',
            targets.length ? `Объекты: ${targets.join(', ')}` : ''
          ].filter(Boolean).join(' · ');
          return `
            <article class="agent-manual-review-item cleanup">
              <div class="agent-manual-review-heading"><span>Проверить вручную</span><code>${escapeHtml(item?.category || '')}</code></div>
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

function pluralize(value, one, few, many) {
  const number = Math.abs(Number(value || 0));
  const mod100 = number % 100;
  const mod10 = number % 10;
  if (mod100 >= 11 && mod100 <= 19) return many;
  if (mod10 === 1) return one;
  if (mod10 >= 2 && mod10 <= 4) return few;
  return many;
}
