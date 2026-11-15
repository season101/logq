# Paper draft

`main.tex` uses the template the ICSE 2027 Research Track requires: the IEEE conference proceedings template, `\documentclass[10pt,conference]{IEEEtran}` without `compsoc`/`compsocconf`, at most 10 pages of main text plus 2 pages of references, double-anonymous review ([call for papers](https://conf.researchr.org/track/icse-2027/icse-2027-research-track), read 2026-11-15). ICSE 2026 used the ACM format; 2027 switched to IEEE.

The bibliography is `../references.bib`, styled with `IEEEtran.bst`. Red `[TODO: ...]` marks (the `\todo{}` macro) are left for the author: pilot numbers and judgments to confirm.

## Building

No PDF is committed: this machine has no LaTeX install, and the local `texlive/texlive:latest-small` Docker image lacks `IEEEtran.cls`. The draft was compiled in that image with a stand-in `article` class: 9 pages, all 25 sources cited, no LaTeX or BibTeX warnings. To build the real thing, either:

- upload `main.tex` and `../references.bib` to Overleaf (it ships IEEEtran) and fix the `\bibliography` path, or
- install the class into the container first (downloads it from CTAN):

```bash
cd docs/advances && tar c paper references.bib | docker --context desktop-linux run -i --rm texlive/texlive:latest-small sh -c 'mkdir /w && tar x -C /w && cd /w/paper && tlmgr install ieeetran >&2 && pdflatex main >&2 && bibtex main >&2 && pdflatex main >&2 && pdflatex main >&2 && cat main.pdf' > paper/main.pdf
```
