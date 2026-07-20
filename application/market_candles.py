from __future__ import annotations

from application.candles import candle_row_from_event
from application.dto import MarketCandleProcessResult
from application.ports import MarketCandleRepository
from application.strategy_state import StrategyStateService
from domain.stream_events import CandleEvent


class MarketCandleService:
    """Application use case for live candle persistence and strategy state refresh."""

    def __init__(
            self,
            db: MarketCandleRepository,
            strategy_state_svc: StrategyStateService,
    ):
        self._db = db
        self._strategy_state_svc = strategy_state_svc

    async def process_candle(self, event: CandleEvent) -> MarketCandleProcessResult:
        row = candle_row_from_event(event)
        if row is None:
            return MarketCandleProcessResult(stored=False)

        async with self._db.session_factory() as session:
            await self._db.upsert_candles([row], session=session)
            await session.commit()

        if not event.is_complete:
            return MarketCandleProcessResult(stored=True)

        strategy_state = await self._strategy_state_svc.refresh_instruments(
            [event.instrument_id]
        )
        return MarketCandleProcessResult(stored=True, strategy_state=strategy_state)
