"""
This file is part of the everest project. 
See LICENSE.txt for licensing, CONTRIBUTORS.txt for contributor information.

Created on Jun 1, 2011.
"""
from everest.orm import get_metadata
from everest.orm import is_metadata_initialized
from everest.orm import reset_metadata
from everest.querying.filtering import SqlFilterSpecificationVisitor
from everest.querying.specifications import FilterSpecificationFactory
from everest.repository import REPOSITORIES
from everest.representers.config import IGNORE_OPTION
from everest.representers.config import RepresenterConfiguration
from everest.representers.config import WRITE_AS_LINK_OPTION
from everest.representers.mapping import SimpleMappingRegistry
from everest.resources.attributes import ResourceAttributeKinds
from everest.resources.base import Collection
from everest.resources.base import ResourceToEntityFilterSpecificationVisitor
from everest.resources.descriptors import terminal_attribute
from everest.resources.utils import get_member_class
from everest.resources.utils import get_root_collection
from everest.resources.utils import new_stage_collection
from everest.testing import Pep8CompliantTestCase
from everest.testing import ResourceTestCase
from everest.tests.testapp_db.entities import MyEntity
from everest.tests.testapp_db.entities import MyEntityChild
from everest.tests.testapp_db.entities import MyEntityParent
from everest.tests.testapp_db.interfaces import IMyEntity
from everest.tests.testapp_db.interfaces import IMyEntityChild
from everest.tests.testapp_db.interfaces import IMyEntityParent
from everest.tests.testapp_db.resources import MyEntityMember
from everest.tests.testapp_db.resources import MyEntityParentMember
from everest.tests.testapp_db.testing import create_entity
from everest.url import resource_to_url
from pkg_resources import resource_filename # pylint: disable=E0611
import datetime

__docformat__ = 'reStructuredText en'
__all__ = ['AttributesTestCase',
           'DescriptorsTestCase',
           ]


class AttributesTestCase(Pep8CompliantTestCase):
    def test_names(self):
        self.assert_equal(
                    MyEntityMember.get_attribute_names(),
                    ['id', 'parent', 'nested_parent', 'children', 'text',
                     'text_rc', 'number', 'date_time', 'parent_text'])

    def test_types(self):
        attrs = MyEntityMember.get_attributes().values()
        self.assert_equal(attrs[0].name, 'id')
        self.assert_equal(attrs[0].kind, ResourceAttributeKinds.TERMINAL)
        self.assert_equal(attrs[0].entity_name, 'id')
        self.assert_equal(attrs[0].value_type, int)
        self.assert_equal(attrs[1].name, 'parent')
        self.assert_equal(attrs[1].kind, ResourceAttributeKinds.MEMBER)
        self.assert_equal(attrs[1].entity_name, 'parent')
        self.assert_equal(attrs[1].value_type, IMyEntityParent)
        self.assert_equal(attrs[3].name, 'children')
        self.assert_equal(attrs[3].kind,
                          ResourceAttributeKinds.COLLECTION)
        self.assert_equal(attrs[3].entity_name, 'children')
        self.assert_equal(attrs[3].value_type, IMyEntityChild)
        self.assert_equal(attrs[4].name, 'text')
        self.assert_equal(attrs[4].kind, ResourceAttributeKinds.TERMINAL)
        self.assert_equal(attrs[4].entity_name, 'text')
        self.assert_equal(attrs[4].value_type, str)
        self.assert_equal(attrs[6].name, 'number')
        self.assert_equal(attrs[6].kind, ResourceAttributeKinds.TERMINAL)
        self.assert_equal(attrs[6].entity_name, 'number')
        self.assert_equal(attrs[6].value_type, int)

    def test_inheritance(self):
        class MyEntityDerivedMember(MyEntityMember):
            text = terminal_attribute(int, 'text')
        attrs = MyEntityDerivedMember.get_attributes()
        attr = attrs['text']
        self.assert_equal(attr.kind,
                          ResourceAttributeKinds.TERMINAL)
        self.assert_equal(attr.entity_name, 'text')
        self.assert_equal(attr.value_type, int)


class DescriptorsTestCase(ResourceTestCase):
    package_name = 'everest.tests.testapp_db'
    ini_file_path = resource_filename('everest.tests.testapp_db',
                                      'testapp.ini')
    ini_section_name = 'app:testapp_db'

    TEST_TEXT = 'TEST TEXT'
    UPDATED_TEXT = 'UPDATED TEXT'

    @classmethod
    def teardown_class(cls):
        if is_metadata_initialized(REPOSITORIES.ORM):
            metadata = get_metadata(REPOSITORIES.ORM)
            metadata.drop_all()
            reset_metadata()

    def test_terminal_access(self):
        entity = MyEntity()
        member = MyEntityMember.create_from_entity(entity)
        self.assert_true(isinstance(member.text, str))
        self.assert_true(isinstance(member.number, int))
        self.assert_true(isinstance(member.date_time, datetime.datetime))

    def test_member_access(self):
        parent = MyEntityParent()
        entity = MyEntity(parent=parent)
        member = MyEntityMember.create_from_entity(entity)
        self.assert_true(isinstance(member.parent, MyEntityParentMember))
        self.assert_true(member.parent.get_entity() is parent)

    def test_collection_access(self):
        parent = MyEntityParent()
        entity = MyEntity(parent=parent)
        coll = get_root_collection(IMyEntity)
        member = coll.create_member(entity)
        self.assert_true(isinstance(member.children, Collection))
        i = 0
        n = 5
        while i < n:
            child_entity = MyEntityChild()
            member.children.create_member(child_entity)
            i += 1
        self.assert_equal(len(member.children), n)

    def test_update_terminal(self):
        my_entity = create_entity()
        coll = new_stage_collection(IMyEntity)
        member = coll.create_member(my_entity)
        member.text = self.UPDATED_TEXT
        mp = self._make_mapping()
        data_el = mp.map_to_data_element(member)
        del member
        del my_entity
        my_entity = create_entity()
        coll = get_root_collection(IMyEntity)
        context = coll.create_member(my_entity)
        self.assert_equal(context.text, MyEntity.DEFAULT_TEXT)
        context.update_from_data(data_el)
        self.assert_equal(context.text, self.UPDATED_TEXT)

    def test_update_terminal_in_parent(self):
        my_entity = create_entity()
        my_entity.parent.text = self.UPDATED_TEXT
        coll = new_stage_collection(IMyEntity)
        member = coll.create_member(my_entity)
        mp = self._make_mapping()
        data_el = mp.map_to_data_element(member)
        del member
        del my_entity
        my_entity = create_entity()
        coll = get_root_collection(IMyEntity)
        context = coll.create_member(my_entity)
        self.assert_equal(context.parent.text, MyEntity.DEFAULT_TEXT)
        context.update_from_data(data_el)
        self.assert_equal(context.parent.text, self.UPDATED_TEXT)

    def test_update_terminal_in_child(self):
        my_entity = create_entity()
        my_entity.children[0].text = self.UPDATED_TEXT
        coll = new_stage_collection(IMyEntity)
        member = coll.create_member(my_entity)
        mp = self._make_mapping()
        data_el = mp.map_to_data_element(member)
        del member
        del my_entity
        my_entity = create_entity()
        coll = get_root_collection(IMyEntity)
        context = coll.create_member(my_entity)
        self.assert_equal(iter(context.children).next().text,
                          MyEntity.DEFAULT_TEXT)
        context.update_from_data(data_el)
        self.assert_equal(iter(context.children).next().text,
                          self.UPDATED_TEXT)

    def test_update_member(self):
        my_entity = create_entity()
        new_parent = MyEntityParent()
        new_parent.text = self.UPDATED_TEXT
        new_parent.id = 2
        my_entity.parent = new_parent
        coll = new_stage_collection(IMyEntity)
        member = coll.create_member(my_entity)
        mp = self._make_mapping()
        data_el = mp.map_to_data_element(member)
        del member
        del my_entity
        my_entity = create_entity()
        coll = get_root_collection(IMyEntity)
        context = coll.create_member(my_entity)
        self.assert_equal(context.parent.text, MyEntity.DEFAULT_TEXT)
        context.update_from_data(data_el)
        self.assert_equal(context.parent.text, self.UPDATED_TEXT)

    def test_update_member_with_link(self):
        my_entity = create_entity()
        new_parent = MyEntityParent()
        new_parent.text = self.UPDATED_TEXT
        new_parent.id = 2
        my_entity.parent = new_parent
        coll = new_stage_collection(IMyEntity)
        member = coll.create_member(my_entity)
        mp = self._make_mapping()
        mapping_options = {('parent',):{WRITE_AS_LINK_OPTION:True},
                           ('nested_parent',):{IGNORE_OPTION:True}}
        mp_cloned = mp.clone(mapping_options=mapping_options)
        data_el = mp_cloned.map_to_data_element(member)
        # The linked-to parent needs to be in the root collection.
        my_entity.parent = None
        del member
        del my_entity
        parent_coll = get_root_collection(IMyEntityParent)
        parent_coll.create_member(new_parent)
        my_entity = create_entity()
        coll = get_root_collection(IMyEntity)
        context = coll.create_member(my_entity)
        self.assert_equal(context.parent.text, MyEntity.DEFAULT_TEXT)
        context.update_from_data(data_el)
        self.assert_equal(context.parent.text, self.UPDATED_TEXT)

    def test_delete_child(self):
        my_entity = create_entity()
        del my_entity.children[0]
        coll = new_stage_collection(IMyEntity)
        member = coll.create_member(my_entity)
        mp = self._make_mapping()
        data_el = mp.map_to_data_element(member)
        del member
        del my_entity
        my_entity = create_entity()
        coll = get_root_collection(IMyEntity)
        context = coll.create_member(my_entity)
        self.assert_equal(len(context.children), 1)
        context.update_from_data(data_el)
        self.assert_equal(len(context.children), 0)

    def test_delete_grandchild(self):
        my_entity = create_entity()
        del my_entity.children[0].children[0]
        coll = new_stage_collection(IMyEntity)
        member = coll.create_member(my_entity)
        mp = self._make_mapping()
        data_el = mp.map_to_data_element(member)
        del member
        del my_entity
        my_entity = create_entity()
        coll = get_root_collection(IMyEntity)
        context = coll.create_member(my_entity)
        self.assert_equal(len(iter(context.children).next().children),
                          1)
        context.update_from_data(data_el)
        self.assert_equal(len(iter(context.children).next().children),
                          0)

    def test_add_child(self):
        my_entity = create_entity()
        new_child = MyEntityChild()
        my_entity.children.append(new_child)
        coll = new_stage_collection(IMyEntity)
        member = coll.create_member(my_entity)
        self.assert_equal(len(member.children), 2)
        mp = self._make_mapping()
        data_el = mp.map_to_data_element(member)
        del member
        del my_entity
        my_entity = create_entity()
        coll = get_root_collection(IMyEntity)
        context = coll.create_member(my_entity)
        self.assert_equal(len(context.children), 1)
        context.update_from_data(data_el)
        self.assert_equal(len(context.children), 2)

    def test_filter_specification_visitor(self):
        coll = get_root_collection(IMyEntity)
        mb_cls = get_member_class(coll)
        my_entity = create_entity()
        member = coll.create_member(my_entity)
        spec_fac = FilterSpecificationFactory()
        specs = [
                # Terminal access.
                spec_fac.create_equal_to('text', self.TEST_TEXT),
                # Terminal access with different name in entity.
                spec_fac.create_equal_to('text_rc', self.TEST_TEXT),
                # Nested member access with different name in entity.
                spec_fac.create_equal_to('parent.text_rc', self.TEST_TEXT),
                # Nested collection access with different name in entity.
                spec_fac.create_equal_to('children.text_rc', self.TEST_TEXT),
                # Access with dotted entity name in rc attr declaration.
                spec_fac.create_equal_to('parent_text', self.TEST_TEXT),
                # Access to member.
                spec_fac.create_equal_to('parent', member.parent.get_entity()),
                ]
        expecteds = [('text', MyEntity.text.__eq__(self.TEST_TEXT)),
                     ('text_ent', MyEntity.text_ent.__eq__(
                                                        self.TEST_TEXT)),
                     ('parent.text_ent',
                          MyEntity.parent.has(
                                    MyEntityParent.text_ent.__eq__(
                                                        self.TEST_TEXT))),
                     ('children.text_ent',
                          MyEntity.children.any(
                                    MyEntityChild.text_ent.__eq__(
                                                        self.TEST_TEXT))),
                     ('parent.text_ent',
                          MyEntity.parent.has(
                                    MyEntityParent.text_ent.__eq__(
                                                        self.TEST_TEXT))),
                     ('parent',
                          MyEntity.parent.__eq__(member.parent.get_entity())),
                     ]
        for spec, expected in zip(specs, expecteds):
            new_attr_name, expr = expected
            visitor = ResourceToEntityFilterSpecificationVisitor(mb_cls)
            spec.accept(visitor)
            new_spec = visitor.expression
            self.assert_equal(new_spec.attr_name, new_attr_name)
            visitor = SqlFilterSpecificationVisitor(MyEntity)
            new_spec.accept(visitor)
            self.assert_equal(str(visitor.expression), str(expr))

    def test_nested_access(self):
        my_entity = create_entity()
        coll = new_stage_collection(IMyEntity)
        member = coll.create_member(my_entity)
        self.assert_equal(member.parent_text, MyEntityParent.DEFAULT_TEXT)

    def test_urls(self):
        my_entity = create_entity()
        coll = get_root_collection(IMyEntity)
        mb = coll.create_member(my_entity)
        self.assert_equal(resource_to_url(mb),
                          'http://0.0.0.0:6543/my-entities/0/')
        self.assert_equal(resource_to_url(mb.parent),
                          'http://0.0.0.0:6543/my-entity-parents/0/')
        self.assert_equal(resource_to_url(mb.nested_parent),
                        'http://0.0.0.0:6543/my-entities/0/nested-parent/')
        self.assert_equal(resource_to_url(mb.children),
                          'http://0.0.0.0:6543/my-entities/0/children/')
        mb_child = mb.children['0']
        self.assert_equal(mb_child.id, 0)
        self.assert_equal(resource_to_url(mb_child.children),
                          'http://0.0.0.0:6543/my-entity-grandchildren/'
                          '?q=parent:equal-to:'
                          'http://0.0.0.0:6543/my-entities/0/children/0/')
        self.assert_equal(resource_to_url(mb_child.no_backref_children),
                          'http://0.0.0.0:6543/my-entity-grandchildren/'
                          '?q=id:contained:0')

    def _make_mapping(self):
        reg = SimpleMappingRegistry()
        mp_opts = {('parent',):{WRITE_AS_LINK_OPTION:False,
                                IGNORE_OPTION:False},
                   ('nested_parent',):{WRITE_AS_LINK_OPTION:False,
                                       IGNORE_OPTION:False},
                   ('children',):{WRITE_AS_LINK_OPTION:False,
                                  IGNORE_OPTION:False},
                   ('children', 'children'):{WRITE_AS_LINK_OPTION:False,
                                             IGNORE_OPTION:False},
                   ('children', 'no_backref_children'):{IGNORE_OPTION:True},
                   }
        conf = RepresenterConfiguration(mapping_options=mp_opts)
        mp = reg.create_mapping(MyEntityMember, conf)
        reg.set_mapping(mp)
        return mp
