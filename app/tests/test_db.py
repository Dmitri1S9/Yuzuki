import os
from pathlib import Path
import pytest
from dotenv import load_dotenv

from app.db import DBGet
from app.ApiClients.clientOpenAI import OpenaiClient

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

if os.getenv("DEBUG") is None:
    raise Exception("Please set DEBUG=True environment variable")

character_name = "test_name"
universe_name = "test_universe"

client = OpenaiClient()
db = DBGet()

@pytest.mark.integration
def test_db_connection_and_create():
    data = client.get_character_profile(character_name, universe_name)
    client.save_character_to_db(character_name, universe_name, data)

@pytest.mark.integration
def test_get_data():
    character_id = db.get_character_id(character_name, universe_name)["id"]
    db.get_character_profile(character_id)

def test_get_not_existing_character():
    character_name_ = "new_test_name"
    res = db.get_character_id(character_name_, universe_name)
    if res:
        character_id = res["id"]
        db.get_character_profile(character_id)


