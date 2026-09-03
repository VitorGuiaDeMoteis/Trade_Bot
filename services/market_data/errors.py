"""Erros classificados sem incluir payloads, URLs ou segredos externos."""


class ProviderError(Exception):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class ContentConflict(ValueError):
    """Identidade conhecida com conteúdo divergente; nunca ignorar."""


class PartialCandle(ValueError):
    """Candle não fechado não pode chegar à estratégia."""
