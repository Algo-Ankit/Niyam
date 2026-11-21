import { formatDate } from '../lib/format'

export function Footer({ snapshot }: { snapshot: string | null }) {
  return (
    <footer className="footer">
      <p>
        <strong>Not legal advice.</strong> Niyam explains 8 CFR 214.2(f) and computes dates from
        what you tell it. Confirm every deadline with your DSO.
      </p>
      <p className="muted">
        {snapshot ? `Regulation text as of ${formatDate(snapshot)} (eCFR). ` : ''}
        Follow-up questions stay in this page only and clear on reload. No accounts.{' '}
        <a href="https://github.com/Algo-Ankit/Niyam" target="_blank" rel="noreferrer">
          Source on GitHub
        </a>
      </p>
    </footer>
  )
}
