import pytest
from src import DuctTapeDB
import tempfile
import os
from .data import Data
import json
import threading


@pytest.fixture
def memory_db() -> DuctTapeDB:
    """Fixture to provide an in-memory DuctTapeDB instance."""
    db = DuctTapeDB.create_memory()
    return db


def get_temp_db_path(prefix: str = "default"):
    """Create and return a temporary file-based database path."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=".db")
    return temp_file.name


@pytest.fixture
def file_db() -> DuctTapeDB:
    """Fixture to create a file-based NoSQLLiteDB instance."""
    db_path = get_temp_db_path()
    db = DuctTapeDB.create("main", db_path)

    yield db

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture
def thread_db() -> DuctTapeDB:
    """Fixture to create a file-based NoSQLLiteDB instance."""
    db_path = get_temp_db_path(prefix="thread")
    db = DuctTapeDB.create("thread", db_path)

    yield db

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


def query_for_table(db: DuctTapeDB):
    """queries if a table exists and returns the result"""

    db.connect()
    db._initialize_table()
    # Check if the expected table exists
    query = """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name=?
    """
    cursor = db.conn.execute(query, (db.table,))
    result = cursor.fetchone()
    db.close()
    return result


def test_db_initialized(memory_db: DuctTapeDB):
    """Test if the database is initialized and the table exists."""

    result = query_for_table(memory_db)

    # Assert that the table exists
    assert result is not None, "Database table should exist after initialization."
    assert (
        result[0] == memory_db.table
    ), f"Expected table '{memory_db.table}', got '{result[0]}'"


def test_factory_methods():
    """Test if the database is initialized and the table exists after creating with factories"""
    memory_db = DuctTapeDB.create_memory()

    result = query_for_table(memory_db)

    # Assert that the table exists
    assert result is not None, "Database table should exist after initialization."
    assert (
        result[0] == memory_db.table
    ), f"Expected table '{memory_db.table}', got '{result[0]}'"


def test_file_db(file_db):
    """tests the creation of a file db, not memory"""
    result = query_for_table(file_db)

    # Assert that the table exists
    assert result is not None, "Database table should exist after initialization."
    assert (
        result[0] == file_db.table
    ), f"Expected table '{file_db.table}', got '{result[0]}'"


def test_invalid_db_path():
    """Test that invalid database paths raise an error."""
    with pytest.raises(RuntimeError, match="Failed to connect"):
        DuctTapeDB(path="/invalid/path/to/db.sqlite", table="main")


@pytest.fixture
def dq_db() -> DuctTapeDB:
    """Initialize a db with sample data"""
    db_path = get_temp_db_path()
    db = DuctTapeDB.create("dq", db_path)

    db._initialize_table()  # connects but doesn't close
    db.upsert_document(Data.hero)
    db.upsert_document(Data.monster)
    db.upsert_document(Data.equipment)
    # Close here I suppose since it's not in memory
    db.close()

    yield db

    # Cleanup
    if os.path.exists(db_path):
        os.remove(db_path)


def test_insert_hero(dq_db):
    """Test inserting and retrieving the hero document."""
    hero = Data.hero
    hero_data = hero["data"]
    dq_db.connect()
    db = dq_db
    result = db.conn.execute(
        f"SELECT data FROM {db.table} WHERE id = ?", (hero["id"],)
    ).fetchone()
    assert result is not None, "Hero document should be present in the database."
    print("result", result)
    retrieved_hero = json.loads(result[0])
    assert (
        retrieved_hero["name"] == hero_data["name"]
    ), f"Expected hero name '{hero_data['name']}', got '{retrieved_hero['name']}'"
    db.close()


def test_insert_and_update_monster(dq_db):
    """Test inserting and retrieving the monster document."""
    monster = Data.monster
    monster_data = monster["data"]
    updated_monster_data = {
        **monster_data,
        "level": 99,
        "abilities": monster_data["abilities"]
        + [
            "MegaMagic",
        ],
    }
    updated_monster = {**monster, "data": updated_monster_data}

    # Check the insert
    dq_db.connect()
    db = dq_db
    result = db.conn.execute(
        f"SELECT data FROM {db.table} WHERE id = ?", (monster["id"],)
    ).fetchone()
    assert result is not None, "Monster document should be present in the database."
    retrieved_monster = json.loads(result[0])
    assert (
        retrieved_monster["name"] == monster_data["name"]
    ), f"Expected monster name '{monster_data['name']}', got '{retrieved_monster['name']}'"

    # Okay now make an edit
    db.upsert_document(updated_monster)
    result = db.conn.execute(
        f"SELECT data FROM {db.table} WHERE id = ?", (updated_monster["id"],)
    ).fetchone()
    assert (
        result is not None
    ), "Updated monster should still be present in the database."

    # Verify the updated data
    retrieved_monster = json.loads(result[0])
    assert (
        retrieved_monster["level"] == updated_monster_data["level"]
    ), f"Expected updated level {updated_monster_data['level']}, got {retrieved_monster['level']}"
    assert (
        retrieved_monster["abilities"] == updated_monster_data["abilities"]
    ), f"Expected updated abilities {updated_monster_data['abilities']}, got {retrieved_monster['abilities']}"
    db.close()


def test_insert_and_delete(dq_db):
    """Test inserting a document and then deleting it."""
    metal_slime = Data.metal_slime

    # Step 1: Insert Metal Slime
    dq_db.connect()
    db = dq_db
    ms_id = db.upsert_document(metal_slime)
    result = db.conn.execute(
        f"SELECT data FROM {db.table} WHERE id = ?", (ms_id,)
    ).fetchone()
    assert (
        result is not None
    ), "Metal Slime should be present in the database after insertion."

    # Verify the inserted data
    retrieved_slime = json.loads(result[0])
    assert (
        retrieved_slime["name"] == metal_slime["name"]
    ), f"Expected Metal Slime name '{metal_slime['name']}', got '{retrieved_slime['name']}'"

    # Step 2: Delete Metal Slime
    db.delete_document(ms_id)
    result = db.conn.execute(
        f"SELECT data FROM {db.table} WHERE id = ?", (ms_id,)
    ).fetchone()
    assert (
        result is None
    ), "Metal Slime should no longer be present in the database after deletion."
    db.close()


def test_find_existing_document(dq_db):
    """Test finding an existing document by its ID."""
    slime = Data.monster

    # Insert the document
    dq_db.connect()
    db = dq_db
    # Test find
    result = db.find(slime["id"])
    assert (
        result is not None
    ), "The find method should return a result for an existing document."
    assert result["id"] == slime["id"], f"Expected ID {slime['id']}, got {result['id']}"
    assert (
        result["data"]["name"] == slime["data"]["name"]
    ), f"Expected name '{slime['data']['name']}', got '{result['data']['name']}'"
    db.close()


def test_find_nonexistent_document(memory_db):
    """Test finding a non-existent document by its ID."""
    non_existent_id = 999
    with memory_db as db:
        db._initialize_table()
        result = db.find(non_existent_id)
    assert (
        result is None
    ), "The find method should return None for a non-existent document."


def test_search_existing_key_value(dq_db):
    """Test searching for documents with an existing key-value pair."""
    slime = Data.monster

    # Insert the document
    dq_db.connect()
    db = dq_db

    # Test search
    results = db.search("name", slime["data"]["name"])
    assert (
        len(results) > 0
    ), "The search method should return at least one result for an existing key-value pair."
    assert (
        results[0]["data"]["name"] == slime["data"]["name"]
    ), f"Expected name '{slime['data']['name']}', got '{results[0]['data']['name']}'"
    db.close()


def test_search_nonexistent_key_value(dq_db):
    """Test searching for documents with a non-existent key-value pair."""
    dq_db.connect()
    db = dq_db
    results = db.search("name", "Nonexistent Monster")
    assert (
        len(results) == 0
    ), "The search method should return an empty list for a non-existent key-value pair."
    db.close()


def test_aggregate_safe(memory_db):
    """Test the aggregate function with parameterized conditions."""

    # Insert monsters into the database
    with memory_db as db:
        memory_db._initialize_table()
        for monster in Data.monster_list:
            db.upsert_document(monster)

        # Aggregate: COUNT monsters with level > 5
        count = db.aggregate(
            "COUNT", "level", where_values=[{"field": "level", "sign": ">", "value": 5}]
        )
        assert count == 2, f"Expected 2 monsters with level > 5, got {count}"

        # Aggregate: SUM of HP for all monsters
        total_hp = db.aggregate("SUM", "hp")
        assert total_hp == 59, f"Expected total HP to be 59, got {total_hp}"


def test_aggregate_where_raw(memory_db):
    """Test the aggregate function with raw WHERE clause (use cautiously)."""

    # Insert monsters into the database
    with memory_db as db:
        memory_db._initialize_table()
        for monster in Data.monster_list:
            db.upsert_document(monster)

        # Aggregate: COUNT monsters with a raw WHERE clause
        count = db.aggregate(
            "COUNT", "level", where_raw="json_extract(data, '$.type') = 'Monster'"
        )
        assert count == 3, f"Expected 3 monsters, got {count}"

        # Quick and dirty SQL injection test
        with pytest.raises(
            RuntimeError, match="You can only execute one statement at a time"
        ):
            db.aggregate("COUNT", "level", where_raw="1=1; DROP TABLE documents;")


def worker(db_obj: DuctTapeDB, thread_id):
    db_obj.connect()
    db = db_obj
    for i in range(100):
        db.insert({"name": f"Thread-{thread_id}-{i}", "age": (thread_id * 10) + i})

    for i in range(100):
        result = db.search("name", f"Thread-{thread_id}-{i}")
        assert len(result) == 1
        assert result[0]["data"]["age"] == (thread_id * 10) + i
    db_obj.close()


def test_thread_safety(thread_db):
    """Test database operations in multiple threads."""

    threads = []
    for i in range(5):  # Create 5 threads
        t = threading.Thread(target=worker, args=(thread_db, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # Verify the aggregate count
    with thread_db as db:
        assert db.aggregate("COUNT", "age") == 500, "Total count should be 500"