#!/usr/bin/env python3
from copy import deepcopy

from canonical_gate import assess_canonical_compatibility
from platform_group_canonical_adapter import adapt_platform_group


def fixture():
    source_rows = [
        {
            "source_ref":"tracking code generator!5","sheet":"tracking code generator","excel_row":5,
            "input_values":{"target URL":"https://example.test/landing","placement (medium)":"social media","Ad Name":"Social B","Format Type":"Image","ad width":1920,"ad height":1080},
            "derived_values":{"targeting":"Bespoke Tech Audience"},
        },
        {
            "source_ref":"tracking code generator!6","sheet":"tracking code generator","excel_row":6,
            "input_values":{"target URL":"https://example.test/landing","placement (medium)":"social media","Ad Name":"Social B","Format Type":"Image","ad width":1920,"ad height":1080},
            "derived_values":{"targeting":"Bespoke Tech Audience"},
        },
    ]
    campaign = {
        "campaign_candidate_id":"CMPCAND-EXAMPLE","client":"Example Client","campaign_name":"Campaign Innovation 2024",
        "objective":"Traffic","market":"UK","currency":"GBP","platform":"Facebook","platform_candidates":["Facebook"],
        "flight_start":"2024-07-01","flight_end":"2024-09-30","platform_origin":"source_activation_partition",
    }
    return {
        "schema":"nexus-platform-groups-v0","status":"READY_PLATFORM_GROUPS","compiler_allowed":False,
        "source":{"filename":"historical_tracking_fixture.xlsx","sheet":"tracking code generator","read_only":True},
        "source_rows":deepcopy(source_rows),"unresolved_ambiguities":[],"blocking_validation_issues":[],
        "platform_groups":[{
            "platform_group_id":"PLATGRP-FACEBOOK","platform":"Facebook","status":"READY_FOR_CANONICAL_ADAPTER",
            "campaign":campaign,"eligible_activation_candidate_ids":["ACTCAND-5"],"excluded_activation_candidate_ids":["ACTCAND-6"],
            "activation_candidates":[{
                "activation_candidate_id":"ACTCAND-5","source_ref":"tracking code generator!5","platform":"Facebook",
                "audience_candidate_id":"AUDCAND-A","creative_candidate_id":"CRECAND-B","campaign_period":"Q3 24",
                "placement_name":"UK | Traffic | Campaign Innovation 2024 | Image","device":"All devices","paid_link":True,
                "landing_page_url":"https://example.test/landing","final_tracking_url":"https://example.test/landing?cid=test",
            }],
            "source_evidence":["tracking code generator!5","tracking code generator!6"],"source_rows":deepcopy(source_rows),
            "audience_candidate_ids":["AUDCAND-A"],"creative_candidate_ids":["CRECAND-B"],
        }],
    }


def main():
    boundary = fixture()
    before = deepcopy(boundary)
    first = adapt_platform_group(boundary, "PLATGRP-FACEBOOK")
    second = adapt_platform_group(boundary, "PLATGRP-FACEBOOK")

    assert boundary == before
    assert first == second
    assert first["schema"] == "nexus-canonical-campaign-v0"
    assert first["canonical_status"] == "READY"
    assert first["counts"] == {"source_rows":2,"campaigns":1,"audiences":1,"creatives":1,"activations":1}
    assert first["campaign"]["platform"] == "Facebook"
    assert first["campaign"]["flight_scope"] == "exact"
    assert first["ambiguities"] == [] and first["validation_issues"] == []
    assert first["source_rows"][0]["canonical_disposition"] == "ACTIVATION_SOURCE"
    assert first["source_rows"][1]["canonical_disposition"] == "EVIDENCE_ONLY_EXCLUDED"
    assert first["relationships"]["excluded_source_rows"] == ["tracking code generator!6"]
    assert first["activations"][0]["plan_row_id"] == "tracking code generator!5"
    assert first["activations"][0]["plan_row_id_origin"] == "source_ref"
    assert first["creatives"][0]["creative_id"] == "Social B"
    assert first["creatives"][0]["creative_id_origin"] == "source.Ad Name"
    assert first["campaign"]["campaign_key"].startswith("CMP-")
    assert first["audiences"][0]["audience_row_id"].startswith("AUD-")
    assert first["creatives"][0]["creative_row_id"].startswith("CRE-")
    assert first["activations"][0]["activation_id"].startswith("ACT-")

    gate = assess_canonical_compatibility(first)
    assert gate["status"] == "READY_FOR_COMPILE"
    assert gate["compiler_allowed"] is True

    # Stable IDs must not depend on excluded duplicate evidence.
    trimmed = fixture()
    trimmed_group = trimmed["platform_groups"][0]
    trimmed_group["source_rows"] = [trimmed_group["source_rows"][0]]
    trimmed_group["source_evidence"] = ["tracking code generator!5"]
    trimmed["source_rows"] = [trimmed["source_rows"][0]]
    trimmed_group["excluded_activation_candidate_ids"] = []
    third = adapt_platform_group(trimmed, "PLATGRP-FACEBOOK")
    assert third["campaign"]["campaign_key"] == first["campaign"]["campaign_key"]
    assert third["audiences"][0]["audience_row_id"] == first["audiences"][0]["audience_row_id"]
    assert third["creatives"][0]["creative_row_id"] == first["creatives"][0]["creative_row_id"]
    assert third["activations"][0]["activation_id"] == first["activations"][0]["activation_id"]

    print("PASS: one platform group adapts to nexus-canonical-campaign-v0")
    print("PASS: source evidence including excluded duplicate row is preserved")
    print("PASS: Campaign/Audience/Creative/Activation IDs are deterministic across reruns")
    print("PASS: existing canonical compatibility gate returns READY_FOR_COMPILE")
    print("PASS: adapter does not mutate boundary input or call compiler/Hermes")

if __name__ == "__main__":
    main()
