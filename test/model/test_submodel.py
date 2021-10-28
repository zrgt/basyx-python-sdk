# Copyright (c) 2020 PyI40AAS Contributors
#
# This program and the accompanying materials are made available under the terms of the Eclipse Public License v. 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0, or the Apache License, Version 2.0 which is available
# at https://www.apache.org/licenses/LICENSE-2.0.
#
# SPDX-License-Identifier: EPL-2.0 OR Apache-2.0

import unittest

from aas import model


class EntityTest(unittest.TestCase):

    def test_set_entity(self):
        with self.assertRaises(model.AASConstraintViolation) as cm:
            obj = model.Entity(id_short='Test', entity_type=model.EntityType.SELF_MANAGED_ENTITY, statement=())
        self.assertIn(
            'A self-managed entity has to have a globalAssetId or a specificAssetId',
            str(cm.exception)
        )
        with self.assertRaises(model.AASConstraintViolation) as cm:
            obj2 = model.Entity(id_short='Test', entity_type=model.EntityType.CO_MANAGED_ENTITY,
                                global_asset_id=model.Reference((model.Key(type_=model.KeyElements.GLOBAL_REFERENCE,
                                                                           value='http://acplt.org/TestAsset/',
                                                                           id_type=model.KeyType.IRI),)),
                                statement=())
        self.assertIn(
            'A co-managed entity has to have neither a globalAssetId nor a specificAssetId',
            str(cm.exception)
        )

        identifier_key_value_pair = model.IdentifierKeyValuePair(key="TestKey",
                                                                 value="TestValue",
                                                                 external_subject_id=model.Reference((model.Key(
                                                                     type_=model.KeyElements.GLOBAL_REFERENCE,
                                                                     value='http://acplt.org/SpecificAssetId/',
                                                                     id_type=model.KeyType.IRI),)))
        with self.assertRaises(model.AASConstraintViolation) as cm:
            obj3 = model.Entity(id_short='Test', entity_type=model.EntityType.CO_MANAGED_ENTITY,
                                specific_asset_id=identifier_key_value_pair, statement=())
        self.assertIn(
            'A co-managed entity has to have neither a globalAssetId nor a specificAssetId',
            str(cm.exception))


class PropertyTest(unittest.TestCase):
    def test_set_value(self):
        property = model.Property('test', model.datatypes.Int, 2)
        self.assertEqual(property.value, 2)
        property.value = None
        self.assertIsNone(property.value)


class RangeTest(unittest.TestCase):
    def test_set_min_max(self):
        range = model.Range('test', model.datatypes.Int, 2, 5)
        self.assertEqual(range.min, 2)
        self.assertEqual(range.max, 5)
        range.min = None
        self.assertIsNone(range.min)
        range.max = None
        self.assertIsNone(range.max)


class SubmodelElementCollectionTest(unittest.TestCase):
    def test_submodel_element_collection_unordered_unique_semantic_id(self):
        propSemanticID1 = model.Reference((model.Key(type_=model.KeyElements.GLOBAL_REFERENCE,
                                                     value='http://acplt.org/Test1',
                                                     id_type=model.KeyType.IRI),))
        propSemanticID2 = model.Reference((model.Key(type_=model.KeyElements.GLOBAL_REFERENCE,
                                                     value='http://acplt.org/Test2',
                                                     id_type=model.KeyType.IRI),))
        property1 = model.Property('test1', model.datatypes.Int, 2, semantic_id=propSemanticID1)
        property2 = model.Property('test1', model.datatypes.Int, 2, semantic_id=propSemanticID2)
        property3 = model.Property('test2', model.datatypes.Int, 2, semantic_id=propSemanticID1)
        property4 = model.Property('test2', model.datatypes.Int, 2, semantic_id=propSemanticID2)

        collection = model.SubmodelElementCollection.create("TestSM", allow_duplicates=False, ordered=False)
        collection.value.add(property1)
        self.assertIn(property1, collection.value)
        with self.assertRaises(KeyError) as cm:
            collection.value.add(property2)
        self.assertEqual('"Object with attribute (name=\'id_short\', value=\'test1\') is already present in this set '
                         'of objects"',
                         str(cm.exception))

        with self.assertRaises(KeyError) as cm:
            collection.value.add(property3)
        self.assertEqual('"Object with attribute (name=\'semantic_id\', value=\'Reference(key=(Key(id_type=IRI, '
                         'value=http://acplt.org/Test1),))\') is already present in this set of objects"',
                         str(cm.exception))
        collection.value.add(property4)
        self.assertIs(property1, collection.get_referable("test1"))
        self.assertIs(property1, collection.get_object_by_semantic_id(propSemanticID1))
        self.assertIs(property4, collection.get_object_by_semantic_id(propSemanticID2))
