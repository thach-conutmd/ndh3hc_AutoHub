# ndh3hc_AutoHub
Ngo Huu Dat
# AutoHub

Windows desktop app (PySide6) that automates the ECU variant workflow: it reads
the Master Sheet, ECU Info Sheet and System Matrix Excel files, manages variant
rows in the Master Sheet, and creates and fills WebFlow jobs through browser
automation. Each feature is a module plugged into the main window sidebar.

## Features

### Main window

- Fixed-size window (1024x700) with a dark theme and dark title bar.
- Collapsible sidebar (220px to 56px icon-only) with the logo and Home / Creation / Comparison navigation.
- The window title shows the active module.
- Cross-module wiring: variants loaded on Home are passed to Creation automatically.
- All external job links open on double-click only, in both Home and Creation. Single-click does not open a browser.
- On close, pages that hold resources (the WebFlow browser session) are shut down.
- WebFlow job filling reads each drop-down list in one query (no per-option waits, no option cap) and confirms the "Saved successfully" toast after Save; an error toast or no toast fails the job with a clear log line.
- Job creation stops before submission if a form selection fails. If WebFlow replaces the Confirm button or loading indicator during an Angular refresh, automation re-finds it within the existing timeout; a successful submission is never retried.
- WebFlow-controlled checkboxes that are disabled for a variant are left unchanged; any requested values that could not be applied are listed in the job-creation completion summary.
- Every WebFlow step also records the page for analysis in `logs/webflow_trace/<timestamp>/` (`NNN_step_OK|FAILED|ERROR.html`, `.png` screenshot, `.json` list of every input, select, button, link and label with id, class, text, state and CSS path, `NNN_step_OK.changes.json` with every DOM change (added / removed elements, attribute and text changes) and every fetch / XHR request (method, url, status, ms) that happened while the step ran, plus `index.jsonl` with url, title, outcome, duration, change / request counts and whether the page was reloaded); turn it off with **Analysis** in the Settings module.
- Logging to `logs/autohub.log` and the console, including every WebFlow creation step (browser start, dashboard, form fields, each tab field, save, job ids, link writing) with its outcome and duration; every step names the value it sets (e.g. `General: limitations = NO`, `(empty)` / `(none)` for blank values) and each job first logs one `Values to fill` line with all its General / ECU / Customer values; turn it off or on with the **Logging** checkbox in the Settings module (saved as `logging_enabled`, applied with **Apply**, default on).
- User settings are persisted to `%APPDATA%/AutoHub/settings.json`: file paths and WebFlow config.

### Home module

- Browse and remember the Master Sheet (`.xlsx`).
- **New variant**:
  - Prompts for the ECU Info Sheet CR and System Matrix CR.
  - Hover tooltip: "Create new variant by reading ECU Info Sheet CR and System Matrix CR."
  - Reads all three files through Excel COM automation on a background thread.
  - Computes variants that are not yet in the Master Sheet. Nothing is written at this step.
  - Fails with a clear message if the files are inconsistent, for example Main/Container/Boot counts that don't match, or a part number missing from the System Matrix.
- **Derived columns**: ECU HW Name equals ECU Type; TP Level is `TP9` when the ECU Info Sheet's ROM Check and Tuning Protection are both ACTIVE, otherwise `TP3`; Engine Family is read from the ECU Info Sheet's `1) Issue CR` sheet (the entry marked YES, e.g. `NP1`).
- **Project Purpose**: new variants use `<Project> - <Event> Lot / <MP>`, for example `62XS - HIN Lot / MP1`. Existing values are not rewritten; duplicate detection and Creation event filtering support both this format and the legacy format.
- **SW Version / Indi Spec**: SW Version is `01` for ECU type MG1CS022 only, otherwise `-`; Indi Spec (e.g. `Honda_MG1CS022_CS_IndiSpec_01`) is filled in the table and the WebFlow job uses that cell.
- **PST_Lib selection**: Program version (PVER) from Master Sheet column `AY` searches the WebFlow **Pick PST_Lib** dialog's Program Identification column. Sheet values such as `MG1CS022_62XSC_V020_CS` match WebFlow's `MG1CS022_62XSC/V020_CS;0` format, ignoring only the revision suffix. The job proceeds only when exactly one row matches; the matched row is selected with **Pick PST**.
- **WebFlow values**: all mapped job values come from the loaded Master Sheet, not hard-coded defaults: ECU Generation / Brand / ECU Type (`Q` / `R` / `S`), General (`T`–`AA`), Hardware/Plant (`AB`–`AZ`), ECU (`BC`–`BG`) and Customer (`BH`, `CL`–`CN`, `CQ`, `CR`). Blank optional cells are skipped except checkbox cells, which default to False (X); blank required creation fields stop submission. Checkbox cells accept Yes/No, True/False, 1/0 or X (checked). TP Level `TP3` / `TP9` maps to the WebFlow option `3` / `9`; multi-select cells use `|` between values. Tool version, routing, customer group and working mode remain configuration because they have no mapped sheet columns. Selected variants must share ECU Generation, Brand and ECU Type. Reload variants after changing the sheet, or use Update Master Sheet to save Home edits before creating jobs.
- **Additional WebFlow fields**: Hardware/Plant automation includes vehicle model, engine family, power, emissions, immobilizer, transmission, displacement, market, model year, cylinders, project numbers, hardware/customer/software identifiers, car, customer name, lead plant, ECR number, PVER and data version. Nonblank columns without a matching control in the recorded form (e.g. DWG NO., ECU ID., CALIB ID., boot ID, security authentication fields, EC/EU-MARK and SS-ID) are ignored and not shown. Missing dropdown options and values that do not stick fail the fill step.
- **Total WebFlow time**: the completion or failure dialog and log show elapsed seconds for the entire operation, including browser startup, job creation, filling, saving and link writing.
- **WebFlow fill order**: Delivery Type, Release class, Release scope, Limitations, Safety Monitoring SW by RB, Safety Calibration responsibility, Bosch Cal Data Responsibility, Data Integration responsibility, Hardware part number, Import from Race in Classification, Development number, then Lead Plant. Race import is clicked only after the hardware part number is successfully filled; blank hardware part numbers skip the import. Remaining General fields follow the form top to bottom, followed by ECU, Customer and Save. Blank optional fields are skipped without changing the order.
- **Nonblank checkboxes**: blank Master Sheet checkbox cells (`X`–`AA`) default to False (X), rather than being skipped. From a blank WebFlow control, True takes one click and False takes two sequential clicks. State is verified using the displayed icon because WebFlow reports `aria-checked="false"` for both blank and X; a disabled blank checkbox fails the step.
- **General-tab panels**: controls are located inside their actual panels: General info, Bosch logistic info, Customer logistic info, Ident Numbers and ECR Information. Hardware part number / Development number belong to Bosch logistic info; Lead Plant belongs to Ident Numbers, not Hardware/Plant information. Mappings are checked against the recorded browser form and both filled-job XML samples; sample values never override the Master Sheet.
- **Software part number**: immediately after selecting Lead Plant, click Import from pool once and wait up to the WebFlow timeout for a nonblank, nonzero software part number. The imported value is logged and is not overwritten by Master Sheet column `AX`. A disabled button or failed import fails the job-fill step.
- **Before Lead Plant**: set Classification's Number of variants to `1`, Time limitation required? to `X` (false), and Successor to Time Limited Delivery ECU? to `X` (false). These are explicit workflow values, not sheet defaults. Lead Plant selection waits up to the WebFlow timeout for its popup options to load, including the requested plant.
- **Lead Plant visibility**: scroll the control to the center of the form before clicking its dropdown trigger, read only visible popup options, and verify the selected plant before continuing. Pool import also scrolls its button into view before the single allocation click.
- **Pool button scope**: find Import from pool only inside the Ident Numbers panel containing Lead Plant and Software part number, never by a page-wide button search.
- **Pool import confirmation**: if WebFlow warns that entered data will be saved before import, click Yes once in that warning dialog, then wait for the imported software part number. Unrelated dialogs are not confirmed automatically.
- **Allocated software number**: copy the imported number into Software name and Customer software part number, overriding the sheet's customer software number for pool imports. Retain it per variant and return it as `SoftwarePartNumber` with the job result.
- **MG1 software number formula**: when the request row's AX cell references K on the same row (`=K59`, for example), write the imported software number into K and preserve the AX formula. Unexpected formulas, including formulas in K, are rejected rather than overwritten.
- **ECR import**: configure Change engineer (Outlook Display Name), Cost allocation, Change Reason and ECR notes in Creation Settings. Change Reason must match the WebFlow options (`|` separates multiple reasons). With all four settings blank, the previous workflow is unchanged; once any is configured, all four are required before opening the browser. After PST_Lib selection, fill the ECR Information panel and click **ECR Import** once; if the known save-before-import warning appears, confirm Yes once. Wait for a nonblank, nonzero ECR number; any fill/import failure stops before Save. The imported number replaces the sheet's read-only ECR number for this workflow, is retained per variant as `imported_ecr_number` even if a later step fails, and is returned as `ECRNumber` for Master Sheet write-back after successful job completion. ISIR, release-by and compliance controls are left unchanged.
- **New variant source files**: one dialog asks for the ECU Info Sheet and System Matrix (required) and the HW Info and Kick Off Meeting (optional), each with a Browse button. The dialog always starts empty (the chosen files are not remembered). OK is enabled once the required files exist.
- **Mx17 Master Sheet**: a workbook with the sheet `ECU Container Release Honda GDI` (e.g. `Honda_GDI_container_release_info_latest.xlsx`) is detected automatically and handled by `Mx17MasterSheet`; MG1 workbooks use the unchanged MG1 code. Variants are read from the flat main sheet (one row per part number, from row 7) and overlaid with their `*_Info` sheet row. New variants append a main row and a row in an Info sheet named `<project>_Info` (created from `Mx17_5xFx_Info` when missing). Update writes only the cells you changed (to the main sheet and, when the variant has one, its Info row; Info-only fields create an Info row); fields with no column in this layout are reported after Update. Variants that were not changed are not touched. Delete finds the variant by part number (never by a remembered row number) and removes that main row only; no worksheet is ever deleted or renamed, and Info rows stay. Not mapped (left blank for new rows): TP level, TPROT, ENG, Info released-by/cost allocation, PVER, lead plant. Excel COM paths are untested without Excel.
- **Column widths**: every Home table column is kept between 60 and 300 px, both when fitted to content and when dragged (`modules/home/column_limits.py`).
- **Latest variants**: Settings module > **Home** > *Latest variants* (5, 10, 20, 50, 100, All) sets how many of the newest variants *Load variants* shows (the last rows of the sheet; *All* = no limit). Apply refreshes the table from the last Load, asking first if the table has unsaved changes. It is saved in `settings.json` (`latest_variant_count`). WebFlow still gets every variant.
- **Delete variants**: select one or more rows (Ctrl/Shift-click) and click *Delete selected* (after a confirmation). They leave the table at once; *Update Master Sheet* then also deletes their REQ/IMPL/comparison rows from the Master Sheet. Each variant is found by its part number right before deleting (never by a remembered row number), so a moved row can never take another variant with it; rows never saved there are just dropped. Deletions are discarded by Clear or a reload.
- **Confirmations**: the Clear button and the Update Master Sheet button each ask "Are you sure?" before acting when the table has variants.
- **Existing rows**: New variants and Load variants both ask when the table holds variants: **Clear** replaces them with the new/loaded ones, **Keep** leaves them and adds the new ones below (skipping ones already there, pending deletions are kept), **Cancel** stops the action. Nothing is removed until the new rows arrive, so a failed action never loses the table.
- **Progress window**: New variant, Load variants and Update show a window with each step, then the result (e.g. `Found 3 new variants`, `Loaded 12 variants`) or the error. It can only be closed once the action has finished or failed.
- **Market** is built from the System Matrix destination codes (`KJ` -> Japan, `KE/KG` -> `UK|Germany/Greece/...`) using the table in `core/markets.py`; unknown codes are kept as written.
- **Model Year** is a four-digit year (`27.0MY`, `MY28` or `19` become `2027`, `2028`, `2019`).
- **List-box columns**: Lead Plant (RtW2, SaW, SiP_test), Delivery Type, Release Class, Release Scope, Limitations and the four Yes/No columns (Safety Monitoring SW, Safety Calibration, Cal Data and Data Integration responsibility) are drop-downs in the table, with the same options as the webFLOW Configurator (`core/variant_choices.py`).
- **Kick Off Meeting (optional)**: New variant can also read a Kick Off Meeting `.pptx` (password `honda` or `hb` is tried when encrypted) and fills Power (kW), Num. of Cylinder (also from "4-cylinder engine" text) and Engine Family (when the ECU Info Sheet CR has none) where those columns are blank, Displacement (cc to litres, e.g. 1199 cc -> 1.2; a System Matrix value is never changed), and corrects Emission (the deck's EM Category, e.g. `BS6 + RDE`, replaces a System Matrix value that means the same norm such as `BS6`; a different norm like EURO 5 is kept) and Immobilizer (`Active|IMMO6`).
- **Load variants**: reads the existing variant rows from the Master Sheet.
- **Editable variant table**:
  - Shows the Master Sheet request columns.
  - Cells can be edited in place.
  - Right-click a column header to filter it by text and/or values (marked with ▼); filters combine across columns. Hidden rows are still considered on update.
  - "Update Master Sheet" is enabled only after a user edit.
- **Update Master Sheet**:
  - Only changed existing rows are updated; the confirmation lists each affected Part Number. Changes to any field in a row qualify.
  - New rows are inserted from the variant template and stamped with the created date.
  - The table is then reloaded from the sheet.
- After Create/Load/Update, the WebFlow-ready variant list is sent to the Creation page.
- Results and errors are shown in message boxes. Button text shows progress.

### Creation module

- Variant checklist:
  - Fed from Home.
  - Read-only grid table with a separate Select checkbox column, followed by Part Number, Family Name, FSWID Project Version, FSWID Program Version and WebFlow Link. Version values come from the same ECU data used to fill the WebFlow job. No variant count is shown above the table.
  - The event selector is left-aligned and table text is centered. Part Number is always the widest column and receives spare width. Other columns fit their content where space permits; narrower windows proportionally shrink the columns to keep the entire table within the available width.
  - Filter by event (the latest event is selected automatically when variants are loaded, until you pick one yourself), select all or clear.
  - The selection always starts empty: it is cleared whenever variants arrive from Home (Load variants, New variant, Update Master Sheet, ...) and after every Create WebFlow jobs run, whether it succeeded or failed. It is not saved between sessions.
- **Settings** module (pinned at the bottom of the sidebar; a module opts in with `pinned_bottom = True`): Theme = System / Light / Dark, saved as `theme` and applied only when you click **Apply** (button at the right, grey while nothing has changed; in Light the buttons use dark text); System follows the Windows setting, also when it changes. Default is Dark. Muted text (file names, hints), links and drop-down highlights follow the theme. Leaving the page (or closing the app) with unapplied changes asks to **Apply**, **Discard** or Cancel (stay).
- Every push / tool button and drop-down list (and the sidebar module list) shows a hand cursor while it is enabled (`autohub/ui/button_cursor.py`).
- **Settings > Home** also has "Show the WebFlow link column": a read-only "WebFlow Link" column (WF<number>, blue and underlined, double-click to open the job), fixed right after Part Number like No. and Part Number; off by default.
- **Settings** button (next to Create WebFlow jobs) opens a dialog for Base URL, Tool version, Routing and the four ECR fields above; OK saves them. Change Reason opens a searchable checkbox dropdown with the four recorded WebFlow options: Correction of a situation, Customer requirement, New supplier / increase of capacity / relocation / standards / others, and Q-Problem. Select all applies to visible search results; multiple checked reasons are saved using `|`. Previous unrecognized settings remain visible and checked so they are not silently discarded. ECR notes uses a compact editor at half its default height. The variant list now grows with the window, so more variants are visible at once.
- **Allocated numbers**: Creation shows **SW Part Number** and **ECR Number** immediately after WebFlow Link. Column widths refresh after loading, importing and filtering, filling the available window width with Part Number widest. Loaded values come from the Master Sheet. After job completion, imported numbers update both Creation and Home and are written as text to existing MG1 columns `AX`/`AW`, or Mx17 main-sheet columns `X`/`Y`, matched by the latest variant's part number. No new Excel columns are added. Write failures are reported explicitly; numbers stay visible and Home enables Update Master Sheet for retry, preserving other edits and pending deletions. Reloading or updating the Master Sheet synchronizes saved Home values back into Creation.
- **Create WebFlow jobs**:
  - Validation: at least one variant is selected, tool version and routing are filled, and all selected variants share the same ECU type.
  - Selenium (Edge) opens the WebFlow dashboard and creates one job per selected variant. WebFlow creates at most 10 jobs at once, so larger selections are created in groups of up to 10 (e.g. 24 variants = 10 + 10 + 4); each group is filled and saved before the next group is created, and results stay in selection order.
  - It then fills the General, ECU and Customer tabs and saves each job.
  - A progress window (same as Home) shows each step: starting the browser, opening the dashboard, creating the jobs and filling every job; it ends with the job IDs or the error.
  - After the jobs are created, each variant shows its WebFlow link as "WF<job number>" in the list, and the link is written to the Master Sheet column I ("Webflow No. with Link", MG1 layout) of that variant's request row as a hyperlink whose text is "WF<job number>". Loading the variants reads the hyperlink address back from that cell. The Mx17 layout has no such column, so the window says the links were not written there.
  - Completed job links also update matching rows in Home immediately, without reloading or discarding edits, filters or pending deletions. Enable "Show the WebFlow link column" in Settings > Home to see them. Links remain visible in the session even if writing them to the Master Sheet fails.
  - Selecting variants that already have a WebFlow link asks before creating: **Create anyway**, **Skip them** (only the others are created) or Cancel.
  - A summary of part number and job ID is shown on success.
  - The Settings page separates controls into **Theme**, **Logging**, **Analysis**, **Home**, and **WebFlow Retry** groups. The retry checkbox and maximum attempt count are grouped together; Apply saves changes across all groups. Home no longer has a separate settings button or dialog.
   - **Retry and resume**: Settings > **Enable automatic retries** switches retries on or off (default on). When unchecked, WebFlow makes one attempt and the attempt-count control is disabled, preserving its value. **Maximum WebFlow attempts** controls total attempts, including the first (1-100, default 5); setting it to 1 also prevents automatic retries. Each retry uses a new browser, waits 5 seconds, and continues from saved progress. Progress is saved to `%APPDATA%/AutoHub/webflow_batch.json` before every server-side effect, so retries never create the batch again, never refill completed jobs and never click Import from pool or ECR Import a second time; an import already clicked without a readable number is reported as a warning. Failures that could duplicate jobs (creation submitted but job IDs unknown) and validation errors are not retried. If AutoHub crashes or is closed mid-run, or all configured attempts fail, the next start asks whether to continue the unfinished work (Yes resumes with the saved settings, retry switch and attempt limit, No discards it). A confirmed resume starts a fresh set of attempts; older saved batches without retry settings use retries enabled and 5 attempts.
  - The browser session is closed on error or app exit.

### Comparison module

- Placeholder page ("Coming soon").

## Project structure

Dependency rule: `modules` -> `core` <- `services`. Feature modules never import `services/`, and `services/`
never import Qt or `modules/`. `bootstrap.py` is the only place that names concrete classes. The rules are
enforced by `tests/test_architecture.py`; the design requirements are in
[docs/SOLID_REQUIREMENTS.md](docs/SOLID_REQUIREMENTS.md).

```
AutoHub/
├── main.py                       # entry point
├── requirements.txt
├── autohub/
│   ├── bootstrap.py              # composition root: builds services and the module list
│   ├── config.py                 # app name/version, paths
│   ├── core/                     # interfaces and shared, I/O-free code
│   │   ├── module_base.py        # AutoHubModule interface
│   │   ├── capabilities.py       # VariantSource / VariantSink / Closable protocols
│   │   ├── ports.py, records.py  # narrow service interfaces and typed data shapes
│   │   ├── variant_schema.py     # Master Sheet columns shown in the table
│   │   ├── normalizers.py        # pure text normalisers
│   │   ├── webflow_defaults.py   # fixed WebFlow job values
│   │   ├── dialogs.py            # file/message dialog port + Qt implementation
│   │   ├── com.py, workers.py    # COM session per thread, background tasks
│   │   └── settings.py           # SettingsStore protocol + JSON implementation
│   ├── ui/                       # main_window, sidebar, theme
│   ├── modules/
│   │   ├── home/                 # ui (layout), presenter (workflows), service, variant_table
│   │   │                         #   + table_clipboard / table_search / table_filter (row_filter, filter_dialog) / table_actions / frozen_columns
│   │   ├── creation/             # service, ui, variant_checklist, config_form
│   │   └── comparison/           # placeholder
│   ├── services/                 # I/O adapters (Excel COM, email/xlsx, Selenium)
│   │   ├── common/               # sheet_grid, header_rules, workbook
│   │   ├── MasterSheet/          # session | row_reader | row_writer | variant_builder | webflow_variants
│   │   ├── EcuInfoSheet/         # reader + header-rule parser
│   │   ├── SystemMatrix/         # reader + label-driven parser
│   │   ├── HWInfo/               # reader, parser and per-file-type sources (.xlsx/.eml/.msg)
│   │   ├── KickOff/              # Kick Off Meeting .pptx reader + rule-table parser (power, cylinders, displacement, emission, immobilizer)
│   │   └── WebFlow/              # flat Python package: page adapters, session facade, workflows and helpers
│   │                             #   | components (shared section / drop-down / input / tab / checkbox widgets) | page objects
│   └── resources/                # icons, logo, banner
├── docs/SOLID_REQUIREMENTS.md
├── logs/
└── tests/                        # fakes.py holds the test doubles for Excel, Selenium and dialogs
```

## Requirements

- Windows with Microsoft Excel installed (COM automation through `pywin32`).
- Microsoft Edge and a matching Edge WebDriver (for WebFlow).
- Python packages: `PySide6`, `openpyxl`, `msoffcrypto-tool`, `pywin32`, `selenium`, `olefile`, `python-pptx`, `pytest`.

## Extending

- **New module:** create `autohub/modules/<name>/` with a Qt-free `service.py`, a `ui.py`, and a `module.py`
  (an `AutoHubModule` subclass whose constructor takes its factories). Add it to
  `autohub/bootstrap.py::build_modules()`.
- **New HW info file type:** write a class with `read(path, password) -> list[dict]` and register it in
  `autohub/services/HWInfo/sources.py::default_registry()`.
- **New Kick Off fact:** add one `Rule` to `RULES` in `autohub/services/KickOff/parser.py`, then map its field to a column in `variant_builder._apply_kick_off_info`.
- **New ECU Info Sheet column:** add one `HeaderRule` to `HEADER_RULES` in
  `autohub/services/EcuInfoSheet/parser.py`.

## Run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Test

```powershell
pytest
```
