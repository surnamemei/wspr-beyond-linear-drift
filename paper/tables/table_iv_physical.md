# Table IV — Representative synthetic oscillator decoder cells

All cells use injected SNR −31.0 dB and 100 trials. Residual RMS is the median across the cell's 100 projected trajectories.

| Noise family | Carrier (MHz) | Target σᵧ(1 s) | Median residual RMS (Hz) | Correct decodes/100 | P_decode |
| --- | ---: | ---: | ---: | ---: | ---: |
| White FM | 10 | 1×10⁻⁸ | 0.09746 | 53 | 0.53 |
| Flicker FM | 10 | 1×10⁻⁸ | 0.15570 | 22 | 0.22 |
| Random-walk FM | 10 | 1×10⁻⁸ | 0.34478 | 1 | 0.01 |
| Random-walk FM | 10 | 3×10⁻⁹ | 0.11282 | 43 | 0.43 |
| Random-walk FM | 14 | 3×10⁻⁹ | 0.14218 | 27 | 0.27 |
| Random-walk FM | 28 | 3×10⁻⁹ | 0.27776 | 2 | 0.02 |

Source: [physical decoder summary](../../results/csv/physical_oscillator_decoder/physical_oscillator_decoder_summary.csv) and [scaling audit](../../results/analysis/physical_oscillator_decoder/physical_oscillator_scaling_audit.csv). Carrier is the simulated fractional-to-Hz scaling parameter; these are not measured transmitters or hardware specifications.
