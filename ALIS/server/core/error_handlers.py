"""
ALIS Error Handlers - E02-S10

MODULE: Shared Services
LAYER: API / Interface Layer

This module converts ALIS exceptions into standard JSON responses.
It should be imported and registered in the main FastAPI app.

Response Format:
{
    "status": "error",
    "code": "ERR_CODE",
    "message": "User friendly message",
    "details": { ... }
}
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from .exceptions import ALISError


async def alis_exception_handler(request: Request, exc: ALISError):
    """
    Generic handler for all ALISError subclasses.
    Uses the exception's internal http_status and code.
    """
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "status": "error",
            "code": exc.code,
            "message": exc.message,
            "details": exc.details
        }
    )


async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all for unhandled exceptions (bugs).
    Prevents raw stack traces from leaking to the user.
    """
    # In a real system, log the full traceback here to Sentry/logs
    print(f"CRITICAL UNHANDLED ERROR: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "code": "ERR_INTERNAL_SYSTEM",
            "message": "An internal system error occurred.",
            "details": {"error": str(exc)}  # Dev mode only? Decide based on env.
        }
    )


def register_exception_handlers(app):
    """Helper to register handlers on a FastAPI app instance."""
    app.add_exception_handler(ALISError, alis_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
