from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from application.dto import ActiveStrategyBinding, StrategyStateRefreshResult
from application.ports import StrategyStateRepository
from domain.strategies import StrategyRegistry


class StrategyStateService:
    """Application use case for recalculating persisted strategy state from candles."""

    def __init__(
            self,
            db: StrategyStateRepository,
            *,
            strategy_registry: StrategyRegistry | None = None,
    ):
        self._db = db
        self._strategy_registry = strategy_registry or StrategyRegistry.with_defaults()
        self._log = logging.getLogger(self.__class__.__name__)

    async def refresh_all(self) -> StrategyStateRefreshResult:
        refreshed = 0
        warming = 0
        skipped = 0
        async with self._db.session_factory() as session:
            bindings = await self._db.list_active_strategy_bindings(session=session)
            for binding in bindings:
                result = await self._refresh_binding(binding, session=session)
                refreshed += result.refreshed_count
                warming += result.warming_count
                skipped += result.skipped_count
            await session.commit()

        return StrategyStateRefreshResult(
            refreshed_count=refreshed,
            warming_count=warming,
            skipped_count=skipped,
        )

    async def _refresh_binding(
            self,
            binding: ActiveStrategyBinding,
            *,
            session: Any,
    ) -> StrategyStateRefreshResult:
        try:
            strategy = self._strategy_registry.get(binding.strategy_code, binding.version)
        except KeyError:
            self._log.warning(
                "Skip unknown strategy binding %s@%s for %s",
                binding.strategy_code,
                binding.version,
                binding.instrument_id,
            )
            return StrategyStateRefreshResult(refreshed_count=0, warming_count=0, skipped_count=1)

        calculate_state = getattr(strategy, "calculate_state", None)
        if calculate_state is None:
            return StrategyStateRefreshResult(refreshed_count=0, warming_count=0, skipped_count=1)

        refreshed = 0
        warming = 0
        for requirement in strategy.requirements(binding.params).candles:
            candles = await self._db.list_candles(
                instrument_id=binding.instrument_id,
                timeframe=requirement.timeframe,
                limit=requirement.warmup,
                session=session,
            )
            status = "ready" if len(candles) >= requirement.warmup else "warming"
            state = dict(calculate_state(candles, binding.params))
            state["warmup_required"] = requirement.warmup
            state["candles_loaded"] = len(candles)
            await self._db.upsert_strategy_state(
                {
                    "binding_id": binding.binding_id,
                    "timeframe": requirement.timeframe,
                    "instrument_id": binding.instrument_id,
                    "strategy_code": binding.strategy_code,
                    "status": status,
                    "state_json": state,
                    "last_calculated_at": datetime.now(timezone.utc),
                    "last_market_event_time": getattr(candles[-1], "time", None) if candles else None,
                },
                session=session,
            )
            if status == "ready":
                refreshed += 1
            else:
                warming += 1

        return StrategyStateRefreshResult(
            refreshed_count=refreshed,
            warming_count=warming,
            skipped_count=0,
        )
