import type { Candidate } from '../../api/types'
import { candidateStructureId, useStructures } from '../../state/structuresStore'
import { DirAuto, LtrIsolate } from '../ui/TextDirection'
import { ExportButtons } from './ExportButtons'
import { ModificationsList } from './ModificationsList'
import { SequenceView } from './SequenceView'

interface CandidateCardProps {
  candidate: Candidate
  /** Hide the Structures shortcut (e.g. when already inside the expanded Structures view). */
  showViewInStructures?: boolean
}

function formatPercent(value: number | null): string {
  if (value === null) return '—'
  return `${Math.round(value * 100)}%`
}

export function CandidateCard({
  candidate,
  showViewInStructures = true,
}: CandidateCardProps) {
  const { viewInStructures } = useStructures()
  const canViewStructure =
    Boolean(candidate.structure.available && candidate.structure.structure_id) ||
    Boolean(candidate.sequence)

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm transition-colors duration-150 dark:border-slate-700 dark:bg-slate-800">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
          {candidate.origin}
        </span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
          {candidate.method}
        </span>
        {candidate.warnings.map((warning) => (
          <span
            key={warning}
            className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-950 dark:text-amber-300"
          >
            {warning}
          </span>
        ))}
      </div>

      {candidate.parent && (
        <DirAuto as="div" className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
          Parent:{' '}
          <span className="font-medium text-slate-700 dark:text-slate-200">
            {candidate.parent.protein_name ?? candidate.parent.accession ?? 'unknown'}
          </span>
          {candidate.parent.accession && (
            <LtrIsolate className="ml-1 font-mono text-[11px]">
              ({candidate.parent.accession})
            </LtrIsolate>
          )}
          {candidate.identity_to_parent !== null && (
            <LtrIsolate className="ml-2">
              identity: {formatPercent(candidate.identity_to_parent)}
            </LtrIsolate>
          )}
        </DirAuto>
      )}

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600 dark:text-slate-300">
        <LtrIsolate as="span">
          pLDDT:{' '}
          <span className="font-medium text-slate-800 dark:text-slate-100">
            {candidate.structure.mean_plddt !== null
              ? candidate.structure.mean_plddt.toFixed(1)
              : candidate.structure.available
                ? '—'
                : 'not folded'}
          </span>
        </LtrIsolate>
        {candidate.esm1v_score !== null && (
          <LtrIsolate as="span">
            ESM-1v:{' '}
            <span className="font-medium text-slate-800 dark:text-slate-100">{candidate.esm1v_score.toFixed(2)}</span>
          </LtrIsolate>
        )}
        {showViewInStructures && canViewStructure && (
          <button
            type="button"
            onClick={() => viewInStructures(candidateStructureId(candidate.sequence))}
            className="text-indigo-600 hover:underline dark:text-indigo-400"
          >
            View in Structures
          </button>
        )}
      </div>

      {candidate.explanation && (
        <DirAuto as="p" className="mt-2 text-xs italic text-slate-500 dark:text-slate-400">
          {candidate.explanation}
        </DirAuto>
      )}

      <div className="mt-2">
        <SequenceView sequence={candidate.sequence} modifications={candidate.modifications} />
        <ModificationsList modifications={candidate.modifications} />
        <ExportButtons candidate={candidate} />
      </div>
    </div>
  )
}
