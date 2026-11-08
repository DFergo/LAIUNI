import { BrandingConfig } from './types'
import { brandTokens, isLight } from './branding'

// Sidecar-served logo variants per slot (pushed by the backend on upload/change).
const slotUrl = (slot: string, variant: 'color' | 'white') => `/internal/branding-logo/${slot}/${variant}`
const DEFAULT = '/uni-logo.png'

type Slot = 'header' | 'page' | 'chat_bg'

function uploaded(b: BrandingConfig | undefined, slot: Slot): { uploaded: boolean; has_white: boolean } {
  const s = b?.logos?.[slot]
  if (s) return s
  // Sidecar state from before the slots: one logo for the top bar and the pages
  if (slot !== 'chat_bg') return { uploaded: !!b?.logo_uploaded, has_white: !!b?.logo_has_white }
  return { uploaded: false, has_white: false }
}

/**
 * Top-bar logo. An uploaded logo is served pre-processed; its white variant is used when the text on the
 * primary colour is light. With no upload the URL/bundled logo is forced to the text colour with CSS.
 */
export function headerLogo(b?: BrandingConfig): { src: string; filter: string } {
  const light = isLight(brandTokens().color_on_primary)
  const up = uploaded(b, 'header')
  if (up.uploaded) {
    if (b?.logo_mode !== 'color' && up.has_white && light) return { src: slotUrl('header', 'white'), filter: '' }
    return { src: slotUrl('header', 'color'), filter: '' }
  }
  return { src: b?.logo_url || DEFAULT, filter: light ? 'brightness-0 invert' : 'brightness-0' }
}

/** Full-colour logo for the light pages (disclaimer / instructions / language). */
export function pageLogo(b?: BrandingConfig): string {
  if (uploaded(b, 'page').uploaded) return slotUrl('page', 'color')
  return b?.logo_url || DEFAULT
}

/** Faded logo behind the chat. Without its own upload it follows the page logo, so an organization never sees another's. */
export function chatBackgroundLogo(b?: BrandingConfig): string {
  if (uploaded(b, 'chat_bg').uploaded) return slotUrl('chat_bg', 'color')
  return pageLogo(b)
}
