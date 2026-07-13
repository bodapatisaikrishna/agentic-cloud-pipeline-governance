# Cost-budget policy (§5.3): deny scale-ups whose projected marginal cost exceeds the
# remaining budget; always allow scale-downs (marginal cost <= 0). The caller computes
# projected_marginal_cost so OPA stays a pure decision function (DEVIATIONS D-021).
package acde.cost_budget

import rego.v1

result := {
	"allowed": true,
	"escalate": false,
	"reason": "scale-down or zero marginal cost",
	"policy_id": "cost_budget",
} if {
	input.context.projected_marginal_cost <= 0
}

result := {
	"allowed": true,
	"escalate": false,
	"reason": "within remaining budget",
	"policy_id": "cost_budget",
} if {
	input.context.projected_marginal_cost > 0
	input.context.projected_marginal_cost <= input.context.budget_remaining_units
}

result := {
	"allowed": false,
	"escalate": false,
	"reason": sprintf(
		"projected marginal cost %v exceeds remaining budget %v",
		[input.context.projected_marginal_cost, input.context.budget_remaining_units],
	),
	"policy_id": "cost_budget",
} if {
	input.context.projected_marginal_cost > input.context.budget_remaining_units
}
