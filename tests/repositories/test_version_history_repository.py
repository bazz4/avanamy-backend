from types import SimpleNamespace
from unittest.mock import MagicMock

from avanamy.repositories.version_history_repository import VersionHistoryRepository


def test_create_version_history_increments(monkeypatch):
    fake_db = MagicMock()
    fake_db.add = MagicMock()
    fake_db.commit = MagicMock()
    fake_db.refresh = MagicMock()

    # First call, no existing versions
    monkeypatch.setattr(
        VersionHistoryRepository,
        "_get_latest_row",
        lambda db, api_spec_id: None,
    )
    first = VersionHistoryRepository.create(fake_db, api_spec_id="spec-1", changelog="init")
    assert first.version == 1

    # Next call, existing latest version=1
    monkeypatch.setattr(
        VersionHistoryRepository,
        "_get_latest_row",
        lambda db, api_spec_id: SimpleNamespace(version=1),
    )
    second = VersionHistoryRepository.create(fake_db, api_spec_id="spec-1", changelog="second")
    assert second.version == 2


def test_version_helpers():
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = SimpleNamespace(
        version=3
    )
    assert VersionHistoryRepository.get_latest_version_number(fake_db, "spec-1") == 3
    assert VersionHistoryRepository.latest_version_label(fake_db, "spec-1") == "v3"
    assert VersionHistoryRepository.next_version_number(fake_db, "spec-1") == 4
    assert VersionHistoryRepository.current_version_label_for_spec(fake_db, "spec-1") == "v3"


def test_list_version_history_for_spec():
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = ["v1", "v2"]
    versions = VersionHistoryRepository.list_for_spec(fake_db, "spec-1")
    assert versions == ["v1", "v2"]
