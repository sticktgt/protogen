const PREFIX_TRANSLATIONS = [
  [
    'Requirement links reference IDs outside the current input: ',
    'Связи с требованиями содержат ID, отсутствующие в текущем входном файле: '
  ],
  [
    'Inherited requirement link issues were preserved for manual review and do not block current synchronization: ',
    'Проблемы унаследованных связей с требованиями сохранены для ручной проверки и не блокируют текущую синхронизацию: '
  ]
];

const OLD_MISSING_REQUIREMENTS_PREFIXES = [
  'Связи с требованиями содержат ID, отсутствующие в текущем входном файле: ',
  'Requirement links reference IDs outside the current input: '
];

const OLD_INHERITED_ISSUES_PREFIXES = [
  'Проблемы унаследованных связей с требованиями сохранены для ручной проверки и не блокируют текущую синхронизацию: ',
  'Inherited requirement link issues were preserved for manual review and do not block current synchronization: '
];

export function localizeAgentMessage(value) {
  let text = String(value || '');

  const missingPrefix = OLD_MISSING_REQUIREMENTS_PREFIXES.find(prefix => text.startsWith(prefix));
  if (missingPrefix) {
    const ids = text.slice(missingPrefix.length).split(',').map(item => item.trim()).filter(Boolean);
    return `Найдены сохранённые связи с требованиями, которых нет в выбранном входном файле. Количество требований: ${ids.length || 'не определено'}. Они не удалены автоматически. Откройте раздел «Ручная проверка» и решите, оставить, переименовать или удалить эти связи.`;
  }

  const issuesPrefix = OLD_INHERITED_ISSUES_PREFIXES.find(prefix => text.startsWith(prefix));
  if (issuesPrefix) {
    const details = text.slice(issuesPrefix.length);
    const count = (details.match(/(?:Связь с требованием|Requirement link|Связь )/g) || []).length;
    return `Проблемных сохранённых связей с отсутствующими требованиями: ${count || 'несколько'}. Они не блокируют синхронизацию. Целевые объекты, технические ID и рекомендации показаны в разделе «Ручная проверка».`;
  }

  for (const [source, target] of PREFIX_TRANSLATIONS) {
    if (text.startsWith(source)) {
      text = target + text.slice(source.length);
      break;
    }
  }
  return text
    .replace(/Requirement link ([^;]+?) has unsupported relation: ([^;]+)/g,
      'Связь с требованием $1 использует неподдерживаемый тип связи: $2')
    .replace(/Requirement link ([^;]+?) has missing target: ([^;]+)/g,
      'Связь с требованием $1 ведёт на отсутствующую цель: $2')
    .replace(/Duplicate requirement link id: ([^;]+)/g,
      'Повторяющийся id связи с требованием: $1')
    .replace(/Requirement ID/g, 'Идентификатор требования')
    .replace(/legacy relation/g, 'устаревший тип связи');
}
