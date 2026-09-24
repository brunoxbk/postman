class PacoteVicioError(Exception):
    pass


class PacoteVicioClientError(PacoteVicioError):
    """Erro 4xx que exige decisão por error.code (contrato da API), nunca pela message."""

    def __init__(self, status_code: int, message: str = "", code: str = ""):
        self.status_code = status_code
        self.code = code
        super().__init__(message or f"Erro {status_code}")


class PacoteVicioServerError(PacoteVicioError):
    pass