import type { Modification } from '../../api/types'

interface ModificationsListProps {
  modifications: Modification[]
}

export function ModificationsList({ modifications }: ModificationsListProps) {
  if (modifications.length === 0) return null

  return (
    <details className="mt-2 text-xs text-slate-600">
      <summary className="cursor-pointer select-none font-medium text-slate-700">
        Modifications ({modifications.length})
      </summary>
      <table className="mt-1.5 w-full border-collapse text-[11px]">
        <thead>
          <tr className="text-left text-slate-400">
            <th className="pr-2 font-normal">Pos</th>
            <th className="pr-2 font-normal">Change</th>
            <th className="font-normal">Reason</th>
          </tr>
        </thead>
        <tbody>
          {modifications.map((mod) => (
            <tr key={`${mod.position}-${mod.original}-${mod.new}`} className="align-top">
              <td className="pr-2 py-0.5 font-mono">{mod.position}</td>
              <td className="pr-2 py-0.5 font-mono">
                {mod.original}&rarr;{mod.new}
              </td>
              <td className="py-0.5 text-slate-500">{mod.reason ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
