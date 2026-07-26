"""Sequence identity calculation used to populate `identity_to_parent`.

Uses Biopython's Bio.Align.PairwiseAligner in global (Needleman-Wunsch-style)
mode:

    identity = alignment.counts().identities / alignment.length

where `alignment.length` is the total aligned length (including gap
columns) of the best-scoring global alignment between the parent and
candidate sequences. Gap penalties are set explicitly (rather than left at
Biopython's permissive defaults) so the aligner behaves like a standard
global alignment instead of preferring free gaps over mismatches.
"""

from Bio import Align

_aligner = Align.PairwiseAligner()
_aligner.mode = "global"
_aligner.match_score = 1.0
_aligner.mismatch_score = -1.0
_aligner.open_gap_score = -10.0
_aligner.extend_gap_score = -0.5


def compute_identity(parent_sequence: str, candidate_sequence: str) -> float:
    """Return the fraction (0.0-1.0) of identical aligned positions between
    two amino-acid sequences, using a global alignment."""
    if not parent_sequence or not candidate_sequence:
        return 0.0

    alignments = _aligner.align(parent_sequence, candidate_sequence)
    best_alignment = alignments[0]
    counts = best_alignment.counts()

    if best_alignment.length == 0:
        return 0.0

    return counts.identities / best_alignment.length
