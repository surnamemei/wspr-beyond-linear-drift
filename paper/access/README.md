# IEEE Access submission working copy

This directory is independent of `paper/latex/` and `paper/arxiv/`. The scientific text, numerical values, seven composite figures, five tables, and 13 verified bibliography records were transferred from the current reviewed LaTeX draft. The official May 13, 2026 Access class and support files are staged locally.

Build from this directory with:

```text
pdflatex -interaction=nonstopmode -halt-on-error main.tex
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
```

The output is `main.pdf`. Do not compile against the earlier `paper/latex/` path. The PNG graphical-abstract draft is conceptual and is not included in the manuscript; its source is `figures/build_graphical_abstract.py`. The draft must not be presented as a measured-hardware diagram.

Build audit (2026-09-25): 9 pages; PDF 1,590,704 bytes; `main.tex` 29,823 bytes; seven figure environments; five table environments; 13 cited bibliography items; zero unresolved citations or labels; zero missing figures. The log contains 21 overfull-box warnings, with the same two 9.2679-pt title warnings and 505.12177-pt output-routine warnings in the distributed official template sample. All nine pages were rendered and inspected; figures, tables, references, acknowledgment, and biography are visible without clipping. A font-shape substitution warning for `T1/pcr/n/n` also remains.

The Access-only `figures/build_fig7_access.py` reproduces Fig. 7 from the same saved summary with only the six panel titles changed to `SNR =` and math-rendered minus signs. The plotted data and Wilson intervals are unchanged; prior figure copies were not overwritten.

Before submission, associate the confirmed ORCID with the author's submission account and verify that the public profile is populated; review the journal portal's current requirements and resolve the distributed class's placeholder publication footer and blank DOI label. The confirmed University of Sydney email is in the PDF. The Zenodo DOI identifies the archived software/data release; no article DOI, funding, member grade, or author photo has been invented.
