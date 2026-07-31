"""Unit tests for UniProt ID Mapping client (fixture / mocked HTTP)."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import config
from app.tools.uniprot_idmapping import (
    map_to_uniprot,
    run_id_mapping,
)

UNIPROT_HOST = httpx.URL(config.uniprot_base_url).host

INS_ENTRY = {
    "entryType": "UniProtKB reviewed (Swiss-Prot)",
    "primaryAccession": "P01308",
    "organism": {"scientificName": "Homo sapiens", "taxonId": 9606},
    "proteinDescription": {
        "recommendedName": {"fullName": {"value": "Insulin"}}
    },
    "comments": [
        {
            "commentType": "FUNCTION",
            "texts": [{"value": "Decreases blood glucose."}],
        }
    ],
    "sequence": {"value": "MALWMR", "length": 6},
}

MOUSE_ENTRY = {
    **INS_ENTRY,
    "primaryAccession": "P01326",
    "organism": {"scientificName": "Mus musculus", "taxonId": 10090},
}

TREMBL_ENTRY = {
    **INS_ENTRY,
    "entryType": "UniProtKB unreviewed (TrEMBL)",
    "primaryAccession": "A0A9E9AQX1",
    "proteinDescription": {
        "recommendedName": {"fullName": {"value": "Insulin-like"}}
    },
}


@pytest.mark.asyncio
async def test_run_id_mapping_parses_results():
    with respx.mock:
        respx.post(host=UNIPROT_HOST, path="/idmapping/run").mock(
            return_value=httpx.Response(200, json={"jobId": "job-1"})
        )
        respx.get(host=UNIPROT_HOST, path="/idmapping/status/job-1").mock(
            return_value=httpx.Response(200, json={"jobStatus": "FINISHED"})
        )
        respx.get(host=UNIPROT_HOST, path="/idmapping/uniprotkb/results/job-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"from": "INS", "to": "P01308"},
                        {"from": "BAD", "to": None},
                    ],
                    "failedIds": ["BAD"],
                },
            )
        )

        out = await run_id_mapping(["INS", "BAD"], from_db="Gene_Name")

    assert out["mappings"] == [
        {"from": "INS", "to": "P01308", "entry": None}
    ]
    assert "BAD" in out["failed_ids"]


@pytest.mark.asyncio
async def test_map_to_uniprot_uses_embedded_entry_and_filters_organism():
    with respx.mock:
        route = respx.post(host=UNIPROT_HOST, path="/idmapping/run").mock(
            return_value=httpx.Response(200, json={"jobId": "job-2"})
        )
        respx.get(host=UNIPROT_HOST, path="/idmapping/status/job-2").mock(
            return_value=httpx.Response(200, json={"jobStatus": "FINISHED"})
        )
        respx.get(host=UNIPROT_HOST, path="/idmapping/uniprotkb/results/job-2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"from": "INS", "to": INS_ENTRY},
                        {"from": "Ins", "to": MOUSE_ENTRY},
                    ],
                    "failedIds": [],
                },
            )
        )

        out = await map_to_uniprot(
            ["INS", "Ins"], from_db="Gene_Name", organism_id="9606"
        )

    assert route.calls.last.request.content
    body = route.calls.last.request.content.decode()
    assert "taxId=9606" in body

    assert len(out["proteins"]) == 1
    assert out["proteins"][0]["accession"] == "P01308"
    assert out["proteins"][0]["protein_name"] == "Insulin"
    assert out["proteins"][0]["retrieval_method"] == "uniprot_idmapping"
    assert out["proteins"][0]["mapped_from"] == "INS"
    assert out["mappings"] == [
        {"from": "INS", "to": "P01308"},
        {"from": "Ins", "to": "P01326"},
    ]
    assert any(s["accession"] == "P01326" for s in out["skipped_accessions"])


@pytest.mark.asyncio
async def test_map_to_uniprot_skips_unreviewed_by_default():
    with respx.mock:
        respx.post(host=UNIPROT_HOST, path="/idmapping/run").mock(
            return_value=httpx.Response(200, json={"jobId": "job-rev"})
        )
        respx.get(host=UNIPROT_HOST, path="/idmapping/status/job-rev").mock(
            return_value=httpx.Response(200, json={"jobStatus": "FINISHED"})
        )
        respx.get(
            host=UNIPROT_HOST, path="/idmapping/uniprotkb/results/job-rev"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"from": "INS", "to": INS_ENTRY},
                        {"from": "INS", "to": TREMBL_ENTRY},
                    ],
                    "failedIds": [],
                },
            )
        )

        out = await map_to_uniprot(["INS"], from_db="Gene_Name")

    assert [p["accession"] for p in out["proteins"]] == ["P01308"]
    assert any(
        s["accession"] == "A0A9E9AQX1" and s["reason"] == "unreviewed"
        for s in out["skipped_accessions"]
    )

    with respx.mock:
        respx.post(host=UNIPROT_HOST, path="/idmapping/run").mock(
            return_value=httpx.Response(200, json={"jobId": "job-all"})
        )
        respx.get(host=UNIPROT_HOST, path="/idmapping/status/job-all").mock(
            return_value=httpx.Response(200, json={"jobStatus": "FINISHED"})
        )
        respx.get(
            host=UNIPROT_HOST, path="/idmapping/uniprotkb/results/job-all"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"from": "INS", "to": INS_ENTRY},
                        {"from": "INS", "to": TREMBL_ENTRY},
                    ],
                    "failedIds": [],
                },
            )
        )

        out_all = await map_to_uniprot(
            ["INS"], from_db="Gene_Name", reviewed=False
        )

    assert {p["accession"] for p in out_all["proteins"]} == {
        "P01308",
        "A0A9E9AQX1",
    }


@pytest.mark.asyncio
async def test_map_to_uniprot_falls_back_to_get_entry_for_string_to():
    with respx.mock:
        respx.post(host=UNIPROT_HOST, path="/idmapping/run").mock(
            return_value=httpx.Response(200, json={"jobId": "job-str"})
        )
        respx.get(host=UNIPROT_HOST, path="/idmapping/status/job-str").mock(
            return_value=httpx.Response(200, json={"jobStatus": "FINISHED"})
        )
        respx.get(
            host=UNIPROT_HOST, path="/idmapping/uniprotkb/results/job-str"
        ).mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [{"from": "INS", "to": "P01308"}],
                    "failedIds": [],
                },
            )
        )
        respx.get(host=UNIPROT_HOST, path="/uniprotkb/P01308.json").mock(
            return_value=httpx.Response(200, json=INS_ENTRY)
        )

        out = await map_to_uniprot(["INS"], from_db="Gene_Name")

    assert len(out["proteins"]) == 1
    assert out["proteins"][0]["accession"] == "P01308"


@pytest.mark.asyncio
async def test_run_id_mapping_treats_303_as_finished():
    with respx.mock:
        respx.post(host=UNIPROT_HOST, path="/idmapping/run").mock(
            return_value=httpx.Response(200, json={"jobId": "job-303"})
        )
        respx.get(host=UNIPROT_HOST, path="/idmapping/status/job-303").mock(
            return_value=httpx.Response(
                303,
                headers={
                    "Location": f"{config.uniprot_base_url}/idmapping/uniprotkb/results/job-303"
                },
            )
        )
        respx.get(
            host=UNIPROT_HOST, path="/idmapping/uniprotkb/results/job-303"
        ).mock(
            return_value=httpx.Response(
                200,
                json={"results": [{"from": "P01308", "to": "P01308"}], "failedIds": []},
            )
        )

        out = await run_id_mapping(["P01308"], from_db="UniProtKB_AC-ID")

    assert out["mappings"] == [
        {"from": "P01308", "to": "P01308", "entry": None}
    ]
