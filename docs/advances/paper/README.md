# Paper draft

`main.tex` uses the template the ICSE 2027 Research Track requires: the IEEE conference proceedings template, `\documentclass[10pt,conference]{IEEEtran}` without `compsoc`/`compsocconf`, at most 10 pages of main text plus 2 pages of references, double-anonymous review ([call for papers](https://conf.researchr.org/track/icse-2027/icse-2027-research-track), read 2026-11-15). ICSE 2026 used the ACM format; 2027 switched to IEEE.

The bibliography is `../references.bib`, styled with `IEEEtran.bst`. No red `[TODO: ...]` marks (the `\todo{}` macro) remain; the judgments in the Discussion and Conclusion are the author's. The AI use statement is not in the paper; per the class instruction it is a separate front cover, `cover.tex` (build it the same way with `cover` in place of `main`, no BibTeX). Pilot numbers are filled in from the TeamMatch write-up (`docs/advances/logq-pilot.md` at TeamMatch commit `3616eb4`).

## Building

No PDF is committed: this machine has no LaTeX install, and the local `texlive/texlive:latest-small` Docker image lacks `IEEEtran.cls`. The draft was compiled in that image with a stand-in `article` class set to IEEEtran's text and column widths, Times, and a Courier-width typewriter font: 5 pages (also with a shorter text height and a small-print bibliography), the 6 sources it cites listed (the other 19 verified entries stay in the bib, uncited), no overfull boxes, no BibTeX warnings. That stand-in reproduces the Fig. 1 overflow Overleaf reported but not every IEEEtran underfull box, so check the real compile. To build the real thing, either:

- upload `main.tex` and `../references.bib` to Overleaf (it ships IEEEtran) and fix the `\bibliography` path, or
- install the class and the Courier font into the container first (downloads both from CTAN; without `courier`, every `\texttt` comes out blank):

```bash
cd docs/advances && tar c paper references.bib | docker --context desktop-linux run -i --rm texlive/texlive:latest-small sh -c 'mkdir /w && tar x -C /w && cd /w/paper && (tlmgr install ieeetran courier || tlmgr install ieeetran courier) >&2 && pdflatex main >&2 && bibtex main >&2 && pdflatex main >&2 && pdflatex main >&2 && cat main.pdf' > paper/main.pdf
```

## To do (author)

- Add a `README.md` to the logq repository on GitHub that describes logq and links the literature-search record, `docs/advances/search-log.md` and `docs/advances/source-matrix.md`. The paper no longer links them, and the brief asks for a link to the search results. The repo is private, so it also has to be made public (or shared with the instructor) for the link to work.
