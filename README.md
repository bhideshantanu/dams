# America's Dams

An interactive look at every dam in the National Inventory of Dams (NID): when each was
built, how old it is, what it's for, who owns it, and how high-hazard dams are managed,
state by state.

Live page (once set up): **https://shantanubhide.com/dams/**

## What's on the page

For everyone
- **Time-lapse map:** press Play to watch about 72,700 dams with a known completion year
  appear, 1850 to today, with a running count and the per-decade chart filling in.
- **Color by age or hazard potential**, with hover details for any dam (name, river,
  year, height, storage, purpose, owner type, NID ID).
- **Pick a state** to zoom in. Every number and chart on the page switches to that state.
- **Dams near me:** finds the five closest dams using the browser's location. The
  location never leaves the visitor's browser.
- **Charts:** dams per decade, the "aging wave" (share 50+ years old, 1980–2050), primary
  purposes, and owner types.
- **Removals:** a third map mode shows the 2,338 dams American Rivers has recorded as
  removed (1912–2025) over the dams still standing, with hover details (year removed,
  year built, height, original use, reasons, reported river miles reopened), a
  removals-per-year chart, reasons, and a removals column in the state scorecard.
- **Zoom and pan:** + and − buttons, pinch, Ctrl/⌘ + scroll, drag to pan; picking a
  state zooms to it.
- **Save image:** a 2400 × 2400 PNG sized for LinkedIn, for the current state, color mode
  and year.

For dam safety professionals
- High-hazard figures: how many have an Emergency Action Plan, condition ratings, and
  inspection recency.
- High-hazard dams by decade completed.
- **State scorecard:** sortable, clickable, and downloadable as a CSV.

## How it works

| Part | File | What it does |
|---|---|---|
| Data script | `scripts/build_dams.py` | Reads the NID national CSV and writes the three files in `data/`. |
| Data files | `data/dams.json`, `data/names.json`, `data/removals.json`, `data/summary.json` | Map positions and attributes, dam names (loaded only when someone hovers), removed dams, and national/state statistics. |
| Removal source | `sources/ARDamRemovalList_Figshare_Oct2026.csv` | The American Rivers Dam Removal Database. The data script reads the newest file in this folder. |
| Monthly robot | `.github/workflows/refresh-data.yml` | On the 3rd of each month, GitHub downloads the latest NID file, reruns the data script, and saves any changes. |
| Web page | `index.html` | Everything visitors see. GitHub Pages hosts it. |

`assets/states.json` holds the state outlines, and `scripts/albers.py` is the map
projection (the same ones the salt tracker uses).

## Setup

The data files are already built, so the page works as soon as it is uploaded. See the
step-by-step deployment guide in the chat, or in short:

1. Create a public repository named `dams` and upload everything in this folder.
2. Create `.github/workflows/refresh-data.yml` by hand (Add file → Create new file) if
   the upload skipped the hidden `.github` folder.
3. **Settings → Actions → General → Workflow permissions → Read and write permissions.**
4. **Settings → Pages → Deploy from a branch → main / (root).**
5. Visit https://shantanubhide.com/dams/.

No API key is needed.

## Updating the removal data (once a year)

American Rivers updates its database annually on figshare
(https://doi.org/10.6084/m9.figshare.5234068). When a new version comes out, download the
CSV and upload it into the `sources` folder (keep the `ARDamRemovalList` start of the
file name). Then run **Refresh dam data** from the Actions tab. The script picks the
newest file automatically. You can delete the old file afterwards.

The data is licensed CC BY 4.0: anywhere it appears, including maps and shared images,
American Rivers must be credited with the DOI link. The page, the saved images and the
CSV download already do this.

## Updating the data by hand (optional)

```bash
python scripts/build_dams.py path/to/nation.csv
```

Download `nation.csv` from https://nid.sec.usace.army.mil/api/nation/csv. Needs Python 3.10+
with pandas and numpy (`pip install -r requirements.txt`).

To preview locally: `python -m http.server 8000` in this folder, then open
http://localhost:8000. Double-clicking `index.html` won't work, because browsers block
pages opened from a file from reading the data files.

## Method notes

- **Counting:** associated structures (saddle dams and dikes listed under a main dam) are
  dropped, so each dam counts once: 91,684 dams in the Oct 30, 2026 data.
- **Age:** age = data year − year completed. The year is unknown for 18,961 dams (21%),
  which are left out of age figures but counted in totals.
- **Hazard potential** (federal guidelines): High = failure would probably cause loss of
  life; Significant = no probable loss of life but economic, environmental or lifeline
  damage; Low = little loss beyond the owner's property. It describes consequences, not
  condition.
- **Condition, inspections and EAPs** are self-reported to the NID and often incomplete.
  They are shown only as totals, never per dam.
- The map shows the lower 48. Alaska, Hawaii, Puerto Rico and Guam are in every total.

## If something goes wrong

- **Monthly run shows a red X:** open it on the Actions tab and read the last lines. If
  the NID download failed, nothing was changed; the next month's run will try again, or
  click **Run workflow** to retry now.
- **Page says "The data didn't load":** check that the `data` folder with its three
  files is in the repo.

Data: [National Inventory of Dams](https://nid.sec.usace.army.mil/), U.S. Army Corps of
Engineers; American Rivers. 2026. Raw Dataset – ARDamRemovalList_Figshare_Oct2026.
figshare. https://doi.org/10.6084/m9.figshare.5234068 (CC BY 4.0). An independent
analysis of public data, not an official product.
