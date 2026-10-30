# Cover letter (template)

Fill in the bracketed fields before sending. Keep the claims in step with the manuscript: every
number below is quoted from it.

---

[Date]

[Editor's name]
Editor-in-Chief, [Journal name]

Dear [Editor's name],

We submit the manuscript "A Policy-Bounded Agentic Framework for Autonomous Governance of Cloud
Data Pipelines" for consideration as a [regular article / replication study] in [Journal name].

A recent proposal reports that four policy-gated LLM agents improve recovery time, cost and manual
workload when governing cloud data pipelines. It does not say whether those gains were measured
with a real model or a mock. We implemented the design and evaluated it in a 560-run campaign with a
live remote model, three non-LLM comparators and a mock-model arm. The results only partly support
the original claims:

- Under a deterministic mock, the same configuration recovers about three orders of magnitude
  faster and reports perfect decision correctness; with the live model it chose a correct mitigation
  in 42% of runs. Mock and live evaluations of one system lead to different conclusions.
- Manual interventions rose sixfold instead of falling, and two idealized non-LLM baselines
  recovered faster than the agents.
- After the campaign we found that the simulated on-call engineer rewarded repeated escalation,
  which accounts for most of the measured recovery-time gain. The manuscript reports this openly
  (Section VII-H) with generated numbers, and the corrected simulator is in the public repository.
- An adversarial corpus graded against an independent oracle exposed two contract-layer gaps; after
  the fixes, all 3,867 unsafe cases among 5,547 generated were contained (Wilson 95% lower bound
  0.9990).

We think the paper suits [Journal name] because [one sentence on the journal's scope, e.g. its
interest in empirical evaluation methodology and negative results]. Every table, figure and quoted
number is regenerated from the committed per-run data by one command, and the code, data and
pre-registered plan for a corrected re-run are public at
https://github.com/bodapatisaikrishna/agentic-cloud-pipeline-governance [and archived at DOI].

The manuscript has not been published and is not under review elsewhere. AI-assisted tools were used
as described in the acknowledgment; the authors take responsibility for all content. [Funding and
competing-interest statements, or "The authors declare no competing interests."]

Suggested reviewers (optional): [names, affiliations, emails, and why each is suitable].

Sincerely,
[Corresponding author's name], [ORCID]
[Affiliation, address, email]
