import asyncio

from runtime.context import load_config_dict
from runtime.telegram_service import Service
from utils.arg_parse import parser
from utils.logger import setup_logging_from_dict


async def main():
    args = parser.parse_args()
    setup_logging_from_dict(load_config_dict(args.config))
    service = Service(args.config)
    try:
        await service.start()
    finally:
        await service.stop()


if __name__ == '__main__':
    asyncio.run(main())
