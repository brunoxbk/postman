class PacoteVicioError(Exception):
    pass


class PacoteVicioClientError(PacoteVicioError):
    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        super().__init__(message or f"Erro {status_code}")


class PacoteVicioServerError(PacoteVicioError):
    pass