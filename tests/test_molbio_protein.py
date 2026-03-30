"""Tests for molbio/protein -- ProtParam calculations."""

import pytest

from hive.molbio.protein import (
    amino_acid_composition,
    charge_at_ph,
    extinction_coefficient,
    gravy,
    instability_index,
    isoelectric_point,
    molecular_weight,
)

# Insulin B chain (human): well-characterized reference protein
_INSULIN_B = "FVNQHLCGSHLVEALYLVCGERGFFYTPKT"


class TestMolecularWeight:
    def test_insulin_b_chain(self):
        mw = molecular_weight(_INSULIN_B)
        # ExPASy reference: ~3400 Da for insulin B chain
        assert 3300 < mw < 3500

    def test_single_residue(self):
        mw = molecular_weight("M")
        # Single Met residue = Met MW (149.2 Da, no peptide bonds)
        assert 140 < mw < 160

    def test_strips_stop(self):
        assert molecular_weight("MK*") == molecular_weight("MK")


class TestIsoelectricPoint:
    def test_insulin_b_chain(self):
        pi = isoelectric_point(_INSULIN_B)
        # ExPASy reference: ~6.74
        assert 6.0 < pi < 7.5

    def test_acidic_peptide(self):
        # All Asp -> very acidic
        pi = isoelectric_point("DDDDD")
        assert pi < 4.0

    def test_basic_peptide(self):
        # All Lys -> very basic
        pi = isoelectric_point("KKKKK")
        assert pi > 10.0


class TestChargeAtPh:
    def test_neutral_is_near_zero_at_pi(self):
        pi = isoelectric_point(_INSULIN_B)
        charge = charge_at_ph(_INSULIN_B, pi)
        assert abs(charge) < 0.1

    def test_positive_at_low_ph(self):
        assert charge_at_ph(_INSULIN_B, 2.0) > 0

    def test_negative_at_high_ph(self):
        assert charge_at_ph(_INSULIN_B, 13.0) < 0


class TestAminoAcidComposition:
    def test_returns_20_entries(self):
        comp = amino_acid_composition("MKFA")
        assert len(comp) == 20

    def test_counts(self):
        comp = amino_acid_composition("AAAKK")
        by_aa = {c["amino_acid"]: c for c in comp}
        assert by_aa["A"]["count"] == 3
        assert by_aa["K"]["count"] == 2
        assert by_aa["A"]["percent"] == 60.0

    def test_strips_stop(self):
        comp = amino_acid_composition("MK*")
        by_aa = {c["amino_acid"]: c for c in comp}
        assert by_aa["M"]["count"] == 1
        assert by_aa["K"]["count"] == 1


class TestExtinctionCoefficient:
    def test_no_chromophores(self):
        ec = extinction_coefficient("AAAKKK")
        assert ec["reduced"] == 0
        assert ec["oxidized"] == 0

    def test_tryptophan(self):
        ec = extinction_coefficient("W")
        assert ec["reduced"] == 5500

    def test_cysteine_pair(self):
        ec = extinction_coefficient("CC")
        assert ec["oxidized"] == ec["reduced"] + 125


class TestGravy:
    def test_hydrophobic(self):
        # All Ile -> very hydrophobic
        assert gravy("IIIII") > 4.0

    def test_hydrophilic(self):
        # All Arg -> very hydrophilic
        assert gravy("RRRRR") < -4.0


class TestInstabilityIndex:
    def test_returns_float(self):
        ii = instability_index(_INSULIN_B)
        assert isinstance(ii, float)

    def test_short_sequence(self):
        assert instability_index("M") == 0.0
