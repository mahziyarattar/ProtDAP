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
