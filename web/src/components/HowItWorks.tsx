import { motion } from 'motion/react'

const PRINCIPLES = [
  {
    glyph: '∑',
    title: 'The AI never does date maths',
    body: 'A language model only reads your message and writes the explanation. Every deadline and day count comes from plain code written against the regulation.',
  },
  {
    glyph: '§',
    title: 'Every rule is quoted',
    body: 'Answers come from 8 CFR 214.2(f), the F-1 student regulation. The exact paragraphs are shown so you can read them yourself.',
  },
  {
    glyph: '✓',
    title: 'Checked before you see it',
    body: 'If the written answer cites a paragraph it was not given or states a date the code did not compute, it is hidden and you see only the computed dates.',
  },
]

export function HowItWorks() {
  return (
    <section className="how" aria-labelledby="how-title">
      <motion.h2
        id="how-title"
        initial={{ opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-80px' }}
      >
        Built to be <em>wrong less often</em>
      </motion.h2>
      <div className="principles">
        {PRINCIPLES.map((p, i) => (
          <motion.article
            key={p.title}
            className="card principle"
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ duration: 0.6, delay: i * 0.12, ease: [0.22, 1, 0.36, 1] }}
            whileHover={{ y: -4 }}
          >
            <span className="glyph" aria-hidden="true">
              {p.glyph}
            </span>
            <h3>{p.title}</h3>
            <p>{p.body}</p>
          </motion.article>
        ))}
      </div>
      <motion.div
        className="card scope"
        initial={{ opacity: 0 }}
        whileInView={{ opacity: 1 }}
        viewport={{ once: true }}
      >
        <h3>What it covers, and what it doesn't</h3>
        <p>
          <strong>Covers:</strong> post-completion OPT filing and start dates, unemployment days,
          STEM OPT filing, reporting and evaluations, and the H-1B cap-gap extension for F-1
          students.
        </p>
        <p>
          <strong>Doesn't cover:</strong> the H-1B lottery or petition itself, green cards, taxes,
          visa stamping, or statuses other than F-1. For those, and for any decision about your
          status, talk to your DSO or an immigration attorney.
        </p>
      </motion.div>
    </section>
  )
}
