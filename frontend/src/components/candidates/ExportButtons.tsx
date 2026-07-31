import { useState } from 'react'
import { getStructureUrl } from '../../api/client'
import type { Candidate } from '../../api/types'

interface ExportButtonsProps {
  candidate: Candidate
}

function downloadBlob(filename: string, content: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

const buttonClass =
  'rounded border border-slate-200 px-2 py-1 text-slate-600 transition-colors duration-150 hover:bg-slate-50 hover:text-slate-800 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-slate-100'

export function ExportButtons({ candidate }: ExportButtonsProps) {
  const [copied, setCopied] = useState(false)
  const fastaId = candidate.structure.structure_id ?? candidate.parent?.accession ?? 'candidate'

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(candidate.sequence)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard API can be unavailable (permissions/insecure context) -
      // silently ignore rather than showing an intrusive error for a
      // non-critical convenience feature.
    }
  }

  function handleDownloadFasta() {
    downloadBlob(`${fastaId}.fasta`, `>${fastaId}\n${candidate.sequence}\n`, 'text/plain')
  }

  return (
    <div className="mt-2 flex flex-wrap gap-2 text-xs">
      <button type="button" onClick={handleCopy} className={buttonClass}>
        {copied ? 'Copied!' : 'Copy sequence'}
      </button>
      <button type="button" onClick={handleDownloadFasta} className={buttonClass}>
        Download FASTA
      </button>
      {candidate.structure.available && candidate.structure.structure_id && (
        <a
          href={getStructureUrl(candidate.structure.structure_id)}
          download={`${fastaId}.pdb`}
          className={buttonClass}
        >
          Download PDB
        </a>
      )}
    </div>
  )
}
