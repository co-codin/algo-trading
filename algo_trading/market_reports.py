from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from algo_trading.market_intelligence import (
    MarketEvent,
    build_breadth_confirmation_events,
    build_futoi_position_dashboard,
    public_market_event,
)


@dataclass(frozen=True)
class ReportSection:
    title: str
    lines: list[str]


@dataclass(frozen=True)
class DailyMarketReport:
    date: date
    language: str
    title: str
    summary: str
    sections: list[ReportSection]
    text: str
    triggered_symbols: list[str]
    events: list[MarketEvent]


def build_daily_market_report(
    *,
    trading_date: date,
    futoi_records: Sequence[Any],
    algopack_records: Sequence[Any],
    breadth_bars_by_symbol: Mapping[str, Sequence[Any]],
    triggered_events: Sequence[MarketEvent],
) -> DailyMarketReport:
    futoi_events = list(triggered_events)
    breadth_events = build_breadth_confirmation_events(breadth_bars_by_symbol)
    events = [*futoi_events, *breadth_events]
    triggered_symbols = sorted(
        {
            event.symbol
            for event in events
            if event.symbol and event.symbol != "BREADTH"
        }
        | {
            str(getattr(record, "ticker", "")).upper()
            for record in algopack_records
            if str(getattr(record, "ticker", "")).strip()
        }
    )
    sections = [
        ReportSection(
            title="Что изменилось сегодня",
            lines=_change_lines(trading_date, events, algopack_records),
        ),
        ReportSection(
            title="Позиционирование FUTOI",
            lines=_futoi_lines(futoi_records),
        ),
        ReportSection(
            title="Сигналы и аномалии",
            lines=_trigger_lines(events, algopack_records),
        ),
        ReportSection(
            title="Ширина рынка",
            lines=_breadth_lines(breadth_events, breadth_bars_by_symbol),
        ),
    ]
    summary = (
        f"Сработали символы: {', '.join(triggered_symbols)}."
        if triggered_symbols
        else "Сработавших символов нет."
    )
    title = f"Ежедневный отчет рынка за {trading_date.isoformat()}"
    text = _render_report_text(title, summary, sections)
    return DailyMarketReport(
        date=trading_date,
        language="ru",
        title=title,
        summary=summary,
        sections=sections,
        text=text,
        triggered_symbols=triggered_symbols,
        events=events,
    )


def public_daily_market_report(report: DailyMarketReport) -> dict[str, Any]:
    return {
        "date": report.date.isoformat(),
        "language": report.language,
        "title": report.title,
        "summary": report.summary,
        "sections": [
            {"title": section.title, "lines": section.lines}
            for section in report.sections
        ],
        "text": report.text,
        "triggered_symbols": report.triggered_symbols,
        "events": [public_market_event(event) for event in report.events],
    }


def _change_lines(
    trading_date: date,
    events: Sequence[MarketEvent],
    algopack_records: Sequence[Any],
) -> list[str]:
    lines = [
        f"Дата анализа: {trading_date.isoformat()}.",
        f"Рыночных событий: {len(events)}.",
        f"Записей AlgoPack: {len(algopack_records)}.",
    ]
    if events:
        strongest = sorted(events, key=lambda event: _severity_rank(event.severity), reverse=True)[0]
        lines.append(f"Главное событие: {strongest.title} ({strongest.severity}).")
    return lines


def _futoi_lines(futoi_records: Sequence[Any]) -> list[str]:
    tickers = sorted(
        {
            str(getattr(record, "ticker", "")).upper()
            for record in futoi_records
            if str(getattr(record, "ticker", "")).strip()
        }
    )
    if not tickers:
        return ["Нет данных FUTOI для отчета."]
    lines: list[str] = []
    for ticker in tickers:
        ticker_records = [
            record
            for record in futoi_records
            if str(getattr(record, "ticker", "")).upper() == ticker
        ]
        dashboard = build_futoi_position_dashboard(ticker_records)
        summary = dashboard.summary
        lines.append(
            (
                f"{ticker}: net {summary['net_position']}, "
                f"день {summary['net_change_1d']}, "
                f"неделя {summary['net_change_1w']}."
            )
        )
    return lines


def _trigger_lines(
    events: Sequence[MarketEvent],
    algopack_records: Sequence[Any],
) -> list[str]:
    lines: list[str] = []
    for event in events:
        lines.append(f"{event.symbol}: {event.title} - {event.description}")
    for record in algopack_records:
        dataset = str(getattr(record, "dataset", "")).lower()
        if dataset != "alerts":
            continue
        metrics = getattr(record, "metrics", {}) or {}
        alert_type = str(metrics.get("alert_type") or getattr(record, "record_key", "") or "alert")
        lines.append(f"{getattr(record, 'ticker', '')}: MegaAlert {alert_type}.")
    return lines or ["Сигналы не сработали."]


def _breadth_lines(
    breadth_events: Sequence[MarketEvent],
    breadth_bars_by_symbol: Mapping[str, Sequence[Any]],
) -> list[str]:
    if breadth_events:
        return [event.description for event in breadth_events]
    latest_values: list[float] = []
    for bars in breadth_bars_by_symbol.values():
        if bars:
            latest_values.append(float(sorted(bars, key=lambda item: item.date)[-1].close))
    if not latest_values:
        return ["Нет данных ширины рынка."]
    average = sum(latest_values) / len(latest_values)
    return [f"Средняя ширина рынка: {round(average, 4)}%."]


def _render_report_text(
    title: str,
    summary: str,
    sections: Sequence[ReportSection],
) -> str:
    blocks = [title, "", summary]
    for section in sections:
        blocks.extend(["", section.title])
        blocks.extend(f"- {line}" for line in section.lines)
    return "\n".join(blocks)


def _severity_rank(severity: str) -> int:
    return {"low": 1, "medium": 2, "high": 3}.get(severity, 0)
