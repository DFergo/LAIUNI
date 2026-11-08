// Branding tokens (Sprint 43): the organization's name, the tool's name and the colours.
// The backend pushes the real values; these are the look of the app before it has
// (the same values as the backend catalog — backend/tests/test_branding_tokens.py checks it).

export type BrandTokens = Record<string, string>

export const DEFAULT_TOKENS: BrandTokens = {
  org_name: 'UNI Global Union',
  org_short_name: 'UNI',
  tool_name: 'HRDD Helper',
  color_primary: '#003087',
  color_on_primary: '#FFFFFF',
  color_accent: '#E31837',
  color_dark: '#1A1A2E',
}

let current: BrandTokens = { ...DEFAULT_TOKENS }

export function brandTokens(): BrandTokens {
  return current
}

function channels(hex: string, fallback: string): string {
  const h = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : fallback
  return [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)).join(' ')
}

/** True when text of this colour is light (so it needs a dark background to be read). */
export function isLight(hex: string): boolean {
  const [r, g, b] = channels(hex, '#000000').split(' ').map(Number)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5
}

/** Use the tokens pushed by the backend: colours become CSS variables (Tailwind reads them), the tab gets the tool's name. */
export function applyBranding(tokens?: BrandTokens): void {
  current = { ...DEFAULT_TOKENS, ...(tokens ?? {}) }
  const style = document.documentElement.style
  style.setProperty('--brand-primary', channels(current.color_primary, DEFAULT_TOKENS.color_primary))
  style.setProperty('--brand-on-primary', channels(current.color_on_primary, DEFAULT_TOKENS.color_on_primary))
  style.setProperty('--brand-accent', channels(current.color_accent, DEFAULT_TOKENS.color_accent))
  style.setProperty('--brand-dark', channels(current.color_dark, DEFAULT_TOKENS.color_dark))
  document.title = current.tool_name
}

/** Replace {{org_name}}, {{org_short_name}}, {{tool_name}}… in a text (unknown names are left alone). */
export function resolveTokens(text: string): string {
  return text.replace(/\{\{\s*([a-z_]+)\s*\}\}/g, (whole, name: string) => current[name] ?? whole)
}
