"""Canonical slot naming.

Both arms must be able to map their own slot ids back to the task's canonical
vocabulary (`g_milk`, `g_butter`, `c_no_collision`, ...). This is *not* a CoPE
advantage: giving FSR-PC this helper is what keeps it a strong baseline rather
than an artificially forgetful one. What differs between the arms is whether
the persistent *identity* survives -- not whether the method can name things.

    g_butter                -> g_butter        (untouched)
    g_butter@basket_A       -> g_butter        (CoPE override cover)
    g_butter#r1             -> g_butter        (FSR-PC regeneration re-mint)
    g_butter#r1@basket_A    -> g_butter
"""
from __future__ import annotations

from typing import Iterable, List, Optional


def canonical_id(slot_id: str) -> str:
    """Strip regeneration (`#r<k>`) and override (`@<target>`) decorations."""
    return slot_id.split("@", 1)[0].split("#", 1)[0]


def canonical_ids(slot_ids: Iterable[str]) -> List[str]:
    return sorted({canonical_id(s) for s in slot_ids})
