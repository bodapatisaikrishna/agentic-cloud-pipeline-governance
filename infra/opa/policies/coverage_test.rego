# Property test: every legitimate (agent, action_type) pair reaches a real policy branch --
# never silently falls through to `default decision` (which would mean a real ProposedAction gets
# an unintended "escalated for safety, reason: no matching policy" response instead of the branch
# actually written for it). Found while auditing for this coverage: rate_limit.rego's whole
# module was unreachable dead code (main.rego duplicated its logic inline instead of delegating),
# and 7 of these 18 combinations had never been exercised by any test at all.
#
# This list must mirror src/acde/contracts/actions.py::ACTION_TYPES exactly (that's the runtime
# source of truth -- a ProposedAction can't even be constructed outside this set). If this test
# fails after adding a new action_type in Python, the fix belongs in main.rego or the relevant
# sub-policy first, then add the entry here.
package acde.policy

import rego.v1

action_type_matrix := [
	{"agent": "monitoring", "action_type": "raise_anomaly"},
	{"agent": "monitoring", "action_type": "escalate"},
	{"agent": "monitoring", "action_type": "no_action"},
	{"agent": "optimization", "action_type": "scale_workers"},
	{"agent": "optimization", "action_type": "adjust_pool_slots"},
	{"agent": "optimization", "action_type": "reprioritize_pipeline"},
	{"agent": "optimization", "action_type": "no_action"},
	{"agent": "schema", "action_type": "allow_compatible"},
	{"agent": "schema", "action_type": "apply_mapping"},
	{"agent": "schema", "action_type": "quarantine_partition"},
	{"agent": "schema", "action_type": "block_ingestion"},
	{"agent": "schema", "action_type": "no_action"},
	{"agent": "recovery", "action_type": "retry_with_backoff"},
	{"agent": "recovery", "action_type": "replay"},
	{"agent": "recovery", "action_type": "rollback"},
	{"agent": "recovery", "action_type": "partial_recompute"},
	{"agent": "recovery", "action_type": "escalate_to_human"},
	{"agent": "recovery", "action_type": "no_action"},
]

test_every_legitimate_action_reaches_a_real_decision if {
	every combo in action_type_matrix {
		res := decision with input as {
			"action": {"agent": combo.agent, "action_type": combo.action_type},
			"context": ctx({"has_prior_version": true}),
		}
		is_boolean(res.allowed)
		is_boolean(res.escalate)
		is_string(res.reason)
		res.reason != ""
		is_string(res.policy_id)
		res.policy_id != ""
		res.policy_id != "default"
	}
}

test_action_type_matrix_size_matches_the_contract if {
	# 3 (monitoring) + 4 (optimization) + 5 (schema) + 6 (recovery) = 18, per ACTION_TYPES.
	count(action_type_matrix) == 18
}
