# Copyright (c) 2020 the Eclipse BaSyx Authors
#
# This program and the accompanying materials are made available under the terms of the MIT License, available in
# the LICENSE file of this project.
#
# SPDX-License-Identifier: MIT
"""
Module for creation of an example :class:`~aas.model.concept.ConceptDescription`
"""
import logging

from ... import model
from ._helper import AASDataChecker
from ...model.concept import *

logger = logging.getLogger(__name__)


def create_iec61360_concept_description() -> IEC61360ConceptDescription:
    """
    Creates a :class:`~aas.model.concept.ConceptDescription` after the IEC61360 standard

    :return: Example concept description
    """
    identification = 'http://acplt.org/DataSpecifciations/Example/Identification'
    return IEC61360ConceptDescription(
        id_=identification,
        preferred_name=model.LangStringSet({'de': 'Test Specification', 'en-US': "TestSpecification"}),
        data_type=IEC61360DataType.REAL_MEASURE,
        definition=model.LangStringSet({'de': 'Dies ist eine Data Specification für Testzwecke',
                                        'en-US': "This is a DataSpecification for testing purposes"}),
        short_name=model.LangStringSet({'de': 'Test Spec', 'en-US': "TestSpec"}),
        is_case_of={model.GlobalReference((model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE,
                                                     value='http://acplt.org/ReferenceElements/ConceptDescriptionX'),
                                           ))},
        id_short="TestSpec_01",
        category=None,
        description=None,
        parent=None,
        administration=model.AdministrativeInformation(version='0.9', revision='0'),
        unit="SpaceUnit",
        unit_id=model.GlobalReference((model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE,
                                                 value='http://acplt.org/Units/SpaceUnit'),)),
        source_of_definition="http://acplt.org/DataSpec/ExampleDef",
        symbol="SU",
        value_format=model.datatypes.String,
        value_list={
            model.ValueReferencePair(
                value_type=model.datatypes.String,
                value='exampleValue',
                value_id=model.GlobalReference((model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE,
                                                          value='http://acplt.org/ValueId/ExampleValueId'),)),),
            model.ValueReferencePair(
                value_type=model.datatypes.String,
                value='exampleValue2',
                value_id=model.GlobalReference((model.Key(type_=model.KeyTypes.GLOBAL_REFERENCE,
                                                          value='http://acplt.org/ValueId/ExampleValueId2'),)),)},
        value="TEST",
        value_id=None,
        level_types={IEC61360LevelType.MIN, IEC61360LevelType.MAX})


##############################################################################
# check functions for checking if an given object is the same as the example #
##############################################################################
def check_example_iec61360_concept_description(checker: AASDataChecker,
                                               concept_description: model.concept.IEC61360ConceptDescription) -> None:
    expected_concept_description = create_iec61360_concept_description()
    checker.check_concept_description_equal(concept_description, expected_concept_description)


def check_full_example(checker: AASDataChecker, obj_store: model.DictObjectStore) -> None:
    expected_data: model.DictObjectStore[model.Identifiable] = model.DictObjectStore()
    expected_data.add(create_iec61360_concept_description())
    checker.check_object_store(obj_store, expected_data)
