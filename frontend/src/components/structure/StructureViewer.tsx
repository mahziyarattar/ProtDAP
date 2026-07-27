import { useEffect, useRef, useState } from 'react'
import { getStructureUrl } from '../../api/client'

// Mol*'s npm package only ships a prebuilt viewer bundle (a global script
// that assigns `window.molstar`, not an ES module - see
// node_modules/molstar/build/viewer/molstar.js), so it can't be `import`ed
// through Vite like a normal dependency. scripts/copy-molstar-assets.mjs
// copies that prebuilt bundle into public/molstar-viewer at dev/build time,
// and this component loads it via a plain <script>/<link> tag, mirroring
// Mol*'s own documented "embedded" usage (see
// node_modules/molstar/build/viewer/embedded.html).
//
// Calling loadStructureFromUrl repeatedly on the same Viewer instance adds
// each PDB as another model in the same scene (overlay / as-is coordinates;
// no superposition is attempted).

interface MolstarViewerInstance {
  loadStructureFromUrl: (
    url: string,
    format: string,
    isBinary: boolean,
  ) => Promise<unknown>
}

declare global {
  interface Window {
    molstar?: {
      Viewer: {
        create: (
          target: HTMLElement | string,
          options?: Record<string, unknown>,
        ) => Promise<MolstarViewerInstance>
      }
    }
  }
}

let assetsLoadPromise: Promise<void> | null = null

function loadMolstarAssets(): Promise<void> {
  if (window.molstar) return Promise.resolve()
  if (assetsLoadPromise) return assetsLoadPromise

  assetsLoadPromise = new Promise((resolve, reject) => {
    if (!document.querySelector('link[data-molstar-css]')) {
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = '/molstar-viewer/molstar.css'
      link.setAttribute('data-molstar-css', 'true')
      document.head.appendChild(link)
    }

    const existingScript = document.querySelector<HTMLScriptElement>('script[data-molstar-js]')
    if (existingScript) {
      existingScript.addEventListener('load', () => resolve())
      existingScript.addEventListener('error', () =>
        reject(new Error('Failed to load the Mol* viewer script.')),
      )
      return
    }

    const script = document.createElement('script')
    script.src = '/molstar-viewer/molstar.js'
    script.setAttribute('data-molstar-js', 'true')
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Failed to load the Mol* viewer script.'))
    document.body.appendChild(script)
  })

  return assetsLoadPromise
}

interface StructureViewerProps {
  /** One or more structure_ids to load into a single Mol* scene (overlay). */
  structureIds: string[]
  className?: string
  heightClassName?: string
}

export function StructureViewer({
  structureIds,
  className,
  heightClassName = 'h-80',
}: StructureViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  // Stable key so reordering alone doesn't remount if the set is identical;
  // order still matters for sequential load, so we join in given order.
  const idsKey = structureIds.join('|')

  useEffect(() => {
    let cancelled = false
    const container = containerRef.current

    if (structureIds.length === 0) {
      setStatus('idle')
      setErrorMessage(null)
      if (container) container.innerHTML = ''
      return () => {
        cancelled = true
      }
    }

    setStatus('loading')
    setErrorMessage(null)

    loadMolstarAssets()
      .then(() => {
        if (cancelled || !container || !window.molstar) return null
        container.innerHTML = ''
        return window.molstar.Viewer.create(container, {
          layoutIsExpanded: false,
          layoutShowControls: false,
          layoutShowRemoteState: false,
          layoutShowSequence: false,
          layoutShowLog: false,
          layoutShowLeftPanel: false,
          viewportShowExpand: false,
          viewportShowSelectionMode: false,
          viewportShowAnimation: false,
        })
      })
      .then(async (viewer) => {
        if (cancelled || !viewer) return
        // Sequential loads: each call adds another model to the same scene.
        for (const structureId of structureIds) {
          if (cancelled) return
          await viewer.loadStructureFromUrl(getStructureUrl(structureId), 'pdb', false)
        }
      })
      .then(() => {
        if (!cancelled) setStatus('ready')
      })
      .catch((error: unknown) => {
        if (cancelled) return
        setStatus('error')
        setErrorMessage(error instanceof Error ? error.message : String(error))
      })

    return () => {
      cancelled = true
      // Mol*'s embedded Viewer doesn't expose a documented teardown API;
      // clearing the container is enough since this effect re-runs (and
      // re-creates a fresh viewer inside it) whenever structureIds change
      // or the component unmounts.
      if (container) container.innerHTML = ''
    }
    // idsKey captures structureIds content/order without depending on array identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey])

  return (
    <div
      className={`relative w-full overflow-hidden rounded-lg border border-slate-200 bg-slate-900 ${heightClassName} ${className ?? ''}`}
    >
      {status === 'idle' && (
        <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-xs text-slate-400">
          Select one or more structures to overlay.
        </div>
      )}
      {status === 'loading' && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-400">
          Loading structure{structureIds.length > 1 ? 's' : ''}...
        </div>
      )}
      {status === 'error' && (
        <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-xs text-red-400">
          Failed to load structure: {errorMessage}
        </div>
      )}
      <div ref={containerRef} className="h-full w-full" />
    </div>
  )
}
