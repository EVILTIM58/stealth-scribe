import React, { useState } from 'react'
import { api } from '../api.js'
import { Link } from '../router.jsx'
import { SITE } from '../config/siteMeta.js'
import { VERSION_HISTORY } from '../config/version.js'

function LegalPage({ title, subtitle, children }) {
  return (
    <article className="legal">
      <Link to="/" className="link back">&larr; Back to {SITE.name}</Link>
      <h1>{title}</h1>
      {subtitle && <p className="legal-sub muted">{subtitle}</p>}
      <div className="legal-stamp muted small">Last updated: {SITE.lastUpdated}</div>
      <div className="legal-body">{children}</div>
      <div className="legal-foot muted small">
        Questions about this page? Email{' '}
        <a href={`mailto:${SITE.legalEmail}`}>{SITE.legalEmail}</a>.
      </div>
    </article>
  )
}

/* ------------------------------------------------------------------ about */
export function AboutPage() {
  return (
    <LegalPage title="About Stealth-Scribe" subtitle={SITE.strapline}>
      <p>
        Stealth-Scribe turns recordings into readable, searchable text. You upload
        an audio or video file — or record straight from your phone — and get back
        a full transcript with each speaker labelled, a written summary, the key
        points, and any action items that came up. If the recording is not in
        English, you get an English translation alongside the original.
      </p>
      <p>
        Every finished recording keeps three files side by side: the original
        audio or video, a PDF, and a plain text transcript. All three are yours to
        download whenever you want.
      </p>

      <h2>Why it exists</h2>
      <p>
        Recordings are easy to make and miserable to use. A one-hour conversation is
        one hour to re-listen to, and you cannot search it. Stealth-Scribe exists to make the
        contents of a recording as easy to work with as a document: skim the summary,
        search for the phrase you half-remember, click the line and hear exactly that
        moment.
      </p>

      <h2>How it works</h2>
      <p>
        Speech recognition and translation both run on <strong>OpenAI&rsquo;s
        Whisper</strong> model, which handles around 99 languages and translates
        any of them into English. Speaker separation — working out who spoke when
        — uses <strong>pyannote</strong>, which also produces the voiceprints that
        let Stealth-Scribe recognise a person you have named in later recordings.
        Summaries are written from the transcript text.
      </p>
      <p>
        All of it runs on hardware the operator owns and controls. Your recordings
        are never sent to a third-party transcription service.
      </p>

      <h2>What we believe about your recordings</h2>
      <ul>
        <li><strong>They're yours.</strong> Your recordings and transcripts are private
          to your account. We don't sell them, mine them, or train models on them.</li>
        <li><strong>Text should outlive the app.</strong> Every transcript is also saved
          as a plain <code>.txt</code> file. You can take it and go.</li>
        <li><strong>Delete means delete.</strong> Removing a recording removes the
          media file, its transcript and its PDF from disk — not just from a list.
          The Nuke button erases everything you own, and your account too if you
          want, the instant you confirm it. No ticket, no wait, no undo.</li>
      </ul>

      <h2>Who's behind it</h2>
      <p>
        Stealth-Scribe is an independent project, operated from {SITE.jurisdiction}. It isn't
        affiliated with OpenAI, Google, Meta, or any other company whose technology or
        sign-in it uses. Reach us at{' '}
        <a href={`mailto:${SITE.contactEmail}`}>{SITE.contactEmail}</a> or through the{' '}
        <Link to="/contact">contact page</Link>.
      </p>
    </LegalPage>
  )
}

/* ---------------------------------------------------------------- privacy */
export function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy"
               subtitle="What we collect, why we collect it, and what we never do with it.">
      <h2>The short version</h2>
      <p>
        We collect the minimum needed to run an account and turn your recordings
        into text. Your recordings are private to your account. We do not sell
        your data, we do not use your recordings to train models, and there are
        no ads and no third-party trackers anywhere on this site.
      </p>

      <h2>What we collect, and why</h2>
      <table className="collect-table">
        <thead><tr><th>What</th><th>Why</th></tr></thead>
        <tbody>
          <tr>
            <td><strong>Your email address and name</strong></td>
            <td>To identify your account and contact you about it. If you sign in
              with Google or Facebook we also receive your profile picture.</td>
          </tr>
          <tr>
            <td><strong>A password hash</strong> (only if you set a password)</td>
            <td>To sign you in. It is a salted scrypt hash — we cannot read your
              password and neither could anyone who stole the database.</td>
          </tr>
          <tr>
            <td><strong>Your recordings and video</strong></td>
            <td>To transcribe them. They are the reason the service exists.</td>
          </tr>
          <tr>
            <td><strong>Everything derived from them</strong> — transcript,
              English translation, summary, speaker labels, PDF, plain text</td>
            <td>To give you something readable and searchable, and so the text
              survives independently of this app.</td>
          </tr>
          <tr>
            <td><strong>Voiceprints</strong> — a numeric representation of what a
              speaker&rsquo;s voice sounds like</td>
            <td>So that once you name a voice, that person is recognised in your
              later recordings. See the section below; this is the most sensitive
              thing we hold.</td>
          </tr>
          <tr>
            <td><strong>Sign-in records</strong> — times, the IP address a session
              was created from, and your browser&rsquo;s user-agent</td>
            <td>To keep your account secure and to detect abuse.</td>
          </tr>
          <tr>
            <td><strong>Moderation records</strong> — if an account is suspended,
              the reason, the duration and which admin did it</td>
            <td>So moderation decisions can be reviewed and reversed.</td>
          </tr>
        </tbody>
      </table>

      <h2>Voiceprints and biometric data</h2>
      <p>
        When speaker separation runs, we compute a <strong>voiceprint</strong> for
        each speaker: a list of numbers describing vocal characteristics. It is
        not a recording and cannot be played back, but it can be used to
        recognise the same person in a different recording. In some places that
        makes it <strong>biometric data</strong>, regulated more strictly than
        ordinary personal information.
      </p>
      <ul>
        <li>Voiceprints are created only when you put a <em>name</em> to a voice.
          Naming is what stores one.</li>
        <li>They are scoped strictly to your account. They are never shared with
          other users, never pooled, and never used to identify anyone outside
          your own recordings.</li>
        <li>The numbers are never sent to your browser and never leave this
          server.</li>
        <li>You can delete any of them at any time from the <em>Voices</em> page,
          or all of them at once with the Nuke button in your account.</li>
      </ul>
      <p>
        <strong>Important:</strong> voiceprints describe people who did not sign
        up for this service. Only name voices belonging to people whose
        recordings you had the right to make in the first place.
      </p>

      <h2>What we do not collect</h2>
      <ul>
        <li>No advertising or cross-site tracking cookies. The only cookie we set
          is the one that keeps you signed in.</li>
        <li>No third-party analytics of any kind.</li>
        <li>No payment details — the service does not take payments and there is
          no subscription.</li>
      </ul>

      <h2>Who can see your recordings</h2>
      <p>
        You can. Administrators of this installation can also access recordings
        for moderation, abuse investigation and support — an operational
        necessity on a service where users can upload anything, and you should
        assume it is possible. No other user can see your recordings.
      </p>

      <h2>Where processing happens</h2>
      <p>
        Recordings are stored on servers the operator controls. Transcription,
        translation and speaker recognition all run on the operator&rsquo;s own
        hardware. Your audio is never uploaded to a third-party transcription
        service. If the optional AI summary feature is enabled, the <em>text</em>
        of a transcript — never the audio — may be sent to that provider to write
        the summary.
      </p>

      <h2>Third parties we use</h2>
      <ul>
        <li><strong>Google and Meta (Facebook)</strong> — only if you choose to
          sign in with them, and only to confirm your identity and email.</li>
        <li><strong>Resend</strong> — to deliver confirmation and password-reset
          email.</li>
        <li><strong>Cloudflare</strong> — to route traffic to the service.</li>
      </ul>

      <h2>How long we keep things</h2>
      <p>
        Recordings, transcripts, PDFs and voiceprints are kept until you delete
        them or delete your account. Sign-in sessions expire after 30 days.
        Email confirmation links expire in 24 hours and password reset links in
        one hour. A suspension record is kept for as long as the account exists.
      </p>

      <h2>Deleting your data</h2>
      <p>
        Deleting a single recording removes its audio, transcript, PDF and text
        file from disk. The <strong>Nuke</strong> button in your account deletes
        every recording you own and everything derived from it in one action, and
        optionally your voiceprints too.
      </p>
      <p>
        <strong>Nuked files cannot be retrieved.</strong> There is no archive, no
        recycle bin and no backup we can restore from. That is deliberate — when
        you ask us to destroy a recording, it is destroyed.
      </p>
      <p>
        <strong>You can delete your entire account yourself, instantly.</strong>{' '}
        The Nuke button in your account settings erases every recording, every
        transcript, every PDF, your voiceprints and the account record itself the
        moment you confirm it. There is no support ticket, no waiting period, no
        review queue and no way for us to undo it. You do not need to ask us and
        you do not need a reason.
      </p>

      <h2>Children</h2>
      <p>
        This service is not intended for anyone under {SITE.minimumAge}. We do not
        knowingly collect information from children. If you believe a child has
        created an account, email us and we will remove it.
      </p>

      <h2>Changes</h2>
      <p>
        If this policy changes materially we will update the date at the top of
        this page, and where the change affects how your recordings or
        voiceprints are handled, we will notify you by email.
      </p>
    </LegalPage>
  )
}

/* ------------------------------------------------------------------ terms */
export function TermsPage() {
  return (
    <LegalPage title="Terms of Service"
               subtitle="The agreement between you and this service. Please read section 3.">
      <h2>1. Accepting these terms</h2>
      <p>
        By creating an account or using {SITE.name}, you agree to these terms. If
        you do not agree, do not use the service. If you use it on behalf of an
        organisation, you confirm you are authorised to bind that organisation.
      </p>

      <h2>2. Who may use it</h2>
      <p>
        You must be at least {SITE.minimumAge} years old. You are responsible for
        everything done through your account, so keep your credentials to
        yourself and tell us promptly if you believe someone else has access.
      </p>

      <h2>3. Your recordings, your responsibility</h2>
      <p>
        This is the most important section in this document.
      </p>
      <p>
        <strong>Laws about recording conversations vary widely.</strong> Some
        jurisdictions permit a recording if one participant consents; others
        require every participant to consent; others regulate recording in
        particular places or circumstances. Penalties can be criminal as well as
        civil.
      </p>
      <p>
        <strong>You alone are responsible</strong> for determining which laws
        apply to each recording you upload and for complying with them. By
        uploading or recording any content, you represent and warrant that:
      </p>
      <ul>
        <li>you made or lawfully obtained the recording;</li>
        <li>you had every consent, permission or legal authority required where
          the recording was made, and from every person recorded;</li>
        <li>you have the right to have that recording transcribed, translated and
          stored by this service; and</li>
        <li>doing so does not violate any law, contract, court order or duty of
          confidentiality you are subject to.</li>
      </ul>
      <p>
        We do not review recordings before processing them and we cannot verify
        any of the above. We are not the maker of your recordings and we do not
        determine why they exist.
      </p>

      <h2>4. Voice recognition and biometric information</h2>
      <p>
        When you assign a name to a speaker, the service stores a{' '}
        <strong>voiceprint</strong> — a numeric representation of that
        speaker&rsquo;s vocal characteristics — so the same person can be
        recognised in your later recordings. Depending on where you and the
        speaker are located, a voiceprint may constitute{' '}
        <strong>biometric information</strong> under laws that regulate it
        specifically.
      </p>
      <p>
        By naming a voice, you represent and warrant that you have obtained any
        consent or provided any notice required by applicable law from the person
        whose voice it is. <strong>Do not name a voice belonging to someone who
        has not agreed to it.</strong>
      </p>
      <p>
        Voiceprints are stored only for your own account, are never shared with
        other users or third parties, and are deleted when you delete them, when
        you use the Nuke function, or when your account is deleted. Further detail
        is in the <Link to="/privacy">Privacy Policy</Link>.
      </p>

      <h2>5. Prohibited uses</h2>
      <p>You must not use {SITE.name} to:</p>
      <ul>
        <li>upload a recording made unlawfully, or without a consent the law
          required;</li>
        <li>process content that sexualises, endangers or exploits a minor;</li>
        <li>harass, stalk, threaten, defame or surveil any person, including a
          partner, family member, employee or housemate;</li>
        <li>process content you have no right to copy or handle, including
          material subject to another party&rsquo;s copyright or confidentiality
          obligations;</li>
        <li>attempt to identify a person from a recording for an unlawful purpose;
          or</li>
        <li>circumvent usage limits, automate bulk submission, resell access, or
          interfere with the operation of the service.</li>
      </ul>

      <h2>6. Your content and ownership</h2>
      <p>
        You keep all rights in the recordings you upload and the transcripts
        produced from them. You grant us only the limited, revocable licence
        necessary to store, process, translate and display that content back to
        you in order to operate the service. We claim no ownership, we do not use
        your content to train machine-learning models, and we do not sell it or
        disclose it except as described in the Privacy Policy or as required by
        law.
      </p>

      <h2>7. Accuracy — transcripts are not records</h2>
      <p>
        Automatic speech recognition, translation and speaker identification all
        make mistakes. Accuracy varies with audio quality, accents, crosstalk,
        background noise, technical vocabulary and language. Speaker labels and
        voice matches are <strong>probabilistic estimates, not identifications</strong>.
        Translations are machine-generated.
      </p>
      <p>
        <strong>Output from this service is not a certified, verbatim or legally
        authoritative record.</strong> Do not rely on a transcript, translation,
        summary or speaker label for any legal, medical, financial, employment,
        journalistic or safety-critical purpose without verifying it against the
        original audio yourself.
      </p>

      <h2>8. Availability and your own backups</h2>
      <p>
        The service is provided on a best-effort basis and may be unavailable,
        interrupted or discontinued at any time. Deletion is permanent and
        irreversible — the Nuke function in particular destroys content with no
        archive or backup from which it can be restored.{' '}
        <strong>Keep your own copies of anything you cannot afford to lose.</strong>
      </p>

      <h2>9. Disclaimer of warranties</h2>
      <p>
        To the fullest extent permitted by law, {SITE.name} is provided{' '}
        <strong>&ldquo;as is&rdquo; and &ldquo;as available&rdquo;</strong>,
        without warranties of any kind, express or implied, including any implied
        warranties of merchantability, fitness for a particular purpose, accuracy
        and non-infringement. No advice or information obtained from the service
        creates any warranty not expressly stated here.
      </p>

      <h2>10. Limitation of liability</h2>
      <p>
        To the fullest extent permitted by law, neither the operator nor any
        contributor will be liable for any indirect, incidental, special,
        consequential, punitive or exemplary damages, or for any loss of profits,
        data, goodwill or business, arising out of or relating to your use of or
        inability to use the service — including any claim arising from a
        recording you uploaded, an inaccurate transcript, translation or speaker
        label, or the permanent deletion of content.
      </p>
      <p>
        This service is provided free of charge. To the fullest extent permitted
        by law, the operator&rsquo;s total aggregate liability arising out of or
        relating to these terms or the service will not exceed one hundred US
        dollars (US$100).
      </p>

      <h2>11. Indemnification</h2>
      <p>
        You agree to indemnify, defend and hold harmless the operator of{' '}
        {SITE.name} from and against any claim, demand, proceeding, loss,
        liability, damage, cost or expense (including reasonable legal fees)
        arising out of or relating to: (a) content you uploaded, recorded, named
        or processed; (b) your breach of these terms or of any representation or
        warranty you made in them; (c) your violation of any law or of the rights
        of any third party, including privacy, publicity, biometric, wiretapping,
        eavesdropping, confidentiality and intellectual-property rights; or (d)
        any dispute between you and a person appearing in one of your recordings.
      </p>

      <h2>12. Suspension and termination</h2>
      <p>
        We may suspend an account for a fixed period or permanently, or remove
        content, where we reasonably believe these terms or the{' '}
        <Link to="/guidelines">Community Guidelines</Link> have been breached, or
        where required by law. Where circumstances allow, we will say why.
      </p>
      <p>
        You may stop using the service at any time. You do not need to ask us to
        delete anything: the <strong>Nuke</strong> button on your dashboard erases
        your recordings, transcripts, PDFs, voiceprints and your account itself the
        moment you confirm it. The deletion is immediate, permanent and
        irreversible.
      </p>

      <h2>13. Changes to these terms</h2>
      <p>
        We may update these terms. Material changes will be reflected in the
        &ldquo;last updated&rdquo; date above, and continued use after a change
        means you accept the updated terms.
      </p>

      <h2>14. Governing law</h2>
      <p>
        These terms are governed by the laws of {SITE.jurisdiction}, without
        regard to its conflict-of-laws rules. You and the operator agree to the
        exclusive jurisdiction of the courts located there for any dispute not
        subject to another agreed process.
      </p>

      <h2>15. Severability</h2>
      <p>
        If any provision of these terms is held unenforceable, that provision will
        be limited or removed to the minimum extent necessary and the remaining
        provisions will stay in full force.
      </p>
    </LegalPage>
  )
}

/* ------------------------------------------------------------- guidelines */
export function GuidelinesPage() {
  return (
    <LegalPage title="Community Guidelines"
               subtitle="Stealth-Scribe handles people's private conversations. Treat them that way.">
      <h2>Record lawfully</h2>
      <p>
        Consent rules differ by jurisdiction — "one-party" in some places, "all-party"
        in others. Know which applies where you are and where the other people were.
        When in doubt, ask before you press record. This is the single most important
        rule here.
      </p>

      <h2>Respect the people in your recordings</h2>
      <p>
        The people in a recording usually can't see what happens to it. Don't upload
        conversations to expose, embarrass or build a case against someone who had a
        reasonable expectation of privacy. Don't publish a transcript that names people
        who never agreed to be named.
      </p>

      <h2>Never involving minors</h2>
      <p>
        Do not upload recordings of children that a parent or guardian hasn't consented
        to. Any content that sexualises a minor is reported and the account removed
        permanently, without warning.
      </p>

      <h2>Don't use Stealth-Scribe for surveillance of a partner or family member</h2>
      <p>
        Covertly recording a partner, housemate or relative to monitor them is abuse,
        it is illegal in many places, and it is not welcome here.
      </p>

      <h2>Be honest about transcripts</h2>
      <p>
        Machine transcripts contain errors. Don't present one as a verbatim record
        without saying so, and don't edit a transcript to change the meaning and then
        pass it off as automatic output.
      </p>

      <h2>Reporting</h2>
      <p>
        If you believe someone is misusing Stealth-Scribe, email{' '}
        <a href={`mailto:${SITE.legalEmail}`}>{SITE.legalEmail}</a> with as much detail
        as you can. Reports are reviewed by an administrator.
      </p>
    </LegalPage>
  )
}

/* ------------------------------------------------------------------- dmca */
export function DmcaPage() {
  return (
    <LegalPage title="Copyright &amp; DMCA Policy"
               subtitle="How to report infringing material, and how to dispute a removal.">
      <p>
        Stealth-Scribe respects copyright and responds to valid notices under the Digital
        Millennium Copyright Act. Recordings are private to their uploader by default
        and are not published, but if you believe material stored here infringes your
        copyright, you can tell us.
      </p>

      <h2>Filing a notice</h2>
      <p>
        Send the following to our designated agent at{' '}
        <a href={`mailto:${SITE.dmcaEmail}`}>{SITE.dmcaEmail}</a>:
      </p>
      <ol>
        <li>Your physical or electronic signature</li>
        <li>Identification of the copyrighted work you claim has been infringed</li>
        <li>Identification of the material claimed to be infringing, with enough detail
          for us to locate it</li>
        <li>Your address, telephone number and email address</li>
        <li>A statement that you have a good-faith belief the use is not authorised by
          the copyright owner, its agent, or the law</li>
        <li>A statement, under penalty of perjury, that the information in your notice
          is accurate and that you are the copyright owner or authorised to act on
          their behalf</li>
      </ol>

      <h2>What we do</h2>
      <p>
        On receiving a valid notice we remove or disable access to the material and
        notify the account holder. Accounts that repeatedly infringe are terminated.
      </p>

      <h2>Counter-notice</h2>
      <p>
        If you believe your material was removed by mistake or misidentification, send
        a counter-notice to the same address including your signature, identification
        of the removed material and where it appeared, a statement under penalty of
        perjury that you have a good-faith belief it was removed in error, and your
        consent to the jurisdiction of the federal court for your district.
      </p>

      <h2>Misuse</h2>
      <p>
        Knowingly filing a false notice carries liability for damages under 17 U.S.C.
        &sect; 512(f). Please be sure before you file.
      </p>
    </LegalPage>
  )
}

/* ---------------------------------------------------------------- contact */
export function ContactPage() {
  const [form, setForm] = useState({ name: '', email: '', subject: '', message: '' })
  const [state, setState] = useState({ busy: false, sent: false, error: '' })

  const submit = async (e) => {
    e.preventDefault()
    setState({ busy: true, sent: false, error: '' })
    try {
      await api.contact(form)
      setState({ busy: false, sent: true, error: '' })
    } catch (err) {
      setState({ busy: false, sent: false, error: err.message })
    }
  }

  return (
    <LegalPage title="Contact us"
               subtitle="Questions, bug reports, account problems, legal notices.">
      <div className="contact-grid">
        <div>
          <h2>Email directly</h2>
          <ul className="contact-list">
            <li>General &amp; support: <a href={`mailto:${SITE.contactEmail}`}>{SITE.contactEmail}</a></li>
            <li>Legal &amp; privacy: <a href={`mailto:${SITE.legalEmail}`}>{SITE.legalEmail}</a></li>
            <li>Copyright / DMCA: <a href={`mailto:${SITE.dmcaEmail}`}>{SITE.dmcaEmail}</a></li>
          </ul>
          <p className="muted small">
            We read everything. Account and abuse reports get looked at first.
          </p>
        </div>

        <div>
          <h2>Or send a message</h2>
          {state.sent ? (
            <div className="notice">Thanks — your message is on its way. We'll reply by email.</div>
          ) : (
            <form onSubmit={submit} className="auth-form">
              <div className="two-col">
                <label>Name
                  <input value={form.name}
                         onChange={(e) => setForm({ ...form, name: e.target.value })} />
                </label>
                <label>Email
                  <input type="email" required value={form.email}
                         onChange={(e) => setForm({ ...form, email: e.target.value })} />
                </label>
              </div>
              <label>Subject
                <input value={form.subject}
                       onChange={(e) => setForm({ ...form, subject: e.target.value })} />
              </label>
              <label>Message
                <textarea rows={6} required value={form.message}
                          onChange={(e) => setForm({ ...form, message: e.target.value })} />
              </label>
              {state.error && <div className="rec-error">{state.error}</div>}
              <button className="btn" disabled={state.busy}>
                {state.busy ? 'Sending...' : 'Send message'}
              </button>
            </form>
          )}
        </div>
      </div>
    </LegalPage>
  )
}

/* -------------------------------------------------------------- changelog */
export function ChangelogPage() {
  return (
    <LegalPage title="Changelog" subtitle="What's shipped, newest first.">
      {VERSION_HISTORY.map((entry) => (
        <div className="changelog-entry" key={entry.version}>
          <h2>v{entry.version} <span className="muted small">{entry.date}</span></h2>
          <ul>{entry.changes.map((c, i) => <li key={i}>{c}</li>)}</ul>
        </div>
      ))}
    </LegalPage>
  )
}
