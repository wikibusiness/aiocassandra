import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from cassandra.cluster import Cluster
from cassandra.protocol import SyntaxException
from cassandra.query import SimpleStatement

from aiocassandra import aiosession


@pytest.mark.asyncio
async def test_prepare_future(cassandra):
    query = 'SELECT now() as now FROM system.local;'

    blocking = cassandra.prepare(query)

    non_blocking = await cassandra.prepare_future(query)

    assert blocking.query_id == non_blocking.query_id


@pytest.mark.asyncio
async def test_execute_future_prepare(cassandra):
    cql = cassandra.prepare('SELECT now() as now FROM system.local;')

    ret = await cassandra.execute_future(cql)

    assert len(ret) == 1

    assert isinstance(ret[0].now, uuid.UUID)


@pytest.mark.asyncio
async def test_execute_future(cassandra):
    cql = 'SELECT now() as now FROM system.local;'

    ret = await cassandra.execute_future(cql)

    assert len(ret) == 1

    assert isinstance(ret[0].now, uuid.UUID)


@pytest.mark.asyncio
async def test_execute_future_error(cassandra):
    cql = 'SELECT 1;'

    with pytest.raises(SyntaxException):
        await cassandra.execute_future(cql)


@pytest.mark.asyncio
async def test_execute_future_cancel(cassandra, caplog, loop):
    cql = 'SELECT now() as now FROM system.local;'

    old_fut_factory = cassandra._asyncio_fut_factory

    def new_patch_factory():
        fut = old_fut_factory()
        fut.cancel()
        return fut

    cassandra._asyncio_fut_factory = new_patch_factory

    fut = loop.create_task(cassandra.execute_future(cql))

    with caplog.at_level(logging.ERROR):
        await asyncio.sleep(0.1, loop=loop)

    assert len(caplog.records) == 0

    with pytest.raises(asyncio.CancelledError):
        await fut


@pytest.mark.asyncio
async def test_execute_future_cancel_error(cassandra, caplog, loop):
    cql = 'SELECT 1;'

    old_fut_factory = cassandra._asyncio_fut_factory

    def new_patch_factory():
        fut = old_fut_factory()
        fut.cancel()
        return fut

    cassandra._asyncio_fut_factory = new_patch_factory

    fut = loop.create_task(cassandra.execute_future(cql))

    with caplog.at_level(logging.ERROR):
        await asyncio.sleep(0.1, loop=loop)

    assert len(caplog.records) == 0

    with pytest.raises(asyncio.CancelledError):
        await fut


@pytest.mark.asyncio
async def test_execute_futures_simple(cassandra):
    cql = 'SELECT now() as now FROM system.local;'

    ret = []

    async with cassandra.execute_futures(cql) as paginator:
        async for row in paginator:
            ret.append(row)

    assert len(ret) == 1

    assert isinstance(ret[0].now, uuid.UUID)


@pytest.mark.asyncio
async def test_execute_futures_simple_statement_empty(cassandra):
    cql = 'SELECT * FROM system_schema.types;'
    statement = SimpleStatement(cql, fetch_size=1)

    ret = []

    async with cassandra.execute_futures(statement) as paginator:
        async for row in paginator:
            ret.append(row)

    assert len(ret) == 0


@pytest.mark.asyncio
async def test_execute_futures_simple_statement(cassandra):
    cql = 'SELECT * FROM system.size_estimates;'
    statement = SimpleStatement(cql, fetch_size=100)

    ret = []

    async with cassandra.execute_futures(statement) as paginator:
        async for row in paginator:
            assert isinstance(row, tuple)
            ret.append(row)

    assert len(ret) != 0


@pytest.mark.asyncio
async def test_execute_futures_simple_statement_limit_pages(cassandra):
    cql = 'SELECT * FROM system.size_estimates LIMIT 50;'
    statement = SimpleStatement(cql, fetch_size=10)

    ret = []

    async with cassandra.execute_futures(statement, max_in_memory_pages=3) as paginator:
        await asyncio.sleep(0.5)  # wait for fetching pages
        assert len(paginator._deque) == 30
        async for row in paginator:
            await asyncio.sleep(0.2)  # slow down consumer
            assert isinstance(row, tuple)
            assert len(paginator._deque) <= 30
            ret.append(row)

    assert len(ret) == 50


@pytest.mark.asyncio
async def test_execute_futures_break(cassandra):
    cql = 'SELECT * FROM system.size_estimates;'
    statement = SimpleStatement(cql, fetch_size=100)

    ret = []

    async with cassandra.execute_futures(statement) as paginator:
        async for row in paginator:
            assert isinstance(row, tuple)
            ret.append(row)
            break

    assert len(ret) == 1

    assert len(paginator._deque) == 0


@pytest.mark.asyncio
async def test_execute_futures_simple_statement_error(cassandra):
    cql = 'SELECT 1;'
    statement = SimpleStatement(cql, fetch_size=1)

    ret = []

    with pytest.raises(SyntaxException):
        async with cassandra.execute_futures(statement) as paginator:
            async for row in paginator:
                ret.append(row)

    assert len(ret) == 0


@pytest.mark.asyncio
async def test_execute_futures_runtime_error(cassandra):
    cql = 'SELECT * FROM system.size_estimates;'
    statement = SimpleStatement(cql, fetch_size=100)

    paginator = cassandra.execute_futures(statement)

    ret = []

    with pytest.raises(RuntimeError):
        async for row in paginator:
            ret.append(row)

    assert len(ret) == 0


def test_malformed_session():
    with pytest.raises(RuntimeError):
        aiosession(None)


def test_patched_twice(cassandra, session, loop):
    with pytest.raises(RuntimeError):
        aiosession(session, loop=loop)


def test_main_thread_loop_missing(session):
    with pytest.raises(RuntimeError):
        aiosession(session)


def test_main_thread_loop(loop, session):
    asyncio.set_event_loop(loop)
    cluster = Cluster()
    session = cluster.connect()

    aiosession(session)

    assert loop is session._asyncio_loop


def test_explicit_loop(cassandra, loop):
    assert loop is cassandra._asyncio_loop


def test_explicit_executor(loop, session):
    executor = ThreadPoolExecutor(max_workers=1)

    aiosession(session, executor=executor, loop=loop)

    assert executor is session._asyncio_executor

    executor.shutdown(wait=True)


def test_wrong_executor(loop, session):
    with pytest.raises(RuntimeError):
        aiosession(session, executor=1, loop=loop)


def test_session_patched(cassandra):
    assert getattr(cassandra, 'execute_future', None) is not None
