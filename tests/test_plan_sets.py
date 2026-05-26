"""
Test plan set discovery and deduplication rules (from 14-DISCOVERY audit).

No live browser — unit tests for normalize_plan_sets function.
"""
import pytest
from browser import normalize_plan_sets


class TestPlanSetDedupe:
    """Test dedupe rules from 14-DISCOVERY.md"""

    def test_morehouse_dedupe_aggregate(self):
        """Morehouse: Drop aggregate folder with both v1+v2 in name"""
        raw = [
            {
                "folder_id": 35240651,
                "name": "Plans MSP3- ISSUE FOR BID-COMBINEDv1 MSP3- ISSUE FOR BID-COMBINEDv2",
            },
            {
                "folder_id": 35240700,
                "name": "MSP3- ISSUE FOR BID-COMBINEDv1",
            },
            {
                "folder_id": 35240694,
                "name": "MSP3- ISSUE FOR BID-COMBINEDv2",
            },
        ]
        result = normalize_plan_sets(raw)
        
        # Should drop the aggregate (both v1 and v2 in one name)
        assert len(result) == 2
        folder_ids = {s["folder_id"] for s in result}
        assert 35240700 in folder_ids  # v1
        assert 35240694 in folder_ids  # v2
        assert 35240651 not in folder_ids  # aggregate dropped

    def test_baking_social_drop_parent(self):
        """Bid for Baking Social: Drop 'Plans X' when child 'X' exists"""
        raw = [
            {
                "folder_id": 35218810,
                "name": "Plans 2026_0515_Baking Social Permit Set Combined 1",
                "sheet_count": 22,
            },
            {
                "folder_id": 35218877,
                "name": "2026_0515_Baking Social Permit Set Combined 1",
                "sheet_count": 22,
            },
        ]
        result = normalize_plan_sets(raw)
        
        # Should drop the "Plans X" parent when child "X" exists
        assert len(result) == 1
        assert result[0]["folder_id"] == 35218877
        assert result[0]["name"] == "2026_0515_Baking Social Permit Set Combined 1"

    def test_athens_fire_drop_parent(self):
        """Athens Fire Station: Drop 'Plans X' parent"""
        raw = [
            {
                "folder_id": 35228910,
                "name": "Plans Athens Fire Station No. 3 - 100_ CD Set - Drawings - 2026-04-24",
                "sheet_count": 120,
            },
            {
                "folder_id": 35228916,
                "name": "Athens Fire Station No. 3 - 100_ CD Set - Drawings - 2026-04-24",
                "sheet_count": 120,
            },
        ]
        result = normalize_plan_sets(raw)
        
        assert len(result) == 1
        assert result[0]["folder_id"] == 35228916

    def test_laseraway_drop_parent(self):
        """LaserAway: Drop 'Plans X' parent"""
        raw = [
            {
                "folder_id": 35190267,
                "name": "Plans Exhibit A - 260138 LSA Cumming_ GA CD_5-7-26",
                "sheet_count": 43,
            },
            {
                "folder_id": 35190393,
                "name": "Exhibit A - 260138 LSA Cumming_ GA CD_5-7-26",
                "sheet_count": 43,
            },
        ]
        result = normalize_plan_sets(raw)
        
        assert len(result) == 1
        assert result[0]["folder_id"] == 35190393

    def test_skip_system_folders(self):
        """Skip Bookmarks, Supporting Documents, generic Plans"""
        raw = [
            {"folder_id": 1, "name": "Plans"},
            {"folder_id": 2, "name": "Bookmarks"},
            {"folder_id": 3, "name": "Supporting Documents"},
            {"folder_id": 4, "name": "Real Plan Set"},
        ]
        result = normalize_plan_sets(raw)
        
        assert len(result) == 1
        assert result[0]["name"] == "Real Plan Set"

    def test_battery_two_distinct_sets(self):
        """Baking Social - The Battery: Two distinct permit sets (not duplicates)"""
        raw = [
            {
                "folder_id": 35218945,
                "name": "2026_0506_PERMIT SET COMBINED_BAKING SOCIAL S_S",
                "sheet_count": 45,
            },
            {
                "folder_id": 35218946,
                "name": "2026_0515_Baking Social Permit Set Combined",
                "sheet_count": 45,
            },
        ]
        result = normalize_plan_sets(raw)
        
        # Both should remain (different dates, not parent/child)
        assert len(result) == 2
        folder_ids = {s["folder_id"] for s in result}
        assert 35218945 in folder_ids
        assert 35218946 in folder_ids

    def test_empty_input(self):
        """Handle empty input gracefully"""
        result = normalize_plan_sets([])
        assert result == []

    def test_all_system_folders(self):
        """All system folders filtered out"""
        raw = [
            {"folder_id": 1, "name": "Plans"},
            {"folder_id": 2, "name": "Bookmarks"},
            {"folder_id": 3, "name": "supporting documents"},
        ]
        result = normalize_plan_sets(raw)
        assert result == []
