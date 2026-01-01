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
from concurrent.futures import ThreadPoolExecutor

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

# R2 settings - fill these in
R2_ACCOUNT_ID = "REDACTED_ACCOUNT_ID"
R2_ACCESS_KEY = "REDACTED_ACCESS_KEY"
R2_SECRET_KEY = "REDACTED_SECRET_KEY"
R2_BUCKET = "fplonkadev-photos"
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

    # Check if already processed
    if thumb_path.exists() and full_path.exists():
        return {
            "thumb_local": thumb_path,
            "full_local": full_path,
            "hash": file_hash,
            "date": photo.date,
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

        print(f"  Processed: {photo.filename}")
        return {
            "thumb_local": thumb_path,
            "full_local": full_path,
            "hash": file_hash,
            "date": photo.date,
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


def list_r2_objects(dry_run: bool = False) -> set:
    """List all objects currently in R2 bucket."""
    if dry_run:
        return set()

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


def generate_html(photos: list[dict]) -> str:
    """Generate the gallery HTML with embedded photo data."""
    template = HTML_TEMPLATE.read_text()

    photo_data = [
        {
            "thumb": f"{R2_PUBLIC_URL}/thumb/{p['hash']}.webp",
            "full": f"{R2_PUBLIC_URL}/full/{p['hash']}.webp",
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
    processed = []
    photos_to_process = photos[:args.limit] if args.limit > 0 else photos
    for photo in photos_to_process:
        # Skip RAW files
        ext = Path(photo.filename).suffix.lower()
        if ext in SKIP_EXTENSIONS:
            continue

        file_hash = get_photo_hash(photo)
        result = process_image(photo, CACHE_DIR, file_hash)
        if result:
            processed.append(result)

    # Sort by date (newest first)
    processed.sort(key=lambda x: x["date"], reverse=True)

    print(f"\nProcessed {len(processed)} images")

    # Check what's already uploaded
    print("\nChecking R2...")
    existing = list_r2_objects(args.dry_run)

    # Upload new images
    print("\nUploading to R2...")
    uploaded = 0
    for p in processed:
        thumb_key = f"thumb/{p['hash']}.webp"
        full_key = f"full/{p['hash']}.webp"

        if thumb_key not in existing:
            if upload_to_r2(p["thumb_local"], thumb_key, args.dry_run):
                uploaded += 1

        if full_key not in existing:
            if upload_to_r2(p["full_local"], full_key, args.dry_run):
                uploaded += 1

    print(f"Uploaded {uploaded} new files")

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
