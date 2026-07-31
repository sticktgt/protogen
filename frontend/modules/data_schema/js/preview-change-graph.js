export function previewFieldColors(action) {
  if (action === 'added') return { fill: '#f0fdf4', stroke: '#86efac', text: '#166534' };
  if (action === 'modified') return { fill: '#fffbeb', stroke: '#fcd34d', text: '#92400e' };
  return { fill: '#f8fafc', stroke: '#e2e8f0', text: '#0f172a' };
}

export function previewEntityColors(action) {
  if (action === 'added') return { fill: '#f0fdf4', stroke: '#22c55e', strokeWidth: 2.2 };
  if (action === 'modified') return { fill: '#fffbeb', stroke: '#f59e0b', strokeWidth: 2.2 };
  return { fill: '#f8fafc', stroke: '#dbe3ef', strokeWidth: 1.4 };
}

export function previewRelationColors(action) {
  if (action === 'added') {
    return {
      fill: '#f0fdf4', border: '#86efac', stroke: '#16a34a',
      text: '#166534', strokeWidth: 2.5, changed: true
    };
  }
  if (action === 'modified') {
    return {
      fill: '#fffbeb', border: '#fcd34d', stroke: '#d97706',
      text: '#92400e', strokeWidth: 2.5, changed: true
    };
  }
  return {
    fill: '#f8fafc', border: '#dbe3ef', stroke: '#64748b',
    text: '#475569', strokeWidth: 1.5, changed: false
  };
}
