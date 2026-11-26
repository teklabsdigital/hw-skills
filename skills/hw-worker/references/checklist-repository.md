# Repository checklist

The starting checklist for the project layout (ST0) and publication (ST13). The procedure is `references/repository.md`. The columns work as in the logical checklist (`references/checklist-logical.md`, How to use it). Switch names are in `references/packs.md` (Board-type switches).

Setup copies this file to `design/checklists/repository.md`, so `table_check.py checklists` counts its items with the others. Use the project's copy; it may have grown.

## Release items (PB-)

| ID | What to check | Authority | Stage | Script | Switch |
|---|---|---|---|---|---|
| PB-01 | Licences of copied library parts and 3D models allow publishing (each vendor's download terms) | vendor download terms, fetched | ST13 | none | always |
| PB-02 | Files readable by Windows users: line endings, path lengths, no names that differ only by case, no characters Windows forbids | user; platform rules | ST13 | none | always |
| PB-03 | Datasheet copyright note in `datasheets/README.md` | user | ST13 | none | always |
| PB-04 | Repository naming prefix asked | user | ST13 | none | always |
| PB-05 | Generated artefacts such as rule-check reports not committed | `.gitignore` | ST0, ST13 | `table_check.py writers` | always |
| PB-06 | Datasheets and text extracts kept; dead files removed; every committed file has a writer (a script, or hand-owned in the ownership record) | `design/ownership.csv` | ST13 | `table_check.py writers` | always |
| PB-07 | README: images asked for; lead with the real-board result when there is one; repository description and tags | user | ST13 | none | always |
| PB-08 | Confidentiality scan clean | `design/.private-terms`; scan rules | ST13 | `table_check.py scan` | always |
| PB-09 | Fresh-context "clone, build, compare" review offered | build output | ST13 | `build.py --twice` | always |
| PB-10 | No change to the visibility of any other repository | user | ST13 | none | always |
| PB-11 | Licence terms of every committed simulation model allow publishing; a model that does not is removed and named in `design/sim-models.csv` with its source | each maker's model licence, fetched | ST13 | none | always |
| PB-12 | Committed third-party documents (datasheets, application notes, standards) may be published; one that may not is removed and listed as "not committed" with its source and revision | each document's terms; user | ST13 | none | always |
