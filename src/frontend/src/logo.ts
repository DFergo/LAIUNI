import { BrandingConfig } from './types'

// Sidecar-served logo variants (pushed once by the backend on upload/change).
const COLOR = '/internal/branding-logo/color'
const WHITE = '/internal/branding-logo/white'
const DEFAULT = '/uni-logo.png'

/**
 * Header (blue bar) logo. When a logo has been uploaded we serve the pre-processed
 * variant and apply no CSS filter (the white variant is already white). With no
 * upload we keep the legacy behaviour: the URL/bundled logo forced white via CSS.
 */
export function headerLogo(b?: BrandingConfig): { src: string; invert: boolean } {
  if (b?.logo_uploaded) {
    if (b.logo_mode !== 'color' && b.logo_has_white) return { src: WHITE, invert: false }
    return { src: COLOR, invert: false }
  }
  return { src: b?.logo_url || DEFAULT, invert: true }
}

/** Full-colour logo for the light pages (disclaimer / instructions / language). */
export function pageLogo(b?: BrandingConfig): string {
  if (b?.logo_uploaded) return COLOR
  return b?.logo_url || DEFAULT
}
