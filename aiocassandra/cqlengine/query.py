"""
Patch cqlengine, add async functions.
"""
from warnings import warn

from cassandra.cqlengine import CQLEngineException, columns
from cassandra.cqlengine.query import (DMLQuery, EqualsOperator, ModelQuerySet,
                                       SimpleStatement, ValidationError,
                                       check_applied, conn)
from cassandra.cqlengine.statements import (BaseCQLStatement, DeleteStatement,
                                            InsertStatement, UpdateStatement)


async def _execute_statement(model,
                             statement,
                             consistency_level,
                             timeout,
                             connection=None):
    """
    Based on cassandra.cqlengine.query._execute_statement
    """
    params = statement.get_context()
    s = SimpleStatement(
        str(statement),
        consistency_level=consistency_level,
        fetch_size=statement.fetch_size)
    if model._partition_key_index:
        key_values = statement.partition_key_values(model._partition_key_index)
        if not any(v is None for v in key_values):
            parts = model._routing_key_from_values(
                key_values,
                conn.get_cluster(connection).protocol_version)
            s.routing_key = parts
            s.keyspace = model._get_keyspace()
    connection = connection or model._get_connection()
    return await execute(s, params, timeout=timeout, connection=connection)


async def execute(query,
                  params=None,
                  consistency_level=None,
                  timeout=conn.NOT_SET,
                  connection=None):
    """
    Based on cassandra.cqlengine.connection.execute
    """

    _connection = conn.get_connection(connection)

    if isinstance(query, SimpleStatement):
        pass  #
    elif isinstance(query, BaseCQLStatement):
        params = query.get_context()
        query = SimpleStatement(
            str(query),
            consistency_level=consistency_level,
            fetch_size=query.fetch_size)
    elif isinstance(query, str):
        query = SimpleStatement(query, consistency_level=consistency_level)

    result = await _connection.session.execute_future(
        query, params, timeout=timeout)

    return result


class AioDMLQuery(DMLQuery):
    async def _async_execute(self, statement):
        connection = self.instance._get_connection(
        ) if self.instance else self.model._get_connection()
        if self._batch:
            if self._batch._connection:
                if not self._batch._connection_explicit and connection and \
                        connection != self._batch._connection:
                    raise CQLEngineException(
                        'BatchQuery queries must be executed '
                        'on the same connection')
            else:
                # set the BatchQuery connection from the model
                self._batch._connection = connection
            return self._batch.add_query(statement)
        else:
            results = await _execute_statement(
                self.model,
                statement,
                self._consistency,
                self._timeout,
                connection=connection)
            if self._if_not_exists or self._if_exists or self._conditional:
                check_applied(results)
            return results

    async def async_delete(self):
        """ Deletes one instance """
        if self.instance is None:
            raise CQLEngineException("DML Query instance attribute is None")

        ds = DeleteStatement(
            self.column_family_name,
            timestamp=self._timestamp,
            conditionals=self._conditional,
            if_exists=self._if_exists)
        for name, col in self.model._primary_keys.items():
            val = getattr(self.instance, name)
            if val is None and not col.partition_key:
                continue
            ds.add_where(col, EqualsOperator(), val)
        await self._async_execute(ds)

    async def async_save(self):
        """
        Creates / updates a row.
        This is a blind insert call.
        All validation and cleaning needs to happen
        prior to calling this.
        """
        if self.instance is None:
            raise CQLEngineException("DML Query intance attribute is None")
        assert type(self.instance) == self.model

        nulled_fields = set()
        if self.instance._has_counter or self.instance._can_update():
            if self.instance._has_counter:
                warn("'create' and 'save' actions on Counters are deprecated. "
                     "A future version will disallow this. Use the 'update' "
                     "mechanism instead.")
            return await self.async_update()
        else:
            insert = InsertStatement(
                self.column_family_name,
                ttl=self._ttl,
                timestamp=self._timestamp,
                if_not_exists=self._if_not_exists)
            static_save_only = False if len(
                self.instance._clustering_keys) == 0 else True
            for name, col in self.instance._clustering_keys.items():
                static_save_only = static_save_only and col._val_is_null(
                    getattr(self.instance, name, None))
            for name, col in self.instance._columns.items():
                if static_save_only and not col.static \
                        and not col.partition_key:
                    continue
                val = getattr(self.instance, name, None)
                if col._val_is_null(val):
                    if self.instance._values[name].changed:
                        nulled_fields.add(col.db_field_name)
                    continue
                if col.has_default and not self.instance._values[name].changed:
                    # Ensure default columns included in a save()
                    # are marked as explicit, to get them *persisted* properly
                    self.instance._values[name].explicit = True
                insert.add_assignment(col, getattr(self.instance, name, None))

        # skip query execution if it's empty
        # caused by pointless update queries
        if not insert.is_empty:
            await self._async_execute(insert)
        # delete any nulled columns
        if not static_save_only:
            self._delete_null_columns()

    async def async_update(self):
        """
        updates a row.
        This is a blind update call.
        All validation and cleaning needs to happen
        prior to calling this.
        """
        if self.instance is None:
            raise CQLEngineException("DML Query intance attribute is None")
        assert type(self.instance) == self.model
        null_clustering_key = False if len(
            self.instance._clustering_keys) == 0 else True
        static_changed_only = True
        statement = UpdateStatement(
            self.column_family_name,
            ttl=self._ttl,
            timestamp=self._timestamp,
            conditionals=self._conditional,
            if_exists=self._if_exists)
        for name, col in self.instance._clustering_keys.items():
            null_clustering_key = null_clustering_key and col._val_is_null(
                getattr(self.instance, name, None))

        updated_columns = set()
        # get defined fields and their column names
        for name, col in self.model._columns.items():
            # if clustering key is null, don't include non static columns
            if null_clustering_key and not col.static \
                    and not col.partition_key:
                continue
            if not col.is_primary_key:
                val = getattr(self.instance, name, None)
                val_mgr = self.instance._values[name]

                if val is None:
                    continue

                if not val_mgr.changed and not isinstance(
                        col, columns.Counter):
                    continue

                static_changed_only = static_changed_only and col.static
                statement.add_update(col, val, previous=val_mgr.previous_value)
                updated_columns.add(col.db_field_name)

        if statement.assignments:
            for name, col in self.model._primary_keys.items():
                # only include clustering key if clustering key is not null,
                # and non static columns are changed to avoid cql error
                if (null_clustering_key
                        or static_changed_only) and (not col.partition_key):
                    continue
                statement.add_where(col, EqualsOperator(),
                                    getattr(self.instance, name))
            await self._async_execute(statement)

        if not null_clustering_key:
            # remove conditions on fields that have been updated
            delete_conditionals = [
                condition for condition in self._conditional
                if condition.field not in updated_columns
            ] if self._conditional else None
            self._delete_null_columns(delete_conditionals)


class AioQuerySet(ModelQuerySet):

    async def _async_execute_query(self):
        if self._batch:
            raise CQLEngineException("Only inserts, updates, "
                                     "and deletes are available in batch mode")
        if self._result_cache is None:
            results = await self._async_execute(self._select_query())
            self._result_generator = (i for i in results)
            self._result_cache = []
            self._construct_result = self._maybe_inject_deferred(
                self._get_result_constructor())

            # "DISTINCT COUNT()" is not supported in C* < 2.2,
            # so we need to materialize all results to get
            # len() and count() working with DISTINCT queries
            if self._materialize_results or self._distinct_fields:
                self._fill_result_cache()

    async def _async_execute(self, statement):
        if self._batch:
            return self._batch.add_query(statement)
        else:
            connection = self._connection or self.model._get_connection()
            result = await _execute_statement(
                self.model,
                statement,
                self._consistency,
                self._timeout,
                connection=connection)
            if self._if_not_exists or self._if_exists or self._conditional:
                check_applied(result)
            return result

    async def async_create(self, **kwargs):
        return await self.model(**kwargs) \
            .batch(self._batch) \
            .ttl(self._ttl) \
            .consistency(self._consistency) \
            .if_not_exists(self._if_not_exists) \
            .timestamp(self._timestamp) \
            .if_exists(self._if_exists) \
            .using(connection=self._connection) \
            .async_save()

    async def async_all(self):
        await self._async_execute_query()
        return self

    async def async_get(self, *args, **kwargs):
        if args or kwargs:
            return await self.filter(*args, **kwargs).async_get()

        await self._async_execute_query()

        # Check that the resultset only contains one element,
        # avoiding sending a COUNT query
        try:
            self[1]
            raise self.model.MultipleObjectsReturned('Multiple objects found')
        except IndexError:
            pass

        try:
            obj = self[0]
        except IndexError:
            raise self.model.DoesNotExist

        return obj

    async def async_update(self, **values):
        if not values:
            return

        nulled_columns = set()
        updated_columns = set()
        us = UpdateStatement(
            self.column_family_name,
            where=self._where,
            ttl=self._ttl,
            timestamp=self._timestamp,
            conditionals=self._conditional,
            if_exists=self._if_exists)
        for name, val in values.items():
            col_name, col_op = self._parse_filter_arg(name)
            col = self.model._columns.get(col_name)
            # check for nonexistant columns
            if col is None:
                raise ValidationError(
                    "{0}.{1} has no column named: {2}".format(
                        self.__module__, self.model.__name__, col_name))
            # check for primary key update attempts
            if col.is_primary_key:
                raise ValidationError(
                    "Cannot apply update to primary key '{0}' for {1}.{2}".
                    format(col_name, self.__module__, self.model.__name__))

            if col_op == 'remove' and isinstance(col, columns.Map):
                if not isinstance(val, set):
                    raise ValidationError(
                        "Cannot apply update operation '{0}' on column '{1}' "
                        "with value '{2}'. A set is required."
                        .format(col_op, col_name, val))
                val = {v: None for v in val}
            else:
                # we should not provide default values in this use case.
                val = col.validate(val)

            if val is None:
                nulled_columns.add(col_name)
                continue

            us.add_update(col, val, operation=col_op)
            updated_columns.add(col_name)

        if us.assignments:
            await self._async_execute(us)

        if nulled_columns:
            delete_conditional = [
                condition for condition in self._conditional
                if condition.field not in updated_columns
            ] if self._conditional else None
            ds = DeleteStatement(
                self.column_family_name,
                fields=nulled_columns,
                where=self._where,
                conditionals=delete_conditional,
                if_exists=self._if_exists)
            await self._async_execute(ds)
