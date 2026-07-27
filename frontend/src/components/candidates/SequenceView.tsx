import type { Modification } from '../../api/types'

interface SequenceViewProps {
  sequence: string
  modifications: Modification[]
}

interface Segment {
  text: string
  modification?: Modification
}

function buildSegments(sequence: string, modifications: Modification[]): Segment[] {
  // `position` is 1-indexed and computed in code from the flanking-context
  // match (see app/tools/generation.py::_apply_modifications), so it's
  // trustworthy - but still guard against out-of-range values defensively.
  const sorted = [...modifications]
    .filter((mod) => mod.position >= 1 && mod.position <= sequence.length)
    .sort((a, b) => a.position - b.position)

  const segments: Segment[] = []
  let cursor = 0

  for (const mod of sorted) {
    const index = mod.position - 1
    if (index < cursor) continue // overlapping/duplicate position, skip rather than corrupt ordering

    if (index > cursor) {
      segments.push({ text: sequence.slice(cursor, index) })
    }
    segments.push({ text: sequence[index], modification: mod })
    cursor = index + 1
  }

  if (cursor < sequence.length) {
    segments.push({ text: sequence.slice(cursor) })
  }

  return segments
}

export function SequenceView({ sequence, modifications }: SequenceViewProps) {
  const segments = buildSegments(sequence, modifications)

  return (
    <p dir="ltr" className="sequence-mono ltr-isolate rounded bg-slate-50 p-2 text-[11px] text-slate-700">
      {segments.map((segment, index) =>
        segment.modification ? (
          <mark
            key={index}
            title={`${segment.modification.original}${segment.modification.position}${segment.modification.new}${
              segment.modification.reason ? `: ${segment.modification.reason}` : ''
            }`}
            className="cursor-help rounded bg-amber-200 px-0.5 text-amber-900"
          >
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </p>
  )
}
