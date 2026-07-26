import { useState } from 'react'
import type { Candidate } from '../../api/types'
import { StructureViewer } from '../structure/StructureViewer'
import { ExportButtons } from './ExportButtons'
import { ModificationsList } from './ModificationsList'
import { SequenceView } from './SequenceView'

interface CandidateCardProps {
  candidate: Candidate
}

function formatPercent(value: number | null): string {
  if (value === null) return '—'
  return `${Math.round(value * 100)}%`
}

export function CandidateCard({ candidate }: CandidateCardProps) {
  const [showStructure, setShowStructure] = useState(false)
  const structureId = candidate.structure.structure_id

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-medium text-indigo-700">
          {candidate.origin}
        </span>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium text-slate-600">
          {candidate.method}
        </span>
        {candidate.warnings.map((warning) => (
          <span
            key={warning}
            className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700"
          >
            {warning}
          </span>
        ))}
      </div>

      {candidate.parent && (
        <div className="mt-1.5 text-xs text-slate-500">
          Parent:{' '}
          <span className="font-medium text-slate-700">
            {candidate.parent.protein_name ?? candidate.parent.accession ?? 'unknown'}
          </span>
          {candidate.parent.accession && (
            <span className="ml-1 font-mono text-[11px]">({candidate.parent.accession})</span>
          )}
          {candidate.identity_to_parent !== null && (
            <span className="ml-2">identity: {formatPercent(candidate.identity_to_parent)}</span>
          )}
        </div>
      )}

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-600">
        <span>
          pLDDT:{' '}
          <span className="font-medium text-slate-800">
            {candidate.structure.mean_plddt !== null
              ? candidate.structure.mean_plddt.toFixed(1)
              : candidate.structure.available
                ? '—'
                : 'not folded'}
          </span>
        </span>
        {candidate.esm1v_score !== null && (
          <span>
            ESM-1v: <span className="font-medium text-slate-800">{candidate.esm1v_score.toFixed(2)}</span>
          </span>
        )}
        {candidate.structure.available && structureId && (
          <button
            type="button"
            onClick={() => setShowStructure((prev) => !prev)}
            className="text-indigo-600 hover:underline"
          >
            {showStructure ? 'Hide structure' : 'View 3D structure'}
          </button>
        )}
      </div>

      {showStructure && structureId && (
        <div className="mt-2">
          <StructureViewer structureId={structureId} />
        </div>
      )}

      {candidate.explanation && (
        <p className="mt-2 text-xs italic text-slate-500">{candidate.explanation}</p>
      )}

      <div className="mt-2">
        <SequenceView sequence={candidate.sequence} modifications={candidate.modifications} />
        <ModificationsList modifications={candidate.modifications} />
        <ExportButtons candidate={candidate} />
      </div>
    </div>
  )
}
