"""Tests for Repository pattern covering store/repository.py."""
import pytest


class TestRepository:
    def test_create_and_get(self):
        from fuxi.store.repository import ItemRepository
        repo = ItemRepository()
        item_id = repo.create(
            raw_text="Repo test memory",
            drawer_id="default",
            importance=0.5,
            source="test",
        )
        assert item_id
        item = repo.get(item_id)
        assert item is not None
        assert item["raw_text"] == "Repo test memory"

    def test_list(self):
        from fuxi.store.repository import ItemRepository
        repo = ItemRepository()
        items = repo.list(limit=10)
        assert isinstance(items, list)

    def test_update(self):
        from fuxi.store.repository import ItemRepository
        repo = ItemRepository()
        item_id = repo.create(
            raw_text="Update test",
            drawer_id="default",
            importance=0.3,
            source="test",
        )
        result = repo.update(item_id, importance=0.9)
        assert result is True
        updated = repo.get(item_id)
        assert updated["importance"] == 0.9

    def test_soft_delete(self):
        from fuxi.store.repository import ItemRepository
        repo = ItemRepository()
        item_id = repo.create(
            raw_text="Delete test",
            drawer_id="default",
            importance=0.5,
            source="test",
        )
        result = repo.delete(item_id, soft=True)
        assert result is True
        item = repo.get(item_id)
        assert item is not None
        assert item.get("archived") == 1

    def test_count(self):
        from fuxi.store.repository import ItemRepository
        repo = ItemRepository()
        total = repo.count()
        assert total >= 0
        with_drawer = repo.count(drawer_id="default")
        assert with_drawer <= total

    def test_create_no_table_raises(self):
        from fuxi.store.repository import Repository
        repo = Repository()
        with pytest.raises(ValueError):
            repo.create(data="test")

    def test_get_nonexistent(self):
        from fuxi.store.repository import ItemRepository
        repo = ItemRepository()
        item = repo.get("nonexistent-id-12345")
        assert item is None

    def test_update_nonexistent(self):
        from fuxi.store.repository import ItemRepository
        repo = ItemRepository()
        result = repo.update("nonexistent-id", importance=0.5)
        assert result is False  # rowcount == 0 when item doesn't exist

    def test_delete_nonexistent(self):
        from fuxi.store.repository import ItemRepository
        repo = ItemRepository()
        result = repo.delete("nonexistent-id")
        assert result is False  # rowcount == 0 when item doesn't exist

    def test_json_serialization(self):
        from fuxi.store.repository import ItemRepository
        repo = ItemRepository()
        item_id = repo.create(
            raw_text="JSON test",
            drawer_id="default",
            tags=["test", "json"],
            collaborators=["user1"],
            source="test",
        )
        item = repo.get(item_id)
        assert isinstance(item["tags"], list)
        assert "test" in item["tags"]
