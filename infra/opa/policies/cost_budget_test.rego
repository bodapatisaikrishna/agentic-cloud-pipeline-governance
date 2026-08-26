package acde.cost_budget

import rego.v1

test_scale_down_allowed if {
	result.allowed with input as {"context": {"projected_marginal_cost": -3, "budget_remaining_units": 10}}
}

test_within_budget_allowed if {
	result.allowed with input as {"context": {"projected_marginal_cost": 4, "budget_remaining_units": 10}}
}

test_over_budget_denied if {
	not result.allowed with input as {"context": {"projected_marginal_cost": 40, "budget_remaining_units": 10}}
}

test_over_budget_not_escalated if {
	res := result with input as {"context": {"projected_marginal_cost": 40, "budget_remaining_units": 10}}
	res.escalate == false
}

# Boundary: cost exactly equal to remaining budget. The rule is `<=`, so this must allow -- an
# off-by-one here (e.g. accidentally written as `<`) would silently deny every action that spends
# a pipeline's budget down to precisely zero, which is the common case for a well-tuned scale-up.
test_cost_exactly_equal_to_budget_allowed if {
	res := result with input as {"context": {"projected_marginal_cost": 10, "budget_remaining_units": 10}}
	res.allowed
	not res.escalate
}
