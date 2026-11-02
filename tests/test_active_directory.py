from types import SimpleNamespace

from autohub.modules.settings import creation_form
from tests.fakes import MemorySettings


def test_change_engineer_uses_current_active_directory_profile(monkeypatch):
    monkeypatch.setenv("USERNAME", "current.user")
    monkeypatch.setenv("USERDNSDOMAIN", "example.com")
    monkeypatch.setattr(
        creation_form, "_query_active_directory", lambda username, domain: ("Ngo Huu Dat", "MS/EJV5-PS")
    )

    config = creation_form.load_config(MemorySettings({"change_engineer": "Previously saved"}))

    assert config.change_engineer == "Ngo Huu Dat (MS/EJV5-PS)"


def test_change_engineer_falls_back_to_saved_value_when_directory_lookup_fails(monkeypatch):
    monkeypatch.setenv("USERNAME", "current.user")
    monkeypatch.setenv("USERDNSDOMAIN", "example.com")

    def fail_lookup(username, domain):
        raise OSError("directory unavailable")

    monkeypatch.setattr(creation_form, "_query_active_directory", fail_lookup)
    config = creation_form.load_config(MemorySettings({"change_engineer": "Previously saved"}))
    assert config.change_engineer == "Previously saved"


def test_active_directory_query_uses_escaped_username_and_profile_attributes(monkeypatch):
    requests = []

    class Recordset:
        EOF = False

        def __init__(self):
            self.Fields = SimpleNamespace(Item=lambda name: SimpleNamespace(
                Value={"displayName": "Ngo Huu Dat", "department": "MS/EJV5-PS", "cn": "Dat"}[name]
            ))

        def Close(self):
            pass

    class Connection:
        def Open(self, provider):
            assert provider == "Active Directory Provider"

        def Close(self):
            pass

    class Command:
        def Execute(self):
            requests.append(self.CommandText)
            return Recordset(), 1

    def dispatch(progid):
        return Connection() if progid == "ADODB.Connection" else Command()

    client = SimpleNamespace(Dispatch=dispatch)
    monkeypatch.setitem(__import__("sys").modules, "win32com", SimpleNamespace(client=client))
    monkeypatch.setitem(__import__("sys").modules, "win32com.client", client)

    profile = creation_form._query_active_directory("user*(x)", "example.com")

    assert profile == ("Ngo Huu Dat", "MS/EJV5-PS")
    assert requests == [
        "<LDAP://DC=example,DC=com>;(&(objectCategory=person)(objectClass=user)"
        r"(sAMAccountName=user\2a\28x\29));displayName,department,cn;subtree"
    ]
