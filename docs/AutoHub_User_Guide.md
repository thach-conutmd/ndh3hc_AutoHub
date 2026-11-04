# AutoHub User Guide

## Table of Contents

1. [AutoHub Overview and Purpose](#1-autohub-overview-and-purpose)
2. [System and Prerequisite Requirements](#2-system-and-prerequisite-requirements)
3. [Starting AutoHub](#3-starting-autohub)
4. [Main User Interface](#4-main-user-interface)
5. [Master Sheet Workflow](#5-master-sheet-workflow)
6. [WebFlow Workflow (Creation)](#6-webflow-workflow-creation)
7. [Comparison Workflow](#7-comparison-workflow)
8. [Manual XML Compare](#8-manual-xml-compare)
9. [Update Master Sheet Workflow](#9-update-master-sheet-workflow)
10. [Form B Generation](#10-form-b-generation)
11. [Template Manager](#11-template-manager)
12. [Settings and Configuration](#12-settings-and-configuration)
13. [Export Functions](#13-export-functions)
14. [Common Warnings, Errors, and Troubleshooting](#14-common-warnings-errors-and-troubleshooting)
15. [Recommended End-to-End Workflow](#15-recommended-end-to-end-workflow)
16. [FAQ](#16-faq)

---

## 1. AutoHub Overview and Purpose

AutoHub is a Windows desktop application that works with the AutoHub Master Sheet (an Excel `.xlsx` workbook) and WebFlow. It helps you:

- Load the variants listed in a Master Sheet.
- Create WebFlow jobs for selected variants and write the resulting links back to the Master Sheet.
- Compare the Master Sheet values with the values in WebFlow exports, or with two XML files you choose.
- Write comparison target values back to the Master Sheet.
- Generate a Form B Excel workbook for selected variants.
- Adjust application settings, including the Master Sheet and Form B templates.

[SCREENSHOT: Main Window]
- Capture the sidebar (Home, Creation, Form B, Comparison, Settings), the window title, and the Home toolbar.

---

## 2. System and Prerequisite Requirements

| Requirement | Details |
|---|---|
| Operating system | Windows. AutoHub uses Excel automation (pywin32) and the Microsoft Edge browser for WebFlow. |
| Microsoft Excel | Must be installed. AutoHub reads and writes `.xlsx` workbooks through Excel. |
| Microsoft Edge | Required for WebFlow operations (Creation and the WebFlow export used by Comparison and Form B). |
| Master Sheet | An `.xlsx` file in a supported layout. Load it from Home. |
| Templates | The bundled Master Sheet and Form B templates are used unless you select others in Settings. |
| Network access | WebFlow operations need access to WebFlow. The guide does not describe the network setup. |

> **Note:** You do not need to install Python to run the packaged AutoHub application. Keep the `config/`, `templates/`, and `assets/` folders next to `AutoHub.exe`.

---

## 3. Starting AutoHub

1. Open the AutoHub folder and double-click `AutoHub.exe`.
2. A startup dialog appears while AutoHub loads settings, logging, and modules.
3. If the Master Sheet you used last time still exists and has a supported layout, AutoHub loads its variants automatically.
4. If a previous Creation batch did not finish, AutoHub offers to continue it. The options are **Continue WebFlow jobs** and **Discard WebFlow retry**.

---

## 4. Main User Interface

The main window has a fixed size and a left sidebar:

| Sidebar item | Purpose |
|---|---|
| Home | Load and manage the Master Sheet and its variants. |
| Creation | Create WebFlow jobs for variants. |
| Form B | Export Form B workbooks. |
| Comparison | Compare Master Sheet and WebFlow data, or two XML files. |
| Settings | Application settings. Pinned at the bottom of the sidebar. |

The window title shows the current module, for example `AutoHub - Home`.

[SCREENSHOT: Home Module]
- Capture the **Load Master Sheet** and **Open Master Sheet** buttons, the variant table, and the toolbar buttons **New variants**, **Load variants**, **Update Master Sheet**, **Clear Data**, and **Delete selected**.

---

## 5. Master Sheet Workflow

### Purpose

The Master Sheet is the central workbook. AutoHub reads variants from it, and other modules (Creation, Comparison, Form B) use it for variant data.

### Prerequisites

- An `.xlsx` Master Sheet in a supported layout.
- Microsoft Excel installed.

### 5.1 Load or Select a Master Sheet

#### Steps

1. Open **Home**.
2. Click **Load Master Sheet**.
3. In the file dialog, choose an `.xlsx` file. The dialog filter is `Excel Files (*.xlsx)`.
4. AutoHub stores the path and shows the file name on Home.

To open the loaded file in Excel, click **Open Master Sheet**. AutoHub checks that the file still exists and then opens it with the default application for `.xlsx` files.

#### Expected Result

- The file name of the Master Sheet appears on Home.
- The path is saved, so the same Master Sheet is loaded at the next startup if it still exists and has a supported layout.

#### Possible Errors / Notes

- If the file is no longer valid, AutoHub reports that the Master Sheet cannot be used. Select another file.
- **Open Master Sheet** shows `Could not open the Master Sheet:` followed by the path if Windows cannot open the file.

### 5.2 Default Master Sheet Template

The default Master Sheet template is used when you create a new Master Sheet with **New variants** and no Master Sheet is loaded. The default is set in **Settings > Home** (see [Section 11](#11-template-manager)).

- If a configured template is not valid, AutoHub uses the bundled default template.
- A template must be an `.xlsx` file that AutoHub can open.

### 5.3 Add Variants (New variants)

**New variants** creates a new Master Sheet from source files.

#### Steps

1. Open **Home** and click **New variants**.
2. In the source dialog, select the **ECU Info Sheet** (required, `.xlsx`).
3. Select the **System Matrix** (required, `.xlsx`).
4. Optionally select the **HW Info**, **Kick Off**, and **Calibration** folder.
5. Confirm. If variants already exist in the table, AutoHub asks whether to clear them or keep them.

#### Expected Result

- AutoHub reports `Found N new variant(s)...`.
- If no Master Sheet is loaded, AutoHub copies the default template to a file named `Honda_<Project>_Container_MasterSheet_r00.xlsx` (the name is set from the **Settings > Home** description and the project name), then loads it.

#### Possible Errors / Notes

- The ECU Info Sheet and the System Matrix are required. The dialog does not continue without them.
- The optional HW Info, Kick Off, and Calibration folder are used only when provided.

### 5.4 Select and Load Variants

#### Steps

1. Open **Home**. Make sure a Master Sheet is loaded.
2. Click **Load variants**.
3. If the table already has rows, choose whether to keep them (keeping preserves any edits made in the table).

#### Expected Result

- The variant table is filled from the Master Sheet. A progress window shows while variants load.
- Your edits are kept if you choose to keep the existing rows, or the table is reloaded.

#### Possible Errors / Notes

- **Load variants** needs a valid Master Sheet. If none is loaded, AutoHub prompts you to load one.
- Variants can be removed with **Delete selected** (you are asked to confirm). **Clear Data** removes all loaded data after confirmation.

### 5.5 WebFlow URL Handling

- WebFlow links are stored in the Master Sheet. They are written by the **Creation** module (see [Section 6](#6-webflow-workflow-creation)).
- The **Home** table has a **Show the WebFlow link column** option, which you set in **Settings > Home**.
- The **Comparison** module lists only variants whose WebFlow link is valid (see [Section 7](#7-comparison-workflow)).

[SCREENSHOT: Home Variant Table]
- Capture the variant table, the WebFlow link column, the **Latest variants** count, and the **Load variants** button.

---

## 6. WebFlow Workflow (Creation)

The **Creation** module creates WebFlow jobs for variants.

### Purpose

Create one WebFlow job per selected variant and record the resulting link, SW Part Number, and ECR Number in the Master Sheet.

### Prerequisites

- A loaded Master Sheet with variants (see [Section 5](#5-master-sheet-workflow)).
- **Tool version** and **Routing** filled in on **Settings > Creation**.
- Microsoft Edge installed. WebFlow sign-in is handled in the browser.

### Steps

1. Open **Creation**.
2. Select one or more variants in the checklist. Use **Select visible**, **Clear selection**, and the **Event** filter to help you select.
3. Optionally fill in the ECR fields. Either fill in all four ECR fields or leave all of them empty.
4. Click **Create WebFlow jobs**.
5. If a selected variant already has a WebFlow link, choose **Create anyway** to create another job, or **Skip them**.
6. Wait for the batch to finish.

### Rules Checked Before Creation

- Selected variants must share the same **ECU Generation**, **Brand**, and **ECU Type**. If not, AutoHub reports the mismatch and does not start.
- **Tool version** and **Routing** must be set.

### Expected Result

- Each job's WebFlow link, SW Part Number, and ECR Number are written to the Master Sheet.
- If writing to the Master Sheet fails, AutoHub shows `The links were not written to the Master Sheet:` followed by the reason. Jobs that were already created are not undone.

### Retries

- Automatic retries are controlled by **Settings > Creation > WebFlow Retry**. Retries are on by default.
- **Maximum WebFlow attempts** sets the number of attempts (1 to 100, default 5).
- Progress is saved. If the batch does not finish, it is offered again at the next startup (see [Section 3](#3-starting-autohub)).

### Possible Errors / Notes

- Create WebFlow jobs needs the **Tool version** and **Routing** values from Settings. Set them first.
- Partial ECR entries (some but not all ECR fields filled) are not accepted.

---

## 7. Comparison Workflow

### Purpose

Find differences between Master Sheet values and WebFlow values, or between two XML files.

### Modes

The **Comparison** module has two modes:

- **Master Sheet Compare**: compares Master Sheet values with WebFlow exports for selected variants.
- **Manual XML Compare**: compares XML files you choose (see [Section 8](#8-manual-xml-compare)).

### 7.1 Compare Variants (Master Sheet Compare)

#### Prerequisites

- A loaded Master Sheet.
- Variants with a valid **WebFlow** link. Variants without a valid link do not appear in the table.
- Microsoft Edge installed (used for the WebFlow export).

#### Steps

1. Open **Comparison** and select **Master Sheet Compare**.
2. In the variant table, select variants using the **Select** checkbox. Use **Select all** or **Clear selection** as needed.
3. Click **Compare selected**.
4. Wait for each variant's **Status** to change. Variants are processed one at a time.

The variant table has these columns: **Select**, **Part Number**, **WebFlow**, **Base WebFlow Link**, **Status**, **Error**.

Status values for variants: **Pending**, **Exporting**, **Comparing**, **Completed**, **Failed**, **Cancelled**.

#### Expected Result

- The result table opens with these columns: **Part Number**, **Parameter**, **Master**, **Base**, **Target**, **Status**, **Comment**.

#### Possible Errors / Notes

- A variant with an error shows the message in its **Error** column.
- You can cancel a comparison in progress.

### 7.2 Interpret Comparison Results

Each row is one parameter. The **Status** column uses these values:

| Status | Meaning |
|---|---|
| `MATCH` | The compared values are equal. |
| `VALUE_MISMATCH` | The values are different. |
| `MISSING_IN_MASTER` | The parameter is not in the Master Sheet. |
| `MISSING_IN_WEBFLOW` | The parameter is not in the WebFlow data (Master Sheet Compare only). |
| `MATCHES_MASTER` | Manual XML Compare: the target matches the master value. |
| `MATCHES_BASE` | Manual XML Compare: the target matches the base value. |
| `MATCHES_BOTH` | Manual XML Compare: the target matches both. |
| `MATCHES_NEITHER` | Manual XML Compare: the target matches neither. |
| `MISSING_IN_BASE` | Manual XML Compare: the parameter is not in the base file. |
| `MISSING_IN_TARGET` | Manual XML Compare: the parameter is not in the target file. |

- A **deviation** is any status other than `MATCH`, `MATCHES_MASTER`, or `MATCHES_BOTH`.
- A blank target value never counts as a match.
- You can change a row's status: right-click the row and choose **Change Status**. Choose **Reset Status** to return to the calculated status.
- You can edit a row's comment with **Edit Comment** and remove it with **Clear Comment**.
- Other right-click commands: **Copy** and **Copy Row**.

### 7.3 Filters

Filter the result table by column:

1. Click or right-click a column header (any column after the first).
2. Choose the values to show in the filter dialog.

The filter applies to every table view. To reset filters on the HTML report, use **Clear Filters**.

### 7.4 Excluded Parameters

Parameters can be excluded from comparison in **Settings > Comparison**:

- The **Exclude Compare Data** table lists exclusions. Each row has a checkbox, plus **Edit** and **Delete** buttons.
- **Apply to Master Sheet Compare** controls whether an exclusion applies to Master Sheet Compare.
- **Restore defaults** resets the table.
- Exclusions that apply only to the Master Sheet (master-only) always apply to Manual XML Compare.
- The default exclusions are `Files/` and `Notes/`.

Excluded parameters are removed from the comparison, so they do not appear in the result table.

### 7.5 Export Comparison

1. Click **Export Comparison**.
2. Choose a location if prompted.

AutoHub writes an HTML report named `Comparison_Result_<timestamp>.html`. The report includes a search box and **Clear Filters**.

### Possible Errors / Notes

- If no variants are selected, **Compare selected** does nothing. Select at least one variant.
- If no variant has a valid WebFlow link, no variants are listed.

---

## 8. Manual XML Compare

### Purpose

Compare one base XML file with one or more target XML files, without a Master Sheet.

### Steps

1. Open **Comparison** and select **Manual XML Compare**.
2. Under **Base XML:**, click **Select XML...** and choose the base file.
3. Under **Target XML:**, click **Select XML(s)...** and choose one or more target files.
4. Click **Compare**.

### Requirements

- Both a base XML and at least one target XML are required before **Compare** is available.

### Expected Result

The result table has these columns: **Parameter**, **Base**, **Target(s)**, **Status**, **Comment**. The status values and the context-menu actions are the same as in [Section 7.2](#72-interpret-comparison-results).

### Filtering and Export

- Use the header filters described in [Section 7.3](#73-filters).
- Use **Export Comparison** to save the HTML report described in [Section 7.5](#75-export-comparison).

### Possible Errors / Notes

- Master-only exclusions apply in Manual XML Compare (see [Section 7.4](#74-excluded-parameters)).
- Update Master Sheet is not available for Manual XML Compare (see [Section 9](#9-update-master-sheet-workflow)).

---

## 9. Update Master Sheet Workflow

### Purpose

Write the target values from a Master Sheet comparison back into the Master Sheet.

### Prerequisites

- A Master Sheet Compare has been run and completed for the variants.
- The module is in **Master Sheet Compare** mode. This action is not available in Manual XML Compare.

### Steps

1. Open **Comparison** and run **Compare selected** (see [Section 7.1](#71-compare-variants-master-sheet-compare)).
2. Click **Update Master Sheet**.
3. Confirm the prompt.

### What Is Updated

- The **Target** values are written to the Master Sheet's IMPL columns for each successful variant.
- **Base** values are not written.

### Expected Result

AutoHub shows `Master Sheet updated successfully for N of M variant(s).`

### Possible Errors / Notes

- Variants that failed in the comparison are not updated.
- Confirm the prompt only if you have reviewed the target values.

---

## 10. Form B Generation

### Purpose

Create a Form B Excel workbook for the selected variants.

### 10.1 Required User Inputs

Fill in these fields in the **Form B Information** section:

| Field | Notes |
|---|---|
| Department / Organization | Used to build **Return To**. |
| Name | Used to build **Return To**. |
| Phone Number | Required. |
| Date | Defaults to today. |
| Return To | Built automatically from Department / Organization and Name. |
| Project / Production Release Project | Filled automatically from the Master Sheet when possible (see 10.2). |
| Production Project | Filled automatically when possible. |
| Bosch Project Number | Required. |
| ECU-Type | Filled automatically when possible. |
| Expected Receipt Date | Format `YYYY-MM-DD`. |

Some of these fields can be hidden in **Settings > Form B** (see [Section 12](#12-settings-and-configuration)).

If any required field is empty, AutoHub shows `Complete the following Form B Information fields:` followed by the field names.

Fields other than the dates keep their values between sessions.

### 10.2 Automatically Populated Values

- **Project / Production Release Project**: the Master Sheet project name plus the suffix from **Settings > Form B > Production Release Project Suffix** (default `Honda Project`).
- **Production Project**: `<project> <MP phase>` when a single value applies.
- **ECU-Type**: taken from the Master Sheet's form_b data or ECU type.
- **Phase** (`MP<digits>`): read from the Master Sheet event name. If it is missing, AutoHub asks you to enter it in the format `MP<digits>`.

If the selected variants have different Production Project values, AutoHub shows a warning.

### 10.3 Master Sheet and WebFlow Data

- Variant data comes from the Master Sheet for the selected variants.
- The CRC value is read from the Master Sheet (see 10.4).

### 10.4 CRC Handling

- **Is CRC required?** Yes. Form B needs a CRC32 value for each variant.
- **Is it entered by the user?** No. AutoHub reads it from the Master Sheet's **BA** column.
- **If the CRC is blank or masked (`*`)**: AutoHub fetches it from WebFlow. This requires a linked WebFlow job and a loaded Master Sheet.
- AutoHub writes the fetched CRC back to the Master Sheet's **BA** column.
- If WebFlow returns no value, AutoHub shows `WebFlow did not provide a CRC32 for <filename>.`

### 10.5 Export

#### Steps

1. Open **Form B**.
2. Fill in the **Form B Information** fields.
3. Select one or more variants in the variant checklist.
4. Click **Export Form B**. The button is enabled when at least one variant is selected and the Form B template is valid.
5. In the save dialog, choose a folder. The default file name is `Form_B.xlsx`.

#### Required Template

- The Form B template is set in **Settings > Form B** (see [Section 11](#11-template-manager)). The bundled default is `Form_B_Default_Template.xlsx`.
- If the template is not valid, AutoHub shows `Form B template is not available. Please select a valid Form B template in Settings.`

#### Output

- Output type: an Excel `.xlsx` workbook.
- Output location: the folder you choose in the save dialog.
- File name: `<Project>_<MP>_FORMB_<ECU Type>_<YYYYMMDD>.xlsx`, for example `Project_MP1_FORMB_ECU_20250101.xlsx`. The date is the export date.
- AutoHub writes a temporary `.partial` file, then replaces the target with it.
- AutoHub refuses to overwrite the template file.

#### Expected Result

AutoHub shows `Form B workbook saved to <path>.`

#### Possible Errors / Notes

- Variants with different **ECU HW Name** values are rejected.
- Variants with different Project, Phase, or ECU Type values are rejected.

---

## 11. Template Manager

AutoHub does not include a separate Template Manager window in the current implementation. Templates are selected in **Settings**.

### Master Sheet Template

- Location: **Settings > Home**, field **Default Master Sheet Template**.
- Must be an `.xlsx` file that AutoHub can open.
- If the selected file is not valid, AutoHub uses the bundled default template.

### Form B Template

- Location: **Settings > Form B**, field **Default Form B Template**.
- Must be an `.xlsx` file that AutoHub can open.
- If the selected file is not valid, AutoHub uses the bundled default template `Form_B_Default_Template.xlsx`.

### Default-Template Behavior

- The configured template is used first. If it is missing or invalid, the bundled default is used.
- The selected template path is saved and used the next time you run AutoHub.

---

## 12. Settings and Configuration

Open **Settings** in the sidebar. Click **Apply changes** to save. The footer shows **Unsaved changes** or **All changes saved**.

### General

- **Theme**: the application theme.
- **Logging**
  - **Enable application logging**: turns on logging.
  - **Log location**: the folder for logs (default `logs`). Use **Browse...** to choose another folder.
  - **Open log file**: opens the log file.
  - **Clear log content**: clears the log file.
- **Analysis**
  - **Record WebFlow steps for analysis**: records WebFlow steps (on by default).

### Home

- **Latest variants:** how many variants to show: 5, 10, 20, 50, 100, or All.
- **Show the WebFlow link column**: shows or hides the WebFlow link column in the Home table.
- **A2L component ID symbol:** the symbol used for the A2L component ID.
- **Default Master Sheet Template**: see [Section 11](#11-template-manager).

### Creation

- **WebFlow Environment**: the WebFlow environment to use.
- **Tool version:** required for Creation.
- **Routing:** required for Creation.
- **Change engineer:** used in the WebFlow job.
- **Cost allocation:** used in the WebFlow job.
- **Change Reason:** the change reason list.
- **WebFlow Retry**
  - **Enable automatic retries**: on by default.
  - **Maximum WebFlow attempts:** 1 to 100, default 5.

### Form B

- **Default Form B Template**: see [Section 11](#11-template-manager).
- **Show Return To**, **Show Project / Production Release Project**, **Show Production Project**, **Show ECU-Type**: show or hide these fields.
- **Production Release Project Suffix:** default `Honda Project`.

### Comparison

- **Exclude Compare Data**: the exclusion table (see [Section 7.4](#74-excluded-parameters)).
- **Apply to Master Sheet Compare**
- **Restore defaults**

---

## 13. Export Functions

| Function | Where | Output | File name | Location |
|---|---|---|---|---|
| Comparison report | Comparison > **Export Comparison** | HTML report | `Comparison_Result_<timestamp>.html` | Chosen by you |
| Form B workbook | Form B > **Export Form B** | Excel `.xlsx` | `<Project>_<MP>_FORMB_<ECU Type>_<YYYYMMDD>.xlsx` | Folder you choose in the save dialog |
| Log file | Settings > General > **Open log file** | Log file | Set by AutoHub | Log location in Settings |

---

## 14. Common Warnings, Errors, and Troubleshooting

| Message / Symptom | Likely Cause | What the User Should Do |
|---|---|---|
| `Could not open the Master Sheet:` | Windows could not open the file. | Load the Master Sheet again from **Home**. |
| `Log file does not exist:` | **Open log file** was clicked before a log file was created. | Enable logging in **Settings > General** and run AutoHub again. |
| `Form B template is not available. Please select a valid Form B template in Settings.` | The configured template is missing or invalid. | Select a valid `.xlsx` in **Settings > Form B**. |
| `Complete the following Form B Information fields:` | One or more required fields are empty. | Fill in the listed fields. |
| `WebFlow did not provide a CRC32 for <filename>.` | WebFlow returned no CRC for the variant. | Check the WebFlow job for the variant. |
| `The links were not written to the Master Sheet:` | The Master Sheet could not be updated. | Check the reason shown and correct it. Jobs already created are not undone. |
| `Master Sheet updated successfully for N of M variant(s).` | Success. | No action needed. |
| Selected variants have different ECU Generation, Brand, or ECU Type | Creation requires one group. | Select variants from one group. |

---

## 15. Recommended End-to-End Workflow

1. Start AutoHub.
2. On **Settings > Creation**, fill in **Tool version** and **Routing**. Check the templates in **Settings**.
3. On **Home**, click **Load Master Sheet** (or confirm the automatically loaded one).
4. Click **Load variants**.
5. Open **Creation** and create WebFlow jobs for the variants you need.
6. Open **Comparison**, select variants, and click **Compare selected**.
7. Review the results. Change statuses or comments where needed.
8. Click **Update Master Sheet** to write the target values to the Master Sheet.
9. Open **Form B**, fill in the information, select variants, and click **Export Form B**.
10. Click **Export Comparison** if you need an HTML report.

Optional branches:

- Use **Manual XML Compare** without a Master Sheet (Section 8).
- Use **New variants** to create a new Master Sheet (Section 5.3).

---

## 16. FAQ

**Why is a variant not listed in Comparison?**
Only variants with a valid WebFlow link are listed. Create the WebFlow job in **Creation** first.

**Why is Export Form B disabled?**
Select at least one variant, and make sure the Form B template is valid.

**Which template is used?**
The configured template in **Settings**. If it is missing or invalid, the bundled default is used.

**How is the default template selected?**
Set it in **Settings > Home** (Master Sheet) or **Settings > Form B** (Form B). AutoHub uses the bundled default when the configured file is not valid.

**What do comparison results mean?**
See [Section 7.2](#72-interpret-comparison-results).

**How do excluded parameters work?**
Excluded parameters are removed from the comparison. See [Section 7.4](#74-excluded-parameters).

**Where is an exported file saved?**
Comparison reports are saved where you choose. Form B workbooks are saved in the folder you choose in the save dialog.

**How is the Form B file name determined?**
`<Project>_<MP>_FORMB_<ECU Type>_<YYYYMMDD>.xlsx`. See [Section 10.5](#105-export).

**What happens if required data is missing?**
AutoHub shows a message that names the missing item and does not continue.
