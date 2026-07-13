# Aggregating entrypoint (DEVIATIONS D-022): query data.acde.policy.decision with
#   {"input": {"action": <ProposedAction>, "context": {...}}}
# Returns {allowed, escalate, reason, policy_id} matching contracts.PolicyDecision.
# The rate-limit runaway guard is checked first for every agent.
package acde.policy

import rego.v1

import data.acde.cost_budget
import data.acde.recovery
import data.acde.schema

default decision := {
	"allowed": false,
	"escalate": true,
	"reason": "no matching policy; escalated for safety",
	"policy_id": "default",
}

within_rate if input.context.actions_last_10min < 5

# Runaway guard first, for all agents.
decision := {
	"allowed": false,
	"escalate": false,
	"reason": sprintf("rate limit: %v actions in the last 10 minutes", [input.context.actions_last_10min]),
	"policy_id": "rate_limit",
} if {
	input.context.actions_last_10min >= 5
}

# no_action is always permitted (below the rate limit).
decision := {"allowed": true, "escalate": false, "reason": "no action", "policy_id": "noop"} if {
	within_rate
	input.action.action_type == "no_action"
}

# Monitoring: observe / escalate only.
decision := {
	"allowed": true, "escalate": false,
	"reason": "anomaly raised", "policy_id": "monitoring",
} if {
	within_rate
	input.action.agent == "monitoring"
	input.action.action_type == "raise_anomaly"
}

decision := {
	"allowed": false, "escalate": true,
	"reason": "monitoring escalation", "policy_id": "monitoring",
} if {
	within_rate
	input.action.agent == "monitoring"
	input.action.action_type == "escalate"
}

# Optimization: cost-gated scaling; reprioritization is free.
decision := cost_budget.result if {
	within_rate
	input.action.agent == "optimization"
	input.action.action_type in {"scale_workers", "adjust_pool_slots"}
}

decision := {
	"allowed": true, "escalate": false,
	"reason": "pipeline reprioritization", "policy_id": "optimization",
} if {
	within_rate
	input.action.agent == "optimization"
	input.action.action_type == "reprioritize_pipeline"
}

# Recovery and schema delegate to their sub-policies.
decision := recovery.result if {
	within_rate
	input.action.agent == "recovery"
	input.action.action_type != "no_action"
}

decision := schema.result if {
	within_rate
	input.action.agent == "schema"
	input.action.action_type != "no_action"
}
