interface TraceDetailsProps {
  traceSummary: string[]
}

export function TraceDetails({ traceSummary }: TraceDetailsProps) {
  if (traceSummary.length === 0) return null

  return (
    <details className="mt-2 text-xs text-slate-500">
      <summary className="cursor-pointer select-none hover:text-slate-700">
        Tool trace ({traceSummary.length} call{traceSummary.length === 1 ? '' : 's'})
      </summary>
      <ul className="mt-1 space-y-0.5 pl-4 font-mono">
        {traceSummary.map((line, index) => (
          <li key={index} className="list-disc">
            {line}
          </li>
        ))}
      </ul>
    </details>
  )
}
