# Contributing

- Preserve raw scientific result CSVs; do not modify them in place.
- Write derived analyses to separate paths under `results/analysis/`.
- Record deterministic seeds and condition definitions for new experiments.
- Add integrity checks for row counts, unique conditions, and matched seeds where applicable.
- Do not commit decoder caches, virtual environments, temporary C2/WAV files, or LaTeX build junk.
- Keep manuscript claims tied to saved results and document any changed analysis separately.
