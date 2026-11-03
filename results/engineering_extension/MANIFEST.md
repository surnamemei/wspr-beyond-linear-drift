# Engineering result provenance

The CSV files in this directory are compact copies of the saved source tables. The source paths below are **local archival references** relative to the original research checkout; those Gate directories and raw inputs are not included in this public repository and the paths are not download links. No external dataset URL is implied.

| Public file | Local source record | SHA-256 |
|---|---|---|
| `gate0a_summary.csv` | `results/gate0a_screen_20261103_exec_copy/cell_summary.csv` | `6eea1c1371c8c17a0bead287d60347b347bba2d4edc84d54a998dbb5bdc6d82f` |
| `gate0b_descriptor_scores.csv` | `results/gate0b_gate1a_20261103/descriptor_audit/reconciled_scores.csv` | `3f4adfab03acd7aa20b231eb6fd4f42c37e72e5d01c82e54942293629417fe90` |
| `gate1b_paired.csv` | `results/gate1b_integrity_20261103/gate1b_paired_v2.csv` | `361befd02b741898ec4e7e45b448dc1f074e097002fef6ed2ea66891587f8d6c` |
| `gate1c_factorial.csv` | `results/gate1c_factorial_20261103/factorial_cells.csv` | `5110ac0c88aa16579e2b1cd2b976cb26ddbcaf39c2b2e2dad6a06fcd9f57c423` |
| `gate2b_summary.csv` | `results/gate2b_baselines_20261103/comparison_cells.csv` | `e922eed9a46fbe1e27b5d717aeaadd3feb327da77b9a033837c6e848a1fa5cb6` |
| `gate2c_signal_summary.csv` | `results/gate2c_execution_20261103_v3/signal_cells.csv` | `167c8b755f96eca13141fdc22ed0d812e39aa48f300fb10b666d3b132a0964f2` |
| `gate2c_noise_summary.csv` | `results/gate2c_execution_20261103_v3/null_cells.csv` | `cfa6393799d54f661fc5be8f133e3d18433918d3657137fd6f8decd33163269e` |
| `gate2c_multisignal_summary.csv` | `results/gate2c_execution_20261103_v3/multi_cells.csv` | `0bdb613261b6db27d1400e3b017c3b63f4a4f331b3022fc8a524b134c7fae060` |
| `gate2c_ordering_summary.csv` | `results/gate2c_execution_20261103_v3/ordering_cells.csv` | `747d2ce16c143ae32fac974ab51f87ff18117aa44a6dc3e0b9662c6cd6c631a9` |

`gate_summary.csv` is a concise editorial index derived from the sources above; it is not a trial-level dataset.

Gate 2C raw invocation outputs and input manifests remain local in `results/gate2c_execution_20261103_v2/`, `results/gate2c_execution_20261103_v3/`, and `results/gate2c_repair_20261103_v1/`. The complete run contains exactly 12,960 records: 12,559 verified reused invocations and 401 completed during resumption. Interrupted runs and STOP reports were preserved locally.

The uploaded Gate 2C summaries were generated from the complete Parser V2 reparse and independent comparison check; historical Gate 0A/1A wrong-message counts were revised by Parser V2. Do not use the superseded historical incorrect-message counts.

The earlier Zenodo archive identified in the repository predates this engineering extension; no new release or DOI is assigned here.
