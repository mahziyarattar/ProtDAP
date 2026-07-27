import { useState } from 'react'
import type { ProteinHit } from '../../api/types'
import { proteinStructureId, useStructures } from '../../state/structuresStore'
import { DirAuto, LtrIsolate } from '../ui/TextDirection'

interface ProteinCardProps {
  protein: ProteinHit
  /** True when this protein is a parent of at least one proposed candidate. */
  usedAsParent?: boolean
  /** Hide the Structures shortcut (e.g. when already inside the expanded Structures view). */
  showViewInStructures?: boolean
}

const FUNCTION_PREVIEW_LENGTH = 160

export function ProteinCard({
  protein,
  usedAsParent = false,
  showViewInStructures = true,
}: ProteinCardProps) {
  const { viewInStructures } = useStructures()
  const [functionExpanded, setFunctionExpanded] = useState(false)
  const functionText = protein.function ?? ''
  const isLongFunction = functionText.length > FUNCTION_PREVIEW_LENGTH
  const shownFunction =
    isLongFunction && !functionExpanded
      ? `${functionText.slice(0, FUNCTION_PREVIEW_LENGTH)}...`
      : functionText

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <LtrIsolate className="font-mono text-xs font-semibold text-indigo-700">
            {protein.accession}
          </LtrIsolate>
          <DirAuto className="font-medium text-slate-900" as="div">
            {protein.protein_name ?? 'Unnamed protein'}
          </DirAuto>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {usedAsParent && (
            <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-medium text-indigo-700">
              Used
            </span>
          )}
          {protein.reviewed !== null && (
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                protein.reviewed
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'bg-amber-100 text-amber-700'
              }`}
            >
              {protein.reviewed ? 'Reviewed' : 'Unreviewed'}
            </span>
          )}
        </div>
      </div>

      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500">
        {protein.organism && (
          <DirAuto as="span">{protein.organism}</DirAuto>
        )}
        {protein.length !== null && (
          <LtrIsolate as="span">{protein.length} aa</LtrIsolate>
        )}
      </div>

      {functionText && (
        <DirAuto as="p" className="mt-2 text-xs text-slate-600">
          {shownFunction}
          {isLongFunction && (
            <>
              {' '}
              <button
                type="button"
                onClick={() => setFunctionExpanded((prev) => !prev)}
                className="text-indigo-600 hover:underline"
              >
                {functionExpanded ? 'less' : 'more'}
              </button>
            </>
          )}
        </DirAuto>
      )}

      {showViewInStructures && protein.sequence && (
        <div className="mt-2">
          <button
            type="button"
            onClick={() => viewInStructures(proteinStructureId(protein.accession))}
            className="text-xs text-indigo-600 hover:underline"
          >
            View in Structures
          </button>
        </div>
      )}
    </div>
  )
}
