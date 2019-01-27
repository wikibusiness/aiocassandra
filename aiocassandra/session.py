import asyncio
import logging
import sys
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Event
from types import MethodType

from async_generator import async_generator, yield_
from cassandra.cluster import Session

__version__ = '2.0.1'

PY_352 = sys.version_info >= (3, 5, 2)

logger = logging.getLogger(__name__)


class _Paginator:

    def __init__(self, request, *, executor, loop):
        self.cassandra_fut = None

        self._request = request

        self._executor = executor
        self._loop = loop

        self._deque = deque()
        self._exc = None
        self._drain_event = asyncio.Event(loop=loop)
        self._finish_event = asyncio.Event(loop=loop)
        self._exit_event = Event()

        self.__pages = set()

    def _handle_page(self, rows):
        if self._exit_event.is_set():
            _len = len(rows)
            logger.debug(
                'Paginator is closed, skipping new %i records', _len)
            return

        for row in rows:
            self._deque.append(row)

        self._loop.call_soon_threadsafe(self._drain_event.set)

        if self.cassandra_fut.has_more_pages:
            _fn = self.cassandra_fut.start_fetching_next_page
            fut = self._loop.run_in_executor(self._executor, _fn)
            self.__pages.add(fut)
            fut.add_done_callback(self.__pages.remove)
            return

        self._loop.call_soon_threadsafe(self._finish_event.set)

    def _handle_err(self, exc):
        self._exc = exc

        self._loop.call_soon_threadsafe(self._finish_event.set)

    async def __aenter__(self):
        self.cassandra_fut = await self._loop.run_in_executor(
            self._executor,
            self._request
        )

        self.cassandra_fut.add_callbacks(
            callback=self._handle_page,
            errback=self._handle_err
        )
        return self

    async def __aexit__(self, *exc_info):
        self._exit_event.set()
        _len = len(self._deque)
        self._deque.clear()
        logger.debug(
            'Paginator is closed, cleared in-memory %i records', _len)

        await asyncio.gather(*self.__pages, loop=self._loop)

    def __aiter__(self):
        return self._paginator()

    if not PY_352:  # pragma: no cover
        __aiter__ = asyncio.coroutine(__aiter__)

    @async_generator
    async def _paginator(self):
        if self.cassandra_fut is None:
            raise RuntimeError(
                'Pagination should be done inside async context manager')

        while (
            self._deque or
            not self._finish_event.is_set() or
            self._exc is not None
        ):
            if self._exc is not None:
                raise self._exc

            while self._deque:
                await yield_(self._deque.popleft())

            await asyncio.wait(
                (
                    self._drain_event.wait(),
                    self._finish_event.wait(),
                ),
                return_when=asyncio.FIRST_COMPLETED,
                loop=self._loop
            )


def _asyncio_fut_factory(loop):
    try:
        return loop.create_future
    except AttributeError:  # pragma: no cover
        return partial(asyncio.Future, loop=loop)


def _asyncio_result(self, fut, result):
    if fut.cancelled():
        return

    self._asyncio_loop.call_soon_threadsafe(fut.set_result, result)


def _asyncio_exception(self, fut, exc):
    if fut.cancelled():
        return

    self._asyncio_loop.call_soon_threadsafe(fut.set_exception, exc)


async def execute_future(self, *args, **kwargs):
    _request = partial(self.execute_async, *args, **kwargs)
    cassandra_fut = await self._asyncio_loop.run_in_executor(
        self._asyncio_executor,
        _request
    )

    asyncio_fut = self._asyncio_fut_factory()

    cassandra_fut.add_callbacks(
        callback=partial(self._asyncio_result, asyncio_fut),
        errback=partial(self._asyncio_exception, asyncio_fut)
    )

    return await asyncio_fut


def execute_futures(self, *args, **kwargs):
    _request = partial(self.execute_async, *args, **kwargs)
    return _Paginator(
        _request,
        executor=self._asyncio_executor,
        loop=self._asyncio_loop
    )


def prepare_future(self, *args, **kwargs):
    _fn = partial(self.prepare, *args, **kwargs)
    return self._asyncio_loop.run_in_executor(self._asyncio_executor, _fn)


def aiosession(session, *, executor=None, loop=None):
    if not isinstance(session, Session):
        raise RuntimeError(
            'provide cassandra.cluster.Session')

    if hasattr(session, '_asyncio_fut_factory'):
        raise RuntimeError(
            'session is already patched by aiosession')

    if executor is not None:
        if not isinstance(executor, ThreadPoolExecutor):
            raise RuntimeError(
                'executor should be instance of ThreadPoolExecutor')

    if loop is None:
        loop = asyncio.get_event_loop()

    session._asyncio_loop = loop
    session._asyncio_executor = executor
    session._asyncio_fut_factory = _asyncio_fut_factory(loop=loop)

    session._asyncio_result = MethodType(_asyncio_result, session)
    session._asyncio_exception = MethodType(_asyncio_exception, session)
    session.execute_future = MethodType(execute_future, session)
    session.execute_futures = MethodType(execute_futures, session)
    session.prepare_future = MethodType(prepare_future, session)

    return session
