#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pillow",
#     "pillow-heif",
#     "boto3",
#     "osxphotos",
# ]
# ///
"""
Photo gallery sync script.

Pulls photos from an Apple Photos album, creates optimized WebP versions,
uploads to Cloudflare R2, and generates the gallery HTML.

Usage:
    uv run photo-sync.py [--dry-run] [--album "Album Name"]

Setup:
    1. Configure R2 credentials (see CONFIG section below)
    2. Create an album in Apple Photos (default: "Website")
    3. Run: uv run photo-sync.py
"""

import os
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import osxphotos
from PIL import Image, ImageOps
import pillow_heif

# Register HEIF/HEIC support with Pillow
pillow_heif.register_heif_opener()

# Skip RAW formats (process JPEGs/HEICs only)
SKIP_EXTENSIONS = {".raf", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"}

# === CONFIG ===
ALBUM_NAME = "FUJIFILM X100VI"  # Apple Photos album to sync
CACHE_DIR = Path.home() / ".cache" / "photo-gallery"
OUTPUT_HTML = Path(__file__).parent.parent / "static" / "photos" / "index.html"
HTML_TEMPLATE = Path(__file__).parent.parent / "static" / "photos" / "template.html"

# R2 settings - set these environment variables
R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY", "")
R2_SECRET_KEY = os.environ.get("R2_SECRET_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "fplonkadev-photos")
# Use the r2.dev URL from your bucket's settings (no custom domain needed)
R2_PUBLIC_URL = "https://pub-9fffa49765b54776a5da8b81c29321c9.r2.dev"

# Image settings
THUMB_WIDTH = 600
WEBP_QUALITY = 85
# ==============


def get_photo_hash(photo: osxphotos.PhotoInfo) -> str:
    """Get hash for change detection based on photo metadata."""
    h = hashlib.md5()
    h.update(photo.uuid.encode())
    h.update(str(photo.date).encode())
    if photo.date_modified:
        h.update(str(photo.date_modified).encode())
    return h.hexdigest()[:12]


def process_image(photo: osxphotos.PhotoInfo, cache_dir: Path, file_hash: str) -> dict | None:
    """Process a single image, creating thumb and full versions."""
    thumb_path = cache_dir / f"{file_hash}_thumb.webp"
    full_path = cache_dir / f"{file_hash}_full.webp"

    # Check if already processed - need to get aspect ratio from thumb
    if thumb_path.exists() and full_path.exists():
        try:
            with Image.open(thumb_path) as img:
                w, h = img.size
                aspect = round(w / h, 3)
        except:
            aspect = 1.5
        return {
            "thumb_local": thumb_path,
            "full_local": full_path,
            "hash": file_hash,
            "date": photo.date,
            "aspect": aspect,
            "cached": True,
        }

    # Export original from Photos library (use_photos_export triggers iCloud download)
    try:
        exported = photo.export(
            str(cache_dir),
            use_photos_export=True,  # This triggers iCloud download if needed
            timeout=300,  # Wait up to 5 min for iCloud download
        )
        if not exported:
            print(f"  Failed to export (may still be in iCloud): {photo.filename}")
            return None
        src_path = Path(exported[0])
    except Exception as e:
        print(f"  Export error for {photo.filename}: {e}")
        return None

    try:
        img = Image.open(src_path)

        # Handle EXIF orientation
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Convert to RGB if needed
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        orig_width, orig_height = img.size

        # Generate thumbnail
        thumb_height = int(THUMB_WIDTH * orig_height / orig_width)
        thumb = img.copy()
        thumb.thumbnail((THUMB_WIDTH, thumb_height), Image.LANCZOS)
        thumb.save(thumb_path, "WEBP", quality=WEBP_QUALITY)

        # Generate full size (original resolution, just WebP compressed)
        img.save(full_path, "WEBP", quality=WEBP_QUALITY)

        # Clean up exported original
        src_path.unlink(missing_ok=True)

        aspect = round(orig_width / orig_height, 3)

        print(f"  Processed: {photo.filename}")
        return {
            "thumb_local": thumb_path,
            "full_local": full_path,
            "hash": file_hash,
            "date": photo.date,
            "aspect": aspect,
            "cached": False,
        }

    except Exception as e:
        print(f"  Error processing {photo.filename}: {e}")
        src_path.unlink(missing_ok=True)
        return None


def get_r2_client():
    """Create R2 S3 client."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def upload_to_r2(local_path: Path, remote_key: str, dry_run: bool = False) -> bool:
    """Upload a file to R2."""
    if dry_run:
        print(f"  [DRY RUN] Would upload: {remote_key}")
        return True

    try:
        s3 = get_r2_client()
        s3.upload_file(
            str(local_path),
            R2_BUCKET,
            remote_key,
            ExtraArgs={
                "ContentType": "image/webp",
                "CacheControl": "public, max-age=31536000",
            },
        )
        return True
    except Exception as e:
        print(f"  Upload failed for {remote_key}: {e}")
        return False


def list_r2_objects() -> set:
    """List all objects currently in R2 bucket."""
    try:
        s3 = get_r2_client()
        objects = set()
        paginator = s3.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=R2_BUCKET):
            for obj in page.get("Contents", []):
                objects.add(obj["Key"])

        return objects
    except Exception as e:
        print(f"  Warning: Could not list R2 objects: {e}")
        return set()


def delete_from_r2(keys: list[str], dry_run: bool = False) -> int:
    """Delete objects from R2."""
    if not keys:
        return 0

    if dry_run:
        for key in keys:
            print(f"  [DRY RUN] Would delete: {key}")
        return len(keys)

    try:
        s3 = get_r2_client()
        # Delete in batches of 1000 (S3 limit)
        deleted = 0
        for i in range(0, len(keys), 1000):
            batch = keys[i:i+1000]
            s3.delete_objects(
                Bucket=R2_BUCKET,
                Delete={"Objects": [{"Key": k} for k in batch]}
            )
            deleted += len(batch)
        return deleted
    except Exception as e:
        print(f"  Delete failed: {e}")
        return 0


def generate_html(photos: list[dict]) -> str:
    """Generate the gallery HTML with embedded photo data."""
    template = HTML_TEMPLATE.read_text()

    photo_data = [
        {
            "thumb": f"{R2_PUBLIC_URL}/thumb/{p['hash']}.webp",
            "full": f"{R2_PUBLIC_URL}/full/{p['hash']}.webp",
            "aspect": p.get("aspect", 1.5),
        }
        for p in photos
    ]

    return template.replace("PHOTOS_JSON_PLACEHOLDER", json.dumps(photo_data))


def main():
    parser = argparse.ArgumentParser(description="Sync Apple Photos album to gallery")
    parser.add_argument("--dry-run", action="store_true", help="Don't upload, just show what would happen")
    parser.add_argument("--album", default=ALBUM_NAME, help=f"Album name (default: {ALBUM_NAME})")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of photos to process (0 = all)")
    args = parser.parse_args()

    print("Photo Gallery Sync")
    print("==================")

    # Ensure cache directory exists
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Load Photos library
    print(f"\nLoading Apple Photos library...")
    photosdb = osxphotos.PhotosDB()

    # Find album
    albums = [a for a in photosdb.album_info if a.title == args.album]
    if not albums:
        print(f"\nAlbum '{args.album}' not found.")
        print("Available albums:")
        for a in sorted(photosdb.album_info, key=lambda x: x.title or ""):
            if a.title:
                print(f"  - {a.title}")
        return

    album = albums[0]
    photos = album.photos

    if not photos:
        print(f"\nAlbum '{args.album}' is empty. Add some photos and run again.")
        return

    print(f"Found {len(photos)} photos in album '{args.album}'")

    # Process images (downloads from iCloud if needed)
    print("\nProcessing images...")
    photos_to_process = photos[:args.limit] if args.limit > 0 else photos

    # Filter out RAW files first
    photos_filtered = [
        p for p in photos_to_process
        if Path(p.filename).suffix.lower() not in SKIP_EXTENSIONS
    ]

    # Process in parallel (4 workers - gentle on Photos.app)
    processed = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {
            executor.submit(process_image, photo, CACHE_DIR, get_photo_hash(photo)): photo
            for photo in photos_filtered
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                processed.append(result)

    # Sort by date (newest first)
    processed.sort(key=lambda x: x["date"], reverse=True)

    print(f"\nProcessed {len(processed)} images")

    # Upload newly processed images (skip cached ones - they're already in R2)
    print("\nUploading to R2...")
    uploads = []
    for p in processed:
        if not p.get("cached", False):
            uploads.append((p["thumb_local"], f"thumb/{p['hash']}.webp"))
            uploads.append((p["full_local"], f"full/{p['hash']}.webp"))

    uploaded = 0
    if uploads:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(upload_to_r2, local, key, args.dry_run)
                for local, key in uploads
            ]
            for future in as_completed(futures):
                if future.result():
                    uploaded += 1

    print(f"Uploaded {uploaded} new files")

    # Sync deletions - remove from R2 what's no longer in album
    print("\nSyncing deletions...")
    current_hashes = {p["hash"] for p in processed}
    expected_keys = set()
    for h in current_hashes:
        expected_keys.add(f"thumb/{h}.webp")
        expected_keys.add(f"full/{h}.webp")

    existing_keys = list_r2_objects()
    to_delete = [k for k in existing_keys if k not in expected_keys]

    if to_delete:
        deleted = delete_from_r2(to_delete, args.dry_run)
        print(f"Deleted {deleted} orphaned files")
    else:
        print("No orphaned files to delete")

    # Generate HTML
    print("\nGenerating HTML...")
    html = generate_html(processed)

    if args.dry_run:
        print(f"[DRY RUN] Would write HTML to {OUTPUT_HTML}")
    else:
        OUTPUT_HTML.write_text(html)
        print(f"Wrote {OUTPUT_HTML}")

    print("\nDone!")
    print(f"\nGallery: https://fplonka.dev/photos")
    print(f"Images:  {R2_PUBLIC_URL}")


if __name__ == "__main__":
    main()
