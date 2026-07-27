# Finder interface supplement v2

Both prespecified paid slots completed exactly once and are comparison-eligible.
Each arm used Code Finder exactly once for each of the two repositories, made
no direct retrieval calls, used a unique cache scope, and recorded zero
cross-run cache-read tokens. The corrected runtime executed all four canonical
checkpoints in both arms, and the Haiku judge ran through `claude-1`.

The arms tied at 0.575. CLI used 165,745 outer tokens and cost $0.628063,
compared with MCP's 219,848 outer tokens and $0.815832. On this pair, CLI used
24.6% fewer outer tokens, 17.8% fewer combined outer-plus-Finder tokens, cost
23.0% less, and completed 7.4 seconds sooner. Sourcegraph does not report the
Finder subagent's dollar cost, so dollar comparisons cover outer model and
judge usage only.

Adding this valid pair to the two quality-eligible pilot pairs produces a
descriptive sample of three tasks. MCP's mean score is 0.7613 and CLI's is
0.6947, a CLI-minus-MCP mean difference of -0.0667 and a median difference of
zero. Across those three pairs, CLI used 748,121 combined tokens versus MCP's
962,191 and cost $1.762230 versus $2.361548.

The supplement cost $1.443895 in total, 60.0% below its $3.61 outer-cost
forecast. No v1 attempt or score is carried forward: its MCP run remains
operational evidence only because the old runtime staged three checkpoint
scripts under names that did not match the task's canonical verifier contract.

These results are descriptive. Three heterogeneous task pairs do not support
promotion or a general ranking of the MCP and CLI interfaces.
