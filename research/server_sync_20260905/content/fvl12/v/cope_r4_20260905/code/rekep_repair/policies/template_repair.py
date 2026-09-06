"""Baseline: runtime *template instantiation* (not synthesis).

Same runtime machinery as OnlineRepairPolicy -- interrupt, splice, restore
gate, resume -- but candidates come from prewritten event-keyed templates
(CandidateGenerator) rather than operator search.  On a compound disturbance
the detector reports a single event class, so the template it instantiates
addresses only that class -- there is no prewritten compound sequence to fetch.

This isolates the distinction: template instantiation vs. operator synthesis.
"""

from __future__ import annotations

from ..repair.candidate_generator import CandidateGenerator
from .online_repair import OnlineRepairPolicy


class TemplateRepairPolicy(OnlineRepairPolicy):
    name = "template_repair"

    def _make_generator(self, params):
        return CandidateGenerator(params)
