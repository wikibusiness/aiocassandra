from cassandra.cqlengine.models import Model, PolymorphicModelException
from cassandra.cqlengine.query import ValidationError

from aiocassandra.cqlengine.query import AioDMLQuery, AioQuerySet


class AioModel(Model):
    __abstract__ = True
    __dmlquery__ = AioDMLQuery
    __queryset__ = AioQuerySet

    @classmethod
    async def async_create(cls, **kwargs):
        extra_columns = set(kwargs.keys()) - set(cls._columns.keys())
        if extra_columns:
            raise ValidationError(
                "Incorrect columns passed: {0}".format(extra_columns))
        return await cls.objects.async_create(**kwargs)

    async def async_delete(self):
        """
        Deletes the object from the database
        """
        await self.__dmlquery__(
            self.__class__,
            self,
            batch=self._batch,
            timestamp=self._timestamp,
            consistency=self.__consistency__,
            timeout=self._timeout,
            conditional=self._conditional,
            if_exists=self._if_exists).async_delete()

    @classmethod
    async def async_all(cls):
        """
        Returns a queryset representing all stored objects.

        This is a pass-through to the model objects().async_all()
        """
        return await cls.objects.async_all()

    @classmethod
    async def async_get(cls, *args, **kwargs):
        """
        Returns a single object based on the passed filter constraints.

        This is a pass-through to the model objects().
          :method:`~cqlengine.queries.get`.
        """
        return await cls.objects.async_get(*args, **kwargs)

    async def async_save(self):
        # handle polymorphic models
        if self._is_polymorphic:
            if self._is_polymorphic_base:
                raise PolymorphicModelException(
                    'cannot save polymorphic base model')
            else:
                setattr(self, self._discriminator_column_name,
                        self.__discriminator_value__)

        self.validate()
        await self.__dmlquery__(
            self.__class__,
            self,
            batch=self._batch,
            ttl=self._ttl,
            timestamp=self._timestamp,
            consistency=self.__consistency__,
            if_not_exists=self._if_not_exists,
            conditional=self._conditional,
            timeout=self._timeout,
            if_exists=self._if_exists).async_save()

        self._set_persisted()
        self._timestamp = None
        return self

    async def async_update(self, **values):
        """
        Performs an update on the model instance. You can pass in values to
        set on the model for updating, or you can call without values to
        execute an update against any modified fields.
        If no fields on the model have been modified since loading,
        no query will be performed. Model validation is performed normally.
        Setting a value to `None` is equivalent to running a CQL `DELETE` on
        that column.

        It is possible to do a blind update, that is, to update a field without
        having first selected the object out of the database.
        See :ref:`Blind Updates <blind_updates>`
        """
        for column_id, v in values.items():
            col = self._columns.get(column_id)

            # check for nonexistant columns
            if col is None:
                raise ValidationError(
                    "{0}.{1} has no column named: {2}".format(
                        self.__module__, self.__class__.__name__, column_id))

            # check for primary key update attempts
            if col.is_primary_key:
                current_value = getattr(self, column_id)
                if v != current_value:
                    raise ValidationError(
                        "Cannot apply update to primary key '{0}' for {1}.{2}".
                        format(column_id, self.__module__,
                               self.__class__.__name__))

            setattr(self, column_id, v)

        # handle polymorphic models
        if self._is_polymorphic:
            if self._is_polymorphic_base:
                raise PolymorphicModelException(
                    'cannot update polymorphic base model')
            else:
                setattr(self, self._discriminator_column_name,
                        self.__discriminator_value__)

        self.validate()
        await self.__dmlquery__(
            self.__class__,
            self,
            batch=self._batch,
            ttl=self._ttl,
            timestamp=self._timestamp,
            consistency=self.__consistency__,
            conditional=self._conditional,
            timeout=self._timeout,
            if_exists=self._if_exists).async_update()

        self._set_persisted()

        self._timestamp = None

        return self
