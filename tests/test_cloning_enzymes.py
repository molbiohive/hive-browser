"""Tests for cloning/enzymes -- IUPAC cut site scanner."""

from types import SimpleNamespace

import pytest

from hive.cloning.enzymes import (
    _reverse_complement,
    _site_to_regex,
    find_cut_sites,
)


def _make_enzyme(**kwargs):
    """Create an enzyme-like object for testing (no DB required)."""
    defaults = {
        "id": 1, "name": "Test", "site": "GAATTC",
        "cut5": 1, "cut3": -1, "overhang": -4, "length": 6,
        "is_palindrome": True, "is_blunt": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── Helper tests ─────────────────────────────────────────────────


class TestSiteToRegex:
    def test_simple(self):
        p = _site_to_regex("GAATTC")
        assert p.pattern == "GAATTC"

    def test_iupac_n(self):
        p = _site_to_regex("GANTC")
        assert p.pattern == "GA[ACGT]TC"

    def test_iupac_r(self):
        p = _site_to_regex("GRCGYC")
        assert p.pattern == "G[AG]CG[CT]C"

    def test_invalid_char(self):
        with pytest.raises(ValueError, match="Invalid IUPAC"):
            _site_to_regex("GXATTC")


class TestReverseComplement:
    def test_basic(self):
        assert _reverse_complement("GAATTC") == "GAATTC"  # palindrome

    def test_non_palindrome(self):
        assert _reverse_complement("GGTCTC") == "GAGACC"

    def test_iupac(self):
        assert _reverse_complement("GANTC") == "GANTC"  # palindrome with N


# ── Cut site scanner ─────────────────────────────────────────────


def _enzymes(*args) -> dict:
    """Build enzyme dict from Enzyme objects."""
    return {e.name.upper(): e for e in args}


class TestEcoRI:
    """EcoRI: GAATTC, palindromic, 5' overhang."""

    @pytest.fixture
    def ecori(self):
        return _make_enzyme(
            name="EcoRI", site="GAATTC", cut5=1, cut3=-1,
            overhang=-4, length=6, is_palindrome=True, is_blunt=False,
        )

    def test_single_site_linear(self, ecori):
        # GAATTC at position 10
        seq = "AAAAAAAAAA" + "GAATTC" + "AAAAAAAAAA"
        result = find_cut_sites(seq, ["EcoRI"], _enzymes(ecori), circular=False)
        assert result["total_cuts"] == 1
        # 0-based: 10 + 1 = 11
        assert result["all_cuts"] == [11]
        assert result["fragments"] == [15, 11]  # sorted desc

    def test_no_site(self, ecori):
        seq = "AAAAAAAAAA" * 5
        result = find_cut_sites(seq, ["EcoRI"], _enzymes(ecori), circular=False)
        assert result["total_cuts"] == 0
        assert result["fragments"] == [50]

    def test_two_sites_linear(self, ecori):
        # GAATTC at positions 5 and 20
        seq = "AAAAAGAATTCAAAAAAAAA" + "GAATTCAAAAA"
        result = find_cut_sites(seq, ["EcoRI"], _enzymes(ecori), circular=False)
        assert result["total_cuts"] == 2
        assert result["all_cuts"] == [6, 21]


class TestHinfI:
    """HinfI: GANTC, palindromic with IUPAC N."""

    @pytest.fixture
    def hinfi(self):
        return _make_enzyme(
            name="HinfI", site="GANTC", cut5=1, cut3=-1,
            overhang=-3, length=5, is_palindrome=True, is_blunt=False,
        )

    def test_matches_all_n_variants(self, hinfi):
        enzs = _enzymes(hinfi)
        for base in "ACGT":
            seq = "AAAAAAAAAA" + f"GA{base}TC" + "AAAAAAAAAA"
            result = find_cut_sites(seq, ["HinfI"], enzs, circular=False)
            assert result["total_cuts"] == 1, f"Failed for N={base}"


class TestBsaI:
    """BsaI: GGTCTC, non-palindromic, Type IIS."""

    @pytest.fixture
    def bsai(self):
        return _make_enzyme(
            name="BsaI", site="GGTCTC", cut5=7, cut3=5,
            overhang=-4, length=6, is_palindrome=False, is_blunt=False,
        )

    def test_forward_match(self, bsai):
        # GGTCTC at position 10
        seq = "AAAAAAAAAA" + "GGTCTCN" + "AAAAAAAAAA"
        result = find_cut_sites(seq, ["BsaI"], _enzymes(bsai), circular=False)
        assert result["total_cuts"] == 1
        # Forward: 10 + 7 = 17
        assert result["all_cuts"] == [17]

    def test_rc_match(self, bsai):
        # GAGACC (RC of GGTCTC) at position 15
        seq = "AAAAAAAAAAAAAAA" + "GAGACC" + "AAAAAAAAAA"
        result = find_cut_sites(seq, ["BsaI"], _enzymes(bsai), circular=False)
        assert result["total_cuts"] == 1
        # RC: 15 - 5 = 10
        assert result["all_cuts"] == [10]

    def test_both_orientations(self, bsai):
        # GGTCTC at 0, GAGACC (RC) at 17
        seq = "GGTCTCNAAAAAAAAAAGAGACCN"
        result = find_cut_sites(seq, ["BsaI"], _enzymes(bsai), circular=False)
        assert result["total_cuts"] == 2
        # Forward: 0 + 7 = 7, RC: 17 - 5 = 12
        assert result["all_cuts"] == [7, 12]


class TestAccBSI:
    """AccBSI: non-palindromic with negative cut3."""

    @pytest.fixture
    def accbsi(self):
        return _make_enzyme(
            name="AccBSI", site="CCGCTC", cut5=3, cut3=-3,
            overhang=0, length=6, is_palindrome=False, is_blunt=True,
        )

    def test_forward_match(self, accbsi):
        seq = "AAAAAAAAAA" + "CCGCTC" + "AAAAAAAAAA"
        result = find_cut_sites(seq, ["AccBSI"], _enzymes(accbsi), circular=False)
        assert result["total_cuts"] == 1
        # Forward: 10 + 3 = 13
        assert result["all_cuts"] == [13]

    def test_rc_match_negative_cut3(self, accbsi):
        # RC of CCGCTC = GAGCGG
        seq = "AAAAAAAAAA" + "GAGCGG" + "AAAAAAAAAA"
        result = find_cut_sites(seq, ["AccBSI"], _enzymes(accbsi), circular=False)
        assert result["total_cuts"] == 1
        # RC: 10 - (-3) = 13
        assert result["all_cuts"] == [13]


class TestCircular:
    """Circular sequences: wrap-around detection."""

    @pytest.fixture
    def ecori(self):
        return _make_enzyme(
            name="EcoRI", site="GAATTC", cut5=1, cut3=-1,
            overhang=-4, length=6, is_palindrome=True, is_blunt=False,
        )

    def test_wrap_around_site(self, ecori):
        # Site wraps: last 3 chars + first 3 chars = GAATTC
        seq = "TTCAAAAAAAAAAAAAAAAAAGAA"  # TTC at end, GAA at start
        result = find_cut_sites(seq, ["EcoRI"], _enzymes(ecori), circular=True)
        assert result["total_cuts"] == 1

    def test_circular_fragments_sum(self, ecori):
        # Two EcoRI sites in circular sequence
        seq = "GAATTC" + "A" * 20 + "GAATTC" + "A" * 20
        result = find_cut_sites(seq, ["EcoRI"], _enzymes(ecori), circular=True)
        assert result["total_cuts"] == 2
        assert sum(result["fragments"]) == len(seq)


class TestMultiEnzyme:
    """Multiple enzymes in one call."""

    def test_two_enzymes(self):
        ecori = _make_enzyme(
            name="EcoRI", site="GAATTC", cut5=1, cut3=-1,
            overhang=-4, length=6, is_palindrome=True, is_blunt=False,
        )
        bamhi = _make_enzyme(
            id=2, name="BamHI", site="GGATCC", cut5=1, cut3=-1,
            overhang=-4, length=6, is_palindrome=True, is_blunt=False,
        )
        seq = "GAATTC" + "A" * 20 + "GGATCC" + "A" * 20
        result = find_cut_sites(
            seq, ["EcoRI", "BamHI"], _enzymes(ecori, bamhi), circular=False,
        )
        assert result["total_cuts"] == 2
        assert len(result["enzyme_results"]) == 2
        assert result["enzyme_results"][0]["name"] == "EcoRI"
        assert result["enzyme_results"][1]["name"] == "BamHI"


class TestFragments:
    """Fragment size calculations."""

    @pytest.fixture
    def smai(self):
        return _make_enzyme(
            name="SmaI", site="CCCGGG", cut5=3, cut3=-3,
            overhang=0, length=6, is_palindrome=True, is_blunt=True,
        )

    def test_linear_fragments_sum(self, smai):
        seq = "AAAAACCCGGGAAAAAAAAAACCCGGGAAA"
        result = find_cut_sites(seq, ["SmaI"], _enzymes(smai), circular=False)
        assert sum(result["fragments"]) == len(seq)

    def test_circular_fragments_sum(self, smai):
        seq = "AAAAACCCGGGAAAAAAAAAACCCGGGAAA"
        result = find_cut_sites(seq, ["SmaI"], _enzymes(smai), circular=True)
        assert sum(result["fragments"]) == len(seq)

    def test_no_cuts_returns_full_length(self, smai):
        seq = "AAAAAAAAAA"
        result = find_cut_sites(seq, ["SmaI"], _enzymes(smai), circular=False)
        assert result["fragments"] == [10]


class TestUnknownEnzyme:
    def test_raises_on_unknown(self):
        with pytest.raises(ValueError, match="Unknown enzyme"):
            find_cut_sites("AAAA", ["FakeEnzyme"], {})
