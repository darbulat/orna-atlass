# Context and prompt evals

The context-builder contract tests use representative tasks and changed paths to prove that the
router selects the matching role, architecture notes, ADRs, specs and source files while excluding
secrets, binaries and unrelated domains. The fast eval validates the map before every CI test run.
