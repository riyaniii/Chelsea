import gi

gi.require_version('Secret', '1')
from gi.repository import Secret

SERVICE = 'io.github.riyaniii.Chelsea'

SCHEMA = Secret.Schema.new(
    SERVICE,
    Secret.SchemaFlags.NONE,
    {
        'service': Secret.SchemaAttributeType.STRING,
        'account': Secret.SchemaAttributeType.STRING,
    },
)


class Secrets:

    def __init__(self, service: str):
        self.service = service

    def attributes(self, account: str) -> dict:
        return {'service': self.service, 'account': account}

    def save(self, account: str, secret: str) -> None:
        try:
            Secret.password_store_sync(
                SCHEMA, self.attributes(account), Secret.COLLECTION_DEFAULT,
                f'Chelsea {self.service} login for {account}', secret, None)
        except Exception as error:
            print(f'[chelsea] saving the login failed: {error}')

    def load(self, account: str) -> str:
        try:
            return Secret.password_lookup_sync(SCHEMA, self.attributes(account), None) or ''
        except Exception as error:
            print(f'[chelsea] loading the login failed: {error}')
            return ''

    def forget(self, account: str) -> None:
        try:
            Secret.password_clear_sync(SCHEMA, self.attributes(account), None)
        except Exception as error:
            print(f'[chelsea] forgetting the login failed: {error}')
