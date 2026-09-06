"""Deterministic method-neutral paths and relations using the common invariants."""

from .parsers import parse_generic_proposal
from .state_engine import TransactionError, _apply_neutral


def apply_generic(ledger, proposal, *, evidence_records=(), context=None, authority="user",
                  event_id=None, event_timestamp=None):
    proposal = parse_generic_proposal(proposal)
    return _apply_neutral(ledger, proposal,
        creates=proposal["creates"], writes=proposal["writes"], checks=proposal["assertions"],
        relation_additions=proposal["relation_additions"], relation_removals=proposal["relation_removals"],
        evidence_links=proposal["evidence_links"], evidence_records=evidence_records,
        context=context, authority=authority, event_id=event_id, event_timestamp=event_timestamp,
        carrier="generic")


apply_generic_transaction = apply_generic
