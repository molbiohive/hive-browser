"""Shared test fixtures."""

import pytest


@pytest.fixture
def sample_sequence():
    """A minimal sequence dict for testing."""
    return {
        "name": "pEGFP-N1",
        "sequence": "ATGGTGAGCAAGGGCGAGGAG",
        "size_bp": 4733,
        "topology": "circular",
        "features": [
            {"name": "GFP", "type": "CDS", "start": 679, "end": 1398, "strand": 1},
            {"name": "KanR", "type": "CDS", "start": 1629, "end": 2438, "strand": 1},
            {"name": "CMV", "type": "promoter", "start": 1, "end": 588, "strand": 1},
        ],
    }
