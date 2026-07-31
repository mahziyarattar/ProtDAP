import {
  MAX_OVERLAY_STRUCTURES,
  useStructures,
  type StructureCatalogItem,
} from '../../state/structuresStore'
import { useConversation } from '../../state/conversationStore'
import { DirAuto, LtrIsolate } from '../ui/TextDirection'

function statusLabel(item: StructureCatalogItem, foldStatus: string | undefined): string {
  if (item.knownStructureId || foldStatus === 'ready') return 'ready'
  if (foldStatus === 'loading') return 'folding…'
  if (foldStatus === 'error') return 'fold failed'
  if (!item.sequence) return 'no sequence'
  return 'not folded'
}

export function StructureCatalogList({ className }: { className?: string }) {
  const { catalog, selectedIds, foldById, toggleSelect } = useStructures()
  const { allHighlightedAccessions } = useConversation()
  const dimInactive = allHighlightedAccessions.length > 0
  const atCap = selectedIds.length >= MAX_OVERLAY_STRUCTURES
  const proteins = catalog.filter((item) => item.kind === 'protein')
  const candidates = catalog.filter((item) => item.kind === 'candidate')

  if (catalog.length === 0) {
    return (
      <p className={`text-xs text-slate-400 dark:text-slate-500 ${className ?? ''}`}>
        Retrieved proteins and candidates from the conversation will appear here for overlay
        selection.
      </p>
    )
  }

  return (
    <div className={`space-y-3 ${className ?? ''}`}>
      {atCap && (
        <p className="text-[11px] text-amber-700 dark:text-amber-400">
          Overlay limit reached ({MAX_OVERLAY_STRUCTURES}). Uncheck one to add another.
        </p>
      )}
      <CatalogGroup
        title="Retrieved proteins"
        items={proteins}
        selectedIds={selectedIds}
        foldById={foldById}
        atCap={atCap}
        dimInactive={dimInactive}
        onToggle={toggleSelect}
      />
      <CatalogGroup
        title="Candidates"
        items={candidates}
        selectedIds={selectedIds}
        foldById={foldById}
        atCap={atCap}
        dimInactive={false}
        onToggle={toggleSelect}
      />
    </div>
  )
}

function CatalogGroup({
  title,
  items,
  selectedIds,
  foldById,
  atCap,
  dimInactive,
  onToggle,
}: {
  title: string
  items: StructureCatalogItem[]
  selectedIds: string[]
  foldById: ReturnType<typeof useStructures>['foldById']
  atCap: boolean
  dimInactive: boolean
  onToggle: (id: string) => void
}) {
  if (items.length === 0) return null

  return (
    <div>
      <h3 className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
        {title}
      </h3>
      <ul className="space-y-1">
        {items.map((item) => {
          const checked = selectedIds.includes(item.id)
          const fold = foldById[item.id]
          const disabled = !checked && atCap
          const plddt =
            fold?.structureInfo?.mean_plddt ??
            (item.knownStructureId ? item.meanPlddt : null)
          const recommended = Boolean(item.recommended)
          const dimmed = dimInactive && !recommended

          return (
            <li key={item.id}>
              <label
                className={`flex cursor-pointer items-start gap-2 rounded-md border px-2 py-1.5 text-xs transition-colors duration-150 ${
                  checked
                    ? 'border-indigo-200 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-950/50'
                    : recommended
                      ? 'border-indigo-300 bg-white dark:border-indigo-600 dark:bg-slate-800'
                      : 'border-slate-200 bg-white hover:border-slate-300 dark:border-slate-700 dark:bg-slate-800 dark:hover:border-slate-600'
                } ${dimmed ? 'opacity-45' : ''} ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}
              >
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={checked}
                  disabled={disabled}
                  onChange={() => onToggle(item.id)}
                />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <DirAuto as="span" className="truncate font-medium text-slate-800 dark:text-slate-100">
                      {item.label}
                    </DirAuto>
                    {recommended && (
                      <span className="shrink-0 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                        Recommended
                      </span>
                    )}
                    {item.usedAsParent && (
                      <span className="shrink-0 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[9px] font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                        Used
                      </span>
                    )}
                  </span>
                  <span className="mt-0.5 flex flex-wrap gap-x-2 text-[10px] text-slate-500 dark:text-slate-400">
                    {item.subtitle && (
                      <LtrIsolate className="font-mono">{item.subtitle}</LtrIsolate>
                    )}
                    <span>{statusLabel(item, fold?.status)}</span>
                    {plddt != null && (
                      <LtrIsolate as="span">pLDDT {plddt.toFixed(1)}</LtrIsolate>
                    )}
                  </span>
                  {fold?.status === 'error' && fold.error && (
                    <DirAuto as="span" className="mt-0.5 block text-[10px] text-red-600 dark:text-red-400">
                      {fold.error}
                    </DirAuto>
                  )}
                </span>
              </label>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
