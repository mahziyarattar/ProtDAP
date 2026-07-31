import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { ApiError, foldSequence } from '../api/client'
import type { Candidate, ProteinHit, StructureInfo } from '../api/types'
import { useConversation } from './conversationStore'
import {
  parentAccessionsFromCandidates,
  sortProteinsForPanel,
} from './proteinOrdering'

export const MAX_OVERLAY_STRUCTURES = 5

/** Legend colors only - Mol* assigns its own model colors when overlaying. */
export const OVERLAY_LEGEND_COLORS = [
  '#4f46e5',
  '#dc2626',
  '#16a34a',
  '#ca8a04',
  '#0891b2',
] as const

export type RightPanelTab = 'proteins' | 'candidates' | 'structures'
export type StructureItemKind = 'protein' | 'candidate'

export interface StructureCatalogItem {
  id: string
  kind: StructureItemKind
  label: string
  subtitle: string | null
  sequence: string | null
  /** Already known from a /chat candidate fold; proteins start without this. */
  knownStructureId: string | null
  meanPlddt: number | null
  /** True when this retrieved protein is a parent of at least one candidate. */
  usedAsParent: boolean
  /** LLM shortlist from structured final reply (proteins only). */
  recommended?: boolean
}

export type FoldStatus = 'idle' | 'loading' | 'ready' | 'error'

interface FoldEntry {
  status: FoldStatus
  structureInfo: StructureInfo | null
  error: string | null
}

interface StructuresContextValue {
  activeTab: RightPanelTab
  setActiveTab: (tab: RightPanelTab) => void
  catalog: StructureCatalogItem[]
  selectedIds: string[]
  foldById: Record<string, FoldEntry>
  toggleSelect: (id: string) => void
  /** Card shortcut: switch to Structures and add this item (if under the cap). */
  viewInStructures: (id: string) => void
  clearSelection: () => void
  /** Resolved structure_id for each selected item that is ready to display. */
  overlayStructureIds: string[]
  colorIndexById: Record<string, number>
  /** Full-window Structures mode: chat hidden, cards + big Mol* side by side. */
  isExpanded: boolean
  expandStructures: () => void
  collapseStructures: () => void
}

const StructuresContext = createContext<StructuresContextValue | null>(null)

export function proteinStructureId(accession: string): string {
  return `protein:${accession}`
}

export function candidateStructureId(sequence: string): string {
  return `candidate:${sequence}`
}

function buildCatalog(
  proteins: ProteinHit[],
  candidates: Candidate[],
  highlightedAccessions: Set<string>,
): StructureCatalogItem[] {
  const usedAccessions = parentAccessionsFromCandidates(candidates)
  const orderedProteins = sortProteinsForPanel(proteins, highlightedAccessions, usedAccessions)

  const proteinItems: StructureCatalogItem[] = orderedProteins.map((protein) => ({
    id: proteinStructureId(protein.accession),
    kind: 'protein',
    label: protein.protein_name ?? protein.accession,
    subtitle: protein.accession,
    sequence: protein.sequence,
    knownStructureId: null,
    meanPlddt: null,
    usedAsParent: usedAccessions.has(protein.accession),
    recommended: highlightedAccessions.has(protein.accession),
  }))

  const candidateItems: StructureCatalogItem[] = candidates.map((candidate, index) => {
    const parentLabel =
      candidate.parent?.protein_name ?? candidate.parent?.accession ?? 'unknown parent'
    return {
      id: candidateStructureId(candidate.sequence),
      kind: 'candidate',
      label: `Candidate ${index + 1} (${parentLabel})`,
      subtitle: candidate.origin,
      sequence: candidate.sequence,
      knownStructureId: candidate.structure.available ? candidate.structure.structure_id : null,
      meanPlddt: candidate.structure.mean_plddt,
      usedAsParent: false,
    }
  })

  return [...proteinItems, ...candidateItems]
}

export function StructuresProvider({ children }: { children: ReactNode }) {
  const { allRetrievedProteins, allCandidates, allHighlightedAccessions } = useConversation()
  const [activeTab, setActiveTab] = useState<RightPanelTab>('proteins')
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [foldById, setFoldById] = useState<Record<string, FoldEntry>>({})
  const [isExpanded, setIsExpanded] = useState(false)
  const foldByIdRef = useRef(foldById)
  foldByIdRef.current = foldById
  // Successful folds keyed by sequence so re-select (and same sequence under
  // another catalog id) reuses the structure_id without another POST /fold.
  // Tab/session memory only - not persisted. Errors are not cached here so
  // re-select retries automatically.
  const sequenceFoldCache = useRef(new Map<string, StructureInfo>())
  const inflightSequences = useRef(new Set<string>())

  const highlightedAccessions = useMemo(
    () => new Set(allHighlightedAccessions),
    [allHighlightedAccessions],
  )

  const catalog = useMemo(
    () => buildCatalog(allRetrievedProteins, allCandidates, highlightedAccessions),
    [allRetrievedProteins, allCandidates, highlightedAccessions],
  )

  const catalogById = useMemo(() => {
    const map = new Map<string, StructureCatalogItem>()
    for (const item of catalog) map.set(item.id, item)
    return map
  }, [catalog])

  // Drop selection entries that no longer exist after a conversation reset.
  useEffect(() => {
    const validIds = new Set(catalog.map((item) => item.id))
    setSelectedIds((prev) => {
      const next = prev.filter((id) => validIds.has(id))
      return next.length === prev.length ? prev : next
    })
  }, [catalog])

  const markReady = useCallback((id: string, structureInfo: StructureInfo) => {
    setFoldById((prev) => {
      const existing = prev[id]
      if (
        existing?.status === 'ready' &&
        existing.structureInfo?.structure_id === structureInfo.structure_id
      ) {
        return prev
      }
      return {
        ...prev,
        [id]: { status: 'ready', structureInfo, error: null },
      }
    })
  }, [])

  const ensureFolded = useCallback(
    async (id: string) => {
      const item = catalogById.get(id)
      if (!item) return

      const existing = foldByIdRef.current[id]
      if (existing?.status === 'ready' && existing.structureInfo?.structure_id) {
        return
      }
      if (existing?.status === 'loading') {
        return
      }

      if (item.knownStructureId) {
        const info: StructureInfo = {
          available: true,
          mean_plddt: item.meanPlddt,
          model_source: 'BioLM ESMFold',
          structure_id: item.knownStructureId,
        }
        if (item.sequence) {
          sequenceFoldCache.current.set(item.sequence, info)
        }
        markReady(id, info)
        return
      }

      if (!item.sequence) {
        setFoldById((prev) => ({
          ...prev,
          [id]: {
            status: 'error',
            structureInfo: null,
            error: 'No sequence available to fold.',
          },
        }))
        return
      }

      const sequence = item.sequence
      const cached = sequenceFoldCache.current.get(sequence)
      if (cached?.available && cached.structure_id) {
        markReady(id, cached)
        return
      }

      if (inflightSequences.current.has(sequence)) {
        // Another request for this sequence is in flight; show loading until
        // that result lands in the sequence cache (next ensureFolded / effect).
        setFoldById((prev) => {
          if (prev[id]?.status === 'loading' || prev[id]?.status === 'ready') return prev
          return {
            ...prev,
            [id]: { status: 'loading', structureInfo: null, error: null },
          }
        })
        return
      }

      inflightSequences.current.add(sequence)
      setFoldById((prev) => ({
        ...prev,
        [id]: { status: 'loading', structureInfo: null, error: null },
      }))

      try {
        const nameHint =
          item.kind === 'protein' ? (item.subtitle ?? 'protein') : `candidate_${item.label}`
        const result = await foldSequence(sequence, nameHint)
        if (result.available && result.structure_id) {
          sequenceFoldCache.current.set(sequence, result)
          markReady(id, result)
          // Any other catalog ids with the same sequence (e.g. waiting on the
          // shared in-flight request) pick up the cached result immediately.
          for (const [otherId, otherItem] of catalogById) {
            if (otherId === id) continue
            if (otherItem.sequence === sequence) {
              markReady(otherId, result)
            }
          }
        } else {
          const errorMessage =
            result.model_source ?? 'Folding did not produce a structure.'
          setFoldById((prev) => {
            const next = { ...prev }
            next[id] = {
              status: 'error',
              structureInfo: result,
              error: errorMessage,
            }
            for (const [otherId, otherItem] of catalogById) {
              if (otherId === id) continue
              if (otherItem.sequence === sequence && prev[otherId]?.status === 'loading') {
                next[otherId] = {
                  status: 'error',
                  structureInfo: result,
                  error: errorMessage,
                }
              }
            }
            return next
          })
        }
      } catch (error) {
        const errorMessage =
          error instanceof ApiError ? error.message : String(error)
        setFoldById((prev) => {
          const next = { ...prev }
          next[id] = {
            status: 'error',
            structureInfo: null,
            error: errorMessage,
          }
          for (const [otherId, otherItem] of catalogById) {
            if (otherId === id) continue
            if (otherItem.sequence === sequence && prev[otherId]?.status === 'loading') {
              next[otherId] = {
                status: 'error',
                structureInfo: null,
                error: errorMessage,
              }
            }
          }
          return next
        })
      } finally {
        inflightSequences.current.delete(sequence)
      }
    },
    [catalogById, markReady],
  )

  const addToSelection = useCallback((id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) return prev
      if (prev.length >= MAX_OVERLAY_STRUCTURES) return prev
      return [...prev, id]
    })
  }, [])

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      if (prev.includes(id)) {
        return prev.filter((selected) => selected !== id)
      }
      if (prev.length >= MAX_OVERLAY_STRUCTURES) {
        return prev
      }
      return [...prev, id]
    })
  }, [])

  const viewInStructures = useCallback(
    (id: string) => {
      setActiveTab('structures')
      addToSelection(id)
    },
    [addToSelection],
  )

  const clearSelection = useCallback(() => {
    setSelectedIds([])
    setIsExpanded(false)
  }, [])

  const expandStructures = useCallback(() => {
    if (selectedIds.length === 0) return
    setIsExpanded(true)
  }, [selectedIds])

  const collapseStructures = useCallback(() => {
    setIsExpanded(false)
  }, [])

  // Leaving expand when nothing is selected anymore keeps the UI consistent.
  useEffect(() => {
    if (selectedIds.length === 0 && isExpanded) {
      setIsExpanded(false)
    }
  }, [selectedIds, isExpanded])

  // Esc collapses the fullscreen Structures view.
  useEffect(() => {
    if (!isExpanded) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsExpanded(false)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [isExpanded])

  // Fold anything newly selected that still needs a structure_id.
  useEffect(() => {
    for (const id of selectedIds) {
      void ensureFolded(id)
    }
  }, [selectedIds, ensureFolded])

  const colorIndexById = useMemo(() => {
    const map: Record<string, number> = {}
    selectedIds.forEach((id, index) => {
      map[id] = index
    })
    return map
  }, [selectedIds])

  const overlayStructureIds = useMemo(() => {
    const ids: string[] = []
    for (const id of selectedIds) {
      const item = catalogById.get(id)
      const fold = foldById[id]
      if (fold?.status === 'error') continue
      const structureId =
        fold?.structureInfo?.structure_id ?? item?.knownStructureId ?? null
      if (structureId) ids.push(structureId)
    }
    return ids
  }, [selectedIds, foldById, catalogById])

  const value = useMemo<StructuresContextValue>(
    () => ({
      activeTab,
      setActiveTab,
      catalog,
      selectedIds,
      foldById,
      toggleSelect,
      viewInStructures,
      clearSelection,
      overlayStructureIds,
      colorIndexById,
      isExpanded,
      expandStructures,
      collapseStructures,
    }),
    [
      activeTab,
      catalog,
      selectedIds,
      foldById,
      toggleSelect,
      viewInStructures,
      clearSelection,
      overlayStructureIds,
      colorIndexById,
      isExpanded,
      expandStructures,
      collapseStructures,
    ],
  )

  return <StructuresContext.Provider value={value}>{children}</StructuresContext.Provider>
}

export function useStructures(): StructuresContextValue {
  const context = useContext(StructuresContext)
  if (!context) {
    throw new Error('useStructures must be used within a StructuresProvider')
  }
  return context
}
