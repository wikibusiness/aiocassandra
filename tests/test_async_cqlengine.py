import uuid

import pytest
from cassandra.cqlengine import columns

from aiocassandra import AioModel


class User(AioModel):
    user_id = columns.UUID(primary_key=True)
    username = columns.Text()


@pytest.mark.asyncio
async def test_queryset_async_functions(cqlengine_management):
    cqlengine_management.sync_table(User)

    await User.objects.async_create(
        user_id=uuid.uuid4(), username='test-user-0')
    users = await User.objects.async_all()
    user = users[0]
    assert users[0].username == 'test-user-0'

    # test DML query: update
    await User.objects(user_id=user.user_id).async_update(username='test-user-1')
    updated_user = await User.objects.async_get(user_id=user.user_id)
    assert updated_user.username == 'test-user-1'

    # test DML query: delete
    await updated_user.async_delete()
    assert len(await User.objects.async_all()) == 0


@pytest.mark.asyncio
async def test_model_async_functions(cqlengine_management):
    cqlengine_management.sync_table(User)

    await User.async_create(user_id=uuid.uuid4(), username='test-user-0')
    users = await User.async_all()
    user = users[0]
    assert user.username == 'test-user-0'

    user.username = 'updated-user-0'
    await user.async_save()
    updated_user = await User.async_get(user_id=user.user_id)
    assert user.username == updated_user.username
