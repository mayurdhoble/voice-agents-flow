from fastapi import APIRouter, Query
from services.database import (
    get_stats, get_calls, get_call,
    get_bookings, get_events, get_guests,
)

router = APIRouter(prefix="/api")


@router.get("/stats")
def stats():
    return get_stats()


@router.get("/calls")
def calls(limit: int = Query(50, le=200), offset: int = 0):
    return get_calls(limit, offset)


@router.get("/calls/{call_sid}")
def call_detail(call_sid: str):
    return get_call(call_sid)


@router.get("/bookings")
def bookings(limit: int = Query(50, le=200), offset: int = 0):
    return get_bookings(limit, offset)


@router.get("/events")
def events(limit: int = Query(50, le=200), offset: int = 0):
    return get_events(limit, offset)


@router.get("/guests")
def guests(limit: int = Query(50, le=200), offset: int = 0):
    return get_guests(limit, offset)
