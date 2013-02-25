"""
Unit of work.

This file is part of the everest project. 
See LICENSE.txt for licensing, CONTRIBUTORS.txt for contributor information.

Created on Jan 16, 2013.
"""
from collections import defaultdict
from transaction.interfaces import IDataManager
from weakref import WeakSet
from weakref import ref
from zope.interface import implements # pylint: disable=E0611,F0401

__docformat__ = 'reStructuredText en'
__all__ = ['UnitOfWork',
           ]


class OBJECT_STATES(object):
    CLEAN = 'CLEAN'
    NEW = 'NEW'
    DELETED = 'DELETED'
    DIRTY = 'DIRTY'


class ObjectStateManager(object):
    """
    Helper object to track object state.
    
    Initially, an object is marked as NEW (freshly instantiated) or CLEAN
    (freshly fetched from repository).
    
    Only a weak reference to the tracked object is stored to avoid circular
    references.
    
    Allowed transitions are CLEAN -> DIRTY, CLEAN -> DELETED, NEW -> DIRTY, 
    NEW -> DELETED, DIRTY -> DELETED, DIRTY -> CLEAN.
    """
    __allowed_transitions = ((OBJECT_STATES.NEW, OBJECT_STATES.DIRTY),
                             (OBJECT_STATES.NEW, OBJECT_STATES.DELETED),
                             (OBJECT_STATES.CLEAN, OBJECT_STATES.DIRTY),
                             (OBJECT_STATES.CLEAN, OBJECT_STATES.DELETED),
                             (OBJECT_STATES.DIRTY, OBJECT_STATES.DELETED),
                             (OBJECT_STATES.DIRTY, OBJECT_STATES.CLEAN)
                             )

    def __init__(self, tracked_object, initial_state):
        self.__obj_ref = ref(tracked_object)
        if not initial_state in (OBJECT_STATES.NEW, OBJECT_STATES.CLEAN):
            raise ValueError('Invalid initial state "%s".' % initial_state)
        self.__state = initial_state
        self.__last_state_hash = hash(self.__get_state_string())

    def reset_state(self):
        self.state = OBJECT_STATES.CLEAN
        self.__last_state_hash = hash(self.__get_state_string())

    def __get_state_string(self):
        # Concatenate all public attribute name:value pairs.
        obj = self.__obj_ref()
        tokens = ['%s:%s' % (k, v)
                  for k, v in obj.__dict__.iteritems()
                  if not k.startswith('_')]
        return ','.join(tokens)

    def __get_state(self):
        state = self.__state
        if state == OBJECT_STATES.CLEAN:
            obj_hash = hash(self.__get_state_string())
            if obj_hash != self.__last_state_hash:
                state = OBJECT_STATES.DIRTY
        return state

    def __set_state(self, state):
        if not (self.__get_state(), state) in self.__allowed_transitions:
            raise ValueError('Invalid state transition %s -> %s.'
                             % (self.__state, state))
        self.__state = state

    state = property(__get_state, __set_state)


class UnitOfWork(object):
    def __init__(self, repository):
        self.__repository = repository
        self.__entity_set_map = defaultdict(WeakSet)

    def register_new(self, entity_class, entity):
        """
        Registers the given entity for the given class as NEW.
        
        :raises ValueError: If the given entity already holds state.
        """
        if hasattr(entity, '__everest__'):
            raise ValueError('Trying to register a NEW entity that has '
                             'already been registered!')
        entity.__everest__ = ObjectStateManager(OBJECT_STATES.NEW)
        if entity.id is None:
            with self.__repository.lock:
                entity.id = self.__repository.get_next_id(entity_class)
        self.__entity_set_map[entity_class].add(entity)

    def mark_clean(self, entity_class, entity):
        """
        Marks the given entity for the given class as CLEAN.
        
        This is done when an entity is loaded fresh from the repository or
        after a commit.
        """
        if not hasattr(entity, '__everest__'):
            entity.__everest__ = ObjectStateManager(OBJECT_STATES.CLEAN)
        else:
            entity.__everest__.state = OBJECT_STATES.CLEAN
        self.__entity_set_map[entity_class].add(entity)

    def mark_deleted(self, entity_class, entity):
        """
        Marks the given entity for the given class as DELETED.
        
        :raises ValueError: If the given entity does not hold state.
        """
        if not hasattr(entity, '__everest__'):
            raise ValueError('Trying to mark an unregistered entity as '
                             'DELETED!')
        entity.__everest__.state = OBJECT_STATES.DELETED
        self.__entity_set_map[entity_class].add(entity)

    def mark_dirty(self, entity_class, entity):
        """
        Marks the given entity for the given class as DIRTY.
        
        :raises ValueError: If the given entity does not hold state.
        """
        if not hasattr(entity, '__everest__'):
            raise ValueError('Trying to mark an unregistered entity as '
                             'DIRTY!')
        entity.__everest__.state = OBJECT_STATES.DIRTY
        self.__entity_set_map[entity_class].add(entity)

    def get_clean(self, entity_class=None):
        """
        Returns an iterator over all CLEAN entities in this unit of work
        (optionally restricted to entities of the given class).
        """
        return self.__object_iterator(OBJECT_STATES.CLEAN, entity_class)

    def get_new(self, entity_class=None):
        """
        Returns an iterator over all NEW entities in this unit of work
        (optionally restricted to entities of the given class).
        """
        return self.__object_iterator(OBJECT_STATES.NEW, entity_class)

    def get_deleted(self, entity_class=None):
        """
        Returns an iterator over all DELETED entities in this unit of work
        (optionally restricted to entities of the given class).
        """
        return self.__object_iterator(OBJECT_STATES.DELETED, entity_class)

    def get_dirty(self, entity_class=None):
        """
        Returns an iterator over all DIRTY entities in this unit of work
        (optionally restricted to entities of the given class).
        """
        return self.__object_iterator(OBJECT_STATES.DIRTY, entity_class)

    def commit(self):
        """
        
        """
        with self.__repository.lock:
            for ent_cls in self.__entity_set_map.keys():
                for ent in self.__entity_set_map[ent_cls]:
                    if ent.state == OBJECT_STATES.DIRTY:
                        self.__repository.replace(ent)
                    elif ent.state == OBJECT_STATES.NEW:
                        self.__repository.add(ent)
                    elif ent.state == OBJECT_STATES.DELETED:
                        self.__repository.remove(ent)
                    ent.__everest__.reset_state()

    def rollback(self):
        self.__entity_set_map.clear()

    def __object_iterator(self, state, ent_cls):
        if ent_cls is None:
            keys = self.__entity_set_map.keys()
        else:
            keys = [ent_cls]
        for key in keys:
            for ent in self.__entity_set_map[key]:
                if ent.state == state:
                    yield ent


class DataManager(object):
    """
    Data manager to plug a :class:`UnitOfWork` into a zope transaction.
    """
    # TODO: implement safepoints.
    implements(IDataManager)

    def __init__(self, uow):
        self.__uow = uow

    def abort(self, trans): # pylint: disable=W0613
        self.__uow.rollback()

    def tpc_begin(self, trans): # pylint: disable=W0613
        self.__uow.flush()

    def commit(self, trans): # pylint: disable=W0613
        self.__uow.commit()

    def tpc_vote(self, trans): # pylint: disable=W0613
        pass

    def tpc_finish(self, trans):
        pass

    def tpc_abort(self, trans): # pylint: disable=W0613
        self.__uow.rollback()

    def sortKey(self):
        return "everest:%d" % id(self.__uow)
