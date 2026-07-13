package acde.policy

import rego.v1

ctx(overrides) := object.union(
	{
		"projected_marginal_cost": 0,
		"budget_remaining_units": 100,
		"actions_last_10min": 0,
		"schema_compat": "backward",
		"has_prior_version": false,
		"pipeline_criticality": "normal",
		"mode": "acde",
	},
	overrides,
)

test_no_action_allowed if {
	res := decision with input as {"action": {"agent": "recovery", "action_type": "no_action"}, "context": ctx({})}
	res.allowed
	res.policy_id == "noop"
}

test_rate_limit_blocks_everything if {
	res := decision with input as {
		"action": {"agent": "optimization", "action_type": "scale_workers"},
		"context": ctx({"actions_last_10min": 6}),
	}
	not res.allowed
	res.policy_id == "rate_limit"
}

test_scale_workers_over_budget_denied if {
	res := decision with input as {
		"action": {"agent": "optimization", "action_type": "scale_workers"},
		"context": ctx({"projected_marginal_cost": 500, "budget_remaining_units": 10}),
	}
	not res.allowed
	res.policy_id == "cost_budget"
}

test_scale_down_allowed if {
	res := decision with input as {
		"action": {"agent": "optimization", "action_type": "scale_workers"},
		"context": ctx({"projected_marginal_cost": -5}),
	}
	res.allowed
}

test_recovery_rollback_without_prior_escalates if {
	res := decision with input as {
		"action": {"agent": "recovery", "action_type": "rollback"},
		"context": ctx({"has_prior_version": false}),
	}
	res.escalate
	res.policy_id == "recovery_approval"
}

test_schema_breaking_quarantine_allowed_and_escalates if {
	res := decision with input as {
		"action": {"agent": "schema", "action_type": "quarantine_partition"},
		"context": ctx({"schema_compat": "breaking"}),
	}
	res.allowed
	res.escalate
}

test_monitoring_escalate if {
	res := decision with input as {
		"action": {"agent": "monitoring", "action_type": "escalate"},
		"context": ctx({}),
	}
	res.escalate
	res.policy_id == "monitoring"
}
