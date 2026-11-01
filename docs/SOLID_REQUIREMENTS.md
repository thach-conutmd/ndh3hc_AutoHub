# AutoHub – SOLID Requirements

Requirements for applying SOLID across the AutoHub code base. Each requirement has an ID, a rule, the
current state (checked against the code on 2026-10-28) and an acceptance criterion, so progress can be
verified rather than judged.

## 1. Scope and constraints

- **In scope:** everything under `autohub/` and `main.py`. `autohub/services/WebFlow/` is legacy
  Selenium code and is covered by section 8 (audit first, then refactor only what the audit justifies).
- **Behaviour must not change.** The refactor is structural. Master Sheet rows, WebFlow jobs and UI
  behaviour stay the same.
- **Safety net first.** The existing tests (`tests/test_modules.py`, `tests/test_refactor.py`,
  `tests/test_readers.py`) must stay green after every step, and each step adds tests for any seam it
  creates. Excel COM and Selenium code cannot run in CI, so keep the logic around them in pure functions
  that can be tested without Excel or a browser.
- **No speculative abstraction.** Introduce an interface only where the requirement below names a real
  second implementation, a test double, or a concrete coupling to break.

## 2. Single Responsibility (SRP)

A class or module has one reason to change.

| ID | Requirement | Current state | Acceptance criterion |
|----|-------------|---------------|----------------------|
| SRP-1 | `MasterSheet` is split by responsibility: workbook access (open/close/save), reading variant rows, writing variant rows, and building variant values from source documents. | `autohub/services/MasterSheet/MasterSheet.py` is 638 lines with 12 public methods mixing all four. | No class in `services/MasterSheet/` exceeds about 200 lines. Building values from sources (`_build_variant_values`, normalisers) has no Excel/COM import and is unit-tested with plain dicts. |
| SRP-2 | Field normalisers (`_normalize_*`, `_ascii_hex`, `_title_status`, …) live in one pure module, not as static methods of a COM-bound class. | They are static methods on `MasterSheet`. | A `normalizers` module exists with no third-party imports; each function has a test. |
| SRP-3 | `VariantTable` only displays and edits rows. Clipboard (copy/paste/delete), find/replace and the frozen-column overlay are separate components. | `modules/home/variant_table.py` (282 lines) holds all of them, plus the context menu. | Table class under about 120 lines; frozen columns, clipboard actions and search each in their own class, each testable on its own. |
| SRP-4 | `HomeWidget` only lays out the page and forwards user intent. File picking, the HW-info question and the New variant / Load / Update workflows are separate. | `modules/home/ui.py` (264 lines) mixes layout, dialogs, settings and workflow state. | The widget has no direct `QFileDialog` / `QMessageBox` calls outside a small dialog helper; workflow steps are methods of a presenter that is tested with fake dialogs. |
| SRP-5 | Parsers only parse. They do not open files, log, or know about Qt. | `EcuInfoSheet/parser.py`, `SystemMatrix/parser.py` and `HWInfo/parser.py` already follow this. | Keep it: a test asserts these modules import neither `win32com`, `PySide6` nor `logging`. |
| SRP-6 | Hard-coded WebFlow form values are configuration, not code inside the Master Sheet reader. | The same literals ("Plant Introduction", "Pre-Production", "Program and Data", "NO", `tp_level` "3", default IDs) appear in both `build_webflow_variants` and `load_webflow_variants`. | One `WebFlowDefaults` definition used by both; changing a default touches one place. |
| SRP-7 | Remove dead code. | `modules/formb/` is unregistered; `create_variants_from_sources` and `create_variants_from_files` duplicate `compute_new_variants` + `save_variant_rows`. | Either delete them or add a documented caller and a test. No unused public method remains. |

## 3. Open/Closed (OCP)

New behaviour is added by new classes, not by editing existing ones.

| ID | Requirement | Current state | Acceptance criterion |
|----|-------------|---------------|----------------------|
| OCP-1 | New sheet layouts are supported by registering a layout, not by editing parser functions. | Header patterns are module-level lists in each parser; adding a column type means editing `_read_headers` / `_ECU_HEADERS`. | Header-to-field rules are data (a table of pattern → field → section) consumed by one generic reader; a new column is a one-line data change covered by a test. |
| OCP-2 | HW info sources (workbook templates, PN_List, email body) are pluggable. | `HWInfo/parser.py` has a fixed `SHEET_PARSERS` tuple and `HWInfo.load_data` branches on file extension. | A `HWSource` registry maps a file type to a reader; adding `.pdf` or another layout needs no change to `HWInfo`. |
| OCP-3 | Feature modules are added only through `modules/__init__.py`. | Already true: `get_registered_modules()` is the single registration point. | Keep it. A test registers a stub module and shows `MainWindow` shows it with no other change. |
| OCP-4 | Cross-page wiring stays capability-based. | Already true: `MainWindow` uses `VariantSource`, `VariantSink` and `Closable` protocols. | Keep it. No `isinstance` against a concrete page class anywhere in `ui/`. |

## 4. Liskov Substitution (LSP)

Any implementation of an abstraction can replace another without surprising callers.

| ID | Requirement | Current state | Acceptance criterion |
|----|-------------|---------------|----------------------|
| LSP-1 | All document readers honour one contract: `load_data() -> bool`, `last_error: str`, and data exposed in a documented shape. | `EcuInfoSheet` and `SystemMatrix` extend `ExcelDocument`; `HWInfo` has the same methods but no shared type. | A `DocumentReader` protocol is defined; a contract test runs the same assertions against all three readers (and test fakes). |
| LSP-2 | Subclasses do not narrow behaviour: a reader never raises where its base type returns `False`. | `ExcelDocument._parse` returns `None` and sets `last_error`. | Contract test: every reader returns `False` and sets a non-empty `last_error` for an unreadable file. |
| LSP-3 | Data returned by readers has a defined shape. | `ecu_info` / `system_info` are untyped dict-of-dicts; consumers rely on key names. | Typed records (dataclasses or `TypedDict`) for ECU info, System Matrix variants and HW records; `MasterSheet` consumes those types only. |

## 5. Interface Segregation (ISP)

Clients depend only on the methods they use.

| ID | Requirement | Current state | Acceptance criterion |
|----|-------------|---------------|----------------------|
| ISP-1 | `MasterSheet` consumers get narrow interfaces: a reader for the table, a writer for saving rows, a source for WebFlow variants. | `VariantService` and the UI use one large class. | `VariantService` depends on `VariantReader`, `VariantWriter` and `WebFlowVariantSource` protocols, not on `MasterSheet`. |
| ISP-2 | `compute_new_variants` receives only the data it needs, not whole reader objects. | It takes `system_matrix`, `ecu_info_sheet` and `hw_info` objects and reads their attributes. | It takes plain typed data (`SystemMatrixData`, `EcuInfoData`, `HWData`), so tests need no reader objects. |
| ISP-3 | Page capabilities stay small. | Already true: three one-method protocols in `core/capabilities.py`. | Keep it; do not add a combined "page" base class. |

## 6. Dependency Inversion (DIP)

High-level policy depends on abstractions; concrete I/O is injected.

| ID | Requirement | Current state | Acceptance criterion |
|----|-------------|---------------|----------------------|
| DIP-1 | The UI does not import service internals. | `modules/home/variant_table.py` imports `VARIANT_FIELD_LABELS` / `VARIANT_FIELD_ORDER` from `services/MasterSheet/MasterSheet.py`. | The column definitions live in a neutral module (for example `core/variant_schema.py`) imported by both the table and the Master Sheet code; the UI has no import from `autohub/services/`. |
| DIP-2 | Services never construct their collaborators. | `MasterSheet.create_variants_from_files` instantiates `SystemMatrix` and `EcuInfoSheet` itself. | Removed or taking injected readers; no `services/*` class instantiates another service. |
| DIP-3 | Excel COM and Selenium sit behind small interfaces defined by the code that uses them. | `HomeWidget` and `CreationWidget` already accept an injected service; `VariantService` takes factories. | Document this as the pattern and extend it: every service in `modules/*/service.py` is constructed through a factory/interface argument, with a fake used in at least one test per service. |
| DIP-4 | A single composition root builds the object graph. | `main.py` and `get_registered_modules()` create modules; modules create their own widgets and default services. | `main.py` (or one `bootstrap.py`) wires settings store, services and modules; widgets and services receive collaborators and call `default_*` factories nowhere. |
| DIP-5 | Settings access goes through `SettingsStore`. | Already true for the UI. | Keep it; no module reads `%APPDATA%` or `settings.json` directly except `JsonSettingsStore`. |
| DIP-6 | Cross-cutting calls (COM session, file dialogs, message boxes) are injectable. | `com_session()` is called directly inside service methods; dialogs are called directly inside `HomeWidget`. | Both are passed in (a `SessionFactory`, a `Dialogs` helper), so workflows run in tests without Excel or a visible window. |

## 7. Target structure

```
autohub/
├── core/            # interfaces and shared infrastructure: settings, workers, capabilities,
│                    # variant_schema (columns), typed records, DocumentReader protocol
├── services/        # I/O adapters only (Excel COM, Selenium, email/xlsx readers)
│   ├── common/      # sheet_grid, workbook
│   ├── MasterSheet/ # workbook access | row reader | row writer | value builder | normalizers
│   ├── EcuInfoSheet/ SystemMatrix/ HWInfo/   # reader + pure parser each
│   └── WebFlow/
├── modules/<name>/  # service (no Qt) | presenter/workflow | ui (layout only) | widgets
└── bootstrap.py     # composition root
```

Dependency rule: `modules` → `core` ← `services`. A `modules/*/ui.py` never imports from `services/`,
and `services/` never imports from `modules/` or `PySide6`.

## 8. Legacy WebFlow package (audit first)

`services/WebFlow/` was copied from the old app. `Body/Tab/GeneralTab.py` (459 lines),
`ECUTab.py` (345) and `JobCreation/JobCreation.py` (310) are the largest files after `MasterSheet.py`.
Their internals were not reviewed for this document.

- **WF-1 (audit done, nothing changed):** findings from reading the package and measuring it. The code cannot
  be exercised here (no browser), so none of this was refactored.
  - Size: `GeneralTab.py` 601 lines, `ECUTab.py` 464, `JobCreation.py` 404, `CustomerTab.py` 266.
  - 90 bare `except:` clauses (GeneralTab 27, ECUTab 22, JobCreation 19, CustomerTab 12, SideMenuBar 8), 88
    `time.sleep` calls and 107 `WebDriverWait` calls. Errors are swallowed and only surface as `False`.
  - Repeated code: the section-toggle methods (`is_X_expanded`, `is_X_collapsed`, `expand_X`, `collapse_X`)
    exist four times across the tabs, and `get_options` exists in `GeneralTab`, `ECUTab` and `JobCreation`.
  - Good already: locators and timeouts are centralised in `Constants.py`, and page objects receive the
    driver by injection.
  - Suspected defect, unverified: `WebFlow._fill_job` ends with `self.quit()`, but `create_and_fill_jobs`
    calls it once per variant, so a second variant would run `open_job` on a closed browser.
  - Assumption: `JobCreation.jobs_creation` derives the new job ids by incrementing the id in the page URL.
  - A reasonable first refactor, if wanted: one shared section-toggle helper and one `get_options`, replacing
    the bare `except:` with logged exceptions, each checked by a run against a real WebFlow.
- **WF-4 (refactor done):** the package was restructured without changing what is clicked or typed.
  - `components.py` holds each repeated widget once: `Section` (expand / collapse / fill an input),
    `select_dropdown`, `TabLink`, the tri-state checkbox readers, and `wait_for` / `wait_until_idle`.
    The page objects keep every public method name and only hold locators (2,623 → about 1,630 lines).
  - Bare `except:` clauses are gone; every caught exception is logged (debug for state checks,
    warning for failed actions) and the same `True` / `False` result is returned.
  - SRP: `WebFlow` only orchestrates. `browser.edge_service` builds the driver service (the download
    proxy is `Constants.WEBDRIVER_DOWNLOAD_PROXY`). `job_filler.JobFiller` builds and runs the per-job
    steps; its field tables (`GENERAL_FIELDS`, `ECU_FIELDS`, `CUSTOMER_FIELDS`) are data, so adding a
    field is one line (OCP). `JobFiller` depends only on the page objects it is given (DIP).
  - Unused `Header` / `Footer` stubs were removed. `JobCreation.is_job_creation_page` used a misspelt
    constant and always returned `False`; it now uses `BODY_JOBCREATION_PAGE_CLASS` (it is not called).
  - Subsequent correctness changes: collapsing already-collapsed job information succeeds; dropdown
    selection fails if an option is missing or the requested value does not stick. Text inputs are
    checked for read-only state and verified after typing.
  - Tested with fake elements in `tests/test_webflow_components.py`; still to be confirmed by a run
    against a real WebFlow.
- **WF-2:** Any change must keep `WebFlow.create_and_fill_jobs(variants, tool_version, routing)` and the
  existing variant dict keys compatible, because `WebFlowJobService` and the tests depend on them.
  Creation settings may supply an optional `ecr` payload without changing the public method signature.
- **WF-3:** Page-object classes receive the driver by injection (already the case for `SideMenuBar` and
  `Body`); keep it that way for new classes.
- **WF-5 (sheet-authoritative values):** `MasterSheet/webflow_variants.py` reads all mapped fields from
  their sheet columns; it does not substitute `WebFlowDefaults`. Blank optional values are skipped
  except General checkbox cells, which default to False (X) and must not remain blank.
  Invalid checkbox cells and missing required creation fields are errors. `core/webflow_fields.py`
  maps additional General-tab fields, filled by `HardwareFields` using the captured WebFlow form
  labels and their actual panels (General info, Bosch logistic info, Customer logistic info,
  Ident Numbers and ECR Information). These controls are not descendants of the Hardware/Plant
  information panel. Recorded-DOM and XML-export regression tests verify the mappings.
  Columns without a corresponding control are ignored and not shown; values are never guessed.
  Configuration still supplies fields without a sheet column. PST_Lib selection uses Master Sheet Program version (PVER, column AY), not FSWID Project Version. The creation service measures the entire
  operation with `perf_counter`, exposing elapsed seconds to the completion/failure dialog and log.
- **WF-6 (ECR import):** Creation settings supply Change engineer, Cost allocation and Change Reason
  through the creation service, not Selenium imports in the UI. All three settings are
  required if any is configured; all blank preserves the previous workflow. The creation service
  generates each job's ECR notes from its Project Purpose project and event
  (`This container is for {project} {event name} event.`). The page adapter fills
  only these controls in ECR Information, imports once and waits for the read-only ECR number.
  ECR-enabled jobs stop on the first failed step before Save. Retain the imported number per variant
  and expose `ECRNumber` in job results. The creation service writes allocated SW/ECR numbers through
  `WebFlowNumberWriter`, using existing MG1 AX/AW or Mx17 X/Y columns. Capability signals synchronize
  both page tables without importing concrete modules or clearing unrelated edits. Write-back errors
  keep the numbers visible and enable Home's Update Master Sheet retry.

- **WF-7 (workflow separation):** `WebFlow` remains the compatible Selenium session facade, owning
  browser construction, navigation, tracing and shutdown. It composes `JobBatch`, which validates
  requests, creates and fills the batch and returns job results using injected actions and the narrow
  `JobCreationPage` protocol. `JobPlan` builds the ordered steps without executing them; `JobFiller`
  executes an injected `StepPlan`, preserving legacy continue-on-failure behavior, PST picker aborts,
  ECR fail-fast behavior and allocated-number retention. These workflow modules import no Selenium
  or concrete page classes. `PstLibPicker` owns the recorded selection dialog; `NumberImport` owns
  single-submit imports and their known confirmation. `HardwareFields` delegates to them while
  retaining its existing public methods and sheet-backed controls. Field tables and formatting
  helpers remain importable from `job_filler` for compatibility. Regression tests enforce step order,
  one-click allocation and session cleanup only after all jobs succeed; failure cleanup remains the
  creation service's responsibility. Real browser verification is still required.
  All Python modules live directly in `services/WebFlow/`; page classes and workflow components
  use sibling imports rather than nested Body/Tab packages.

- **WF-8 (retry and resume):** `WebFlowJobService` retries a batch up to `MAX_ATTEMPTS` (5) with a
  fresh browser per attempt and persists progress through the injected `core.batch_journal.BatchJournal`
  (`JsonBatchJournal` is built only in `bootstrap.py`). `JobBatch.run(state=, checkpoint=)` records
  `creation_submitted` (via `JobCreation.jobs_creation(before_submit=)`), `job_ids` and completed
  `results`, and `JobFiller` records `attempted_imports` before each number import, so no retry or
  resume repeats a server-side effect. `NonRetryableError` and `ValueError` stop retrying. Pages
  implementing the `StartupTask` capability run after the main window is shown; Creation uses it to
  offer resuming an unfinished batch. Tested with fakes in `tests/test_webflow_retry.py`.

## 9. Order of work

Each step ends with a green test run.

1. **DIP-1, SRP-6, SRP-7:** move the column schema out of `MasterSheet.py`, centralise WebFlow defaults,
   delete or justify dead code. Smallest changes, no behaviour risk.
2. **LSP-1, LSP-2, LSP-3:** define the `DocumentReader` protocol and typed records, add the contract test.
3. **SRP-1, SRP-2, ISP-1, ISP-2:** split `MasterSheet` and give `VariantService` narrow interfaces.
4. **SRP-3, SRP-4, DIP-6:** split `VariantTable` and `HomeWidget`, inject dialogs and the COM session.
5. **OCP-1, OCP-2:** data-driven header rules and a HW source registry.
6. **DIP-2, DIP-4:** remove service-to-service construction and add the composition root.
7. **Section 8:** audit and, if justified, refactor `services/WebFlow/`.

## 10. Definition of done

- Every requirement above is marked met in the checklist below, or has a recorded reason it was waived.
- All tests pass, and new seams have tests that use fakes instead of Excel or a browser.
- An import-rule test enforces the dependency rule in section 7.
- No public method or module is unused.
- `README.md` project structure matches the code.

### Status (checked 2026-10-28)

| ID | Status | Evidence / what is left |
|----|--------|-------------------------|
| SRP-1 | Met | Largest class in `services/MasterSheet/` is 72 lines (`VariantRowWriter`). |
| SRP-2 | Met | `core/normalizers.py` imports only `re`; all 12 functions are tested in `test_variant_builder.py` / `test_variant_table.py`. |
| SRP-3 | Met | `VariantTable` is 107 lines; clipboard, search, context menu and frozen columns are separate classes, tested through the table. |
| SRP-4 | Met | No `QFileDialog` / `QMessageBox` in `ui.py` or `presenter.py`; the presenter is tested with fake dialogs. `HomePresenter` (180 lines) is now the largest class outside WebFlow. |
| SRP-5 | Met | Enforced by `test_architecture.py`. |
| SRP-6 | Met | The named literals live in `core/webflow_defaults.py`. Still literal: "Honda" / "HONDA" / 159 in `variant_builder.py`, and the brand / customer group / working mode parameters of the legacy `WebFlow.create_and_fill_jobs`. |
| SRP-7 | Partial | Removed `modules/formb/`, `create_variants_from_*`, `build_webflow_variants`, `get_registered_modules` and the settings wrappers. No full unused-code sweep was run. |
| OCP-1 | Partial | ECU Info headers are a rule table with tests. The System Matrix label aliases are data tables but have no test for adding one. |
| OCP-2 | Met | `HWSourceRegistry`; `test_extensibility.py` adds a `.pdf` source without touching `HWInfo`. |
| OCP-3 | Met | `test_modules.py` adds a stub module to `MainWindow`. |
| OCP-4 | Met | `MainWindow` uses only the capability protocols (unchanged). |
| LSP-1 | Met | `DocumentReader` protocol and a contract test over all three readers. The protocol is for static checks only (not `runtime_checkable`). |
| LSP-2 | Met | Contract test: unreadable files give `False` plus a `last_error`. `MasterSheet.open` deliberately raises so nothing is written to a workbook that failed to open (tested). |
| LSP-3 | Partial | TypedDicts exist in `core/records.py` and annotate `variant_builder` / `MasterSheet`. The parsers still return plain dicts and no type checker was run. |
| ISP-1 | Partial | `VariantService` depends on the `VariantSheet` protocol, not on `MasterSheet`, but on one combined protocol rather than separate reader / writer ones. |
| ISP-2 | Met | `compute_new_variants(system_info, ecu_info, hw_info)` takes plain data. |
| ISP-3 | Met | Unchanged. |
| DIP-1 | Met | Enforced by `test_architecture.py`. |
| DIP-2 | Met | `create_variants_from_files` is gone; no service builds another service. |
| DIP-3 | Met | `VariantService` and `WebFlowJobService` take factories and are tested with fakes. |
| DIP-4 | Met | `bootstrap.py`. `HomeWidget` still defaults `dialogs` to `QtDialogs`, and `build_modules` defaults `settings` to `JsonSettingsStore`. |
| DIP-5 | Met | Enforced by `test_architecture.py`. |
| DIP-6 | Met | COM session and dialogs are injected. |
| WF-1 | Done | Audit recorded in section 8. |
| WF-2 | Met | `create_and_fill_jobs`, its keyword arguments, the variant dict shape and the result dicts are unchanged. |
| WF-3 | Met | New classes (`Section`, `TabLink`, `JobFiller`) also receive the driver or pages by injection. |
| WF-4 | Done | Shared components, logged exceptions, `browser` / `job_filler` split; see section 8. |
