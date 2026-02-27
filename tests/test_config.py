"""Tests for config: grouped sections, version field, dep_data_dir, logging."""

from hive.config import CURRENT_CONFIG_VERSION, LogConfig, Settings, load_config


class TestGroupedConfig:
    def test_deps_blast_defaults(self):
        s = Settings()
        assert s.deps.blast.bin_dir == ""
        assert s.deps.blast.default_evalue == 1e-5
        assert s.deps.blast.default_max_hits == 50

    def test_deps_mafft_defaults(self):
        s = Settings()
        assert s.deps.mafft.bin_dir == ""

    def test_tools_search_defaults(self):
        s = Settings()
        assert s.tools.search.columns == ["name", "size_bp", "topology", "features"]

    def test_chat_stays_top_level(self):
        s = Settings()
        assert s.chat.max_history_pairs == 20
        assert s.chat.auto_save_after == 1


class TestVersion:
    def test_default_version(self):
        s = Settings()
        assert s.version == CURRENT_CONFIG_VERSION

    def test_version_from_data(self):
        s = Settings(version=2)
        assert s.version == 2


class TestDepDataDir:
    def test_blast_data_dir(self):
        s = Settings(data_root="/data")
        assert s.dep_data_dir("blast") == "/data/blast"

    def test_mafft_data_dir(self):
        s = Settings(data_root="/data")
        assert s.dep_data_dir("mafft") == "/data/mafft"

    def test_tilde_expansion(self):
        s = Settings(data_root="~/hive")
        result = s.dep_data_dir("blast")
        assert "~" not in result
        assert result.endswith("/hive/blast")


class TestLogConfig:
    def test_defaults(self):
        c = LogConfig()
        assert c.level == "INFO"
        assert c.llm_dump is False

    def test_settings_logging_defaults(self):
        s = Settings()
        assert s.logging.level == "INFO"
        assert s.logging.llm_dump is False

    def test_logs_dir(self):
        s = Settings(data_root="/data")
        assert s.logs_dir == "/data/logs"

    def test_logs_dir_tilde(self):
        s = Settings(data_root="~/hive")
        assert "~" not in s.logs_dir
        assert s.logs_dir.endswith("/hive/logs")


class TestLoadConfig:
    def test_load_v2_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "version: 2\n"
            "deps:\n"
            "  blast:\n"
            "    bin_dir: /opt/blast\n"
            "    default_evalue: 0.001\n"
            "  mafft:\n"
            "    bin_dir: /opt/mafft\n"
            "tools:\n"
            "  search:\n"
            "    columns: [name, size_bp]\n"
        )
        s = load_config(str(config_file))
        assert s.version == 2
        assert s.deps.blast.bin_dir == "/opt/blast"
        assert s.deps.blast.default_evalue == 0.001
        assert s.deps.mafft.bin_dir == "/opt/mafft"
        assert s.tools.search.columns == ["name", "size_bp"]

    def test_load_missing_file_uses_defaults(self):
        s = load_config("/nonexistent/config.yaml")
        assert s.version == CURRENT_CONFIG_VERSION
        assert s.deps.blast.default_evalue == 1e-5
