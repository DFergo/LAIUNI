// The admin panel wears the organization's colours and names (Sprint 43): the backend's global branding
// tokens, read before login from /admin/branding/public (no secrets in it).

export interface PublicBrand {
  org_name: string
  org_short_name: string
  tool_name: string
  color_primary: string
  color_on_primary: string
  color_accent: string
  color_dark: string
}

// Same values as the backend catalog, for the moment before it answers.
const DEFAULT_BRAND: PublicBrand = {
  org_name: 'UNI Global Union',
  org_short_name: 'UNI',
  tool_name: 'HRDD Helper',
  color_primary: '#003087',
  color_on_primary: '#FFFFFF',
  color_accent: '#E31837',
  color_dark: '#1A1A2E',
}

let current: PublicBrand = { ...DEFAULT_BRAND }

export const brand = (): PublicBrand => current

export function channels(hex: string): string {
  const h = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : '#000000'
  return [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)).join(' ')
}

export function applyBrand(b?: Partial<PublicBrand>): void {
  current = { ...DEFAULT_BRAND, ...(b ?? {}) }
  const style = document.documentElement.style
  style.setProperty('--brand-primary', channels(current.color_primary))
  style.setProperty('--brand-on-primary', channels(current.color_on_primary))
  style.setProperty('--brand-accent', channels(current.color_accent))
  style.setProperty('--brand-dark', channels(current.color_dark))
  document.title = `${current.tool_name} — Admin`
}

/** Fetch the global tokens and apply them. Falls back to the defaults if the backend does not answer. */
export async function loadBrand(): Promise<void> {
  try {
    const res = await fetch('/admin/branding/public')
    applyBrand(res.ok ? await res.json() : undefined)
  } catch {
    applyBrand()
  }
}
