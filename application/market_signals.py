from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional, Sequence

from application.dto import ActiveStrategyBinding, MarketSignalDecision
from application.ports import MarketSignalRepository
from domain.strategies import (
    DonchianBreakoutStrategy,
    Strategy,
    StrategyContext,
    StrategyRegistry,
)
from domain.stream_events import LastPriceEvent


class MarketSignalService:
    """Application use case for turning market prices into strategy decisions."""

    def __init__(
            self,
            db: MarketSignalRepository,
            *,
            strategy_registry: StrategyRegistry | None = None,
            fallback_strategy: Strategy | None = None,
    ):
        self._db = db
        self._strategy_registry = strategy_registry or StrategyRegistry.with_defaults()
        self._fallback_strategy = fallback_strategy or DonchianBreakoutStrategy()
        self._log = logging.getLogger(self.__class__.__name__)

    async def process_last_price(
            self,
            event: LastPriceEvent,
    ) -> Optional[MarketSignalDecision]:
        async with self._db.session_factory() as session:
            bindings = await self._db.list_active_strategy_bindings_for_instrument(
                event.instrument_id,
                session=session,
            )
            if bindings:
                decision = self._decide_from_strategy_bindings(event, bindings)
            else:
                decision = await self._decide_from_legacy_instrument(event, session)
            if decision is None:
                return None

            await self._db.set_notify(
                decision.instrument.instrument_id,
                notify=False,
                session=session,
            )
            await self._save_strategy_signal(decision, event, session)
            await session.commit()
            return decision

    def _decide_from_strategy_bindings(
            self,
            event: LastPriceEvent,
            bindings: Sequence[ActiveStrategyBinding],
    ) -> Optional[MarketSignalDecision]:
        for binding in bindings:
            strategy = self._get_strategy(binding)
            if strategy is None:
                continue

            signal = strategy.decide(
                StrategyContext(
                    instrument=binding.instrument,
                    position_direction=binding.position_direction,
                    last_price=float(event.price),
                    state=binding.state,
                ),
                params=binding.params,
            )
            if signal is None:
                continue

            return MarketSignalDecision(
                instrument=binding.instrument,
                position_direction=binding.position_direction,
                last_price=float(event.price),
                signal=signal,
                binding=binding,
            )
        return None

    async def _decide_from_legacy_instrument(
            self,
            event: LastPriceEvent,
            session: Any,
    ) -> Optional[MarketSignalDecision]:
        row = await self._db.get_instrument_with_positions(event.instrument_id, session)
        if not row:
            self._log.debug("No instrument in DataBase for %s", event.instrument_id)
            return None

        instrument, position = row
        position_direction = getattr(position, "direction", None)
        signal = self._fallback_strategy.decide(
            StrategyContext(
                instrument=instrument,
                position_direction=position_direction,
                last_price=float(event.price),
            )
        )
        if signal is None:
            return None

        return MarketSignalDecision(
            instrument=instrument,
            position_direction=position_direction,
            last_price=float(event.price),
            signal=signal,
        )

    def _get_strategy(self, binding: ActiveStrategyBinding) -> Optional[Strategy]:
        try:
            return self._strategy_registry.get(binding.strategy_code, binding.version)
        except KeyError:
            self._log.warning(
                "Skip unknown strategy binding %s@%s for %s",
                binding.strategy_code,
                binding.version,
                binding.instrument_id,
            )
            return None

    async def _save_strategy_signal(
            self,
            decision: MarketSignalDecision,
            event: LastPriceEvent,
            session: Any,
    ) -> None:
        if decision.binding is None:
            return

        signal = decision.signal
        await self._db.add_strategy_signal(
            {
                "binding_id": decision.binding.binding_id,
                "instrument_id": decision.instrument.instrument_id,
                "strategy_code": signal.strategy_code,
                "strategy_version": signal.strategy_version,
                "kind": signal.kind.value,
                "side": signal.side,
                "price": _decimal(decision.last_price),
                "boundary": _decimal(signal.boundary),
                "payload": dict(signal.payload),
                "event_time": event.time,
            },
            session=session,
        )


def _decimal(value: float | int | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
