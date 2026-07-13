# Recovery-approval policy (§5.3): auto-allow safe recoveries; rollback only with a prior
# version; escalate destructive/unknown or explicit human escalation.
package acde.recovery

import rego.v1

auto := {"retry_with_backoff", "replay", "partial_recompute"}

result := {
	"allowed": true,
	"escalate": false,
	"reason": "auto-approved recovery action",
	"policy_id": "recovery_approval",
} if {
	input.action.action_type in auto
}

result := {
	"allowed": true,
	"escalate": false,
	"reason": "rollback to an existing prior version",
	"policy_id": "recovery_approval",
} if {
	input.action.action_type == "rollback"
	input.context.has_prior_version
}

result := {
	"allowed": false,
	"escalate": true,
	"reason": "rollback requested but no prior version exists",
	"policy_id": "recovery_approval",
} if {
	input.action.action_type == "rollback"
	not input.context.has_prior_version
}

result := {
	"allowed": false,
	"escalate": true,
	"reason": "escalated to human by the recovery agent",
	"policy_id": "recovery_approval",
} if {
	input.action.action_type == "escalate_to_human"
}
