import { escape as e } from '../redesign/presentation'

export type ResultPartner = {
  id: string
  name: string
  display_order?: number
  english_name?: string | null
  logo_url?: string | null
  category?: string | null
  introduction?: string | null
  description?: string | null
  support_description?: string | null
  official_url?: string | null
  builtin_mark_key?: string | null
}

type PartnerFields = {
  partners?: ResultPartner[]
  presenting_partner?: ResultPartner | null
  official_partners?: ResultPartner[]
}

export function resultPartners(data: PartnerFields): ResultPartner[] {
  if (data.partners) return data.partners
  const legacy = [...(data.official_partners ?? [])]
  if (data.presenting_partner) legacy.unshift(data.presenting_partner)
  return [...new Map(legacy.map(partner => [partner.id, partner])).values()].sort(
    (a, b) => (Number(a.display_order) || 0) - (Number(b.display_order) || 0) || a.id.localeCompare(b.id),
  )
}

export function partnerName(partner?: ResultPartner | null) {
  return [...new Set([partner?.english_name, partner?.name].filter(Boolean))].join(' / ')
}

export function partnerDetails(partner: ResultPartner) {
  const description = partner.support_description || partner.introduction || partner.description
  const website = partner.official_url?.startsWith('https://') ? partner.official_url : ''
  if (!description && !website) return null
  return {
    title: '合作支持详情',
    body: `<h2>${e(partnerName(partner))}</h2>${description ? `<p>${e(description)}</p>` : ''}${
      website ? `<p><a href="${e(website)}" target="_blank" rel="noopener">品牌官网 ↗</a></p>` : ''
    }`,
  }
}

export function renderPartners(partners: ResultPartner[], legacyMark: string) {
  if (!partners.length) return ''
  const items = partners.map((partner, index) => {
    const name = e(partner.english_name || partner.name)
    const fallback = `<span class="results-partner-fallback">${partner.builtin_mark_key === 'nexcore' ? legacyMark : ''}<strong>${name}</strong></span>`
    const image = partner.logo_url ? `<img data-partner-logo src="${e(partner.logo_url)}" alt="${e(partner.name)}" decoding="async">` : ''
    const style = index % 2 ? ' style="--partner-delay:65ms"' : ''
    const brand = partnerDetails(partner)
      ? `<button type="button" class="results-partner-mark" data-partner="${e(partner.id)}" aria-label="${e(partnerName(partner))} · 合作支持详情"${style}>${image}${fallback}</button>`
      : `<div class="results-partner-mark"${style}>${image}${fallback}</div>`
    return `<li class="results-partner">${brand}</li>`
  })
  return `<section class="results-partners" id="partners" aria-label="合作伙伴">
    <div class="results-width">
      <header class="results-partners-heading"><p lang="en">OFFICIAL PARTNERS</p><h2>合作伙伴</h2></header>
      <ul class="results-partners-grid">${items.join('')}</ul>
    </div>
  </section>`
}
