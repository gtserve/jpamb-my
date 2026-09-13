# JPAMB analyzer context

- The goal is to improve `syntactic_new.py`, a Python static analyzer for the Java
  programs in `cases/jpamb/cases`, and maximize its JPAMB score.
- Keep the portable `#!/usr/bin/env python3` shebang; this project requires
  Python 3.13 or later.
- The submitted artifact is `report.sexp`; it records the analyzer command,
  metadata, predictions, expected outcomes, and timings, but not Python source.
- A report must be regenerated after analyzer changes. The existing report was
  produced before the current Tree-sitter implementation and scored 50.376354
  out of 276 for behavior, with Time 100 and Categories 33.33.
- Each of the six JPAMB outcomes is an existential question: report it when
  some input can produce it. Several outcomes may be possible for one method.
- Categories are calibrated over all of their occurrences; their names do not
  imply a direction. Use direct 0% or 100% predictions only for proved facts.
- The preferred implementation direction is Tree-sitter Java with increasingly
  path-sensitive rules. Do not inspect `@Case` annotations to make predictions.
- The supplied Tree-sitter example analyzes the class body instead of the
  selected method body; do not copy that mistake.
- The current baseline parses the requested Java source, finds its method, and
  proves the narrow pattern where the complete body is `assert false;`. It
  correctly scores 6 out of 6 for `Simple.assertFalse`; other methods emit
  neutral 50% predictions.
- The prepared `.jpamb-eval` environment contains `tree-sitter` and
  `tree-sitter-java`. Use it to test, for example:
  `source .jpamb-eval/bin/activate && jpamb analyse ./syntactic.py`.
- Prioritize adding rules for `assert true` and normal completion, then guarded
  division, nullness, array bounds, calls, and loops.
