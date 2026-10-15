#!/usr/bin/env python3
"""Send OpenWebNet frames to a gateway one by one and record what comes back.

Prints, for every frame: ACK or NACK, how long the gateway took, the frames the command
session collected as the reply, and the frames seen on the event session before the next
command. Writes the same as JSON lines with ``--out``.

Usage::

    probe.py --host 192.168.0.92 --port 20000 --password '...' [--wait S] [--listen S]
             [--out file.jsonl] FRAME [FRAME ...]

``OWN_HOST`` / ``OWN_PORT`` / ``OWN_PASSWORD`` in the environment are the defaults.
A frame may be prefixed with ``s:`` to force a status request or ``c:`` to force a
command; ``sleep:N`` pauses N seconds. Only OWNd is needed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time

from OWNd.connection import OWNCommandSession, OWNEventSession, OWNGateway
from OWNd.message import OWNMessage


async def main(args: argparse.Namespace) -> None:
    gateway = OWNGateway(
        {
            "address": args.host,
            "port": args.port,
            "password": args.password,
            "modelName": args.model,
            "serialNumber": args.mac,
        }
    )
    log = logging.getLogger("OWNd")
    log.setLevel(logging.WARNING)
    cmd = OWNCommandSession(gateway=gateway, logger=log)
    evt = OWNEventSession(gateway=gateway, logger=log, inactivity_timeout=None)
    out = open(args.out, "a", encoding="utf-8") if args.out else None  # noqa: SIM115
    events: list[str] = []
    t0 = time.time()

    def rec(kind: str, **fields: object) -> None:
        row = {
            "t": round(time.time() - t0, 3),
            "utc": time.strftime("%H:%M:%S", time.gmtime()),
            "kind": kind,
            **fields,
        }
        if out:
            out.write(json.dumps(row, default=str) + "\n")
            out.flush()

    async def event_loop() -> None:
        while True:
            try:
                message = await evt.get_next()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                rec("event_error", error=repr(err))
                await asyncio.sleep(1)
                continue
            if message is None:
                continue
            raw = str(message)
            readable = message.human_readable_log if isinstance(message, OWNMessage) else ""
            events.append(raw)
            rec("event", raw=raw, cls=type(message).__name__, log=readable)
            print(f"      EVT {raw}   [{type(message).__name__}] {readable}", flush=True)

    print("cmd connect", await cmd.connect())
    print("evt connect", await evt.connect())
    task = asyncio.create_task(event_loop())
    await asyncio.sleep(1)
    for frame in args.frames:
        if frame.startswith("sleep:"):
            await asyncio.sleep(float(frame[6:]))
            continue
        status: bool | None = None
        if frame.startswith("s:"):
            status, frame = True, frame[2:]
        elif frame.startswith("c:"):
            status, frame = False, frame[2:]
        if status is None:
            status = frame.startswith("*#") and "*#" not in frame[2:]
        first_event = len(events)
        started = time.time()
        try:
            result = await cmd.send(frame, is_status_request=status)
        except Exception as err:  # noqa: BLE001
            result = f"EXC {err!r}"
        elapsed = round(time.time() - started, 3)
        replies = [str(x) for x in result] if isinstance(result, list) else result
        ack = result is not None and not isinstance(result, str)
        print(
            f"{round(time.time() - t0, 2):8} TX {frame:<30} {'ACK ' if ack else 'NACK'} {elapsed}s replies={replies}",
            flush=True,
        )
        await asyncio.sleep(args.wait)
        rec(
            "sent",
            frame=frame,
            status=status,
            ack=ack,
            dt=elapsed,
            replies=replies,
            events=events[first_event:],
        )
    if args.listen:
        print(f"listening {args.listen}s ...", flush=True)
        await asyncio.sleep(args.listen)
    task.cancel()
    await cmd.close()
    await evt.close()
    if out:
        out.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default=os.environ.get("OWN_HOST", "192.168.0.92"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OWN_PORT", "20000")))
    parser.add_argument("--password", default=os.environ.get("OWN_PASSWORD"))
    parser.add_argument("--model", default="F461")
    parser.add_argument("--mac", default="00:03:50:00:00:00")
    parser.add_argument("--wait", type=float, default=1.5)
    parser.add_argument("--listen", type=float, default=0)
    parser.add_argument("--out", default=None)
    parser.add_argument("frames", nargs="*")
    asyncio.run(main(parser.parse_args()))
