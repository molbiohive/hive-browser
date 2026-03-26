"""Tests for ChatStorage save/load/delete/list."""

from hive.chat.storage import ChatStorage


class TestChatStorage:
    def test_save_and_load(self, tmp_path):
        store = ChatStorage(str(tmp_path))
        msgs = [{"role": "user", "content": "hi"}]
        store.save("abc123", msgs, title="Test Chat")

        loaded = store.load("abc123")
        assert loaded is not None
        assert loaded["id"] == "abc123"
        assert loaded["title"] == "Test Chat"
        assert loaded["messages"] == msgs

    def test_load_missing(self, tmp_path):
        store = ChatStorage(str(tmp_path))
        assert store.load("nonexistent") is None

    def test_delete(self, tmp_path):
        store = ChatStorage(str(tmp_path))
        store.save("abc123", [])

        assert store.delete("abc123") is True
        assert store.load("abc123") is None
        assert store.delete("abc123") is False

    def test_list_chats(self, tmp_path):
        store = ChatStorage(str(tmp_path))
        store.save("aaa", [{"role": "user", "content": "one"}], title="First")
        store.save("bbb", [{"role": "user", "content": "two"}], title="Second")

        chats = store.list_chats()
        assert len(chats) == 2
        titles = {c["title"] for c in chats}
        assert "First" in titles
        assert "Second" in titles

    def test_list_chats_user_scoped(self, tmp_path):
        store = ChatStorage(str(tmp_path))
        store.save("aaa", [], user_slug="alice", title="Alice chat")
        store.save("bbb", [], user_slug="bob", title="Bob chat")

        alice_chats = store.list_chats(user_slug="alice")
        assert len(alice_chats) == 1
        assert alice_chats[0]["title"] == "Alice chat"

    def test_update_title(self, tmp_path):
        store = ChatStorage(str(tmp_path))
        store.save("abc123", [], title="Old")
        store.update_title("abc123", "New")

        loaded = store.load("abc123")
        assert loaded["title"] == "New"

    def test_save_preserves_existing_fields(self, tmp_path):
        store = ChatStorage(str(tmp_path))
        store.save("abc123", [{"role": "user", "content": "hi"}], title="Original")

        # Save again with new messages but no title
        store.save("abc123", [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hey"}])

        loaded = store.load("abc123")
        assert loaded["title"] == "Original"
        assert len(loaded["messages"]) == 2

    def test_new_chat_id(self, tmp_path):
        store = ChatStorage(str(tmp_path))
        id1 = store.new_chat_id()
        id2 = store.new_chat_id()
        assert isinstance(id1, str)
        assert len(id1) == 8
        # IDs should be hex strings
        int(id1, 16)
