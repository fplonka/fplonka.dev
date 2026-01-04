#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "pillow-heif", "boto3", "osxphotos"]
# ///
"""Sync Apple Photos album to R2 and generate gallery HTML."""

import os
import json
import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
import osxphotos
import pillow_heif
from botocore.config import Config
from PIL import Image, ImageOps

pillow_heif.register_heif_opener()

# Config
ALBUM = "FUJIFILM X100VI"
CACHE = Path.home() / ".cache" / "photo-gallery"
OUTPUT = Path(__file__).parent.parent / "static" / "photos" / "index.html"
TEMPLATE = Path(__file__).parent.parent / "static" / "photos" / "template.html"
R2_URL = "https://pub-9fffa49765b54776a5da8b81c29321c9.r2.dev"
SKIP_EXT = {".raf", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"}


def get_r2():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        config=Config(signature_version="s3v4"),
    )


def list_r2():
    s3 = get_r2()
    keys = set()
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=os.environ.get("R2_BUCKET", "fplonkadev-photos")):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def upload(local, key):
    get_r2().upload_file(str(local), os.environ.get("R2_BUCKET", "fplonkadev-photos"), key,
                         ExtraArgs={"ContentType": "image/webp", "CacheControl": "public, max-age=31536000"})


def delete_keys(keys):
    if keys:
        get_r2().delete_objects(Bucket=os.environ.get("R2_BUCKET", "fplonkadev-photos"),
                                Delete={"Objects": [{"Key": k} for k in keys]})


def photo_hash(photo):
    h = hashlib.md5()
    h.update(photo.uuid.encode())
    h.update(str(photo.date).encode())
    if photo.date_modified:
        h.update(str(photo.date_modified).encode())
    return h.hexdigest()[:12]


def process(photo, h):
    """Process photo, return (hash, aspect, date) or None."""
    thumb = CACHE / f"{h}_thumb.webp"
    full = CACHE / f"{h}_full.webp"

    if thumb.exists() and full.exists():
        with Image.open(thumb) as img:
            w, hi = img.size
        return h, round(w / hi, 3), photo.date, thumb, full

    print(f"  Exporting: {photo.filename}...")
    exported = photo.export(str(CACHE), use_photos_export=True, timeout=30)
    if not exported:
        print(f"  Skip (iCloud): {photo.filename}")
        return None

    src = Path(exported[0])
    img = Image.open(src)
    img = ImageOps.exif_transpose(img) or img
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    w, hi = img.size
    aspect = round(w / hi, 3)

    t = img.copy()
    t.thumbnail((600, int(600 * hi / w)), Image.LANCZOS)
    t.save(thumb, "WEBP", quality=85)
    img.save(full, "WEBP", quality=85)
    src.unlink()

    print(f"  Processed: {photo.filename}")
    return h, aspect, photo.date, thumb, full


def main():
    CACHE.mkdir(parents=True, exist_ok=True)

    # Get album photos
    print("Loading Photos library...")
    db = osxphotos.PhotosDB()
    album = next((a for a in db.album_info if a.title == ALBUM), None)
    if not album:
        print(f"Album '{ALBUM}' not found")
        return

    photos = [(p, photo_hash(p)) for p in album.photos if Path(p.filename).suffix.lower() not in SKIP_EXT]
    print(f"Album: {len(photos)} photos")

    # Check R2
    print("Checking R2...")
    r2_keys = list_r2()
    r2_hashes = {k.split("/")[1].replace(".webp", "") for k in r2_keys if "/" in k}
    print(f"R2: {len(r2_hashes)} photos")

    # Process and upload missing
    to_upload = [(p, h) for p, h in photos if h not in r2_hashes]
    results = []

    if to_upload:
        print(f"\nProcessing {len(to_upload)} new...")
        with ThreadPoolExecutor(4) as ex:
            for i, r in enumerate(ex.map(lambda x: process(x[0], x[1]), to_upload)):
                if r:
                    results.append(r)
                    print(f"  Uploading {i+1}/{len(to_upload)}...")
                    upload(r[3], f"thumb/{r[0]}.webp")
                    upload(r[4], f"full/{r[0]}.webp")

    # Delete orphans
    print("Checking for orphans...")
    album_hashes = {h for _, h in photos}
    orphans = [k for k in r2_keys if k.split("/")[1].replace(".webp", "") not in album_hashes]
    if orphans:
        print(f"Deleting {len(orphans)} orphans...")
        delete_keys(orphans)

    # Generate HTML from R2
    print("Fetching final R2 state...")
    final_r2 = list_r2()
    final_hashes = {k.split("/")[1].replace(".webp", "") for k in final_r2 if "/" in k}
    print("Generating HTML...")

    # Build photo data with dates/aspects
    data = {}
    for p, h in photos:
        if h in final_hashes:
            thumb = CACHE / f"{h}_thumb.webp"
            aspect = 1.5
            if thumb.exists():
                with Image.open(thumb) as img:
                    aspect = round(img.size[0] / img.size[1], 3)
            data[h] = {"hash": h, "aspect": aspect, "date": p.date}

    # Sort by date, generate HTML
    sorted_photos = sorted(data.values(), key=lambda x: x["date"], reverse=True)
    html_data = [{"thumb": f"{R2_URL}/thumb/{p['hash']}.webp", "full": f"{R2_URL}/full/{p['hash']}.webp", "aspect": p["aspect"]} for p in sorted_photos]

    html = TEMPLATE.read_text().replace("PHOTOS_JSON_PLACEHOLDER", json.dumps(html_data))
    OUTPUT.write_text(html)

    print(f"\nDone! {len(sorted_photos)} photos")


if __name__ == "__main__":
    main()
