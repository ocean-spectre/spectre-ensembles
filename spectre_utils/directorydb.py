import json
from pathlib import Path
from datetime import datetime


class LocalMongo:
    """A class that mimics the pymongo API but stores data in a directory structure."""

    def __init__(self, base_path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(
            parents=True, exist_ok=True
        )  # Ensure base directory exists

    def __getitem__(self, db_name):
        """Get a database (top-level directory)."""
        return Database(self.base_path / db_name)


class Database:
    """Represents a MongoDB-like database (maps to a top-level directory)."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)  # Ensure database directory exists

    def __getitem__(self, collection_name):
        """Get a collection (second-level directory)."""
        return Collection(self.path / collection_name)

    def list_collections(self):
        """List available collections in the database."""
        return [d.name for d in self.path.iterdir() if d.is_dir()]


class Collection:
    """Represents a MongoDB-like collection (maps to a subdirectory)."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(
            parents=True, exist_ok=True
        )  # Ensure collection directory exists

    def insert_one(self, doc):
        """Insert a single document (store as a JSON file)."""
        doc_id = doc.get(
            "_id", str(len(list(self.path.iterdir())) + 1)
        )  # Auto-generate ID if not given
        doc["_id"] = doc_id  # Ensure _id exists
        with open(self.path / f"{doc_id}.json", "w") as f:
            json.dump(doc, f)
        return {"_id": doc_id}

    def find_one(self, query):
        """Find a document that matches ALL key-value pairs in the query."""
        for file in self.path.glob("*.json"):
            with open(file, "r") as f:
                doc = json.load(f)
                # Check if all key-value pairs in the query exist in the document
                if all(doc.get(k) == v for k, v in query.items()):
                    return doc  # Return the first matching document
        return None  # No match found

    def find_all(self, query):
        """Find all documents that match ALL key-value pairs in the query."""
        matching_docs = []
        for file in self.path.glob("*.json"):
            with open(file, "r") as f:
                doc = json.load(f)
                # Check if all key-value pairs in the query exist in the document
                if all(doc.get(k) == v for k, v in query.items()):
                    matching_docs.append(doc)

        return matching_docs  # Return all matching documents (empty list if no match)

    def find_most_recent_matching(self, query):
        """Find the most recent document that matches ALL key-value pairs in the query."""
        most_recent_doc = None
        most_recent_time = datetime.min  # Start with the earliest possible datetime

        for file in self.path.glob("*.json"):
            with open(file, "r") as f:
                doc = json.load(f)

                # Check if the document matches the query
                if not all(doc.get(k) == v for k, v in query.items()):
                    continue  # Skip if it doesn't match

                # Parse 'scraped_at' if it exists
                if "_scraped_at" in doc:
                    try:
                        scraped_time = datetime.fromisoformat(doc["_scraped_at"])
                        if scraped_time > most_recent_time:
                            most_recent_time = scraped_time
                            most_recent_doc = doc
                    except ValueError:
                        continue  # Skip invalid date formats

        return most_recent_doc  # Return the most recent matching document (or None if no match)

    def find_most_recent_matching_set(self, query={}):
        """Find the set of documents with the most recent '_scraped_at' timestamp."""
        most_recent_docs = []
        most_recent_time = datetime.min
        for file in self.path.glob("*.json"):
            with open(file, "r") as f:
                doc = json.load(f)
                # Check if the document matches the query
                if not all(doc.get(k) == v for k, v in query.items()):
                    continue  # Skip if it doesn't match

                if "_scraped_at" in doc:
                    # _scraped_at is stored as an ISO string
                    # e.g., "2025-03-14 16:15:30 UTC"
                    scraped_at_str = doc["_scraped_at"].replace(" UTC", "")
                    scraped_time = datetime.strptime(
                        scraped_at_str, "%Y-%m-%d %H:%M:%S"
                    )
                    # If later _scraped_at found, then update most_recent_time and most_recent_docs
                    if scraped_time > most_recent_time:
                        most_recent_time = scraped_time
                        most_recent_docs = [doc]
                    # If same _scraped_at found, then just append to most_recent_docs
                    elif scraped_time == most_recent_time:
                        most_recent_docs.append(doc)
        return most_recent_docs

    def find(self):
        """Return all documents in the collection."""
        documents = []
        for file in self.path.glob("*.json"):
            with open(file, "r") as f:
                documents.append(json.load(f))
        return documents

    def delete_one(self, query):
        """Delete a document by a simple key-value pair."""
        for file in self.path.glob("*.json"):
            with open(file, "r") as f:
                doc = json.load(f)
                if all(doc.get(k) == v for k, v in query.items()):
                    file.unlink()  # Delete the file
                    return {"deleted_count": 1}
        return {"deleted_count": 0}

    def list_documents(self):
        """List all document filenames in the collection."""
        return [file.name for file in self.path.glob("*.json")]


# Example Usage
if __name__ == "__main__":
    db_client = LocalMongo("data")  # Base directory
    db = db_client["test_db"]  # Access database
    collection = db["users"]  # Access collection

    # Insert documents
    collection.insert_one({"_id": "123", "name": "Alice", "age": 30})
    collection.insert_one({"name": "Bob", "age": 25})  # Auto-generate _id

    # Retrieve documents
    print("Find One:", collection.find_one({"name": "Alice"}))
    print("Find All:", collection.find())

    # Delete a document
    print("Delete Result:", collection.delete_one({"_id": "123"}))

    # List collections and documents
    print("Collections in DB:", db.list_collections())
    print("Documents in Collection:", collection.list_documents())

