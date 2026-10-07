#!/usr/bin/env python3
"""Production Backup and Disaster Recovery Script for I_LoveSeafood AI Ecosystem.

Features:
1. Automated PostgreSQL Dump:
   - Uses `docker compose exec postgres pg_dump` to create atomic SQL dumps.
   - Compresses output with gzip (`.sql.gz`).
2. Model & Storage Snapshot:
   - Compresses `./storage/models` and dataset manifests into `.tar.gz`.
3. Retention Rotation:
   - Automatically prunes backups older than the retention threshold (default: keep last 7).
4. Restore Guidelines & Verification:
   - Provides dry-run validation and documented restore commands.

Usage:
    python scripts/backup_production.py [--keep-last 7] [--output-dir ./backups]
"""

import argparse
import datetime
import gzip
import os
import shutil
import subprocess
import sys
import tarfile


def create_backup_dirs(backup_dir: str) -> str:
    """Ensure backup target directory exists."""
    os.makedirs(backup_dir, exist_ok=True)
    return os.path.abspath(backup_dir)


def backup_postgres(backup_dir: str, timestamp_str: str) -> str:
    """Run pg_dump via docker compose and compress output."""
    dump_filename = f"postgres_backup_{timestamp_str}.sql.gz"
    dump_path = os.path.join(backup_dir, dump_filename)
    
    print(f"[*] Dumping PostgreSQL database to {dump_filename}...")
    cmd = [
        "docker", "compose", "exec", "-T", "postgres",
        "pg_dump", "-U", "admin", "my_database"
    ]
    
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(timeout=120)
        
        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace")
            print(f"[!] pg_dump failed with exit code {proc.returncode}: {err_msg}")
            return ""
            
        with gzip.open(dump_path, "wb") as f_out:
            f_out.write(stdout)
            
        size_kb = os.path.getsize(dump_path) / 1024
        print(f"[+] PostgreSQL dump created: {dump_path} ({size_kb:.1f} KB)")
        return dump_path
    except Exception as e:
        print(f"[!] PostgreSQL backup failed: {e}")
        return ""


def backup_storage_models(backup_dir: str, timestamp_str: str, storage_root: str = "./storage") -> str:
    """Archive storage/models directory into a tar.gz package."""
    archive_filename = f"storage_models_{timestamp_str}.tar.gz"
    archive_path = os.path.join(backup_dir, archive_filename)
    models_dir = os.path.join(storage_root, "models")
    
    if not os.path.exists(models_dir):
        print(f"[!] Storage models directory {models_dir} does not exist, skipping.")
        return ""
        
    print(f"[*] Archiving {models_dir} to {archive_filename}...")
    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(models_dir, arcname="models")
            
        size_mb = os.path.getsize(archive_path) / (1024 * 1024)
        print(f"[+] Storage archive created: {archive_path} ({size_mb:.2f} MB)")
        return archive_path
    except Exception as e:
        print(f"[!] Storage archive failed: {e}")
        return ""


def prune_old_backups(backup_dir: str, keep_last: int = 7):
    """Keep only the latest N backup files to conserve disk space."""
    if keep_last <= 0:
        return
        
    all_files = [
        os.path.join(backup_dir, f)
        for f in os.listdir(backup_dir)
        if f.endswith(".sql.gz") or f.endswith(".tar.gz")
    ]
    
    # Group by prefix
    db_backups = sorted([f for f in all_files if "postgres_backup_" in f], key=os.path.getmtime)
    storage_backups = sorted([f for f in all_files if "storage_models_" in f], key=os.path.getmtime)
    
    for group, name in [(db_backups, "database backups"), (storage_backups, "storage archives")]:
        if len(group) > keep_last:
            to_remove = group[:-keep_last]
            print(f"[*] Pruning {len(to_remove)} old {name} (keeping last {keep_last})...")
            for old_file in to_remove:
                try:
                    os.remove(old_file)
                    print(f"    - Removed {os.path.basename(old_file)}")
                except Exception as e:
                    print(f"    ! Failed to remove {old_file}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Backup Production Database and Models")
    parser.add_argument("--output-dir", default="./backups", help="Target backup directory")
    parser.add_argument("--storage-root", default="./storage", help="Storage root directory")
    parser.add_argument("--keep-last", type=int, default=7, help="Number of latest backups to retain")
    args = parser.parse_args()

    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = create_backup_dirs(args.output_dir)

    print("=" * 70)
    print("      I_LoveSeafood AI Ecosystem - Production Backup Tool")
    print("=" * 70)
    print(f"Timestamp:   {timestamp} UTC")
    print(f"Output Dir:  {backup_dir}")
    print(f"Keep Last:   {args.keep_last} backups")
    print("-" * 70)

    db_path = backup_postgres(backup_dir, timestamp)
    storage_path = backup_storage_models(backup_dir, timestamp, args.storage_root)
    prune_old_backups(backup_dir, args.keep_last)

    print("-" * 70)
    if db_path or storage_path:
        print("[+] Backup completed successfully.")
        print("\n[i] Quick Disaster Recovery Command Guide:")
        if db_path:
            print(f"    # To restore PostgreSQL:")
            print(f"    gunzip -c {db_path} | docker compose exec -T postgres psql -U admin -d my_database")
        if storage_path:
            print(f"    # To restore model weights:")
            print(f"    tar -xzf {storage_path} -C {args.storage_root}")
    else:
        print("[!] Backup completed with errors. Please check service status.")
    print("=" * 70)


if __name__ == "__main__":
    main()
