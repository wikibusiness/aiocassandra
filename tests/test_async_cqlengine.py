import uuid

import pytest
from cassandra.cqlengine import columns

from aiocassandra import AioModel


class User(AioModel):
    user_id = columns.UUID(primary_key=True)
    username = columns.Text()


@pytest.mark.asyncio
async def test_queryset_async_functions(cqlengine_management):
    """test cqlengine Model async functions:
    Model.objects.async_get()
    Model.objects.async_all()
    Model.objects.async_create()
    Model.objects(id=obj_id).async_update()
    """
    cqlengine_management.sync_table(User)

    # test: Model.objects.async_create(), Model.objects.async_all(), Model.objects.async_get()
    username1 = 'test-username-1'
    await User.objects.async_create(user_id=uuid.uuid4(), username=username1)
    users = await User.objects.async_all()
    user = users[0]
    _user = await User.objects.async_get(user_id=user.user_id)
    assert user.username == _user.username == username1

    # test DML query: Model.objects(id=obj_id).async_update()
    username2 = 'test-username-2'
    await User.objects(user_id=user.user_id).async_update(username=username2)
    updated_user = await User.objects.async_get(user_id=user.user_id)
    assert updated_user.username == username2


@pytest.mark.asyncio
async def test_model_async_functions(cqlengine_management):
    """test cqlengine Model async functions:
    Model.async_get()
    Model.async_all()
    Model.async_create()
    obj.async_update()
    obj.async_save()
    obj.async_delete()
    """
    cqlengine_management.sync_table(User)

    # test: Model.async_create(), Model.async_all(), Model.async_get()
    username1 = 'test-username-1'
    await User.async_create(user_id=uuid.uuid4(), username=username1)
    users = await User.async_all()
    user = users[0]
    _user = await User.async_get(user_id=user.user_id)
    assert user.username == _user.username == username1

    # test: obj.async_save()
    username2 = 'test-username-2'
    user.username = username2
    await user.async_save()
    _user = await User.async_get(user_id=user.user_id)
    assert user.username == _user.username == username2

    # test: obj.async_update()
    username3 = 'test-username-3'
    await user.async_update(username=username3)
    _user = await User.async_get(user_id=user.user_id)
    assert user.username == _user.username == username3

    # test: obj.async_delete()
    await user.async_delete()
    assert len(await User.objects.async_all()) == 0
