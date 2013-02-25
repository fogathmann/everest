"""

This file is part of the everest project. 
See LICENSE.txt for licensing, CONTRIBUTORS.txt for contributor information.

Created on Jan 8, 2013.
"""
from everest.repositories.base import SessionFactory
from threading import local
from transaction.interfaces import IDataManager
from zope.interface import implements # pylint: disable=E0611,F0401
from weakref import WeakValueDictionary
from everest.utils import id_generator


__docformat__ = 'reStructuredText en'
__all__ = []


class DataManager(object):
    """
    Data manager to plug an :class:`MemorySession` into a zope transaction.
    """
    # TODO: implement safepoints.
    implements(IDataManager)

    def __init__(self, session):
        self.session = session

    def abort(self, trans): # pylint: disable=W0613
        self.session.rollback()

    def tpc_begin(self, trans): # pylint: disable=W0613
        self.session.flush()

    def commit(self, trans): # pylint: disable=W0613
        self.session.commit()

    def tpc_vote(self, trans): # pylint: disable=W0613
        pass

    def tpc_finish(self, trans):
        pass

    def tpc_abort(self, trans): # pylint: disable=W0613
        self.session.rollback()

    def sortKey(self):
        return "everest:%d" % id(self.session)


class EntityCache(object):
    """
    Cache for entities.
    
    Supports add and remove operations as well as lookup by ID and 
    by slug.
    """
    def __init__(self):
        # List of cached entities. This is the only place we are holding a
        # real reference to the entity.
        self.__entities = []
        # Dictionary mapping entity IDs to entities for fast lookup by ID.
        self.__id_map = WeakValueDictionary()
        # Dictionary mapping entity slugs to entities for fast lookup by slug.
        self.__slug_map = WeakValueDictionary()

    def get_by_id(self, entity_id):
        """
        Performs a lookup of an entity by its ID.
        
        :param int entity_id: entity ID.
        :return: entity found or ``None``.
        """
        return self.__id_map.get(entity_id)

    def has_id(self, entity_id):
        return entity_id in self.__id_map

    def get_by_slug(self, entity_slug):
        """
        Performs a lookup of an entity by its slug.
        
        :param str entity_id: entity slug.
        :return: entity found or ``None``.
        """
        return self.__slug_map.get(entity_slug)

    def has_slug(self, entity_slug):
        return entity_slug in self.__slug_map

    def add(self, entity):
        """
        Adds the given entity to this cache.
        
        :param entity: Entity to add.
        :type entity: Object implementing :class:`everest.interfaces.IEntity`.
        :raises ValueError: If the ID of the entity to add is ``None``.
        """
        if entity.id is None:
            raise ValueError('Entity ID must not be None.')
        self.__id_map[entity.id] = entity
        # Unlike the ID, the slug can be a lazy attribute depending on the
        # value of other (possibly not yet initialized) attributes which is
        # why we can not always assume it is available at this point.
        if not entity.slug is None:
            self.__slug_map[entity.slug] = entity
        self.__entities.append(entity)

    def remove(self, entity):
        """
        Removes the given entity from this cache.
        
        :param entity: Entity to remove.
        :type entity: Object implementing :class:`everest.interfaces.IEntity`.
        :raises KeyError: If the given entity is not in this cache.
        """
        del self.__id_map[entity.id]
        # We may not have the slug in the slug map because it might not have
        # been available by the time the entity was added.
        self.__slug_map.pop(entity.slug, None)
        self.__entities.remove(entity)

    def replace(self, entity):
        """
        Replaces the current entity that has the same ID as the given new
        entity with the latter.
        
        :param entity: Entity to replace.
        :type entity: Object implementing :class:`everest.interfaces.IEntity`.
        """
        old_entity = self.__id_map[entity.id]
        self.remove(old_entity)
        self.add(entity)


class EntityIdGenerator(object):
    """
    Helper class generating unique sequential IDs for each entity type.
    """
    def __init__(self):
        self.__id_gen_map = {}
        self.__next_id_map = {}

    def get_current_id(self, entity_class):
        return self.__next_id_map.get(entity_class, 0)

    def set_current_id(self, entity_class, entity_id):
        id_gen = self.__get_id_generator(entity_class)
        id_gen.send(entity_id)

    def get_next_id(self, entity_class):
        id_gen = self.__get_id_generator(entity_class)
        next_id = id_gen.next()
        self.__next_id_map[entity_class] = next_id
        return next_id - 1

    def __get_id_generator(self, ent_cls):
        id_gen = self.__id_gen_map.get(ent_cls)
        if id_gen is None:
            id_gen = self.__id_gen_map[ent_cls] = id_generator()
            self.__next_id_map[ent_cls] = id_gen.next()
        return id_gen


class EntityCacheManager(object):
    def __init__(self):
        self.__cache_map = {}

    def __getitem__(self, entity_class):
        cache = self.__cache_map.get(entity_class)
        if cache is None:
            cache = self._initialize_cache(entity_class)
        return cache

    def _initialize_cache(self, ent_cls):
        cache = self.__cache_map[ent_cls] = EntityCache()
        return cache


class RepositoryEntityCacheManager(EntityCacheManager):
    def __init__(self, repository):
        EntityCacheManager.__init__(self)
        self.__repository = repository

    def _initialize_cache(self, ent_cls):
        cache = EntityCacheManager._initialize_cache(self, ent_cls)
        loader = self.__repository.configuration['loader']
        if not loader is None:
            max_id = -1
            for ent in loader(ent_cls):
                if ent.id is None:
                    ent.id = self.__repository.get_next_id(ent_cls)
                elif isinstance(ent.id, int) and ent.id >= max_id:
                    # If the loaded entity already has an ID, record the
                    # highest ID so we can adjust the ID generator.
                    max_id = ent.id + 1
                cache.add(ent)
            if max_id != -1 \
               and max_id > self.__repository.get_current_id(ent_cls):
                self.__repository.set_current_id(ent_cls, max_id)
        return cache


class Session(object):
    """
    Session object.
    
    The session
     * Holds a Unit Of Work;
     * Serves as identity and slug map;

     * Manages the transaction?!
     * Locking the repository?!
    """
    def __init__(self, unit_of_work):
        self.__unit_of_work = unit_of_work
        self.__cache_mgr = EntityCacheManager()

    def commit(self):
        self.__unit_of_work.commit()

    def rollback(self):
        self.__unit_of_work.rollback()

    def add(self, entity_class, entity):
        """
        Adds the given entity of the given entity class to the session.
        
        At the point an entity is added, it must not have an ID or a slug
        of another entity that is already in the session. However, both the ID
        and the slug may be ``None`` values.
        """
        cache = self.__cache_mgr[entity_class]
        if not entity.id is None and cache.has_id(entity.id):
            raise ValueError('Duplicate entity key "%s".' % entity.id)
        if not entity.slug is None and cache.has_slug(entity.slug):
            raise ValueError('Duplicate entity slug "%s".' % entity.slug)
        self.__unit_of_work.register_new(entity)
        # By now, we have a unique ID, so we can add to the identity map.
        cache.add(entity)

    def remove(self, entity):
        self.__unit_of_work.mark_deleted(entity)

    def merge(self, entity_cls, entity):
        pass

    def get_by_id(self, entity_cls, entity_id):
        """
        Retrieves the entity for the specified entity class and ID.
        """
        return self.__cache_mgr[entity_cls].get_by_id(entity_id)

    def get_by_slug(self, entity_cls, entity_slug):
        """
        Retrieves the entity for the specified entity class and slug.
        
        Lookup with a slug is less efficient than with an ID, since the
        entity might not be in the cache's slug map in which case we have 
        to look it up in the list of pending NEW entities. 
        """
        found_ent = self.__cache_mgr[entity_cls].get_by_slug(entity_slug)
        if found_ent is None:
            for ent in self.__unit_of_work.get_new(entity_cls):
                if ent.slug == entity_slug:
                    found_ent = ent
                    break
        return found_ent

    def get_all(self, entity_cls):
        pass

    def flush(self):
        pass


class MemorySessionFactory(SessionFactory):
    """
    Factory for :class:`MemorySession` instances.
    
    The factory creates exactly one session per thread.
    """
    def __init__(self, entity_store):
        SessionFactory.__init__(self, entity_store)
        self.__session_registry = local()

    def __call__(self):
        session = getattr(self.__session_registry, 'session', None)
        if session is None:
            session = Session(self._entity_store)
            self.__session_registry.session = session
        return session
