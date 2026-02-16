import os
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Dict, Any


class Database:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        mongodb_url = os.getenv("MONGODB_URL")
        self.client = AsyncIOMotorClient(mongodb_url)
        self.db = self.client.zergdb

    async def insert(self, data: dict):
        result = await self.db.entries.insert_one(data)
        return str(result.inserted_id)

    async def search(self, query: str = "", filters: dict = None) -> List[Dict]:
        search_filter = {}
        if query:
            # Simple text search - in production use proper text indexes
            search_filter["$or"] = [
                {"sequences": {"$regex": query, "$options": "i"}},
                {"features": {"$regex": query, "$options": "i"}},
                {"file_path": {"$regex": query, "$options": "i"}},
                {"names": {"$regex": query, "$options": "i"}},
            ]

        if filters:
            if filters.get("data_type") and filters["data_type"] != "all":
                search_filter["data_type"] = filters["data_type"]

        cursor = self.db.entries.find(search_filter).limit(100)
        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    async def get_stats(self):
        total = await self.db.entries.count_documents({})
        dna = await self.db.entries.count_documents({"data_type": "dna"})
        rna = await self.db.entries.count_documents({"data_type": "rna"})
        protein = await self.db.entries.count_documents({"data_type": "protein"})
        return {"total": total, "dna": dna, "rna": rna, "protein": protein}

    async def clear(self):
        await self.db.entries.delete_many({})


db = Database()
