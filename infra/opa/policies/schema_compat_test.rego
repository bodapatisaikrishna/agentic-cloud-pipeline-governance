package acde.schema

import rego.v1

test_compatible_backward_allowed if {
	res := result with input as {"action": {"action_type": "apply_mapping"}, "context": {"schema_compat": "backward"}}
	res.allowed
	not res.escalate
}

test_compatible_breaking_rejected if {
	res := result with input as {"action": {"action_type": "allow_compatible"}, "context": {"schema_compat": "breaking"}}
	not res.allowed
	res.escalate
}

test_quarantine_allowed_and_escalated if {
	res := result with input as {"action": {"action_type": "quarantine_partition"}, "context": {"schema_compat": "breaking"}}
	res.allowed
	res.escalate
}
