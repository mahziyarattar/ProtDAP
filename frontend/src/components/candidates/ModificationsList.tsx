import type { Modification } from '../../api/types'
import { DirAuto, LtrIsolate } from '../ui/TextDirection'

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
              <td className="py-0.5 pr-2 font-mono">
                <LtrIsolate>{mod.position}</LtrIsolate>
              </td>
              <td className="py-0.5 pr-2 font-mono">
                <LtrIsolate>
                  {mod.original}&rarr;{mod.new}
                </LtrIsolate>
              </td>
              <td className="py-0.5 text-slate-500">
                <DirAuto as="span">{mod.reason ?? '—'}</DirAuto>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
