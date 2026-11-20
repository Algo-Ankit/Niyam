import { motion, type Variants } from 'motion/react'
import { useState } from 'react'

import {
  STATUS_INFO,
  factLabel,
  formatDate,
  formatValue,
  ruleTitle,
  shortCitation,
  splitCitations,
} from '../lib/format'
import type { Finding, Reply } from '../lib/types'
import { Sources } from './Sources'
import { Timeline } from './Timeline'

const rise: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] } },
}
const list: Variants = { hidden: {}, show: { transition: { staggerChildren: 0.08 } } }

interface Props {
  reply: Reply
  asOf: string
  sample: boolean
}

export function Results({ reply, asOf, sample }: Props) {
  const [openCitation, setOpenCitation] = useState<string | null>(null)

  function showSource(citation: string) {
    setOpenCitation(citation)
    requestAnimationFrame(() =>
      document.getElementById(sourceId(citation))?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
    )
  }

  const dated = reply.findings.filter((f) => f.opens || f.closes)
  const facts = Object.entries(reply.facts).filter(
    ([, value]) => value !== null && !(Array.isArray(value) && value.length === 0),
  )

  return (
    <motion.section className="results" variants={list} initial="hidden" animate="show">
      {sample && (
        <motion.p variants={rise} className="sample-banner">
          Recorded answer from the live pipeline, replayed. Dates are as of {formatDate(asOf)}.
        </motion.p>
      )}

      <motion.div variants={rise} className="card answer">
        <p className="asked">You asked</p>
        <h2 className="question">{reply.question}</h2>
        {reply.explanation !== null ? (
          <p className="explanation">
            {splitCitations(reply.explanation).map((part, i) =>
              part.citation ? (
                <button key={i} className="cite" onClick={() => showSource(part.text)}>
                  {shortCitation(part.text)}
                </button>
              ) : (
                <span key={i}>{part.text}</span>
              ),
            )}
          </p>
        ) : (
          <div className="withheld">
            <strong>Explanation withheld.</strong> The written answer was hidden because it{' '}
            {reply.withheld_reason}. The dates below come from the rules engine and are still
            reliable.
          </div>
        )}
        {reply.rerank_failed && (
          <p className="muted small">Ranking failed, so sources are shown in search order.</p>
        )}
      </motion.div>

      {dated.length > 0 && (
        <motion.div variants={rise} className="card">
          <h3>Your timeline</h3>
          <Timeline findings={dated} asOf={asOf} />
        </motion.div>
      )}

      {reply.findings.length > 0 && (
        <motion.div variants={rise}>
          <h3 className="section-title">What the rules say for you</h3>
          <motion.ul className="findings" variants={list}>
            {reply.findings.map((finding) => (
              <FindingCard
                key={`${finding.rule}-${finding.citation}`}
                finding={finding}
                onCite={showSource}
              />
            ))}
          </motion.ul>
        </motion.div>
      )}

      <motion.div variants={rise} className="split">
        <div className="card">
          <h3>What I understood</h3>
          {facts.length === 0 ? (
            <p className="muted">No dates or facts were found in your message.</p>
          ) : (
            <dl className="facts">
              {facts.map(([name, value]) => (
                <div key={name}>
                  <dt>{factLabel(name)}</dt>
                  <dd>{formatValue(value)}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
        {reply.missing.length > 0 && (
          <div className="card">
            <h3>Tell me these to compute more</h3>
            <ul className="missing">
              {reply.missing.map((name) => (
                <li key={name}>{factLabel(name)}</li>
              ))}
            </ul>
          </div>
        )}
      </motion.div>

      {reply.out_of_scope.length > 0 && (
        <motion.div variants={rise} className="card notice warn">
          <h3>Outside what Niyam covers</h3>
          <p>{reply.out_of_scope.join(', ')}.</p>
          <p className="muted">{reply.not_covered}</p>
        </motion.div>
      )}

      <motion.div variants={rise}>
        <Sources
          provisions={reply.provisions}
          open={openCitation}
          onToggle={(c) => setOpenCitation((prev) => (prev === c ? null : c))}
          idFor={sourceId}
        />
      </motion.div>

      <motion.p variants={rise} className="disclaimer">
        {reply.disclaimer}
      </motion.p>
    </motion.section>
  )
}

function FindingCard({ finding, onCite }: { finding: Finding; onCite: (c: string) => void }) {
  const status = STATUS_INFO[finding.status]
  return (
    <motion.li className={`card finding tone-${status.tone}`} variants={rise} layout>
      <div className="finding-head">
        <h4>{ruleTitle(finding.rule)}</h4>
        <span className={`pill tone-${status.tone}`}>{status.label}</span>
      </div>
      <p>{finding.summary}</p>
      {finding.assumptions.length > 0 && (
        <details className="assumptions">
          <summary>
            {finding.assumptions.length} assumption{finding.assumptions.length === 1 ? '' : 's'}{' '}
            where the regulation is silent
          </summary>
          <ul>
            {finding.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </details>
      )}
      <button className="cite" onClick={() => onCite(finding.citation)}>
        {shortCitation(finding.citation)}
      </button>
    </motion.li>
  )
}

function sourceId(citation: string): string {
  return `src-${citation.replace(/[^a-zA-Z0-9]+/g, '-')}`
}
