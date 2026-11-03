"""One-off: reads every media/characters/*.jpg still on disk and writes its
bytes into characters.image_bytes for the matching universe+name, by
recomputing the same sha1(f"{universe_name}|{name}")[:16] slug the original
writer (steps/images.py) used. Safe to re-run — skips any character that
already has image_bytes set. Never deletes or moves the original files.

Run from src/ (or with PYTHONPATH=src):
    python -m src.repository.scripts.migrate_character_images_to_db --dry-run
    python -m src.repository.scripts.migrate_character_images_to_db
"""
import argparse
import hashlib
from pathlib import Path

from src.repository import CharacterRepository, UniverseRepository

MEDIA_DIR = Path("media/characters")


def main(dry_run: bool = False) -> None:
    character_repo = CharacterRepository()
    universe_repo = UniverseRepository()

    slug_index: dict[str, tuple[int, str]] = {}
    for u in universe_repo.list_universes():
        full = universe_repo.get_universe_by_id(u.get_id())
        for c in full.get_roster():
            slug = hashlib.sha1(f"{full.get_name()}|{c.get_name()}".encode()).hexdigest()[:16]
            slug_index[slug] = (full.get_id(), c.get_name())

    to_migrate = migrated = skipped_existing = unmatched = 0
    for path in sorted(MEDIA_DIR.glob("*.jpg")):
        match = slug_index.get(path.stem)
        if match is None:
            unmatched += 1
            print(f"UNMATCHED       {path.name} — no character maps to this slug, left in place")
            continue
        universe_id, name = match
        character = character_repo.get_character(universe_id, name)
        if character.has_portrait():
            skipped_existing += 1
            continue
        to_migrate += 1
        print(f"{'WOULD MIGRATE' if dry_run else 'MIGRATING'}  {path.name} -> universe {universe_id}, {name!r}")
        if not dry_run:
            character_repo.save_character_portrait(universe_id, name, path.read_bytes())
            migrated += 1

    total = to_migrate + skipped_existing + unmatched
    print(f"{'would_migrate' if dry_run else 'migrated'}={to_migrate if dry_run else migrated} "
          f"skipped_existing={skipped_existing} unmatched={unmatched} total_files={total} dry_run={dry_run}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    main(**vars(ap.parse_args()))
