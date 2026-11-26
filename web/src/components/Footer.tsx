import { formatDate } from '../lib/format'

const OFFICIAL_LINKS = [
  {
    label: '8 CFR 214.2(f) on eCFR',
    href: 'https://www.ecfr.gov/current/title-8/chapter-I/subchapter-B/part-214/section-214.2#p-214.2(f)',
  },
  {
    label: 'USCIS OPT Guidance',
    href: 'https://www.uscis.gov/working-in-the-united-states/students-and-exchange-visitors/optional-practical-training-opt-for-f-1-students',
  },
  {
    label: 'DHS Study in the States',
    href: 'https://studyinthestates.dhs.gov/',
  },
]

export function Footer({ snapshot }: { snapshot: string | null }) {
  return (
    <footer className="footer">
      <div className="footer-main">
        <p>
          <strong>Not legal advice.</strong> Niyam explains 8 CFR 214.2(f) and computes dates from
          what you tell it. Confirm every deadline with your DSO.
        </p>
        <p className="muted">
          {snapshot ? `Regulation text as of ${formatDate(snapshot)} (eCFR). ` : ''}
          Follow-up questions stay in this page only and clear on reload. No accounts.
        </p>
      </div>
      <nav className="footer-links" aria-label="Official F-1 resources">
        <span className="footer-links-label muted">Official references</span>
        <ul className="footer-links-list">
          {OFFICIAL_LINKS.map((link) => (
            <li key={link.href}>
              <a href={link.href} target="_blank" rel="noopener noreferrer">
                {link.label}
              </a>
            </li>
          ))}
        </ul>
      </nav>
    </footer>
  )
}
