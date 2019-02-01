aiocassandra
============

:info: Simple threaded cassandra wrapper for asyncio

.. image:: https://travis-ci.org/aio-libs/aiocassandra.svg?branch=master
    :target: https://travis-ci.org/aio-libs/aiocassandra

.. image:: https://img.shields.io/pypi/v/aiocassandra.svg
    :target: https://pypi.python.org/pypi/aiocassandra

.. image:: https://codecov.io/gh/aio-libs/aiocassandra/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/aio-libs/aiocassandra

Installation
------------

.. code-block:: shell

    pip install aiocassandra

Usage
-----

.. code-block:: python

    import asyncio

    from aiocassandra import aiosession
    from cassandra.cluster import Cluster
    from cassandra.query import SimpleStatement

    # connection is blocking call
    cluster = Cluster()
    # aiocassandra uses executor_threads to talk to cassndra driver
    # https://datastax.github.io/python-driver/api/cassandra/cluster.html?highlight=executor_threads
    session = cluster.connect()


    async def main():
        # patches and adds `execute_future`, `execute_futures` and `prepare_future`
        # to `cassandra.cluster.Session`
        aiosession(session)

        # best way is to use cassandra prepared statements
        # https://cassandra-zone.com/prepared-statements/
        # https://datastax.github.io/python-driver/api/cassandra/cluster.html#cassandra.cluster.Session.prepare
        # try to create them once on application init
        query = session.prepare('SELECT now() FROM system.local;')

        # if non-blocking prepared statements is really needed:
        query = await session.prepare_future('SELECT now() FROM system.local;')

        print(await session.execute_future(query))

        # pagination is also supported
        query = 'SELECT * FROM system.size_estimates;'
        statement = SimpleStatement(query, fetch_size=100)

        # don't miss *s* (execute_futureS)
        async with session.execute_futures(statement) as paginator:
            async for row in paginator:
                print(row)


    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    cluster.shutdown()
    loop.close()

Python 3.5+ is required


Using with cqlengine
-----

.. code-block:: python

    import asyncio
    import uuid
    import os

    from aiocassandra import aiosession, AioModel
    from cassandra.cluster import Cluster
    from cassandra.cqlengine import columns, connection, management

    cluster = Cluster()
    session = cluster.connect()


    class User(AioModel):
        user_id = columns.UUID(primary_key=True)
        username = columns.Text()


    async def main():
        aiosession(session)

        # Set aiosession for cqlengine
        session.set_keyspace('example_keyspace')
        connection.set_session(session)

        # Model.objects.create() and Model.create() in async way:
        user_id = uuid.uuid4()
        await User.objects.async_create(user_id=user_id, username='user1')
        # also can use: await User.async_create(user_id=user_id, username='user1)

        # Model.objects.all() and Model.all() in async way:
        print(list(await User.async_all()))
        print(list(await User.objects.filter(user_id=user_id).async_all()))

        # Model.object.update() in async way:
        await User.objects(user_id=user_id).async_update(username='updated-user1')

        # Model.objects.get() and Model.get() in async way:
        user = await User.objects.async_get(user_id=user_id)
        assert user.user_id == (await User.async_get(user_id=user_id)).user_id
        print(user, user.username)

        # obj.save() in async way:
        user.username = 'saved-user1'
        await user.async_save()

        # obj.delete() in async way:
        await user.async_delete()

        # Didn't break original functions
        print('Left users: ', len(User.objects.all()))


    def create_keyspace(keyspace):
        os.environ['CQLENG_ALLOW_SCHEMA_MANAGEMENT'] = 'true'
        connection.register_connection('cqlengine', session=session, default=True)
        management.create_keyspace_simple(keyspace, replication_factor=1)
        management.sync_table(User, keyspaces=[keyspace])


    create_keyspace('example_keyspace')

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    cluster.shutdown()
    loop.close()


Thanks
------

The library was donated by `Ocean S.A. <https://ocean.io/>`_

Thanks to the company for contribution.
