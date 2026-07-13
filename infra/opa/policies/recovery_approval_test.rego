package acde.recovery

import rego.v1

test_retry_auto_allowed if {
	res := result with input as {"action": {"action_type": "retry_with_backoff"}, "context": {}}
	res.allowed
	not res.escalate
}

test_rollback_with_prior_allowed if {
	res := result with input as {"action": {"action_type": "rollback"}, "context": {"has_prior_version": true}}
	res.allowed
}

test_rollback_without_prior_escalates if {
	res := result with input as {"action": {"action_type": "rollback"}, "context": {"has_prior_version": false}}
	not res.allowed
	res.escalate
}

test_escalate_to_human if {
	res := result with input as {"action": {"action_type": "escalate_to_human"}, "context": {}}
	res.escalate
}
