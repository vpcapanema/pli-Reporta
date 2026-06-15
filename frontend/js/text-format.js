/** Revisão ortográfica e gramatical via API (pt-BR, norma culta). */

export async function formatDescriptionText(text) {
  const trimmed = (text || '').trim();
  if (!trimmed) return trimmed;

  try {
    const res = await fetch('/api/format-text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: trimmed }),
    });
    if (!res.ok) return trimmed;
    const data = await res.json();
    return (data.formatted || trimmed).trim() || trimmed;
  } catch {
    return trimmed;
  }
}
