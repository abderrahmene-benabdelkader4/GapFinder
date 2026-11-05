# GapFinder

Find credible research gaps in the literature you care about, with the evidence attached.
Type a topic (or add your PDFs), let the app read the papers, and review gap candidates that each point to the exact sentences and pages that support them.

## Quick start

1. Install Python 3.12 (3.10 to 3.13 also work). Get a free Groq key at console.groq.com.
2. **Windows:** double-click `run.bat`. **macOS/Linux:** run `./run.sh`. The first start installs everything (a few minutes) and opens the app in your browser.
3. In the app: **Settings** -> paste your Groq key -> *Test Groq* -> *Save*.
4. **1 · Build corpus** -> type your topic -> *Search* -> *Add selected papers* -> *Build corpus*. (No key yet? Press *Try the demo*.)
5. **2 · Explore gaps** -> read the cards, press **Keep / Later / Dismiss**, add notes.
6. **3 · Ask the literature** for cited answers, **4 · Export** for a report, CSV and BibTeX.

Your projects and settings live in `~/GapFinder` (set `GAPFINDER_HOME` to change). Updating the app never touches them.

## How to read a gap card
* **Type**: method never tried on a problem, setting never studied with a problem, conflicting results, or future work nobody has done.
* **Evidence**: the sentences (with page and a link to the paper) that make it a candidate. A statement is only kept if its sentence really exists in the paper.
* **Confidence**: how likely the gap is to survive more papers. Low confidence means it may just reflect papers you have not added.
* **Already done elsewhere?** A quick OpenAlex check. It looks at the top 5 results only: a lead, not proof.
* **A gap always means "not found in this corpus", never "nobody has done it".** Verify before you build on it.

## Honest expectations
* Quality depends on the papers and the model. Check the **Extraction quality** panel after each build: it shows how many of the model's statements were backed by a real sentence. If it is low, use a larger model (Settings) or check the PDFs.
* Papers without an open-access PDF are read from their abstract only (marked in the table). Abstract-only corpora give shallower gaps: add the PDFs of the key papers.
* Scanned PDFs have no text layer and are skipped (use OCR, e.g. `ocrmypdf`, first).
* Free Groq accounts have daily limits. When you hit one, the build **pauses and keeps its progress**; press *Resume* later.
* Gap detection is rule-based and works best on method/dataset/result-style papers (empirical computer science and similar). Other fields will give fewer, weaker gaps.

## Troubleshooting
| Message | What to do |
|---|---|
| "Groq rejected the API key" | Settings -> paste the key again (starts with `gsk_`) |
| "model ... is not available" | Settings -> *Test Groq* shows a suggested model; copy it into Model and Save |
| "usage limit reached ... Resume later" | Wait, or pick another model; progress is saved |
| "full text unavailable" on a paper | Publisher blocks the download: add the PDF yourself in section B |
| Very few gaps | Add more papers on the topic, use "Key sections" depth, and clean up names in the Build page |

## Optional: Neo4j
Settings -> *Use Neo4j* -> URI/user/password -> *Test Neo4j* -> Save. The graph is then stored in Neo4j (Cypher queries do the detection) and you can explore it in Neo4j Browser:
`MATCH (n {project:'my-project'})-[r]->(m) RETURN n,r,m LIMIT 100`. Without Neo4j the app uses an equivalent built-in engine.

## For developers and the thesis
* `research_app.py` is the thesis workbench (conditions V/G/H, blinded rating via `annotate_app.py`, withholding experiment). Commands: `python cli.py --help`.
* Tests (all offline): `selftest.py` (16), `selftest_app.py` (26), `selftest_real.py` (37), `selftest_ui.py` (23), `selftest_cypher.py` (7, needs `falkordblite`, Linux/macOS).

### What the tests prove, and what they do not
Proven: the full pipeline (search -> download -> parse -> extract -> graph -> gaps) through the **real Groq SDK and real HTTP** against fake servers that return rate limits, daily limits, malformed/truncated JSON, bad keys, retired models, paywall pages, corrupt PDFs; resume after a crash or limit; the Cypher detectors on a **real openCypher engine** (FalkorDB) with the same results as the Python engine; hard PDF layouts (two columns, running headers, hyphenation, rotated stamps); concurrent status polling; the whole UI driven like a user.
**Not verified by the author:** real Groq answers (extraction quality on real papers), the live OpenAlex service, a real Neo4j server (the Cypher passed on FalkorDB, which is openCypher but not Neo4j: run `python selftest.py --neo4j` once), real publisher PDFs, `sentence-transformers`. Run one real topic with 10 to 15 papers and read the Extraction quality panel before trusting a big run.
