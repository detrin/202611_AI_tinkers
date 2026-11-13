import pytest
from fastapi.testclient import TestClient

from backend.app.adapters.executors import InlineExecutor
from backend.app.container import build_services
from backend.app.domain import ImageInput
from backend.app.main import create_app

from .fakes import FakeFetcher, FakePins, FakeProducts, FakeSocial, FakeStore, FakeTasteModel, FakeWeather, InMemoryDatabase, ScriptedChat


class Env:
    """Fakes + wired services, so tests can both act and inspect."""

    def __init__(self):
        self.db, self.store, self.fetcher, self.chat = InMemoryDatabase(), FakeStore(), FakeFetcher(), ScriptedChat()
        self.pins, self.products, self.weather, self.social = FakePins(), FakeProducts(), FakeWeather(), FakeSocial()
        self.taste_model = FakeTasteModel()
        self.c = build_services(db=self.db, store=self.store, fetcher=self.fetcher, chat=self.chat, pins=self.pins,
                                products=self.products, social=self.social, weather=self.weather, taste_model=self.taste_model,
                                executor=InlineExecutor())

    def user(self, **kw):
        return self.c.users.create({"name": "Dan", "city": "Prague", **kw})

    def items(self, uid, n=2):
        return self.c.wardrobe.add(uid, [ImageInput(f"photo{i}".encode()) for i in range(n)])


@pytest.fixture
def env():
    return Env()


@pytest.fixture
def client(env):
    with TestClient(create_app(lambda: env.c)) as c:
        yield c
