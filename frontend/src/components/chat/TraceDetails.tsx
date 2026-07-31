interface TraceDetailsProps {
  traceSummary: string[]
}

export function TraceDetails({ traceSummary }: TraceDetailsProps) {
  if (traceSummary.length === 0) return null

  return (
    <details className="mt-2 min-w-0 max-w-full text-xs text-slate-500 dark:text-slate-400">
      <summary className="cursor-pointer select-none hover:text-slate-700 dark:hover:text-slate-300">
        Tool trace ({traceSummary.length} call{traceSummary.length === 1 ? '' : 's'})
      </summary>
      <ul className="mt-1 max-w-full list-disc space-y-0.5 overflow-x-auto pl-4 font-mono" dir="ltr">
        {traceSummary.map((line, index) => (
          <li key={index} className="break-all [overflow-wrap:anywhere]">
            {line}
          </li>
        ))}
      </ul>
    </details>
  )
}
