"""Home workflows through the presenter and service, with fakes instead of Excel, Qt dialogs and threads."""
from autohub.modules.home.presenter import HomePresenter
from tests.fakes import (
    FakeDialogs,
    FakeDocument,
    FakeMasterSheet,
    FakeView,
    MemorySettings,
    build_service,
    run_inline,
)


def _presenter(tmp_path, service, dialogs=None, view=None, settings=None):
    master = tmp_path / "master.xlsx"
    master.write_bytes(b"x")
    settings = settings or MemorySettings({"master_sheet_path": str(master)})
    view = view or FakeView()
    dialogs = dialogs or FakeDialogs()
    presenter = HomePresenter(view, service, settings, dialogs, run_inline)
    presenter.restore_saved_paths()
    return presenter, view, dialogs, settings


def test_restore_saved_paths_shows_the_master_sheet_name(tmp_path):
    _, view, _, _ = _presenter(tmp_path, build_service())
    assert view.file_names["Master Sheet"].endswith("master.xlsx")


def test_new_variant_enables_update_without_editing(tmp_path):
    master = FakeMasterSheet(new_rows=[{"J": "37820-62X-MD10-M6"}])
    dialogs = FakeDialogs(files=["ecu.xlsx", "matrix.xlsx"])
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), dialogs)

    presenter.new_variant()

    assert view.rows == [{"J": "37820-62X-MD10-M6"}]
    assert view.states["update"] == (True, "Update Master Sheet")
    assert view.states["new"] == (True, "New variants")
    assert dialogs.asked_fields == ["ECU Info Sheet", "System Matrix", "HW Info", "Kick Off"]


def test_new_variant_with_nothing_new_keeps_update_disabled(tmp_path):
    presenter, view, dialogs, _ = _presenter(
        tmp_path, build_service(master=FakeMasterSheet(new_rows=[])), FakeDialogs(files=["e.xlsx", "m.xlsx"])
    )
    presenter.new_variant()
    assert view.states["update"][0] is False
    assert "No new variants" in dialogs.infos[-1][1]


def test_new_variant_passes_hw_info_to_the_master_sheet(tmp_path):
    master = FakeMasterSheet(new_rows=[{"J": "P"}])
    dialogs = FakeDialogs(files=["e.xlsx", "m.xlsx", "hw.eml"], hw_answer=True)
    presenter, _, _, settings = _presenter(tmp_path, build_service(master=master), dialogs)

    presenter.new_variant()

    assert master.compute_args[2] is not None
    assert "hw_info_path" not in settings.data


def test_new_variant_stops_when_a_file_dialog_is_cancelled(tmp_path):
    master = FakeMasterSheet()
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), FakeDialogs(files=["e.xlsx"]))
    presenter.new_variant()
    assert master.compute_args is None
    assert "new" not in view.states


def test_new_variant_reports_the_reader_error(tmp_path):
    matrix = FakeDocument(ok=False, error="'m.xlsx' is not a readable System Matrix: no part numbers")
    presenter, view, dialogs, _ = _presenter(
        tmp_path, build_service(matrix=matrix), FakeDialogs(files=["e.xlsx", "m.xlsx"])
    )
    presenter.new_variant()
    assert dialogs.errors == [("New variants", "'m.xlsx' is not a readable System Matrix: no part numbers")]
    assert view.states["new"] == (True, "New variants")


def test_documents_are_closed_even_when_loading_fails(tmp_path):
    ecu = FakeDocument(ok=False, error="bad", ecu_info={})
    master = FakeMasterSheet()
    matrix = FakeDocument(system_info={})
    presenter, _, _, _ = _presenter(
        tmp_path, build_service(master=master, ecu=ecu, matrix=matrix), FakeDialogs(files=["e.xlsx", "m.xlsx"])
    )
    presenter.new_variant()
    assert ecu.closed and master.closed and matrix.closed


def test_update_saves_the_table_rows_and_publishes_webflow_variants(tmp_path):
    master = FakeMasterSheet(rows=[{"_row": 11, "J": "P"}], webflow=[{"part_number": "P"}])
    presenter, view, dialogs, _ = _presenter(tmp_path, build_service(master=master))
    view.rows = [{"_row": None, "J": "P"}]

    presenter.update_master_sheet()

    assert master.saved == [{"_row": None, "J": "P"}]
    assert view.rows == [{"_row": 11, "J": "P"}]
    assert view.published == [[{"part_number": "P"}]]
    assert view.states["update"] == (False, "Update Master Sheet")
    assert "Updated 1 variant" in dialogs.infos[-1][1]


def test_update_saves_only_changed_rows_and_lists_their_part_numbers(tmp_path):
    master = FakeMasterSheet(
        rows=[
            {"_row": 11, "J": "P1", "A": "before"},
            {"_row": 14, "J": "P2", "A": "before"},
            {"_row": 17, "J": "P3", "A": "unchanged"},
        ],
        webflow=[],
    )
    presenter, view, dialogs, _ = _presenter(tmp_path, build_service(master=master))
    presenter.load_variants()
    view.rows = [
        {"_row": 11, "J": "P1-new", "A": "after"},
        {"_row": 14, "J": "P2", "A": "changed without changing part number"},
        {"_row": 17, "J": "P3", "A": "unchanged"},
        {"_row": None, "J": "P4", "A": "new"},
    ]

    presenter.update_master_sheet()

    assert master.saved == [
        {"_row": 11, "J": "P1-new", "A": "after"},
        {"_row": 14, "J": "P2", "A": "changed without changing part number"},
        {"_row": None, "J": "P4", "A": "new"},
    ]
    confirmation = dialogs.confirmed[-1][1]
    assert "Changed variants:\n- P1-new\n- P2" in confirmation
    assert "New variants to add:\n- P4" in confirmation
    assert "P3" not in confirmation
    assert "Only changed existing rows will be updated." in confirmation


def test_update_saves_other_field_changes_even_when_part_number_is_unchanged(tmp_path):
    master = FakeMasterSheet(rows=[{"_row": 11, "J": "P", "A": "before"}])
    presenter, view, dialogs, _ = _presenter(tmp_path, build_service(master=master))
    presenter.load_variants()
    view.rows = [{"_row": 11, "J": "P", "A": "after"}]

    presenter.update_master_sheet()

    assert master.saved == [{"_row": 11, "J": "P", "A": "after"}]
    assert "Changed variants:\n- P" in dialogs.confirmed[-1][1]


def test_update_without_rows_does_nothing(tmp_path):
    master = FakeMasterSheet()
    presenter, _, _, _ = _presenter(tmp_path, build_service(master=master))
    presenter.update_master_sheet()
    assert master.saved is None


def test_update_requires_a_valid_master_sheet(tmp_path):
    view = FakeView()
    view.rows = [{"J": "P"}]
    presenter, _, dialogs, _ = _presenter(tmp_path, build_service(), view=view, settings=MemorySettings())
    presenter.update_master_sheet()
    assert dialogs.errors == [("Update variants", "Select a valid Master Sheet file.")]


def test_load_shows_rows_and_keeps_update_disabled(tmp_path):
    master = FakeMasterSheet(rows=[{"_row": 11}, {"_row": 14}], webflow=[{"part_number": "P"}])
    presenter, view, dialogs, _ = _presenter(tmp_path, build_service(master=master))

    presenter.load_variants()

    assert len(view.rows) == 2
    assert view.states["update"][0] is False
    assert view.states["clear"] is True
    assert view.states["load"] == (True, "Load variants")
    assert view.published == [[{"part_number": "P"}]]
    assert "Loaded 2 variants" in dialogs.infos[-1][1]


def test_clear_resets_the_table_and_buttons(tmp_path):
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=FakeMasterSheet(rows=[{"_row": 11}])))
    presenter.load_variants()
    presenter.clear_table()
    assert view.rows == []
    assert view.states["clear"] is False and view.states["update"][0] is False


def test_editing_the_table_enables_update(tmp_path):
    presenter, view, _, _ = _presenter(tmp_path, build_service())
    presenter.on_table_edited()
    assert view.states["update"] == (True, "Update Master Sheet")


def test_load_and_new_variant_report_their_steps_in_the_progress_window(tmp_path):
    master = FakeMasterSheet(rows=[{"J": "a"}], new_rows=[])
    dialogs = FakeDialogs(files=["e.xlsx", "m.xlsx"])
    presenter, _, _, _ = _presenter(tmp_path, build_service(master=master), dialogs)

    presenter.load_variants()
    presenter.clear_table()
    presenter.new_variant()

    load, new = dialogs.windows
    assert load.title == "Load variants" and load.steps == ["Opening the Master Sheet...", "Reading the variants..."]
    assert new.title == "New variants" and "Reading the System Matrix..." in new.steps
    assert dialogs.infos[0][1] == "Loaded 1 variant from the Master Sheet."


def _load_twice(tmp_path, table_answer):
    master = FakeMasterSheet(rows=[{"J": "a", "_row": 8}, {"J": "b", "_row": 9}])
    dialogs = FakeDialogs(table_answer=table_answer)
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), dialogs)
    view.rows = [{"J": "edited", "_row": 8}, {"J": "mine", "_row": None}]
    presenter.load_variants()
    return view, dialogs


def test_load_asks_before_replacing_rows_and_can_clear_them(tmp_path):
    view, dialogs = _load_twice(tmp_path, True)
    assert "still contains 2 variants" in dialogs.asked[0]
    assert [r["J"] for r in view.rows] == ["a", "b"]


def test_load_can_keep_the_current_rows_and_adds_only_new_ones(tmp_path):
    view, _ = _load_twice(tmp_path, False)
    assert [r["J"] for r in view.rows] == ["edited", "mine", "b"]  # sheet row 8 is already in the table
    assert view.states["update"][0] is True  # a row not in the sheet yet can still be written


def test_cancelling_the_question_does_nothing(tmp_path):
    view, dialogs = _load_twice(tmp_path, None)
    assert [r["J"] for r in view.rows] == ["edited", "mine"] and dialogs.windows == []


def test_nothing_is_asked_when_the_table_is_empty(tmp_path):
    presenter, _, dialogs, _ = _presenter(tmp_path, build_service(master=FakeMasterSheet(rows=[])))
    presenter.load_variants()
    assert dialogs.asked == []


def test_new_variant_asks_for_every_source_file_in_one_dialog_and_remembers_nothing(tmp_path):
    dialogs = FakeDialogs(files=["e.xlsx", "m.xlsx", "hw.eml", "kom.pptx"], hw_answer=True, kick_off_answer=True)
    presenter, view, _, settings = _presenter(tmp_path, build_service(master=FakeMasterSheet(new_rows=[])), dialogs)

    presenter.new_variant()

    assert dialogs.asked_fields == ["ECU Info Sheet", "System Matrix", "HW Info", "Kick Off"]
    assert set(settings.data) == {"master_sheet_path"}
    presenter.new_variant()
    assert dialogs.initial == {}  # no history: the dialog always starts empty


def test_new_variant_asks_clear_keep_or_cancel_like_load(tmp_path):
    master = FakeMasterSheet(new_rows=[{"J": "fresh"}])
    dialogs = FakeDialogs(files=["e.xlsx", "m.xlsx", "e.xlsx", "m.xlsx"], table_answer=True)
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), dialogs)
    view.rows = [{"J": "old", "_row": 8}]

    presenter.new_variant()  # Clear
    assert dialogs.asked_labels == ("Clear", "Keep")
    assert [r["J"] for r in view.rows] == ["fresh"]

    dialogs.table_answer = False  # Keep: the new variants are added below
    view.rows = [{"J": "old", "_row": 8}]
    presenter.new_variant()
    assert [r["J"] for r in view.rows] == ["old", "fresh"]
    assert view.states["update"] == (True, "Update Master Sheet")


def test_new_variant_cancel_changes_nothing_and_an_empty_table_asks_nothing(tmp_path):
    master = FakeMasterSheet(new_rows=[{"J": "fresh"}])
    dialogs = FakeDialogs(files=["e.xlsx", "m.xlsx"], table_answer=None)
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), dialogs)
    view.rows = [{"J": "old", "_row": 8}]
    presenter.new_variant()
    assert view.rows == [{"J": "old", "_row": 8}] and dialogs.windows == []

    dialogs.asked.clear()
    view.rows = []
    presenter.new_variant()
    assert dialogs.asked == [] and [r["J"] for r in view.rows] == ["fresh"]


def test_keeping_rows_keeps_pending_deletions(tmp_path):
    master = FakeMasterSheet(new_rows=[{"J": "fresh"}])
    dialogs = FakeDialogs(files=["e.xlsx", "m.xlsx"], table_answer=False)
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), dialogs)
    view.rows = [{"J": "a", "_row": 8}, {"J": "b", "_row": 14}]
    view.selected = [0]
    presenter.delete_selected()

    presenter.new_variant()
    presenter.update_master_sheet()

    assert master.deleted == [8]


def test_replaced_rows_stay_until_the_new_ones_arrive(tmp_path):
    master = FakeMasterSheet(rows=[{"J": "a", "_row": 8}])
    dialogs = FakeDialogs(table_answer=True)
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), dialogs)
    view.rows = [{"J": "mine", "_row": None}]

    master.load_variant_rows = lambda: (_ for _ in ()).throw(ValueError("boom"))
    presenter.load_variants()
    assert [r["J"] for r in view.rows] == ["mine"] and dialogs.errors  # a failed action keeps the table

    master.load_variant_rows = lambda: [{"J": "a", "_row": 8}]
    presenter.load_variants()
    assert dialogs.asked_labels == ("Clear", "Keep") and [r["J"] for r in view.rows] == ["a"]


def test_clear_and_update_buttons_ask_for_confirmation(tmp_path):
    master = FakeMasterSheet(rows=[{"_row": 11, "J": "old"}])
    dialogs = FakeDialogs(confirm_answer=False)
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), dialogs)
    presenter.load_variants()
    dialogs.windows.clear()
    view.rows = [{"J": "a", "_row": 11}]

    presenter.clear_table()
    presenter.update_master_sheet()
    assert [title for title, _ in dialogs.confirmed] == ["Clear table", "Update variants"]
    assert view.rows == [{"J": "a", "_row": 11}] and master.saved is None and dialogs.windows == []

    dialogs.confirm_answer = True
    presenter.clear_table()
    assert view.rows == []


def test_delete_selected_variants_are_removed_from_the_sheet_on_update(tmp_path):
    master = FakeMasterSheet(rows=[{"J": "kept", "_row": 14}])
    dialogs = FakeDialogs()
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), dialogs)
    view.rows = [{"J": "a", "_row": 8}, {"J": "kept", "_row": 14}, {"J": "new", "_row": None}, {"J": "b", "_row": 20}]
    view.selected = [0, 2, 3]

    presenter.delete_selected()

    assert [r["J"] for r in view.rows] == ["kept"]
    assert view.states["update"] == (True, "Update Master Sheet")
    assert master.deleted is None  # nothing touches the sheet until Update

    presenter.update_master_sheet()

    assert master.deleted == [8, 20]  # the never-saved row has nothing to delete
    assert "Deleted 2." in dialogs.infos[-1][1]
    presenter.update_master_sheet()  # the pending deletions were consumed
    assert dialogs.confirmed[-1][0] == "Update variants" and master.deleted == [8, 20]


def test_delete_needs_a_selection_and_a_yes(tmp_path):
    dialogs = FakeDialogs(confirm_answer=False)
    presenter, view, _, _ = _presenter(tmp_path, build_service(), dialogs)
    view.rows = [{"J": "a", "_row": 8}]

    presenter.delete_selected()
    assert dialogs.infos and dialogs.confirmed == []

    view.selected = [0]
    presenter.delete_selected()
    assert len(view.rows) == 1


def test_deleting_every_variant_can_still_be_updated(tmp_path):
    master = FakeMasterSheet(rows=[])
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master))
    view.rows = [{"J": "a", "_row": 8}]
    view.selected = [0]

    presenter.delete_selected()
    presenter.update_master_sheet()

    assert view.rows == [] and master.deleted == [8]


def test_delete_button_is_only_active_while_rows_are_selected(tmp_path):
    presenter, view, _, _ = _presenter(tmp_path, build_service())
    view.rows = [{"J": "a", "_row": 8}, {"J": "b", "_row": 9}]

    presenter.on_selection_changed()
    assert view.states["delete"] is False

    view.selected = [1]
    presenter.on_selection_changed()
    assert view.states["delete"] is True

    presenter.delete_selected()  # the selection goes with the removed row
    view.selected = []
    presenter.on_selection_changed()
    assert view.states["delete"] is False


def test_load_shows_only_the_latest_variants_from_the_setting(tmp_path):
    master = FakeMasterSheet(rows=[{"_row": 11 + 3 * i} for i in range(7)], webflow=[{"part_number": "P"}])
    settings = MemorySettings({"master_sheet_path": str(tmp_path / "master.xlsx"), "latest_variant_count": 5})
    presenter, view, dialogs, _ = _presenter(tmp_path, build_service(master=master), settings=settings)

    presenter.load_variants()

    assert [row["_row"] for row in view.rows] == [17, 20, 23, 26, 29]
    assert "latest 5 of 7" in dialogs.infos[-1][1]
    assert view.published == [[{"part_number": "P"}]]


def test_latest_count_is_saved_and_never_negative(tmp_path):
    presenter, _, _, settings = _presenter(tmp_path, build_service())
    presenter.set_latest_count(5)
    assert presenter.latest_count() == 5
    presenter.set_latest_count(7)  # not one of the list box choices
    assert presenter.latest_count() == 0


def _loaded(tmp_path, count, answer=True):
    master = FakeMasterSheet(rows=[{"_row": 11 + 3 * i} for i in range(100)], webflow=[])
    settings = MemorySettings({"master_sheet_path": str(tmp_path / "master.xlsx"), "latest_variant_count": count})
    dialogs = FakeDialogs()
    dialogs.confirm_answer = answer
    presenter, view, dialogs, _ = _presenter(tmp_path, build_service(master=master), dialogs, settings=settings)
    presenter.load_variants()
    return presenter, view, dialogs


def test_changing_latest_count_refreshes_the_table(tmp_path):
    presenter, view, _ = _loaded(tmp_path, 5)
    assert len(view.rows) == 5
    presenter.set_latest_count(20)
    assert len(view.rows) == 20 and view.rows[-1]["_row"] == 11 + 3 * 99
    presenter.set_latest_count(50)
    assert len(view.rows) == 50
    presenter.set_latest_count(0)
    assert len(view.rows) == 100


def test_changing_latest_count_asks_before_discarding_changes(tmp_path):
    presenter, view, dialogs = _loaded(tmp_path, 5, answer=False)
    presenter.on_table_edited()
    presenter.set_latest_count(20)
    assert len(view.rows) == 5 and dialogs.confirmed[-1][0] == "Latest variants"
    dialogs.confirm_answer = True
    presenter.set_latest_count(50)
    assert len(view.rows) == 50


def test_changing_latest_count_before_any_load_changes_nothing(tmp_path):
    presenter, view, _, _ = _presenter(tmp_path, build_service())
    presenter.set_latest_count(20)
    assert view.rows == []


def test_update_reloads_only_the_latest_variants_from_the_setting(tmp_path):
    master = FakeMasterSheet(rows=[{"_row": 11 + 3 * i} for i in range(20)], webflow=[])
    settings = MemorySettings({"master_sheet_path": str(tmp_path / "master.xlsx"), "latest_variant_count": 5})
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master), settings=settings)
    view.rows = [{"_row": None, "J": "P"}]

    presenter.update_master_sheet()

    assert [row["_row"] for row in view.rows] == [56, 59, 62, 65, 68]
    presenter.set_latest_count(10)
    assert len(view.rows) == 10


class _ByPartNumber(FakeMasterSheet):
    def delete_variants_by_part_number(self, part_numbers, save=True):
        self.deleted_parts = list(part_numbers)
        return len(part_numbers)


def test_sheets_that_find_variants_by_part_number_are_given_the_part_numbers(tmp_path):
    master = _ByPartNumber(rows=[{"_row": 11, "J": "P1"}, {"_row": 14, "J": "P2"}])
    presenter, view, _, _ = _presenter(tmp_path, build_service(master=master))
    presenter.load_variants()
    view.selected = [0]

    presenter.delete_selected()
    presenter.update_master_sheet()

    assert master.deleted_parts == ["P1"] and master.deleted is None


def _checked_service(problem="", master=None):
    service = build_service(master=master)
    service._master_sheet_checker = lambda _path: problem
    return service


def test_startup_loads_a_valid_remembered_master_sheet_without_asking(tmp_path):
    master = FakeMasterSheet(rows=[{"J": "P1"}], webflow=[{"part_number": "P1"}])
    presenter, view, dialogs, _ = _presenter(tmp_path, _checked_service(master=master))

    presenter.auto_load_variants()

    assert view.rows == [{"J": "P1"}]
    assert view.published == [[{"part_number": "P1"}]]
    assert view.states["load"] == (True, "Load variants")
    assert dialogs.asked == [] and dialogs.errors == []


def test_startup_skips_an_invalid_or_missing_master_sheet(tmp_path):
    presenter, view, dialogs, _ = _presenter(tmp_path, _checked_service("not a Master Sheet"))
    presenter.auto_load_variants()
    assert view.rows == [] and dialogs.windows == [] and dialogs.errors == []

    presenter, view, dialogs, _ = _presenter(
        tmp_path, _checked_service(), settings=MemorySettings({})
    )
    presenter.auto_load_variants()
    assert view.rows == [] and dialogs.windows == []


def test_startup_does_not_replace_rows_already_in_the_table(tmp_path):
    presenter, view, dialogs, _ = _presenter(tmp_path, _checked_service())
    view.rows = [{"J": "kept"}]
    presenter.auto_load_variants()
    assert view.rows == [{"J": "kept"}] and dialogs.windows == []


def test_home_page_auto_loads_as_a_startup_task(qapp, tmp_path):
    from autohub.core.capabilities import StartupTask
    from autohub.modules.home.ui import HomeWidget

    page = HomeWidget(_checked_service("missing"), MemorySettings({}), FakeDialogs())
    assert isinstance(page, StartupTask)
    page.on_startup()
    assert page.row_count() == 0
