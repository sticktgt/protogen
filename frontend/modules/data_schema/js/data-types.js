import { escapeHtml } from './html-utils.js';

export const DATA_TYPES = [
  { id: 'string', icon: '🔤', title: 'Строка', description: 'Короткое текстовое значение.' },
  { id: 'text', icon: '📝', title: 'Текст', description: 'Длинное текстовое значение.' },
  { id: 'integer', icon: '🔢', title: 'Целое число', description: 'Целочисленное значение.' },
  { id: 'decimal', icon: '💯', title: 'Десятичное число', description: 'Число с дробной частью.' },
  { id: 'boolean', icon: '☑️', title: 'Логическое значение', description: 'Значение да/нет.' },
  { id: 'date', icon: '📅', title: 'Дата', description: 'Календарная дата без времени.' },
  { id: 'datetime', icon: '🕒', title: 'Дата и время', description: 'Дата и время.' },
  { id: 'uuid', icon: '🆔', title: 'Идентификатор', description: 'Универсальный логический идентификатор.' },
  { id: 'dictionary', icon: '📚', title: 'Справочник', description: 'Значение из справочника.' },
  { id: 'json', icon: '🧩', title: 'Структура', description: 'Вложенное структурированное значение.' }
];

export const DATA_TYPE_IDS = DATA_TYPES.map(item => item.id);

export function dataTypeInfo(type) {
  return DATA_TYPES.find(item => item.id === type) || {
    id: type || 'unknown',
    icon: '•',
    title: type || 'unknown',
    description: 'Неизвестный тип данных.'
  };
}

export function renderTypeBadge(type) {
  const info = dataTypeInfo(type);
  return `<span class="type-badge" title="${escapeHtml(info.title)} — ${escapeHtml(info.description)}"><span class="type-icon">${escapeHtml(info.icon)}</span>${escapeHtml(info.id)}</span>`;
}

export function renderTypeOptions(selectedType = '') {
  return DATA_TYPES.map(type => `
    <option value="${escapeHtml(type.id)}" ${type.id === selectedType ? 'selected' : ''}>${type.icon} ${type.id} — ${type.title}</option>
  `).join('');
}
