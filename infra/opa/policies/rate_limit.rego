# Rate-limit runaway guard (§5.3): deny any action once an agent has taken >= 5 actions in the
# last 10 minutes.
package acde.rate_limit

import rego.v1

limit := 5

exceeded if input.context.actions_last_10min >= limit

result := {
	"allowed": false,
	"escalate": false,
	"reason": sprintf("rate limit: %v actions in the last 10 minutes", [input.context.actions_last_10min]),
	"policy_id": "rate_limit",
} if {
	exceeded
}
