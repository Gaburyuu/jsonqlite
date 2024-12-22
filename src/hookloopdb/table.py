import json
from typing import Any
from .controller import AsyncSQLiteController


class HookLoopTable:
    def __init__(self, controller: AsyncSQLiteController, table_name: str):
        self.controller = controller
        self.table_name = table_name

    async def initialize(self, indexes: list[str] = None):
        """Initialize the table with optional JSON indexes."""
        query = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data JSON NOT NULL
            )
        """
        await self.controller.execute(query)

        indexes = indexes or []
        for index in indexes:
            index_query = f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_{index}
                ON {self.table_name} (json_extract(data, '$.{index}'))
            """
            await self.controller.execute(index_query)

    async def upsert(self, document: dict[Any, Any]) -> int:
        """Insert or update a document."""
        id_value = document.get("id")
        json_data = json.dumps(document.get("data", {}))

        if id_value is None:
            query = f"INSERT INTO {self.table_name} (data) VALUES (json(?))"
            params = (json_data,)
        else:
            query = f"""
                INSERT INTO {self.table_name} (id, data)
                VALUES (?, json(?))
                ON CONFLICT (id) DO UPDATE SET data = json(?)
            """
            params = (id_value, json_data, json_data)

        cursor = await self.controller.connection.execute(query, params)
        await self.controller.connection.commit()
        return cursor.lastrowid if id_value is None else id_value

    async def find(self, doc_id: int) -> dict | None:
        """Find a document by ID."""
        query = f"SELECT id, data FROM {self.table_name} WHERE id = ?"
        result = await self.controller.execute(query, (doc_id,))
        if result:
            return {"id": result[0][0], "data": json.loads(result[0][1])}
        return None