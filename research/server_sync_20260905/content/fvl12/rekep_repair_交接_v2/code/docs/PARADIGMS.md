# Three recovery paradigms (deliverable 9)

Precise names for what is actually implemented. **None of these are the
published ReKep or AgentChord systems** — they are controlled abstractions
implemented in this repo for isolation. Do not label results as "beats ReKep"
or "beats AgentChord" until real integrations exist.

| | **Precompiled full branch** | **Runtime template instantiation** | **Runtime operator synthesis** |
|---|---|---|---|
| Implementation | `OfflineFullCoveragePolicy`, `OfflineBudgetedPolicy` | `TemplateRepairPolicy` | `OnlineRepairPolicy` |
| Recovery structure created | Before execution | Before execution (as a template); instantiated at runtime | **At runtime, by search** |
| What is stored | Complete branch per event class | Complete operator sequence per event class | **Only atomic operators** (precondition/effect/cost) |
| Runtime decision | Which branch to activate | Which template to instantiate + parameterize | **Which operator sequence to construct** |
| Task graph rewritten? | No | Yes | Yes |
| Continuation captured? | No | Yes | Yes |
| Restore contract validated? | No | Yes | Yes |
| Handles novel composition? | No — one class per branch | No — one class per template | **Yes** — composes operators |
| Cost | Lowest latency; coverage limited by branch budget | Low latency; coverage limited by template set | Search cost; coverage limited by operator set + reachable goals |
| Fails when | Event class not anticipated | Event class has no template | No operator sequence reaches the goal (→ bounded safe fallback) |

## Where the distinction is measured

- `scripts/compare_known_event.py` — **control condition.** On anticipated
  single-class events, all three succeed. Online buys nothing here.
- `scripts/compare_novel_composition.py` — **the discriminating condition.**
  A compound disturbance (obstacle + slip, where the drop lands by the
  obstacle) has no prewritten branch or template. Only synthesis composes an
  interleaved plan and delivers without collision.

## Honest scope

The online system's operator library and event predicates are finite and fixed.
"Novel" here means a **novel composition of known operators under a
combination of known predicates** — it is not open-set event discovery. The
claim we can support is:

> Runtime operator synthesis covers combinations of disturbances that were
> never enumerated as branches or templates, using an operator library that
> grows linearly rather than a branch set that grows combinatorially.

Not: "online repair handles arbitrary unforeseen events."
