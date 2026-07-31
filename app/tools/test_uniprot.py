"""Unit tests for app/tools/uniprot.py, independent of the LLM/agent.

Fixture-backed tests run by default (no network, no API keys). Set
EVAL_LIVE=1 to additionally run the live-mode sanity check against the
real UniProt REST API.
"""

import json

import httpx
import pytest
import respx

from app.config import config
from app.eval import FIXTURES_DIR
from app.tools.uniprot import (
    UniProtResponseError,
    build_query,
    get_uniprot_entry,
    search_uniprot,
)

UNIPROT_HOST = httpx.URL(config.uniprot_base_url).host


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / name) as f:
        return json.load(f)


# --- 1. search_uniprot parses fixtures into clean records -----------------


async def test_search_uniprot_parses_fixture_without_leaking_raw_keys():
    fixture = _load_fixture("uniprot_search_human_immune.json")

    with respx.mock:
        respx.get(host=UNIPROT_HOST, path="/uniprotkb/search").mock(
            return_value=httpx.Response(200, json=fixture)
        )
        hits = await search_uniprot(text="immune response", organism_id="9606")

    assert len(hits) == len(fixture["results"])
    first = hits[0]
    assert first["accession"] == fixture["results"][0]["primaryAccession"]
    assert first["protein_name"]
    assert first["organism"] == "Homo sapiens"
    assert isinstance(first["length"], int)
    assert first["sequence"]
    # Raw UniProt JSON keys must not leak into the parsed record.
    assert "primaryAccession" not in first
    assert "proteinDescription" not in first


# --- 2 & 3. query building (no HTTP involved) ------------------------------


def test_build_query_includes_reviewed_true_by_default():
    query = build_query(text="kinase", reviewed=True)
    assert "(kinase)" in query
    assert "(reviewed:true)" in query


def test_build_query_omits_reviewed_when_false():
    query = build_query(text="kinase", reviewed=False)
    assert "(kinase)" in query
    assert "reviewed:true" not in query


def test_build_query_ands_organism_id():
    query = build_query(text="kinase", reviewed=True, organism_id="9606")
    assert "(organism_id:9606)" in query
    assert query.count(" AND ") == 2  # text AND reviewed AND organism_id


# --- 4. get_uniprot_entry ---------------------------------------------------


async def test_get_uniprot_entry_parses_fixture():
    fixture = _load_fixture("uniprot_entry_P69905.json")

    with respx.mock:
        respx.get(host=UNIPROT_HOST, path="/uniprotkb/P69905.json").mock(
            return_value=httpx.Response(200, json=fixture)
        )
        entry = await get_uniprot_entry("P69905")

    assert entry["accession"] == "P69905"
    assert entry["sequence"]
    assert len(entry["sequence"]) == entry["length"]
    assert entry["gene_names"] == ["HBA1", "HBAM"]
    assert entry["subcellular_locations"] == ["Cytoplasm"]
    assert entry["diseases"] == ["Heinz body anemias"]
    assert entry["domains"] == [{"name": "Globin", "start": 2, "end": 142}]
    assert entry["go_terms"][0].startswith("GO:0005833")
    assert "primaryAccession" not in entry
    assert "uniProtKBCrossReferences" not in entry


def test_parse_entry_caps_go_and_domains():
    from app.tools.uniprot import MAX_DOMAINS, MAX_GO_TERMS, _parse_entry

    entry = {
        "primaryAccession": "P00000",
        "entryType": "UniProtKB reviewed (Swiss-Prot)",
        "proteinDescription": {},
        "organism": {},
        "sequence": {},
        "uniProtKBCrossReferences": [
            {
                "database": "GO",
                "id": f"GO:{i:07d}",
                "properties": [{"key": "GoTerm", "value": f"F:term{i}"}],
            }
            for i in range(MAX_GO_TERMS + 5)
        ],
        "features": [
            {
                "type": "Domain",
                "description": f"Dom{i}",
                "location": {
                    "start": {"value": i},
                    "end": {"value": i + 10},
                },
            }
            for i in range(MAX_DOMAINS + 3)
        ],
    }
    parsed = _parse_entry(entry)
    assert len(parsed["go_terms"]) == MAX_GO_TERMS
    assert len(parsed["domains"]) == MAX_DOMAINS


# --- 5. HTTP 429 triggers exactly one retry honoring Retry-After -----------


async def test_search_uniprot_retries_once_on_429_then_succeeds():
    success_body = _load_fixture("uniprot_search_minimal.json")

    with respx.mock:
        route = respx.get(host=UNIPROT_HOST, path="/uniprotkb/search")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json=success_body),
        ]

        hits = await search_uniprot(text="insulin", organism_id="9606")

    assert route.call_count == 2
    assert len(hits) == 1
    assert hits[0]["accession"] == "P01308"


async def test_search_uniprot_raises_after_second_429():
    with respx.mock:
        route = respx.get(host=UNIPROT_HOST, path="/uniprotkb/search")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(429, headers={"Retry-After": "0"}),
        ]

        with pytest.raises(Exception):
            await search_uniprot(text="insulin")

    assert route.call_count == 2


# --- 6. malformed response raises a typed error, not a raw KeyError -------


async def test_search_uniprot_raises_typed_error_on_malformed_response():
    malformed = _load_fixture("uniprot_search_malformed.json")

    with respx.mock:
        respx.get(host=UNIPROT_HOST, path="/uniprotkb/search").mock(
            return_value=httpx.Response(200, json=malformed)
        )
        with pytest.raises(UniProtResponseError):
            await search_uniprot(text="insulin")


# --- 7. live-mode sanity check (only runs with EVAL_LIVE=1) ---------------


@pytest.mark.skipif(
    not config.eval_live,
    reason="Live UniProt check skipped (set EVAL_LIVE=1 to run against the real API)",
)
async def test_get_uniprot_entry_live_matches_fixture_shape():
    entry = await get_uniprot_entry("P69905")

    assert entry["accession"] == "P69905"
    assert entry["organism"] == "Homo sapiens"
    assert entry["sequence"]
    assert entry["length"] == len(entry["sequence"])
