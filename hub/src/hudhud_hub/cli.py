# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hudhud serve`, `hudhud pair`, `hudhud devices`."""

from __future__ import annotations

import argparse
import sys
from contextlib import closing

import qrcode

from .auth import create_pairing_code, format_code, list_devices
from .config import Config, load_config, write_template
from .db import MIGRATIONS, apply_migrations, connect, utc_now


def _open(config: Config):
    conn = connect(config.db_path)
    apply_migrations(conn, MIGRATIONS)
    return conn


def print_pairing(config: Config, code: str) -> None:
    url = f"{config.base_url}/?pair={code}"
    print(f"\nPairing code: {format_code(code)}  (valid for 10 minutes, single use)")
    print(f"Open on your device: {url}\n")
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    try:
        qr.print_ascii(invert=True)
    except UnicodeEncodeError:
        print("(this terminal cannot draw the QR code; use the link above)")


def cmd_serve(config: Config, args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app

    if write_template(config):
        print(f"Wrote settings template: {config.config_path}")
    if config.vault_path is None:
        print("No vault_path set: highlights sync but are not written to Obsidian yet.")
    app = create_app(config)
    with closing(_open(config)) as conn:
        if not list_devices(conn):
            print_pairing(config, create_pairing_code(conn, utc_now()))
    if config.client_dir is None:
        print("Client not built: run `pnpm --dir client build` to serve the reader here.")
    print(f"Hudhud hub on {config.base_url}  (data: {config.data_dir})")
    uvicorn.run(app, host=args.host or config.host, port=args.port or config.port,
                log_level="info")
    return 0


def cmd_pair(config: Config, args: argparse.Namespace) -> int:
    with closing(_open(config)) as conn:
        print_pairing(config, create_pairing_code(conn, utc_now()))
    return 0


def cmd_devices(config: Config, args: argparse.Namespace) -> int:
    with closing(_open(config)) as conn:
        devices = list_devices(conn)
    if not devices:
        print("No paired devices. Run `hudhud pair`.")
    for d in devices:
        print(f"{d['id']}  {d['name']:<24} paired {d['paired_at']}  last seen {d['last_seen']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="hudhud", description="Hudhud book reader hub")
    parser.add_argument("--data-dir", help="override the data directory")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the hub")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    sub.add_parser("pair", help="print a new pairing code")
    sub.add_parser("devices", help="list paired devices")
    args = parser.parse_args(argv)
    config = load_config(args.data_dir)
    handlers = {"serve": cmd_serve, "pair": cmd_pair, "devices": cmd_devices}
    return handlers[args.command](config, args)


if __name__ == "__main__":
    sys.exit(main())
