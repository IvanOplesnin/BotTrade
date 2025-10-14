import yaml
import json

from clients.tinkoff.client import TClient
from config import Config
from database.pgsql.repository import Repository
from services.historic_service.historic_service import IndicatorCalculator

config_path = r"C:\Users\aples\PycharmProjects\BotTrade\config.yaml"

with open(config_path, 'r', encoding='utf-8') as f:
    config_dict = yaml.load(f, Loader=yaml.FullLoader)

config = Config(**config_dict)


db = Repository(url=config.db_pgsql.address)

async def main():
    tclient = TClient(token=config.tinkoff_client.token)
    await tclient.start()
    with open("instruments_1.json", "r") as f:
        instruments = json.load(f)

    for instrument in instruments:
        print(instrument)
        candles = await tclient.get_days_candles_for_2_months(instrument_id=instrument["uid"])
        atr_1 = IndicatorCalculator(candles_resp=candles, ticker=instrument["ticker"])._atr(12)
        atr_2 = IndicatorCalculator(candles_resp=candles, ticker=instrument["ticker"])._atr_2(12)
        instrument['atr14_1'] = float(atr_1) if atr_1 else None
        instrument['atr14_2'] = float(atr_2) if atr_2 else None

    print(instruments)
    with open("instruments_1.json", "w") as f:
        json.dump(
            instruments,
            f,
            indent=4
        )

    await tclient.stop()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())