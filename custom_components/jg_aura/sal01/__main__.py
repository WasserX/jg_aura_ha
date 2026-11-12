"""Command line tool: python -m custom_components.jg_aura.sal01 PORT COMMAND ...

Thermostats are named by their JG Aura cloud id (the suffix of the Home Assistant
unique id jg_aura_<id>), for example bea0.
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .client import SAL01Client
from .protocol import Preset, ThermostatStatus, address_to_cloud_id, cloud_id_to_address


def _print_status(status: ThermostatStatus) -> None:
    preset = status.preset.name.lower() if status.preset else status.mode.name.lower()
    heating = "yes" if status.heating else "no"
    room = status.current_temperature
    target = status.target_temperature
    print(
        f"{status.cloud_id}  {preset:<7} heating={heating:<3} "
        f"room={room:4.1f}  target={target:4.1f}",
        flush=True,
    )


async def _run(args: argparse.Namespace) -> None:
    client = SAL01Client(args.port)
    await client.connect()
    client.subscribe(_print_status)
    try:
        if args.command == "devices":
            for address in await client.get_devices():
                print(address_to_cloud_id(address))
        elif args.command == "refresh":
            await client.request_reports()
            await asyncio.sleep(args.wait)
        elif args.command == "monitor":
            await asyncio.sleep(args.wait)
        elif args.command == "preset":
            await client.set_preset(
                cloud_id_to_address(args.id), Preset[args.preset.upper()], args.duration
            )
            print("confirmed")
            await asyncio.sleep(2)
        elif args.command == "temperature":
            await client.set_temperature(cloud_id_to_address(args.id), args.temperature)
            print("confirmed")
            await asyncio.sleep(2)
    finally:
        await client.close()


def main() -> None:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(prog="python -m custom_components.jg_aura.sal01")
    parser.add_argument("port", help="serial port of the SAL01, e.g. /dev/ttyUSB0")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every frame")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("devices", help="list the addresses the stick knows")
    for name, help_text in (
        ("refresh", "ask every thermostat for its status and print it"),
        ("monitor", "print status reports as they arrive"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--wait", type=float, default=30, help="seconds to listen")
    p = sub.add_parser("preset", help="set a preset")
    p.add_argument("id", help="cloud id, e.g. bea0")
    p.add_argument("preset", choices=[x.name.lower() for x in Preset])
    p.add_argument("--duration", type=int, default=1, help="for party and away")
    p = sub.add_parser("temperature", help="set the target temperature")
    p.add_argument("id", help="cloud id, e.g. bea0")
    p.add_argument("temperature", type=float)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(name)s %(message)s",
    )
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
