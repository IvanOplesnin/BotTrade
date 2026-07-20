import argparse
import asyncio
import os
import signal
import socket

from runtime.context import load_config_dict
from runtime.market_worker import MarketWorkerService
from utils.logger import setup_logging_from_dict


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=False)
    parser.add_argument("--consumer", type=str, required=False)
    return parser


def _default_consumer_name() -> str:
    return f"market-worker:{socket.gethostname()}:{os.getpid()}"


async def main() -> None:
    args = _build_parser().parse_args()
    setup_logging_from_dict(load_config_dict(args.config))

    service = MarketWorkerService(
        args.config,
        message_bus_consumer=args.consumer or _default_consumer_name(),
    )
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, service.request_stop)

    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
