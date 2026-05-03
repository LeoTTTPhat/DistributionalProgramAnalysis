# DistributionalProgramAnalysis

Smoke-test prototype for the Distributional Program Analysis NIER paper.

Run the deterministic artifact check with:

```sh
make smoketest
```

The command writes a reproducible run under `runs/smoketest/`, including
the fixed sample programs, per-sample invariants, posterior survival rates,
and `result.json`. The current smoke-test results are recorded in
`main.tex`.
