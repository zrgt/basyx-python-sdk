# Copyright (c) 2020 the Eclipse BaSyx Authors
#
# This program and the accompanying materials are made available under the terms of the MIT License, available in
# the LICENSE file of this project.
#
# SPDX-License-Identifier: MIT
import unittest

from basyx2.aas.examples.data._helper import DataChecker, AASDataChecker
from basyx2.aas import model
from basyx2.aas.model.concept import IEC61360DataType


class DataCheckerTest(unittest.TestCase):
    def test_check(self):
        checker = DataChecker(raise_immediately=True)
        with self.assertRaises(AssertionError) as cm:
            checker.check(2 == 3, 'Assertion test')
        self.assertEqual("('Check failed: Assertion test', {})", str(cm.exception))

    def test_kwargs(self):
        checker = DataChecker(raise_immediately=True)
        with self.assertRaises(AssertionError) as cm:
            checker.check(2 == 3, 'Assertion test 1', value='kwargs1')
        with self.assertRaises(AssertionError) as cm_2:
            checker.check(2 == 3, 'Assertion test 2', value='kwargs2')
        self.assertEqual("('Check failed: Assertion test 1', {'value': 'kwargs1'})", str(cm.exception))
        self.assertEqual("('Check failed: Assertion test 2', {'value': 'kwargs2'})", str(cm_2.exception))

    def test_raise_failed(self):
        checker = DataChecker(raise_immediately=False)
        checker.check(2 == 2, 'Assertion test')
        checker.raise_failed()  # no assertion should be occur
        self.assertEqual(1, sum(1 for _ in checker.successful_checks))
        checker.check(2 == 3, 'Assertion test')
        with self.assertRaises(AssertionError) as cm:
            checker.raise_failed()
        self.assertEqual("('1 of 2 checks failed', ['Assertion test'])", str(cm.exception))


class AASDataCheckerTest(unittest.TestCase):
    def test_qualifiable_checker(self):
        qualifier_expected = model.Qualifier(
            type_='test',
            value_type=model.datatypes.String,
            value='test value'
        )
        property_expected = model.Property(
            id_short='Prop1',
            value_type=model.datatypes.String,
            value='test',
            qualifier={qualifier_expected}
        )

        property = model.Property(
            id_short='Prop1',
            value_type=model.datatypes.String,
            value='test'
        )

        checker = AASDataChecker(raise_immediately=False)
        checker.check_property_equal(property, property_expected)
        self.assertEqual(2, sum(1 for _ in checker.failed_checks))
        self.assertEqual(9, sum(1 for _ in checker.successful_checks))
        checker_iterator = iter(checker.failed_checks)
        self.assertEqual("FAIL: Property[Prop1] must contain 1 Constraints (count=0)",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: ConstraintQualifier(type=test) must exist ()", repr(next(checker_iterator)))

    def test_submodel_element_collection_ordered_checker(self):
        property = model.Property(
            id_short='Prop1',
            value_type=model.datatypes.String,
            value='test'
        )
        range = model.Range(
            id_short='Range1',
            value_type=model.datatypes.Int,
            min=100,
            max=200
        )
        collection = model.SubmodelElementCollectionOrdered(
            id_short='Collection',
            value=(property, range)
        )

        property_expected = model.Property(
            id_short='Prop1',
            value_type=model.datatypes.String,
            value='test'
        )
        range_expected = model.Range(
            id_short='Range1',
            value_type=model.datatypes.Int,
            min=100,
            max=200
        )
        collection_expected = model.SubmodelElementCollectionOrdered(
            id_short='Collection',
            value=(range_expected, property_expected)
        )

        checker = AASDataChecker(raise_immediately=False)
        checker.check_submodel_collection_equal(collection, collection_expected)
        self.assertEqual(2, sum(1 for _ in checker.failed_checks))
        checker_iterator = iter(checker.failed_checks)
        self.assertEqual("FAIL: Property[Collection / Prop1] must be of class Range (class='Property')",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: Range[Collection / Range1] must be of class Property (class='Range')",
                         repr(next(checker_iterator)))

    def test_submodel_element_collection_unordered_checker(self):
        collection = model.SubmodelElementCollectionUnordered(
            id_short='Collection',
            value=()
        )
        property_expected = model.Property(
            id_short='Prop1',
            value_type=model.datatypes.String,
            value='test'
        )
        collection_expected = model.SubmodelElementCollectionUnordered(
            id_short='Collection',
            value=(property_expected,)
        )

        checker = AASDataChecker(raise_immediately=False)
        checker.check_submodel_collection_equal(collection, collection_expected)
        self.assertEqual(2, sum(1 for _ in checker.failed_checks))
        checker_iterator = iter(checker.failed_checks)
        self.assertEqual("FAIL: SubmodelElementCollectionUnordered[Collection] must contain 1 SubmodelElements "
                         "(count=0)",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: Submodel ElementProperty[Collection / Prop1] must exist ()",
                         repr(next(checker_iterator)))

    def test_not_implemented(self):
        class DummySubmodelElement(model.SubmodelElement):
            def __init__(self, id_short: str):
                super().__init__(id_short)
        dummy_submodel_element = DummySubmodelElement('test')
        submodel_collection = model.SubmodelElementCollectionUnordered('test')
        submodel_collection.value.add(dummy_submodel_element)
        checker = AASDataChecker(raise_immediately=True)
        with self.assertRaises(AttributeError) as cm:
            checker.check_submodel_collection_equal(submodel_collection, submodel_collection)
        self.assertEqual(
            'Submodel Element class not implemented',
            str(cm.exception)
        )

        class DummySubmodelElementCollection(model.SubmodelElementCollection):
            def __init__(self, id_short: str):
                super().__init__(id_short)

            @property
            def ordered(self):
                return True

        dummy_submodel_element_collection = DummySubmodelElementCollection('test')
        submodel = model.Submodel(identification=model.Identifier('test', model.IdentifierType.CUSTOM))
        submodel.submodel_element.add(dummy_submodel_element_collection)
        checker = AASDataChecker(raise_immediately=True)
        with self.assertRaises(AttributeError) as cm:
            checker.check_submodel_equal(submodel, submodel)
        self.assertEqual(
            'Submodel Element collection class not implemented',
            str(cm.exception)
        )

    def test_annotated_relationship_element(self):
        rel1 = model.AnnotatedRelationshipElement(id_short='test',
                                                  first=model.AASReference((model.Key(type_=model.KeyElements.PROPERTY,
                                                                                      local=True,
                                                                                      value='ExampleProperty',
                                                                                      id_type=model.KeyType.IDSHORT),),
                                                                           model.Property),
                                                  second=model.AASReference((model.Key(type_=model.KeyElements.PROPERTY,
                                                                                       local=True,
                                                                                       value='ExampleProperty',
                                                                                       id_type=model.KeyType.IDSHORT),),
                                                                            model.Property),
                                                  )
        rel2 = model.AnnotatedRelationshipElement(id_short='test',
                                                  first=model.AASReference((model.Key(type_=model.KeyElements.PROPERTY,
                                                                                      local=True,
                                                                                      value='ExampleProperty',
                                                                                      id_type=model.KeyType.IDSHORT),),
                                                                           model.Property),
                                                  second=model.AASReference((model.Key(type_=model.KeyElements.PROPERTY,
                                                                                       local=True,
                                                                                       value='ExampleProperty',
                                                                                       id_type=model.KeyType.IDSHORT),),
                                                                            model.Property),
                                                  annotation={
                                                      model.Property(id_short="ExampleAnnotatedProperty",
                                                                     value_type=model.datatypes.String,
                                                                     value='exampleValue',
                                                                     parent=None)
                                                  })
        checker = AASDataChecker(raise_immediately=False)
        checker.check_annotated_relationship_element_equal(rel1, rel2)
        self.assertEqual(2, sum(1 for _ in checker.failed_checks))
        checker_iterator = iter(checker.failed_checks)
        self.assertEqual("FAIL: AnnotatedRelationshipElement[test] must contain 1 DataElements "
                         "(count=0)",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: Annotation Property[test / ExampleAnnotatedProperty] must exist ()",
                         repr(next(checker_iterator)))

    def test_submodel_checker(self):
        submodel = model.Submodel(identification=model.Identifier('test', model.IdentifierType.CUSTOM))
        property_expected = model.Property(
            id_short='Prop1',
            value_type=model.datatypes.String,
            value='test'
        )
        submodel_expected = model.Submodel(identification=model.Identifier('test', model.IdentifierType.CUSTOM),
                                           submodel_element=(property_expected,)
                                           )

        checker = AASDataChecker(raise_immediately=False)
        checker.check_submodel_equal(submodel, submodel_expected)
        self.assertEqual(2, sum(1 for _ in checker.failed_checks))
        checker_iterator = iter(checker.failed_checks)
        self.assertEqual("FAIL: Submodel[Identifier(CUSTOM=test)] must contain 1 SubmodelElements (count=0)",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: Submodel ElementProperty[Identifier(CUSTOM=test) / Prop1] must exist ()",
                         repr(next(checker_iterator)))

    def test_asset_administration_shell_checker(self):
        shell = model.AssetAdministrationShell(asset=model.AASReference((model.Key(type_=model.KeyElements.ASSET,
                                                                                   local=False,
                                                                                   value='test',
                                                                                   id_type=model.KeyType.IRI),),
                                                                        model.Asset),
                                               identification=model.Identifier('test', model.IdentifierType.CUSTOM))
        shell_expected = model.AssetAdministrationShell(
            asset=model.AASReference((model.Key(type_=model.KeyElements.ASSET,
                                                local=False,
                                                value='test',
                                                id_type=model.KeyType.IRI),),
                                     model.Asset),
            identification=model.Identifier('test', model.IdentifierType.CUSTOM),
            submodel={model.AASReference((model.Key(type_=model.KeyElements.SUBMODEL,
                                                    local=False,
                                                    value='test',
                                                    id_type=model.KeyType.IRI),),
                                         model.Submodel)},
            concept_dictionary=(model.ConceptDictionary(id_short='test'),),
            view=(model.View(id_short='test2'),)
            )
        checker = AASDataChecker(raise_immediately=False)
        checker.check_asset_administration_shell_equal(shell, shell_expected)
        self.assertEqual(6, sum(1 for _ in checker.failed_checks))
        checker_iterator = iter(checker.failed_checks)
        self.assertEqual("FAIL: AssetAdministrationShell[Identifier(CUSTOM=test)] must contain 1 AASReferences "
                         "(count=0)",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: AssetAdministrationShell[Identifier(CUSTOM=test)] must contain 1 ConceptDictionarys "
                         "(count=0)",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: AssetAdministrationShell[Identifier(CUSTOM=test)] must contain 1 Views "
                         "(count=0)",
                         repr(next(checker_iterator)))

        self.assertEqual("FAIL: Submodel Reference AASReference(type=Submodel, key=(Key(local=False, id_type=IRI, "
                         "value=test),)) must exist ()",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: Concept Dictionary ConceptDictionary[Identifier(CUSTOM=test) / test] must exist ()",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: View View[Identifier(CUSTOM=test) / test2] must exist ()",
                         repr(next(checker_iterator)))

    def test_concept_dictionary_checker(self):
        cd = model.ConceptDictionary(id_short='test')
        cd_expected = model.ConceptDictionary(id_short='test',
                                              concept_description={model.AASReference((model.Key(
                                                  type_=model.KeyElements.CONCEPT_DESCRIPTION,
                                                  local=False,
                                                  value='test',
                                                  id_type=model.KeyType.IRI),),
                                                  model.ConceptDescription)}
                                              )
        checker = AASDataChecker(raise_immediately=False)
        checker.check_concept_dictionary_equal(cd, cd_expected)
        self.assertEqual(2, sum(1 for _ in checker.failed_checks))
        checker_iterator = iter(checker.failed_checks)
        self.assertEqual("FAIL: ConceptDictionary[test] must contain 1 AASReferences (count=0)",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: Concept Description Reference AASReference(type=ConceptDescription, "
                         "key=(Key(local=False, id_type=IRI, value=test),)) must exist ()",
                         repr(next(checker_iterator)))

    def test_view_checker(self):
        view = model.View(id_short='test')
        view_expected = model.View(id_short='test',
                                   contained_element={model.AASReference((model.Key(
                                       type_=model.KeyElements.PROPERTY,
                                       local=False,
                                       value='test',
                                       id_type=model.KeyType.IRI),),
                                       model.Property)})
        checker = AASDataChecker(raise_immediately=False)
        checker.check_view_equal(view, view_expected)
        self.assertEqual(2, sum(1 for _ in checker.failed_checks))
        checker_iterator = iter(checker.failed_checks)
        self.assertEqual("FAIL: View[test] must contain 1 AASReferences (count=0)",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: View Reference AASReference(type=Property, key=(Key(local=False, id_type=IRI, "
                         "value=test),)) must exist ()",
                         repr(next(checker_iterator)))

    def test_concept_description_checker(self):
        cd = model.ConceptDescription(identification=model.Identifier('test', model.IdentifierType.CUSTOM))
        cd_expected = model.ConceptDescription(identification=model.Identifier('test', model.IdentifierType.CUSTOM),
                                               is_case_of={model.Reference((model.Key(
                                                  type_=model.KeyElements.GLOBAL_REFERENCE,
                                                  local=False,
                                                  value='test',
                                                  id_type=model.KeyType.IRI),))}
                                               )
        checker = AASDataChecker(raise_immediately=False)
        checker.check_concept_description_equal(cd, cd_expected)
        self.assertEqual(2, sum(1 for _ in checker.failed_checks))
        checker_iterator = iter(checker.failed_checks)
        self.assertEqual("FAIL: ConceptDescription[Identifier(CUSTOM=test)] must contain 1 References (count=0)",
                         repr(next(checker_iterator)))
        self.assertEqual("FAIL: Concept Description Reference Reference(key=(Key(local=False, id_type=IRI, "
                         "value=test),)) must exist ()",
                         repr(next(checker_iterator)))
        iec = model.IEC61360ConceptDescription(
            identification=model.Identifier('test', model.IdentifierType.CUSTOM),
            preferred_name={'de': 'Test Specification', 'en-us': "TestSpecification"},
            data_type=IEC61360DataType.REAL_MEASURE,
            value_list={model.ValueReferencePair(value_type=model.datatypes.String,
                                                 value='test',
                                                 value_id=model.Reference((model.Key(
                                                     type_=model.KeyElements.GLOBAL_REFERENCE,
                                                     local=False,
                                                     value='test',
                                                     id_type=model.KeyType.IRI),)))}
        )
        iec_expected = model.IEC61360ConceptDescription(
            identification=model.Identifier('test', model.IdentifierType.CUSTOM),
            preferred_name={'de': 'Test Specification', 'en-us': "TestSpecification"},
            data_type=IEC61360DataType.REAL_MEASURE
        )

        checker.raise_immediately = True
        with self.assertRaises(AssertionError) as cm:
            checker.check_concept_description_equal(iec, iec_expected)
        self.assertEqual("('Check failed: ValueList must contain 0 ValueReferencePairs', {'value': 1})",
                         str(cm.exception))

        with self.assertRaises(AssertionError) as cm:
            checker.check_concept_description_equal(iec_expected, iec)
        self.assertEqual("('Check failed: ValueList must contain 1 ValueReferencePairs', {'value': "
                         "{ValueReferencePair(value_type=<class 'str'>, value=test, "
                         "value_id=Reference(key=(Key(local=False, id_type=IRI, value=test),)))}})", str(cm.exception))
