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

# Containment actions (quarantine/block) have no schema_compat condition in the `contain` rule at
# all -- they fire on action_type alone. This locks that in explicitly: quarantine still
# allows+escalates even when schema_compat is "backward", not just "breaking". Without this test,
# someone tightening the rule to also require `schema_compat == "breaking"` (a plausible-looking
# "fix") would silently break recovery's ability to quarantine a partition pre-emptively, before
# compat has even been classified.
test_quarantine_allowed_regardless_of_compat_status if {
	res := result with input as {"action": {"action_type": "quarantine_partition"}, "context": {"schema_compat": "backward"}}
	res.allowed
	res.escalate
}
