"""Timeline entries as a person sees them in Omakanta: the results of one laboratory order form one entry."""
from __future__ import annotations

from typing import Any


def group_entries(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Returns [{'date', 'title', 'count', 'events'}] in the original order. Lab results that share an order id
    (structuredData.panelId) become one entry named after the order, e.g. "Lipidit" with 7 results."""
    entries: list[dict[str, Any]] = []
    by_order: dict[str, dict[str, Any]] = {}
    for event in events:
        structured = event.get('structuredData') or {}
        order_id = structured.get('panelId')
        if not order_id:
            entries.append({'date': event['date'], 'title': event['displayName'], 'events': [event]})
            continue
        entry = by_order.get(order_id)
        if entry is None:
            entry = {'date': event['date'], 'title': structured.get('panelName') or event['displayName'], 'events': []}
            by_order[order_id] = entry
            entries.append(entry)
        entry['events'].append(event)
    for entry in entries:
        entry['count'] = len(entry['events'])
        sizes = [(e.get('structuredData') or {}).get('panelSize') or 0 for e in entry['events']]
        entry['orderSize'] = max([entry['count'], *sizes])
    return entries


def entry_line(entry: dict[str, Any]) -> str:
    """'Lipidit: 7 tulosta' or, when some results of the order are listed elsewhere, 'Lipidit: 6 tulosta, lisäksi 1
    löydöksen kohdalla'."""
    line = f"{entry['title']}: {entry['count']} tulosta"
    elsewhere = entry['orderSize'] - entry['count']
    return f'{line}, lisäksi {elsewhere} löydöksen kohdalla' if elsewhere > 0 else line
