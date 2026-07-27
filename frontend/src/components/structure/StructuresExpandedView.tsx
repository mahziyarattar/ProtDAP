import { useMemo } from 'react'
import { useConversation } from '../../state/conversationStore'
import {
  MAX_OVERLAY_STRUCTURES,
  OVERLAY_LEGEND_COLORS,
  useStructures,
} from '../../state/structuresStore'
import { CandidateCard } from '../candidates/CandidateCard'
import { ProteinCard } from '../proteins/ProteinCard'
import { DirAuto } from '../ui/TextDirection'
import { StructureCatalogList } from './StructureCatalogList'
import { StructureViewer } from './StructureViewer'

export function StructuresExpandedView() {
  const {
    catalog,
    selectedIds,
    foldById,
    clearSelection,
    collapseStructures,
    overlayStructureIds,
    colorIndexById,
  } = useStructures()
  const { allRetrievedProteins, allCandidates } = useConversation()

  const anyFolding = selectedIds.some((id) => foldById[id]?.status === 'loading')

  const selectedCards = useMemo(() => {
    const proteinByAccession = new Map(
      allRetrievedProteins.map((protein) => [protein.accession, protein]),
    )
    const candidateBySequence = new Map(
      allCandidates.map((candidate) => [candidate.sequence, candidate]),
    )
    const usedAccessions = new Set(
      allCandidates
        .map((candidate) => candidate.parent?.accession)
        .filter((accession): accession is string => Boolean(accession)),
    )

    return selectedIds
      .map((id) => {
        if (id.startsWith('protein:')) {
          const accession = id.slice('protein:'.length)
          const protein = proteinByAccession.get(accession)
          if (!protein) return null
          return {
            id,
            kind: 'protein' as const,
            protein,
            usedAsParent: usedAccessions.has(accession),
          }
        }
        if (id.startsWith('candidate:')) {
          const sequence = id.slice('candidate:'.length)
          const candidate = candidateBySequence.get(sequence)
          if (!candidate) return null
          return { id, kind: 'candidate' as const, candidate }
        }
        return null
      })
      .filter((entry): entry is NonNullable<typeof entry> => entry !== null)
  }, [selectedIds, allRetrievedProteins, allCandidates])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-white">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-4 py-2.5">
        <div>
          <h1 className="text-sm font-semibold text-slate-800">Structures</h1>
          <p className="text-[11px] text-slate-500">
            {selectedIds.length}/{MAX_OVERLAY_STRUCTURES} selected · Esc or Collapse to exit
          </p>
        </div>
        <div className="flex items-center gap-3">
          {selectedIds.length > 0 && (
            <button
              type="button"
              onClick={clearSelection}
              className="text-xs text-slate-500 hover:text-slate-800 hover:underline"
            >
              Clear
            </button>
          )}
          <button
            type="button"
            onClick={collapseStructures}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700"
          >
            Collapse
          </button>
        </div>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[380px_1fr]">
        <aside className="flex min-h-0 flex-col border-r border-slate-200 bg-slate-50">
          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
            <section>
              <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Selected ({selectedCards.length})
              </h2>
              {selectedCards.length === 0 ? (
                <p className="text-xs text-slate-400">Select items below to overlay them.</p>
              ) : (
                <div className="space-y-2">
                  {selectedCards.map((entry) =>
                    entry.kind === 'protein' ? (
                      <ProteinCard
                        key={entry.id}
                        protein={entry.protein}
                        usedAsParent={entry.usedAsParent}
                        showViewInStructures={false}
                      />
                    ) : (
                      <CandidateCard
                        key={entry.id}
                        candidate={entry.candidate}
                        showViewInStructures={false}
                      />
                    ),
                  )}
                </div>
              )}
            </section>

            <section>
              <h2 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                Selection catalog
              </h2>
              <StructureCatalogList />
            </section>
          </div>
        </aside>

        <main className="flex min-h-0 flex-col p-3">
          <div className="min-h-0 flex-1">
            <StructureViewer
              structureIds={overlayStructureIds}
              heightClassName="h-full"
              className="h-full"
            />
          </div>
          {anyFolding && (
            <p className="mt-2 shrink-0 text-[11px] text-slate-500">
              Folding selected sequence(s)… (~30s each)
            </p>
          )}
          {selectedIds.length > 0 && (
            <ul className="mt-2 flex shrink-0 flex-wrap gap-x-3 gap-y-1">
              {selectedIds.map((id) => {
                const item = catalog.find((entry) => entry.id === id)
                if (!item) return null
                const color = OVERLAY_LEGEND_COLORS[colorIndexById[id] ?? 0]
                return (
                  <li key={id} className="flex items-center gap-1.5 text-[11px] text-slate-600">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-sm"
                      style={{ backgroundColor: color }}
                      aria-hidden
                    />
                    <DirAuto as="span" className="max-w-[12rem] truncate" title={item.label}>
                      {item.label}
                    </DirAuto>
                  </li>
                )
              })}
            </ul>
          )}
        </main>
      </div>
    </div>
  )
}
