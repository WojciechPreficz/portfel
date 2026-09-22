from app.services.adapters.nbp import NbpAdapter
from app.services.adapters.stooq import StooqAdapter
from app.services.adapters.yahoo import YahooAdapter


def get_adapter(provider: str):
	adapters = {
		"nbp": NbpAdapter,
		"stooq": StooqAdapter,
		"yahoo": YahooAdapter,
	}
	try:
		return adapters[provider]()
	except KeyError as exc:
		raise ValueError(f"Nieobsługiwany provider notowań: {provider}") from exc


__all__ = ["NbpAdapter", "StooqAdapter", "YahooAdapter", "get_adapter"]
