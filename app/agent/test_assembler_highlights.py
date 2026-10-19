"""Unit tests for recommend_proteins highlight shortlist."""

from app.agent.assembler import assemble_response, filter_highlighted_accessions
from app.models import ProteinHit


def test_filter_highlighted_intersects_retrieved():
    retrieved = [
        ProteinHit(accession="P01308", sequence="AAA"),
        ProteinHit(accession="P01315", sequence="BBB"),
    ]
    assert filter_highlighted_accessions(
        ["P01308", "FAKE1", "P01315", "P01308"], retrieved
    ) == ["P01308", "P01315"]


def test_assemble_response_reads_recommend_proteins():
    trace = [
        {
            "tool": "search_uniprot",
            "args": {"text": "insulin"},
            "result": [
                {"accession": "P01308", "sequence": "AAA"},
                {"accession": "P01315", "sequence": "BBB"},
            ],
        },
        {
            "tool": "recommend_proteins",
            "args": {"accessions": ["P01308", "FAKE1"]},
            "result": ["P01308", "FAKE1"],
        },
    ]
    proteins, _candidates, highlighted = assemble_response(trace)
    assert [p.accession for p in proteins] == ["P01308", "P01315"]
    assert highlighted == ["P01308"]


def test_summarize_trace_recommend_proteins():
    from app.agent.assembler import summarize_trace

    lines = summarize_trace(
        [
            {
                "tool": "recommend_proteins",
                "args": {"accessions": ["P01308"]},
                "result": ["P01308"],
            }
        ]
    )
    assert lines == ["recommend_proteins(n=1) -> 1 selected"]


def _propose_trace(parent_sequence: str, parent_name: str, candidate_sequence: str = "AAB"):
    return [
        {
            "tool": "propose_variants",
            "args": {
                "parent_sequence": parent_sequence,
                "parent_name": parent_name,
                "instruction": "stabilize",
                "n": 1,
            },
            "result": [{"sequence": candidate_sequence, "model_version": "test"}],
        }
    ]


def test_parent_warning_when_sequence_not_retrieved():
    _, candidates, _ = assemble_response(
        _propose_trace("MVLSPADKTNVKAAW", "Hemoglobin subunit alpha")
    )
    assert candidates[0].parent.accession is None
    assert "parent_sequence_not_found_in_retrieved_proteins" in candidates[0].warnings


def test_parent_from_prior_retrieved_exact_sequence():
    prior = [
        {
            "accession": "P69905",
            "protein_name": "Hemoglobin subunit alpha",
            "organism": "Homo sapiens",
            "sequence": "MVLSPADKTNVKAAW",
        }
    ]
    proteins, candidates, _ = assemble_response(
        _propose_trace("MVLSPADKTNVKAAW", "Hemoglobin subunit alpha"),
        prior_retrieved=prior,
    )
    assert proteins == []
    assert candidates[0].parent.accession == "P69905"
    assert candidates[0].parent.organism == "Homo sapiens"
    assert "parent_sequence_not_found_in_retrieved_proteins" not in candidates[0].warnings


def test_parent_from_prior_retrieved_ignores_whitespace_and_case():
    prior = [{"accession": "P69905", "sequence": "MVLSPADKTNVKAAW"}]
    _, candidates, _ = assemble_response(
        _propose_trace("mvlspadktnvkaaw\n", "alpha"),
        prior_retrieved=prior,
    )
    assert candidates[0].parent.accession == "P69905"
    assert "parent_sequence_not_found_in_retrieved_proteins" not in candidates[0].warnings


def test_parent_from_prior_retrieved_accession_in_name():
    prior = [
        {
            "accession": "P69905",
            "protein_name": "Hemoglobin subunit alpha",
            "organism": "Homo sapiens",
            "sequence": "MVLSPADKTNVKAAW",
        }
    ]
    _, candidates, _ = assemble_response(
        _propose_trace("NOTTHEPARENTSEQ", "Hemoglobin subunit alpha (P69905)"),
        prior_retrieved=prior,
    )
    assert candidates[0].parent.accession == "P69905"
    assert candidates[0].parent.sequence == "NOTTHEPARENTSEQ"
    assert "parent_sequence_not_found_in_retrieved_proteins" not in candidates[0].warnings


def test_this_turn_retrieved_wins_over_prior():
    trace = [
        {
            "tool": "get_uniprot_entry",
            "args": {"accession": "P69905"},
            "result": {
                "accession": "P69905",
                "protein_name": "This turn",
                "sequence": "MVLSPADKTNVKAAW",
            },
        },
        *_propose_trace("MVLSPADKTNVKAAW", "Hemoglobin subunit alpha (P69905)"),
    ]
    prior = [
        {
            "accession": "P69905",
            "protein_name": "Prior turn",
            "sequence": "MVLSPADKTNVKAAW",
        }
    ]
    _, candidates, _ = assemble_response(trace, prior_retrieved=prior)
    assert candidates[0].parent.protein_name == "This turn"
