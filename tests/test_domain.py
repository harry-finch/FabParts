"""Initial identity, stock and lifecycle rules."""

from uuid import uuid4

import pytest

from kipartmanager.domain.entities import DomainError, Inventory, Part, PartState, StockItem


def test_names_and_uuid_identity() -> None:
    part = Part(name=" NE555P ")
    assert part.name == "NE555P"
    assert part.id != Part(name="NE555P").id
    with pytest.raises(DomainError):
        Inventory(name=" \n ")


@pytest.mark.parametrize("quantity", [-1, 1.5, True, 2**63])
def test_invalid_stock(quantity: int) -> None:
    with pytest.raises(DomainError):
        StockItem(part_id=uuid4(), inventory_id=uuid4(), quantity=quantity)


def test_lifecycle_is_owned_by_domain() -> None:
    draft = Part(name="NE555P")
    identified = draft.transition(PartState.IDENTIFIED)
    assert draft.state == PartState.DRAFT
    assert identified.id == draft.id
    assert identified.transition(PartState.DEPRECATED).state == PartState.DEPRECATED
    with pytest.raises(DomainError):
        identified.transition(PartState.DRAFT)
    with pytest.raises(DomainError):
        identified.transition(PartState.IDENTIFIED)
