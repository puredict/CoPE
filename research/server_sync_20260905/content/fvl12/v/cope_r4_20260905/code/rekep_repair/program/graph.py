"""Task graph and well-formedness predicates.

The task program is a directed graph over stage ids.  For a sequential ReKep
task it is a chain ``v_1 -> v_2 -> ... -> v_N``.  A repair splices a chain of
new nodes ``u_1 -> ... -> u_m`` between an anchor ``v_i`` and its successor,
replacing edge ``v_i -> v_{i+1}`` with
``v_i -> u_1 -> ... -> u_m -> v_{i+1}`` (Eq. ordered_insert / graph rewriting).

We keep the graph explicit so that the WellFormed / Acyclic / HasRestore
predicates of Sec. 5.5 can be checked before a repair is admitted.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


@dataclass
class TaskGraph:
    """Directed graph of stage ids.  Nodes are ids; edges are (src, dst)."""

    nodes: List[str] = field(default_factory=list)
    edges: Set[Tuple[str, str]] = field(default_factory=set)

    @classmethod
    def chain(cls, ids: List[str]) -> "TaskGraph":
        g = cls(nodes=list(ids))
        for a, b in zip(ids, ids[1:]):
            g.edges.add((a, b))
        return g

    def successors(self, node: str) -> List[str]:
        return [b for (a, b) in self.edges if a == node]

    def predecessors(self, node: str) -> List[str]:
        return [a for (a, b) in self.edges if b == node]

    def copy(self) -> "TaskGraph":
        return TaskGraph(nodes=list(self.nodes), edges=set(self.edges))

    def splice_after(self, anchor: str, new_ids: List[str]) -> "TaskGraph":
        """Return a new graph with ``new_ids`` inserted after ``anchor``.

        Replaces every edge (anchor -> succ) with
        anchor -> new_ids[0] -> ... -> new_ids[-1] -> succ.
        """
        g = self.copy()
        succs = g.successors(anchor)
        for s in succs:
            g.edges.discard((anchor, s))
        for nid in new_ids:
            if nid not in g.nodes:
                g.nodes.append(nid)
        g.edges.add((anchor, new_ids[0]))
        for a, b in zip(new_ids, new_ids[1:]):
            g.edges.add((a, b))
        for s in succs:
            g.edges.add((new_ids[-1], s))
        return g

    # --- WellFormed predicate components ---------------------------------
    def is_acyclic(self) -> bool:
        """Kahn's algorithm: acyclic iff a full topological order exists."""
        return self.topological_rank() is not None

    def topological_rank(self) -> Dict[str, int] | None:
        indeg = {n: 0 for n in self.nodes}
        adj = defaultdict(list)
        for a, b in self.edges:
            indeg[b] += 1
            adj[a].append(b)
        q = deque([n for n in self.nodes if indeg[n] == 0])
        rank: Dict[str, int] = {}
        r = 0
        while q:
            n = q.popleft()
            rank[n] = r
            r += 1
            for m in adj[n]:
                indeg[m] -= 1
                if indeg[m] == 0:
                    q.append(m)
        return rank if len(rank) == len(self.nodes) else None

    def is_connected_chain_from(self, start: str) -> bool:
        """Every node reachable from ``start`` and no branching dead-ends."""
        seen, q = set(), deque([start])
        while q:
            n = q.popleft()
            if n in seen:
                continue
            seen.add(n)
            q.extend(self.successors(n))
        return seen == set(self.nodes)
