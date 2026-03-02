"""Tests for deps system: Dep ABC, DepRegistry, BlastDep."""

from hive.deps import Dep, DepRegistry
from hive.deps.blast import BlastDep

# ── Helpers ──


class FakeDep(Dep):
    name = "fake"
    needs_rebuild_on_ingest = False

    def resolve_binary(self, program: str) -> str:
        return f"/usr/bin/{program}"

    async def health(self):
        return {"ok": True, "version": "1.0"}


class RebuildDep(Dep):
    name = "rebuilder"
    needs_rebuild_on_ingest = True

    def __init__(self):
        self.setup_count = 0

    def resolve_binary(self, program: str) -> str:
        return program

    async def setup(self) -> bool:
        self.setup_count += 1
        return True


# ── Dep ABC ──


class TestDep:
    async def test_default_rebuild_delegates_to_setup(self):
        dep = RebuildDep()
        await dep.rebuild()
        assert dep.setup_count == 1

    async def test_default_setup_is_noop(self):
        dep = FakeDep()
        result = await dep.setup()
        assert result is True


# ── DepRegistry ──


class TestDepRegistry:
    def test_register_and_get(self):
        reg = DepRegistry()
        dep = FakeDep()
        reg.register(dep)
        assert reg.get("fake") is dep
        assert reg.get("nonexistent") is None

    def test_all(self):
        reg = DepRegistry()
        reg.register(FakeDep())
        reg.register(RebuildDep())
        assert len(reg.all()) == 2

    def test_rebuild_targets(self):
        reg = DepRegistry()
        reg.register(FakeDep())
        rebuilder = RebuildDep()
        reg.register(rebuilder)
        targets = reg.rebuild_targets()
        assert len(targets) == 1
        assert targets[0].name == "rebuilder"

    async def test_setup_all(self):
        reg = DepRegistry()
        reg.register(FakeDep())
        rebuilder = RebuildDep()
        reg.register(rebuilder)
        results = await reg.setup_all()
        assert results == {"fake": True, "rebuilder": True}
        assert rebuilder.setup_count == 1

    async def test_rebuild_all(self):
        reg = DepRegistry()
        reg.register(FakeDep())
        rebuilder = RebuildDep()
        reg.register(rebuilder)
        results = await reg.rebuild_all()
        assert results == {"rebuilder": True}
        assert rebuilder.setup_count == 1

    async def test_health_all(self):
        reg = DepRegistry()
        reg.register(FakeDep())
        results = await reg.health_all()
        assert results["fake"]["ok"] is True
        assert results["fake"]["version"] == "1.0"


# ── BlastDep ──


class TestBlastDep:
    def test_resolve_binary_with_bin_dir(self):
        dep = BlastDep(data_dir="/data/blast", bin_dir="/opt/blast/bin")
        assert dep.resolve_binary("blastn") == "/opt/blast/bin/blastn"
        assert dep.resolve_binary("makeblastdb") == "/opt/blast/bin/makeblastdb"

    def test_resolve_binary_from_path(self):
        dep = BlastDep(data_dir="/data/blast")
        assert dep.resolve_binary("blastn") == "blastn"

    def test_needs_rebuild(self):
        dep = BlastDep(data_dir="/data/blast")
        assert dep.needs_rebuild_on_ingest is True

    def test_name(self):
        dep = BlastDep(data_dir="/data/blast")
        assert dep.name == "blast"
