from __future__ import annotations

import logging
from typing import Any, Optional

from pymongo import MongoClient, ReadPreference

from config import MONGO_URI

logger = logging.getLogger(__name__)


def get_mongo_client(uri: Optional[str] = None) -> MongoClient:
    uri = uri or MONGO_URI
    if not uri:
        raise RuntimeError("MONGO_URI is not set")

    # Atlas/TLS works by default with modern pymongo. Keep timeouts configurable.
    return MongoClient(
        uri,
        serverSelectionTimeoutMS=10_000,
        connectTimeoutMS=10_000,
        retryWrites=True,
        read_preference=ReadPreference.PRIMARY,
    )


def get_database(client: MongoClient):
    # Use database name from URI if present; fallback to default.
    # Mongo URI typically ends with /<db>?....
    db_name = getattr(client, "_MongoClient__default_database", None)
    # pymongo internal; safe fallback
    return client.get_default_database()


def get_db() -> Any:
    client = get_mongo_client()
    return get_database(client)

