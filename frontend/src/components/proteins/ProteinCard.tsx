import { useState } from 'react'
import { ApiError, foldSequence } from '../../api/client'
import type { ProteinHit, StructureInfo } from '../../api/types'
import { StructureViewer } from '../structure/StructureViewer'

interface ProteinCardProps {
  protein: ProteinHit
}

const FUNCTION_PREVIEW_LENGTH = 160

type FoldState = 'idle' | 'loading' | 'ready' | 'error'

export function ProteinCard({ protein }: ProteinCardProps) {
  const functionText = protein.function ?? ''
  const isLongFunction = functionText.length > FUNCTION_PREVIEW_LENGTH

  // On-demand fold state, kept purely client-side (see POST /fold in
  // app/main.py) - never sent to the backend session, never merged with
  // retrieved_proteins from a /chat response.
  const [foldState, setFoldState] = useState<FoldState>('idle')
  const [structureInfo, setStructureInfo] = useState<StructureInfo | null>(null)
  const [foldError, setFoldError] = useState<string | null>(null)
  const [showStructure, setShowStructure] = useState(false)

  async function handleFoldClick() {
    if (foldState === 'ready') {
      setShowStructure((prev) => !prev)
      return
    }
    if (!protein.sequence || foldState === 'loading') return

    setFoldState('loading')
    setFoldError(null)
    try {
      const result = await foldSequence(protein.sequence, protein.accession)
      setStructureInfo(result)
      if (result.available && result.structure_id) {
        setFoldState('ready')
        setShowStructure(true)
      } else {
        setFoldState('error')
        setFoldError(result.model_source ?? 'Folding did not produce a structure.')
      }
    } catch (error) {
      setFoldState('error')
      setFoldError(error instanceof ApiError ? error.message : String(error))
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-xs font-semibold text-indigo-700">
            {protein.accession}
          </div>
          <div className="font-medium text-slate-900">{protein.protein_name ?? 'Unnamed protein'}</div>
        </div>
        {protein.reviewed !== null && (
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
              protein.reviewed
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-amber-100 text-amber-700'
            }`}
          >
            {protein.reviewed ? 'Reviewed' : 'Unreviewed'}
          </span>
        )}
      </div>

      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500">
        {protein.organism && <span>{protein.organism}</span>}
        {protein.length !== null && <span>{protein.length} aa</span>}
      </div>

      {functionText && (
        <p className="mt-2 text-xs text-slate-600">
          {isLongFunction ? (
            <details>
              <summary className="cursor-pointer select-none list-none">
                {functionText.slice(0, FUNCTION_PREVIEW_LENGTH)}...{' '}
                <span className="text-indigo-600 hover:underline">more</span>
              </summary>
              <span className="mt-1 block">{functionText}</span>
            </details>
          ) : (
            functionText
          )}
        </p>
      )}

      {protein.sequence && (
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600">
          {structureInfo?.mean_plddt != null && (
            <span>
              pLDDT: <span className="font-medium text-slate-800">{structureInfo.mean_plddt.toFixed(1)}</span>
            </span>
          )}
          <button
            type="button"
            onClick={handleFoldClick}
            disabled={foldState === 'loading'}
            className="text-indigo-600 hover:underline disabled:cursor-wait disabled:text-slate-400 disabled:no-underline"
          >
            {foldState === 'idle' && 'Fold & view 3D structure'}
            {foldState === 'loading' && 'Folding… (~30s)'}
            {foldState === 'ready' && (showStructure ? 'Hide structure' : 'View 3D structure')}
            {foldState === 'error' && 'Retry fold'}
          </button>
        </div>
      )}

      {foldState === 'error' && foldError && (
        <p className="mt-1 text-xs text-red-600">{foldError}</p>
      )}

      {showStructure && structureInfo?.structure_id && (
        <div className="mt-2">
          <StructureViewer structureId={structureInfo.structure_id} />
        </div>
      )}
    </div>
  )
}
