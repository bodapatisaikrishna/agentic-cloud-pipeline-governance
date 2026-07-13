package acde.rate_limit

import rego.v1

test_under_limit_no_denial if {
	not result with input as {"context": {"actions_last_10min": 4}}
}

test_at_limit_denied if {
	res := result with input as {"context": {"actions_last_10min": 5}}
	not res.allowed
}
