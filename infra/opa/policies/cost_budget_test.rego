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
