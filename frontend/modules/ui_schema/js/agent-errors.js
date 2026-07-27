export function agentActionErrorMessage(error, fallback = 'Операция не выполнена') {
  const candidates = [
    error?.detail,
    error?.data?.detail,
    error?.body?.detail,
    error?.response?.detail,
    error?.message
  ];
  for (const value of candidates) {
    const text = errorText(value);
    if (text && !isGenericHttpMessage(text)) return text;
  }
  const generic = candidates.map(errorText).find(Boolean);
  return generic ? `${fallback}. ${generic}` : fallback;
}

export function requirementsStartErrorMessage(error, requirementsPath) {
  const path = String(requirementsPath || '').trim();
  return agentActionErrorMessage(
    error,
    path
      ? `Не удалось запустить синхронизацию. Проверьте, что файл требований существует в workspace: ${path}`
      : 'Не удалось запустить синхронизацию. Укажите существующий файл требований в workspace'
  );
}

function errorText(value) {
  if (!value) return '';
  if (typeof value === 'string') return value.trim();
  if (typeof value === 'object') {
    if (typeof value.message === 'string') return value.message.trim();
    try { return JSON.stringify(value); } catch (_) { return String(value); }
  }
  return String(value).trim();
}

function isGenericHttpMessage(value) {
  return /(^|\b)(request failed|http error|bad request|400 bad request)(\b|:)|\b400\b.*\bbad request\b/i.test(value.trim());
}
