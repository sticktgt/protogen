export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"]/g, char => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;'
  }[char]));
}

export function escapeAttr(value) {
  return escapeHtml(value).replace(/'/g, '&#39;');
}

export function statusLabel(status) {
  return {
    planned: 'запланировано',
    in_progress: 'в работе',
    implemented: 'реализовано',
    not_applicable: 'не применимо'
  }[status] || status || 'не указано';
}
