# AutoHub Quick Start Guide

This guide covers the normal first-time workflow. For full details, see the [AutoHub User Guide](AutoHub_User_Guide.md).

## 1. Prerequisites

- Windows, with Microsoft Excel and Microsoft Edge installed. See [System and Prerequisite Requirements](AutoHub_User_Guide.md#2-system-and-prerequisite-requirements).
- An `.xlsx` Master Sheet. Keep the `config/`, `templates/`, and `assets/` folders next to `AutoHub.exe`.

## 2. Start AutoHub

1. Double-click `AutoHub.exe`.
2. Wait for the startup dialog to finish. See [Starting AutoHub](AutoHub_User_Guide.md#3-starting-autohub).

## 3. Minimum Initial Setup

1. Open **Settings > Creation** and fill in **Tool version** and **Routing**. Creation will not run without them. See [Creation](AutoHub_User_Guide.md#12-settings-and-configuration).
2. Check the **Default Master Sheet Template** and **Default Form B Template** paths in **Settings**. See [Template Manager](AutoHub_User_Guide.md#11-template-manager).

## 4. Normal Workflow

1. **Load the Master Sheet.** On **Home**, click **Load Master Sheet** and select an `.xlsx` file. See [Master Sheet Workflow](AutoHub_User_Guide.md#5-master-sheet-workflow).
2. **Load the variants.** Click **Load variants**. See [Select and Load Variants](AutoHub_User_Guide.md#54-select-and-load-variants).
3. **Create WebFlow jobs.** Open **Creation**, select variants, and click **Create WebFlow jobs**. The links are written back to the Master Sheet. See [WebFlow Workflow (Creation)](AutoHub_User_Guide.md#6-webflow-workflow-creation).
4. **Compare.** Open **Comparison**, keep **Master Sheet Compare** selected, select variants, and click **Compare selected**. Review the statuses. See [Compare Variants](AutoHub_User_Guide.md#71-compare-variants-master-sheet-compare) and [Interpret Comparison Results](AutoHub_User_Guide.md#72-interpret-comparison-results).
5. **Update the Master Sheet.** Click **Update Master Sheet** and confirm. See [Update Master Sheet Workflow](AutoHub_User_Guide.md#9-update-master-sheet-workflow).
6. **Generate Form B.** Open **Form B**, fill in **Form B Information**, select variants, and click **Export Form B**. See [Form B Generation](AutoHub_User_Guide.md#10-form-b-generation).

## 5. Essential Inputs

| Where | Input |
|---|---|
| Settings > Creation | Tool version, Routing |
| Home | Master Sheet (`.xlsx`) |
| Creation | Variants, optional ECR fields (all four or none) |
| Comparison | Variants (with a valid WebFlow link) |
| Form B | Form B Information fields, variants, save folder |

## 6. Expected Outputs

- **Master Sheet:** WebFlow links, SW Part Number, and ECR Number from Creation. Target values from **Update Master Sheet**, and CRC values fetched for Form B.
- **Comparison report:** `Comparison_Result_<timestamp>.html` from **Export Comparison**.
- **Form B workbook:** `<Project>_<MP>_FORMB_<ECU Type>_<YYYYMMDD>.xlsx` in the folder you choose. See [Export](AutoHub_User_Guide.md#105-export).

## 7. Critical Warnings

- **Tool version** and **Routing** must be set before creating WebFlow jobs.
- Selected variants for Creation must share the same ECU Generation, Brand, and ECU Type.
- ECR fields must be all filled or all empty.
- Only variants with a valid WebFlow link appear in Comparison.
- **Export Form B** needs at least one selected variant and a valid Form B template.
- Form B reports missing fields in **Form B Information** and does not export until they are filled. See [Required User Inputs](AutoHub_User_Guide.md#101-required-user-inputs).
- Update Master Sheet is available only in **Master Sheet Compare**, not **Manual XML Compare**.
