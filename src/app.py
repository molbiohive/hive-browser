from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from .database import db
from .models import SearchRequest, ScanRequest
from .importer import Importer


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await db.connect()
    print("Connected to MongoDB")
    yield
    # Shutdown
    if db.client:
        db.client.close()


app = FastAPI(title="Zerg Browser", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files
app.mount("/assets", StaticFiles(directory="assets"), name="assets")


@app.get("/")
async def root():
    return FileResponse("assets/index.html")


@app.post("/api/search")
async def search(request: SearchRequest):
    filters = {"data_type": request.data_type} if request.data_type != "all" else {}
    results = await db.search(request.query, filters)

    # Simple field mapping
    if request.from_field != "any" and request.to_field != "any":
        mapped = []
        for r in results:
            if request.from_field in r and request.to_field in r:
                mapped.append(
                    {
                        "from": r.get(request.from_field),
                        "to": r.get(request.to_field),
                        "data": r,
                    }
                )
        results = mapped

    return {"query": request.query, "count": len(results), "results": results}


@app.post("/api/scan")
async def scan(request: ScanRequest):
    importer = Importer(db)
    return await importer.scan_directory(request.directory_path, request.recursive)


@app.get("/api/stats")
async def stats():
    return await db.get_stats()


@app.delete("/api/clear")
async def clear():
    await db.clear()
    return {"message": "Database cleared"}


@app.post("/api/import-sample")
async def import_sample():
    importer = Importer(db)
    return await importer.scan_directory("/app/data", True)
