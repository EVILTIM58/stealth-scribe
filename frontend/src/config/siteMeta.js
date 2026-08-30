// Single source of truth for the legal pages and footer.
// The backend serves the same values at /api/site/meta from environment
// variables — change them there for production and they flow through.

export const SITE = {
  name: 'Stealth-Scribe',
  tagline: 'Audio in. Transcribe to English. Save as PDF.',
  strapline: 'Clear. Accurate. Secure.',
  // Set SITE_BASE_URL in docker-compose; this is only the client-side default.
  url: 'https://stealth-scribe.com',
  contactEmail: 'contact@stealth-scribe.com',
  legalEmail: 'legal@stealth-scribe.com',
  dmcaEmail: 'dmca@stealth-scribe.com',
  jurisdiction: 'the State of Texas, United States',
  operator: 'Stealth-Scribe',
  lastUpdated: 'August 16, 2026',
  minimumAge: 16
}
