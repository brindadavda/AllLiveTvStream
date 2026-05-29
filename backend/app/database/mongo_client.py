import os
import json
import asyncio
import certifi
from typing import Dict, List, Any, Optional
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.utils.logger import logger

class MockCursor:
    def __init__(self, data: List[Dict[str, Any]]):
        self._data = data
        self._index = 0

    def skip(self, num: int) -> 'MockCursor':
        self._data = self._data[num:]
        return self

    def limit(self, num: int) -> 'MockCursor':
        if num > 0:
            self._data = self._data[:num]
        return self

    def sort(self, key_or_list: Any, direction: Optional[int] = None) -> 'MockCursor':
        # Simple sorting helper
        # e.g., sort("latency", 1) or sort([("latency", 1)])
        field = ""
        reverse = False
        
        if isinstance(key_or_list, list) and len(key_or_list) > 0:
            field = key_or_list[0][0]
            reverse = key_or_list[0][1] == -1
        elif isinstance(key_or_list, str):
            field = key_or_list
            if direction is not None:
                reverse = direction == -1
        
        if field:
            def sort_key(item):
                val = item.get(field)
                if val is None:
                    # Place None values at the end
                    return (1, 0) if not reverse else (-1, 0)
                return (0, val)
            self._data.sort(key=sort_key, reverse=reverse)
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._data):
            raise StopAsyncIteration
        item = self._data[self._index]
        self._index += 1
        return item

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        if length is not None:
            return self._data[:length]
        return self._data

class MockCollection:
    def __init__(self, file_path: str):
        self.file_path = file_path
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self._load_data()

    def _load_data(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                    # Convert list to dict for easier _id index lookup
                    self._channels = {item["_id"]: item for item in self._data}
                    logger.info(f"Loaded {len(self._channels)} channels from MockDB file: {self.file_path}")
            except Exception as e:
                logger.error(f"Error reading MockDB: {e}. Starting fresh.")
                self._channels = {}
        else:
            self._channels = {}
            self._save_data()

    def _save_data(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(list(self._channels.values()), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving MockDB: {e}")

    def _match_filter(self, item: Dict[str, Any], filter_dict: Dict[str, Any]) -> bool:
        if not filter_dict:
            return True
        for k, v in filter_dict.items():
            if k == "$or":
                if not isinstance(v, list):
                    continue
                match_any = False
                for sub_filter in v:
                    if self._match_filter(item, sub_filter):
                        match_any = True
                        break
                if not match_any:
                    return False
                continue
                
            # Handle regex search e.g., {"name": {"$regex": "...", "$options": "i"}}
            item_val = item.get(k)
            if isinstance(v, dict):
                if "$regex" in v:
                    pattern = v["$regex"]
                    options = v.get("$options", "")
                    import re
                    flags = re.IGNORECASE if "i" in options else 0
                    if not item_val or not re.search(pattern, str(item_val), flags):
                        return False
                elif "$in" in v:
                    if item_val not in v["$in"]:
                        return False
                elif "$ne" in v:
                    if item_val == v["$ne"]:
                        return False
            else:
                if item_val != v:
                    return False
        return True

    def find(self, filter_dict: Optional[Dict[str, Any]] = None) -> MockCursor:
        filter_dict = filter_dict or {}
        matched = []
        for item in self._channels.values():
            if self._match_filter(item, filter_dict):
                matched.append(item.copy())
        return MockCursor(matched)

    async def find_one(self, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Quick ID optimization
        if "_id" in filter_dict and len(filter_dict) == 1:
            val = self._channels.get(filter_dict["_id"])
            return val.copy() if val else None
            
        for item in self._channels.values():
            if self._match_filter(item, filter_dict):
                return item.copy()
        return None

    async def update_one(self, filter_dict: Dict[str, Any], update_dict: Dict[str, Any], upsert: bool = False) -> Any:
        # Find item
        item = await self.find_one(filter_dict)
        
        # Extract fields to set
        set_fields = update_dict.get("$set", {})
        
        if not item:
            if upsert:
                # Build new item
                new_item = {}
                # Extract filter fields
                for k, v in filter_dict.items():
                    if not k.startswith("$"):
                        new_item[k] = v
                new_item.update(set_fields)
                if "_id" not in new_item:
                    import uuid
                    new_item["_id"] = str(uuid.uuid4())
                self._channels[new_item["_id"]] = new_item
                self._save_data()
                return new_item
            return None
        
        # Update existing
        target_id = item["_id"]
        self._channels[target_id].update(set_fields)
        self._save_data()
        return self._channels[target_id]

    async def bulk_write(self, requests: List[Any]) -> Any:
        """
        Mock implementation of pymongo bulk_write for high-performance ingestion.
        """
        success_count = 0
        for req in requests:
            # Handle standard raw items or PyMongo operations
            filter_dict = getattr(req, "_filter", None)
            update_dict = getattr(req, "_doc", None)
            upsert = getattr(req, "_upsert", False)
            
            if not filter_dict and isinstance(req, dict):
                filter_dict = {"_id": req.get("_id")}
                update_dict = {"$set": req}
                upsert = True
                
            if filter_dict and update_dict:
                item = None
                if "_id" in filter_dict and len(filter_dict) == 1:
                    item = self._channels.get(filter_dict["_id"])
                else:
                    for val in self._channels.values():
                        if self._match_filter(val, filter_dict):
                            item = val
                            break
                
                set_fields = update_dict.get("$set", {})
                if not item:
                    if upsert:
                        new_item = {}
                        for k, v in filter_dict.items():
                            if not k.startswith("$"):
                                new_item[k] = v
                        new_item.update(set_fields)
                        if "_id" not in new_item:
                            import uuid
                            new_item["_id"] = str(uuid.uuid4())
                        self._channels[new_item["_id"]] = new_item
                        success_count += 1
                else:
                    target_id = item["_id"]
                    self._channels[target_id].update(set_fields)
                    success_count += 1
        
        # Save once at the end of the bulk operation
        self._save_data()
        
        class BulkWriteResult:
            def __init__(self, count):
                self.upserted_count = count
                self.modified_count = count
                
        return BulkWriteResult(success_count)

    async def count_documents(self, filter_dict: Dict[str, Any]) -> int:
        count = 0
        for item in self._channels.values():
            if self._match_filter(item, filter_dict):
                count += 1
        return count

    async def distinct(self, field: str, filter_dict: Optional[Dict[str, Any]] = None) -> List[Any]:
        filter_dict = filter_dict or {}
        values = set()
        for item in self._channels.values():
            if self._match_filter(item, filter_dict):
                val = item.get(field)
                if val is not None:
                    if isinstance(val, list):
                        values.update(val)
                    else:
                        values.add(val)
        return sorted(list(values))

    async def create_index(self, keys: Any, **kwargs: Any) -> str:
        return "index_created"

class MockDatabase:
    def __init__(self, file_path: str):
        # Determine base directory from config file path
        if file_path.endswith(".json"):
            self.directory_path = os.path.dirname(file_path)
        else:
            self.directory_path = file_path
        os.makedirs(self.directory_path, exist_ok=True)
        self._collections = {}

    def __getitem__(self, name: str) -> MockCollection:
        if name not in self._collections:
            col_file_path = os.path.join(self.directory_path, f"{name}.json")
            # Migration check: if channels.json is missing but legacy hydra_db.json exists, migrate it
            if name == "channels" and not os.path.exists(col_file_path):
                old_path = os.path.join(self.directory_path, "hydra_db.json")
                if os.path.exists(old_path):
                    try:
                        os.rename(old_path, col_file_path)
                        logger.info("Migrated legacy hydra_db.json to channels.json successfully.")
                    except Exception as e:
                        logger.error(f"Failed to migrate legacy hydra_db.json: {e}")
            self._collections[name] = MockCollection(col_file_path)
        return self._collections[name]

    def __getattr__(self, name: str) -> MockCollection:
        return self[name]

    def get_collection(self, name: str) -> MockCollection:
        return self[name]


# Setup DB Client
mongo_client: Any = None
_actual_db: Any = None
is_mock_db: bool = False

class DBWrapper:
    def __getattr__(self, name):
        global _actual_db
        if _actual_db is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return getattr(_actual_db, name)

    def __getitem__(self, name):
        global _actual_db
        if _actual_db is None:
            raise RuntimeError("Database not initialized. Call init_db() first.")
        return _actual_db[name]

db = DBWrapper()

async def init_db():
    global mongo_client, _actual_db, is_mock_db
    try:
        logger.info(f"Connecting to MongoDB at: {settings.MONGO_URI}...")
        # Check if actual Mongo is available with a short timeout
        client = AsyncIOMotorClient(
            settings.MONGO_URI,
            serverSelectionTimeoutMS=2000,
            tlsCAFile=certifi.where(),
            tls=True,
            tlsAllowInvalidCertificates=True
        )
        # Attempt to get server info to force connection check
        await client.server_info()
        
        mongo_client = client
        _actual_db = client[settings.MONGO_DB]
        is_mock_db = False
        logger.info(f"Successfully connected to MongoDB database '{settings.MONGO_DB}'!")
        
        # Create indexes
        await _actual_db.channels.create_index([("name", 1)])
        await _actual_db.channels.create_index([("category", 1)])
        await _actual_db.channels.create_index([("country", 1)])
        await _actual_db.channels.create_index([("language", 1)])
        await _actual_db.channels.create_index([("status", 1)])
        await _actual_db.channels.create_index([("active", 1)])
        await _actual_db.channels.create_index([("latency", 1)])
        
    except Exception as e:
        logger.warning(f"Could not connect to MongoDB: {e}. Falling back to File-based Mock MongoDB.")
        _actual_db = MockDatabase(settings.FALLBACK_DB_PATH)
        is_mock_db = True
        logger.info("Mock MongoDB initialized successfully in fallback mode!")
