# Schema-compatibility policy (§5.3): compatible changes auto-allowed only when the drift is
# backward-compatible; breaking drift permits only containment (quarantine/block) plus an
# escalation notification.
package acde.schema

import rego.v1

compatible := {"allow_compatible", "apply_mapping"}

contain := {"quarantine_partition", "block_ingestion"}

result := {
	"allowed": true,
	"escalate": false,
	"reason": "backward-compatible schema change",
	"policy_id": "schema_compat",
} if {
	input.action.action_type in compatible
	input.context.schema_compat == "backward"
}

result := {
	"allowed": false,
	"escalate": true,
	"reason": "compatible action rejected: drift is not backward-compatible",
	"policy_id": "schema_compat",
} if {
	input.action.action_type in compatible
	input.context.schema_compat != "backward"
}

result := {
	"allowed": true,
	"escalate": true,
	"reason": "breaking drift contained; human notified",
	"policy_id": "schema_compat",
} if {
	input.action.action_type in contain
}
