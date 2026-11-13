"""Domain errors. Services raise these; the API layer maps them to HTTP status codes."""


class DomainError(Exception):
    status_code = 400


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    status_code = 409


class Invalid(DomainError):
    status_code = 422
