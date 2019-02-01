import asyncio
import gc
import os

import pytest
from cassandra.cluster import Cluster
from cassandra.cqlengine import management
from cassandra.cqlengine import connection as cqlengine_connection

from aiocassandra import aiosession

asyncio.set_event_loop(None)


@pytest.fixture
def cluster():
    cluster = Cluster()

    yield cluster

    cluster.shutdown()


@pytest.fixture
def session(cluster):
    return cluster.connect()


@pytest.fixture
def cassandra(session, loop):
    return aiosession(session, loop=loop)


@pytest.fixture
def cqlengine_management(cassandra):
    """Setup session for cqlengine
    """
    # create test keyspace
    os.environ['CQLENG_ALLOW_SCHEMA_MANAGEMENT'] = 'true'
    test_keyspace = 'test_async_cqlengine'
    cqlengine_connection.register_connection(
        'cqlengine', session=cassandra, default=True)
    management.create_keyspace_simple(test_keyspace, replication_factor=1)

    # setup cqlengine session
    cassandra.set_keyspace(test_keyspace)
    cqlengine_connection.set_session(cassandra)
    yield management
    management.drop_keyspace(test_keyspace)
    cqlengine_connection.unregister_connection('cqlengine')


@pytest.fixture
def event_loop(request):
    loop = asyncio.new_event_loop()
    loop.set_debug(bool(os.environ.get('PYTHONASYNCIODEBUG')))

    yield loop

    loop.run_until_complete(loop.shutdown_asyncgens())

    loop.call_soon(loop.stop)
    loop.run_forever()
    loop.close()

    gc.collect()
    gc.collect()  # for pypy


@pytest.fixture
def loop(event_loop, request):
    asyncio.set_event_loop(None)
    request.addfinalizer(lambda: asyncio.set_event_loop(None))

    return event_loop
