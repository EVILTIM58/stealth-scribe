// VERSIONING POLICY
// -----------------------------------------------------------------------------
// The release below is version 1.0 -- the first complete Stealth-Scribe.
//
//   1.0.x  fixes and small corrections
//   1.x    new features, however large
//   2.0    reserved for an earth-shattering change only. Adding features does
//          not earn a major bump; fundamentally changing what the product IS
//          does.
//
// Every fix and every feature gets an entry here AND in /CHANGELOG.md at the
// repo root. Bump APP_VERSION, add the entry, and update the <title> in
// index.html and "name" in public/manifest.json to match.

export const APP_VERSION = '1.0.2'

export const VERSION_HISTORY = [
  {
    version: '1.0.2',
    date: '2026-08-26',
    changes: [
      'Fixed a missing request model that stopped the backend from starting at all',
      'Fixed every password reset returning a 500',
      'Fixed inline emphasis in the Nuke warning breaking onto its own line',
      'Fixed recording cards and match lines pushing the page sideways on a phone',
      'The library toolbar now wraps instead of overflowing on narrow screens'
    ]
  },
  {
    version: '1.0.1',
    date: '2026-08-16',
    changes: [
      'Canonical domain set to stealth-scribe.com',
      'Account deletion now points at the dashboard Nuke button, not an email',
      'Fixed ADMIN role badges rendering as a large empty box',
      'Fixed the invisible search icon'
    ]
  },
  {
    version: '1.0.0',
    date: '2026-08-16',
    changes: [
      'First complete release of Stealth-Scribe.',
      '',
      'TRANSCRIPTION — audio and video (mp3, wav, m4a, wma, ogg, flac, mp4, mov,',
      'mkv, avi, wmv and more), transcribed on your own GPU with Whisper. Video',
      'has its audio track extracted automatically and stays playable.',
      '',
      'TRANSLATION — around 99 languages into English, with the original kept',
      'alongside. Read English, the original, or both side by side. Arabic,',
      'Hebrew, Farsi, Urdu and Pashto render right-to-left correctly.',
      '',
      'SPEAKERS — separated and labelled, renameable by clicking the name in the',
      'transcript. Naming a voice teaches Stealth-Scribe to recognise that person',
      'in later recordings. Misattributed turns can be reassigned.',
      '',
      'SUMMARIES — overview, key points, action items and questions raised,',
      'written from the English text when a translation exists.',
      '',
      'RECORDING — capture live from a phone or desktop microphone with a level',
      'meter, timer and pause/resume.',
      '',
      'FILES — every finished recording keeps audio, PDF and plain text together.',
      'All three downloadable on demand, and downloads resume if interrupted.',
      '',
      'ACCOUNTS — three tiers. USER (1) has every feature and no subscription.',
      'ADMIN (2) adds user administration and can suspend for a set period.',
      'GOD (3) is the hardcoded owner and alone can promote, demote or delete.',
      'Sign in with Google, Facebook, or email and password.',
      '',
      'PRIVACY — recordings are private to the account that uploaded them.',
      'The Nuke button destroys everything you own, and your account with it if',
      'you choose, the instant you confirm. No ticket, no wait, no undo.',
      '',
      'SEARCH — full text across every transcript you own, including translations,',
      'with results linking to the exact moment in the audio.'
    ]
  }
]
