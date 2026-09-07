#!/usr/bin/env python3
"""Read-only transport boundary for the Nexus DV360 control-plane slice.

The transport owns retrieval only. It does not interpret DV360 semantics.
No OAuth, networking, credentials, or write methods exist in this module.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class DV360ReadSnapshot:
    """One transport result consumed by DV360ActualStateAdapter."""

    responses: dict[str, list[dict[str, Any]]]
    bindings: dict[str, dict[str, str]]
    captured_at: str
    pagination_complete: dict[str, bool]
    raw_snapshot_reference: str | None = None


@runtime_checkable
class DV360ReadTransport(Protocol):
    """Minimal read-only transport contract for future DV360 GET clients."""

    transport_version: str

    def read(self, *, account_context_id: str) -> DV360ReadSnapshot:
        """Return one complete/partial read snapshot for the supplied advertiser context."""
        ...


class FrozenFakeDV360ReadTransport:
    """Deterministic in-memory transport used until a real GET client exists."""

    transport_version = "dv360-frozen-fake-read-v1"

    def __init__(
        self,
        *,
        account_context_id: str,
        responses: dict[str, list[dict[str, Any]]],
        bindings: dict[str, dict[str, str]],
        captured_at: str,
        pagination_complete: dict[str, bool] | None = None,
        raw_snapshot_reference: str | None = None,
    ) -> None:
        if not account_context_id:
            raise ValueError("account_context_id is required")
        if not captured_at:
            raise ValueError("captured_at is required")

        self._account_context_id = str(account_context_id)
        self._responses = copy.deepcopy(responses)
        self._bindings = copy.deepcopy(bindings)
        self._captured_at = captured_at
        self._pagination_complete = copy.deepcopy(
            pagination_complete
            or {"campaign": True, "insertion_order": True, "line_item": True}
        )
        self._raw_snapshot_reference = raw_snapshot_reference

    def read(self, *, account_context_id: str) -> DV360ReadSnapshot:
        if str(account_context_id) != self._account_context_id:
            raise ValueError("Transport account context mismatch")

        return DV360ReadSnapshot(
            responses=copy.deepcopy(self._responses),
            bindings=copy.deepcopy(self._bindings),
            captured_at=self._captured_at,
            pagination_complete=copy.deepcopy(self._pagination_complete),
            raw_snapshot_reference=self._raw_snapshot_reference,
        )
