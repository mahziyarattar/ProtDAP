import type { ProteinHit } from '../../api/types'

interface ProteinCardProps {
  protein: ProteinHit
}

const FUNCTION_PREVIEW_LENGTH = 160

export function ProteinCard({ protein }: ProteinCardProps) {
  const functionText = protein.function ?? ''
  const isLongFunction = functionText.length > FUNCTION_PREVIEW_LENGTH

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
    </div>
  )
}
