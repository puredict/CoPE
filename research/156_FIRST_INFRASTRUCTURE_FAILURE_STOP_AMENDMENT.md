# First infrastructure failure stop amendment

Date: 2026-08-04
Status: frozen before live formal calls

## Gap

Timeout, HTTP/transport outage, or an ambiguous interrupted call invalidates an
entire formal run under the existing preregistration. The runners previously
persisted such a failed cell but continued later calls, even though no later
outcome could restore validity.

## Amendment

For both occurrence and embodied v2 runners:

1. persist the failed result cell in the normal fsynced journal;
2. exclusively create and fsync `05_INFRASTRUCTURE_STOP.txt`;
3. record the failed cell, failure class, `resume_forbidden=true`, and
   `provider_calls_after_stop=0`;
4. immediately exit with code 4 before any later provider call;
5. on any later `--resume`, detect the stop marker before credential access and
   return code 4 without a provider call.

Response parse/schema/semantic failures remain method outcomes and do not
trigger this stop. Only the preregistered infrastructure markers do.

## Consequence

An infrastructure-invalid partial run is preserved and cannot be completed or
mined for a favorable suffix. A new run after infrastructure repair requires a
new explicit preregistration rather than bypassing the marker with `--resume`
or a replacement directory.

This reduces the maximum wasted spend after a decisive infrastructure failure
from the remainder of 200/400 calls to zero. It does not change a model result,
hypothesis, arm, prompt, threshold, or valid-run sample size.
