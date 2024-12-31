import json
from typing import Any
from .controller import AsyncSQLiteController
from aiosqlite import Connection as Aioconnection


class HookLoopTable:
    def __init__(self, controller: AsyncSQLiteController, table_name: str):
        self.controller = controller
        self.table_name = table_name

    @property
    def connection(self) -> Aioconnection:
        return self.controller._connection

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
        print("json_data", json_data)

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

        cursor = await self.controller.execute(query, params)
        await self.controller.commit()
        return cursor.lastrowid if id_value is None else id_value

    async def find(self, doc_id: int) -> dict | None:
        """Find a document by ID."""
        query = f"SELECT id, data FROM {self.table_name} WHERE id = ?"
        cursor = await self.controller.execute(query, (doc_id,))
        result = await cursor.fetchone()
        if result:
            return {"id": result[0], "data": json.loads(result[1])}
        return None

    async def search_basic(self, key: str, value: Any) -> list[dict]:
        """Search for documents by a JSON key-value pair.

        Args:
            key (str): The JSON key to search for.
            value (Any): The value to match against the JSON key.

        Returns:
            list[dict]: A list of matching documents as dictionaries.
        """
        query = f"""
            SELECT id, data
            FROM {self.table}
            WHERE json_extract(data, '$.' || ?) = ?
        """
        cursor = await self.controller.execute(query, (key, value))
        results = [
            {"id": row[0], "data": json.loads(row[1])} for row in cursor.fetchall()
        ]
        return results

    async def search(self, conditions: dict[str, Any]) -> list[dict]:
        """
        Search for documents by multiple conditions.

        Args:
            conditions (dict[str, Any]): A dictionary of conditions.
                - `id` will be matched as a column.
                - Other keys will be matched within the `data` JSON.

        Returns:
            list[dict]: A list of matching documents as dictionaries.
        """
        if not conditions:
            raise ValueError("Conditions cannot be empty.")

        # Separate `id` from JSON conditions
        id_condition = conditions.pop("id", None)

        # Build the WHERE clause
        where_clauses = []
        params = []

        if id_condition is not None:
            where_clauses.append("id = ?")
            params.append(id_condition)

        for key, value in conditions.items():
            where_clauses.append(f"json_extract(data, '$.{key}') = ?")
            params.append(value)

        where_statement = " AND ".join(where_clauses)

        query = f"""
            SELECT id, data
            FROM {self.table_name}
            WHERE {where_statement}
        """

        print("Executing Query:", query)
        print("Query Params:", params)

        # Execute the query
        cursor = await self.connection.execute(query, params)
        results = [
            {"id": row[0], "data": json.loads(row[1])}
            for row in await cursor.fetchall()
        ]
        return results

    async def search_advanced(self, conditions: list[dict[str, Any]]) -> list[dict]:
        """
        Search for documents using advanced conditions.

        Args:
            conditions (list[dict[str, Any]]): A list of conditions.
                Each condition should be a dictionary with the keys:
                    - "key": The JSON key to search.
                    - "value": The value to match.
                    - "operator": The comparison operator (e.g., '=', '!=', '<', '>').

        Returns:
            list[dict]: A list of matching documents as dictionaries.
        """
        if not conditions:
            raise ValueError("Conditions cannot be empty.")

        where_clauses = []
        params = []

        allowed_operators = {"=", "!=", "<", ">", "<=", ">="}

        for condition in conditions:
            key = condition.get("key")
            value = condition.get("value")
            operator = condition.get("operator", "=")

            if operator not in allowed_operators:
                raise ValueError(f"Invalid operator: {operator}")

            where_clauses.append(f"json_extract(data, '$.{key}') {operator} ?")
            params.append(value)

        where_statement = " AND ".join(where_clauses)
        query = f"""
            SELECT id, data
            FROM {self.table_name}
            WHERE {where_statement}
        """

        print("query", query)
        print("params", params)

        cursor = await self.controller.execute(query, params)
        results = [
            {"id": row[0], "data": json.loads(row[1])}
            for row in await cursor.fetchall()
        ]
        return results

    async def delete_document(self, id: int):
        """Delete a document by its unique ID.

        Args:
            id (int): Unique identifier of the document to delete.

        Returns:
            None
        """
        query = f"DELETE FROM {self.table_name} WHERE id = ?"
        await self.controller.execute(query, (id,))
        await self.controller.commit()
