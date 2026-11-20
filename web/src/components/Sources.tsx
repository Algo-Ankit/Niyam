import { AnimatePresence, motion } from 'motion/react'

import { shortCitation } from '../lib/format'
import type { Provision } from '../lib/types'

interface Props {
  provisions: Provision[]
  open: string | null
  onToggle: (citation: string) => void
  idFor: (citation: string) => string
}

/** The regulation paragraphs the answer was allowed to use, quoted in full. */
export function Sources({ provisions, open, onToggle, idFor }: Props) {
  return (
    <div className="card sources">
      <h3>Sources from 8 CFR 214.2(f)</h3>
      <p className="muted small">The only text the explanation was allowed to use.</p>
      <ul>
        {provisions.map((p) => {
          const expanded = open === p.citation
          return (
            <li key={p.citation} id={idFor(p.citation)} className={expanded ? 'open' : ''}>
              <button
                className="source-head"
                aria-expanded={expanded}
                onClick={() => onToggle(p.citation)}
              >
                <span className="source-cite">{shortCitation(p.citation)}</span>
                <span className="source-heading">{p.headings.at(-1) ?? ''}</span>
                <motion.span className="chev" animate={{ rotate: expanded ? 90 : 0 }}>
                  ›
                </motion.span>
              </button>
              <AnimatePresence initial={false}>
                {expanded && (
                  <motion.blockquote
                    className="source-body"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.3 }}
                  >
                    <p>{p.body}</p>
                  </motion.blockquote>
                )}
              </AnimatePresence>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
