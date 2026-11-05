"""Registry of standalone test features. Add a new feature by appending a TestFeature to the list in bootstrap."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import QDialog, QWidget

from autohub.core.dialogs import Dialogs
from autohub.modules.testing.add_instance_member_dialog import AddInstanceMemberDialog
from autohub.modules.testing.service import InstanceMemberTestService


@dataclass(frozen=True)
class TestFeature:
    title: str
    create_dialog: Callable[[QWidget], QDialog]


def add_instance_member_feature(
    service: InstanceMemberTestService, dialogs: Callable[[QWidget], Dialogs]
) -> TestFeature:
    return TestFeature(
        title="Add User to Instance Members",
        create_dialog=lambda parent: AddInstanceMemberDialog(service, dialogs(parent), parent),
    )
