export async function apiFetch(path, options = {}) {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  const response = await fetch(normalized, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    ...options
  });

  if (response.status === 401) {
    window.location.href = '/login';
    throw new Error('Not authenticated');
  }

  const contentType = response.headers.get('content-type') || '';
  const body = contentType.includes('application/json') ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = typeof body === 'object' ? body.detail : body;
    throw new Error(detail || `HTTP ${response.status}`);
  }

  return body;
}
