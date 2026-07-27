import {
  MAX_OVERLAY_STRUCTURES,
  OVERLAY_LEGEND_COLORS,
  useStructures,
} from '../../state/structuresStore'
import { DirAuto } from '../ui/TextDirection'
import { StructureCatalogList } from './StructureCatalogList'
import { StructureViewer } from './StructureViewer'

export function StructuresPanel() {
  const {
    catalog,
    selectedIds,
    foldById,
    clearSelection,
    overlayStructureIds,
    colorIndexById,
    expandStructures,
  } = useStructures()

  const anyFolding = selectedIds.some((id) => foldById[id]?.status === 'loading')
  const canExpand = selectedIds.length > 0

  return (
    <section className="flex h-full flex-col overflow-hidden">
      <div className="protdap-right-section flex shrink-0 items-center justify-between gap-2 border-b border-slate-200 bg-white px-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Structures ({selectedIds.length}/{MAX_OVERLAY_STRUCTURES})
        </h2>
        <div className="flex items-center gap-2">
          {selectedIds.length > 0 && (
            <button
              type="button"
              onClick={clearSelection}
              className="text-[11px] text-slate-500 hover:text-slate-800 hover:underline"
            >
              Clear
            </button>
          )}
          <button
            type="button"
            onClick={expandStructures}
            disabled={!canExpand}
            title={canExpand ? 'Expand structures view' : 'Select at least one structure first'}
            className="rounded-md bg-indigo-600 px-2 py-1 text-[11px] font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
          >
            Expand
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <div className="shrink-0 space-y-1 border-b border-slate-100 p-3">
          <StructureViewer structureIds={overlayStructureIds} heightClassName="h-64" />
          {anyFolding && (
            <p className="text-[11px] text-slate-500">Folding selected sequence(s)… (~30s each)</p>
          )}
          {selectedIds.length > 0 && (
            <ul className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
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
                    <DirAuto as="span" className="max-w-[10rem] truncate" title={item.label}>
                      {item.label}
                    </DirAuto>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <StructureCatalogList />
        </div>
      </div>
    </section>
  )
}
