/** Slow-drifting colour fields behind the page; static when the user prefers reduced motion. */
export function Backdrop() {
  return (
    <div className="backdrop" aria-hidden="true">
      <div className="orb orb-a" />
      <div className="orb orb-b" />
      <div className="orb orb-c" />
      <div className="grain" />
    </div>
  )
}
