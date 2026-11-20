import { motion } from 'motion/react'
import type { ReactNode } from 'react'

const HEADLINE = ['Your', 'F-1', 'work', 'deadlines,']

export function Hero({ children }: { children: ReactNode }) {
  return (
    <header className="hero">
      <motion.p
        className="eyebrow"
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        <span className="mark">§</span> Niyam · OPT · STEM OPT · cap-gap
      </motion.p>
      <h1>
        {HEADLINE.map((word, i) => (
          <motion.span
            key={word}
            className="word"
            initial={{ opacity: 0, y: 24, filter: 'blur(8px)' }}
            animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
            transition={{ duration: 0.7, delay: 0.1 + i * 0.08, ease: [0.22, 1, 0.36, 1] }}
          >
            {word}
          </motion.span>
        ))}
        <motion.em
          className="word accent"
          initial={{ opacity: 0, y: 24, filter: 'blur(8px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          transition={{ duration: 0.8, delay: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          computed and cited.
        </motion.em>
      </h1>
      <motion.p
        className="lede"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.75 }}
      >
        Describe your situation in plain words. Code works out every date from 8 CFR 214.2(f), each
        rule is quoted, and the answer is checked before you see it.
      </motion.p>
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, delay: 0.9 }}
      >
        {children}
      </motion.div>
    </header>
  )
}
