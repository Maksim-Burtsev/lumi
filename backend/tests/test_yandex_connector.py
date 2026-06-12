from lumi.connectors.yandex.caldav_client import (
    get_yandex_connector_row,
    load_yandex_client,
    save_yandex_credentials,
)
from lumi.db.models import ConnectorStatus
from lumi.db.session import session_scope
from lumi.services.users import UserService

from .conftest import TEST_TELEGRAM_ID


async def test_credentials_roundtrip(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        connector = await save_yandex_credentials(
            session, u, username="demo@yandex.ru", app_password="superapppassword"
        )
        assert connector.status == ConnectorStatus.CONNECTED
        assert connector.credentials_encrypted
        # creds must not be stored in plaintext
        assert "superapppassword" not in connector.credentials_encrypted

    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        client = await load_yandex_client(session, u)
        assert client._username == "demo@yandex.ru"  # noqa: SLF001
        assert client._password == "superapppassword"  # noqa: SLF001


async def test_status_when_disconnected(user):
    async with session_scope() as session:
        u = await UserService(session).ensure_user(TEST_TELEGRAM_ID)
        assert await get_yandex_connector_row(session, u) is None
