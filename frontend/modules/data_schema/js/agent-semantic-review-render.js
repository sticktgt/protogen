import { escapeAttr, escapeHtml } from './html-utils.js';

const DISPOSITION_LABELS = {
  must_fix: 'Требует исправления',
  advisory: 'Рекомендация'
};

const LEGACY_SEVERITY_LABELS = {
  critical: 'Требует исправления',
  warning: 'Рекомендация'
};

export function renderSemanticReview(review) {
  if (!review || typeof review !== 'object' || !review.status) return '';
  const issues = Array.isArray(review.issues) ? review.issues : [];
  const counts = normalizedCounts(review);
  const countText = Object.entries(counts)
    .filter(([, count]) => Number(count || 0) > 0)
    .map(([kind, count]) => `${dispositionLabel(kind)}: ${Number(count || 0)}`)
    .join(' · ');
  const reviewTitle = review.review_kind === 'correction_verification'
    ? 'Проверка исправлений'
    : review.review_kind === 'combined'
      ? 'Смысловой контроль'
      : 'LLM review';
  return `
    <section class="card agent-semantic-review ${review.blocking ? 'blocking' : 'approved'}">
      ${review.blocking ? `
        <div class="agent-semantic-blocking-note">
          По результатам LLM review требуются обязательные исправления. Автоматические раунды уже выполнены; просмотрите детали и запустите перегенерацию.
        </div>
      ` : ''}
      <details>
        <summary>${escapeHtml(reviewTitle)} · ${escapeHtml(countText || 'замечаний нет')}</summary>
        <div class="agent-semantic-review-body">
          <p>${escapeHtml(review.summary || '')}</p>
          ${renderStrengths(review.strengths)}
          ${issues.length ? `<div class="agent-semantic-issues">${issues.map(renderIssue).join('')}</div>` : '<div class="empty-state">Семантических замечаний нет.</div>'}
          ${review.review_note ? `<p class="muted-text">${escapeHtml(review.review_note)}</p>` : ''}
        </div>
      </details>
    </section>
  `;
}

function renderIssue(issue) {
  const requirements = Array.isArray(issue.requirement_ids) ? issue.requirement_ids : [];
  const targets = Array.isArray(issue.targets) ? issue.targets : [];
  const disposition = issueDisposition(issue);
  const references = [
    requirements.length ? `Требования: ${requirements.join(', ')}` : '',
    targets.length ? `Объекты: ${targets.join(', ')}` : ''
  ].filter(Boolean).join(' · ');
  return `
    <article class="agent-semantic-issue ${escapeAttr(disposition)}">
      <div class="agent-semantic-issue-heading">
        <span>${escapeHtml(dispositionLabel(disposition))}</span>
        <code>${escapeHtml(issue.category || '')}</code>
      </div>
      <p>${escapeHtml(issue.message || '')}</p>
      ${issue.recommendation ? `<p><strong>Рекомендация:</strong> ${escapeHtml(issue.recommendation)}</p>` : ''}
      ${references ? `<div class="muted-text">${escapeHtml(references)}</div>` : ''}
    </article>
  `;
}

function renderStrengths(values) {
  const strengths = Array.isArray(values) ? values : [];
  if (!strengths.length) return '';
  return `<details class="agent-semantic-strengths"><summary>Отмеченные сильные стороны · ${strengths.length}</summary><ul>${strengths.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></details>`;
}

function normalizedCounts(review) {
  const counts = review.issue_counts && typeof review.issue_counts === 'object'
    ? review.issue_counts
    : {};
  if ('must_fix' in counts || 'advisory' in counts) return counts;
  return {
    must_fix: Number(counts.critical || 0),
    advisory: Number(counts.warning || 0)
  };
}

function issueDisposition(issue) {
  if (issue?.disposition) return issue.disposition;
  if (issue?.severity === 'critical') return 'must_fix';
  return 'advisory';
}

function dispositionLabel(value) {
  return DISPOSITION_LABELS[value] || LEGACY_SEVERITY_LABELS[value] || value || 'Замечание';
}
