"""HTTP service entry point for the cdbr solving pipeline."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Annotated

import cdbr.ui as click
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

from cdbr import __version__
from cdbr.core.exceptions import CdbrCoreError
from cdbr.core.photo import PhotoFormat, detect_photo_format
from cdbr.core.pipeline import solve_photo
from cdbr.core.presentation import write_solution_photo

DEFAULT_MAX_UPLOAD_MIB = 25
CHUNK_SIZE = 1024 * 1024
WEB_ROOT = Path(__file__).parent / "assets" / "web"

app = FastAPI(
    title="cdbr",
    description="Solve photographed Code Break puzzles.",
    version=__version__,
)
app.mount("/static", StaticFiles(directory=WEB_ROOT), name="static")


@app.get("/", response_class=FileResponse, include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_ROOT / "index.html")


@app.get("/favicon.png", response_class=FileResponse, include_in_schema=False)
def favicon() -> FileResponse:
    return FileResponse(WEB_ROOT / "f-logo.png")


def _max_upload_bytes() -> int:
    value = int(os.environ.get("CDBR_MAX_UPLOAD_MIB", DEFAULT_MAX_UPLOAD_MIB))
    return value * 1024 * 1024


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    maximum = _max_upload_bytes()
    written = 0
    with destination.open("wb") as stream:
        while chunk := await upload.read(CHUNK_SIZE):
            written += len(chunk)
            if written > maximum:
                raise HTTPException(
                    status_code=413, detail=f"Photograph exceeds the {maximum // 1024 // 1024} MiB limit"
                )
            stream.write(chunk)
    if not written:
        raise HTTPException(status_code=400, detail="Photograph is empty")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/solve", response_class=Response)
async def solve_endpoint(photo: Annotated[UploadFile, File()]) -> Response:
    suffix = Path(photo.filename or "upload").suffix.lower()
    if suffix not in {".avif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}:
        suffix = ".img"

    with tempfile.TemporaryDirectory(prefix="cdbr-http-") as directory:
        work_dir = Path(directory)
        source = work_dir / f"upload{suffix}"
        destination = work_dir / "solution.jpg"
        await _save_upload(photo, source)
        try:
            if detect_photo_format(source) is PhotoFormat.UNKNOWN:
                raise ValueError("Unsupported or unrecognised image format")
            solved = solve_photo(source, work_dir)
            write_solution_photo(source, destination, solved.puzzle, solved.mapping, work_dir)
        except (CdbrCoreError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        status = "complete" if solved.complete else "partial"
        return Response(
            content=destination.read_bytes(),
            media_type="image/jpeg",
            headers={
                "Content-Disposition": 'inline; filename="solution.jpg"',
                "X-Cdbr-Solution": status,
                "X-Cdbr-Solutions-Found": str(len(solved.result.solutions)),
                "X-Cdbr-Search-Exhausted": str(solved.result.exhausted).lower(),
            },
        )


@click.command(name="cdbrd")
@click.option("--host", default="0.0.0.0", show_default=True, envvar="CDBR_HOST")
@click.option("--port", default=8000, show_default=True, type=click.IntRange(1, 65535), envvar="PORT")
@click.option("--reload", is_flag=True, help="Reload when Python source files change.")
def cdbrd_main(host: str, port: int, reload: bool) -> None:
    """Run the cdbr HTTP service."""

    uvicorn.run("cdbr.server:app", host=host, port=port, reload=reload, workers=1)


def main() -> None:
    cdbrd_main()


if __name__ == "__main__":
    main()
