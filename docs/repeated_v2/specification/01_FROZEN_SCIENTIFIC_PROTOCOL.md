# Frozen Scientific Protocol
## Repeated-Interruption Planning under History Pressure v2

### Research question

Does local editing of a persistent commitment ledger preserve the correct planning problem and downstream execution better than full state/plan reconstruction as task history and interruptions accumulate?

### Primary estimand

Paired absolute risk difference in final active-task success at the fourth interruption in the learned-VLA protocol:

\[
\Delta =
P(Y_{\mathrm{CoPE},K=4}=1)
-
P(Y_{\mathrm{primary\ nonpersistent},K=4}=1).
\]

The primary non-persistent comparator is selected and frozen on a disjoint development split.

### Experimental unit

One master session:

```text
task_id
+ initial_state_id
+ policy_seed
+ master_event_schedule
```

Every method receives the same master specification and runs its own independent environment/state trajectory.

### Continuous-history design

A method is run once through the complete event stream. Results at K=0,1,2,4,8 are checkpoints from the same trajectory. This is essential: errors must accumulate rather than being erased by restarting a fresh K-specific episode.

### Protocols

Controlled protocol:
- eight events;
- accurate structured public event evidence;
- deterministic/privileged execution allowed;
- labeled mechanism evidence only.

Learned-VLA protocol:
- four events;
- same raw observation and public evidence substrate for all methods;
- no hidden cause;
- non-privileged learned policy required.

### Methods

Primary non-oracle methods:

1. CoPE typed persistent edit.
2. Information-equivalent generic persistent transaction.
3. Full semantic-state regeneration.
4. Full-history replanning.
5. Retrieval-augmented replanning.
6. Free-text summary-memory replanning.
7. Skill-local replanning.
8. Classical PDDL/BT-style execution monitoring.

Oracle persistent update is an upper bound only.

### Information conditions

Primary: evidence matched.
Secondary: token matched.

The treatment is the representation and output interface, not access to hidden truth or a stronger model.

### Event families

The full schedule must cover:
- physical grounding shift;
- temporary infeasibility and restoration;
- persistent user preference;
- goal replacement/cancellation;
- repeated semantic goal with a fresh occurrence.

### Primary success definition

A trajectory succeeds only if, after the final scheduled event:
- all active achievement commitments are satisfied;
- no retired/cancelled/superseded occurrence was intentionally executed;
- hard requirements were not violated;
- unaffected verified progress was preserved;
- no timeout/manual intervention occurred.

### Key mechanism outcomes

- planning-problem fidelity;
- unrelated commitment corruption;
- completed-step regression;
- wrong-occurrence execution;
- stale/invalid restoration;
- redundant actions.

### Statistical tests

Primary:
- paired risk difference;
- master-session cluster bootstrap;
- exact McNemar.

Scaling:
- method × log2(K+1) degradation interaction or preregistered bootstrap fallback.

CoPE vs generic:
- one-sided non-inferiority with -5 percentage-point margin.

### Success gates

All must hold for full runtime-claim GO:
- at least +10 percentage points over frozen primary non-persistent comparator at K=4;
- lower 95% paired CI > 0;
- flatter degradation;
- no more than half the comparator's corruption and regression;
- higher pre-execution planning fidelity;
- non-inferior to generic persistent edit;
- no extra hidden information or event-level reasoner calls.

### Interpretation hierarchy

If CoPE and generic persistent edit tie:
- support persistent responsibility structure;
- attribute compactness/direct validation/atomicity to typed carrier;
- do not claim typed semantic superiority.

If only symbolic/control protocol succeeds:
- claim mechanism support only;
- do not claim learned-VLA improvement.

If token cost improves without execution:
- no runtime behavioral claim.
