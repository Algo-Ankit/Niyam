import type { Stage, Status } from './types'

export const STAGE_INFO: Record<Stage, { label: string; who: 'AI' | 'Code' | 'Search'; note: string }> = {
  extract: { label: 'Read', who: 'AI', note: 'Pulls your dates and facts out of your words' },
  rules: { label: 'Compute', who: 'Code', note: 'Plain code works out every date and day count' },
  retrieve: { label: 'Search', who: 'Search', note: 'Finds matching paragraphs of 8 CFR 214.2(f)' },
  rerank: { label: 'Rank', who: 'AI', note: 'Picks the paragraphs that really answer you' },
  explain: { label: 'Explain', who: 'AI', note: 'Writes a plain answer from those paragraphs only' },
  verify: { label: 'Check', who: 'Code', note: 'Hides the answer if it invents a date or source' },
}

export const STATUS_INFO: Record<Status, { label: string; tone: 'ok' | 'info' | 'warn' | 'bad' | 'mute' }> = {
  open: { label: 'Open now', tone: 'ok' },
  within_limit: { label: 'Within limit', tone: 'ok' },
  upcoming: { label: 'Upcoming', tone: 'info' },
  not_yet_open: { label: 'Not open yet', tone: 'info' },
  over_limit: { label: 'Over limit', tone: 'bad' },
  closed: { label: 'Closed', tone: 'bad' },
  passed: { label: 'Passed', tone: 'mute' },
  ended: { label: 'Ended', tone: 'mute' },
  not_applicable: { label: 'Does not apply', tone: 'mute' },
}

const RULE_TITLES: Record<string, string> = {
  opt_filing_window: 'OPT filing window',
  opt_latest_start_date: 'Latest OPT start date',
  opt_completion_limit: 'OPT must be finished by',
  unemployment_days: 'Unemployment days',
  departure_period: 'Grace period to leave or change status',
  stem_filing_window: 'STEM OPT filing window',
  stem_period: 'STEM OPT period',
  stem_12_month_evaluation: '12-month STEM evaluation',
  stem_new_employer_i983: 'New employer: new Form I-983',
  stem_report_loss_of_employment: 'Report loss of employment',
}

const FACT_LABELS: Record<string, string> = {
  program_end_date: 'Program ends',
  opt_recommendation_date: 'DSO recommended OPT',
  opt_start_date: 'OPT starts',
  opt_end_date: 'OPT ends',
  stem_degree: 'STEM degree',
  stem_recommendation_date: 'DSO recommended STEM OPT',
  on_stem_extension: 'On STEM extension',
  jobs: 'Jobs',
  h1b_petition_filed: 'H-1B petition filed',
  h1b_change_of_status: 'H-1B change of status',
  h1b_fiscal_year: 'H-1B fiscal year',
  h1b_petition_outcome: 'H-1B petition outcome',
  h1b_validity_start: 'H-1B validity starts',
  h1b_outcome_date: 'H-1B outcome date',
}

export function ruleTitle(rule: string): string {
  if (RULE_TITLES[rule]) return RULE_TITLES[rule]
  const report = /^stem_validation_report_(\d+)$/.exec(rule)
  if (report) return `STEM validation report ${report[1]}`
  return humanize(rule)
}

export function factLabel(name: string): string {
  return FACT_LABELS[name] ?? humanize(name)
}

function humanize(snake: string): string {
  const words = snake.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

const ISO = /^\d{4}-\d{2}-\d{2}$/

export function formatDate(iso: string): string {
  return toDate(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  })
}

export function toDate(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`)
}

export function isIsoDate(value: unknown): value is string {
  return typeof value === 'string' && ISO.test(value)
}

export function formatValue(value: unknown): string {
  if (isIsoDate(value)) return formatDate(value)
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.length === 0 ? 'None' : `${value.length}`
  return String(value)
}

export function formatMs(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
}

/** A countdown such as "48:12", or "3:05:09" when an hour or more is left. */
export function formatCountdown(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds))
  const pad = (n: number) => String(n).padStart(2, '0')
  const [h, m, sec] = [Math.floor(s / 3600), Math.floor((s % 3600) / 60), s % 60]
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`
}

export function localToday(): string {
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

/** Splits text into plain parts and `[8 CFR ...]` citation parts. */
export function splitCitations(text: string): { text: string; citation: boolean }[] {
  const parts: { text: string; citation: boolean }[] = []
  let last = 0
  for (const match of text.matchAll(/\[(8 CFR [^\]]+)\]/g)) {
    if (match.index > last) parts.push({ text: text.slice(last, match.index), citation: false })
    parts.push({ text: match[1] ?? '', citation: true })
    last = match.index + match[0].length
  }
  if (last < text.length) parts.push({ text: text.slice(last), citation: false })
  return parts
}

export function shortCitation(citation: string): string {
  return citation.replace(/^8 CFR 214\.2/, '§ 214.2')
}
