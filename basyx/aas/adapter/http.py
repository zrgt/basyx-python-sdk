# Copyright 2020 PyI40AAS Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.


import abc
import enum
import io
import json
from lxml import etree  # type: ignore
import werkzeug.exceptions
import werkzeug.routing
import werkzeug.urls
from werkzeug.exceptions import BadRequest, Conflict, NotFound, UnprocessableEntity
from werkzeug.routing import MapAdapter, Rule, Submount
from werkzeug.wrappers import Request, Response

from aas import model
from .xml import XMLConstructables, read_aas_xml_element, xml_serialization
from .json import StrippedAASToJsonEncoder, StrictStrippedAASFromJsonDecoder
from ._generic import IDENTIFIER_TYPES, IDENTIFIER_TYPES_INVERSE

from typing import Callable, Dict, Iterable, List, Optional, Tuple, Type, TypeVar, Union


@enum.unique
class ErrorType(enum.Enum):
    UNSPECIFIED = enum.auto()
    DEBUG = enum.auto()
    INFORMATION = enum.auto()
    WARNING = enum.auto()
    ERROR = enum.auto()
    FATAL = enum.auto()
    EXCEPTION = enum.auto()

    def __str__(self):
        return self.name.capitalize()


class Error:
    def __init__(self, code: str, text: str, type_: ErrorType = ErrorType.UNSPECIFIED):
        self.type = type_
        self.code = code
        self.text = text


ResultData = Union[object, Tuple[object, ...]]


class Result:
    def __init__(self, data: Optional[Union[ResultData, Error]]):
        # the following is True when data is None, which is the expected behavior
        self.success: bool = not isinstance(data, Error)
        self.data: Optional[ResultData] = None
        self.error: Optional[Error] = None
        if isinstance(data, Error):
            self.error = data
        else:
            self.data = data


class ResultToJsonEncoder(StrippedAASToJsonEncoder):
    @classmethod
    def _result_to_json(cls, result: Result) -> Dict[str, object]:
        return {
            "success": result.success,
            "error": result.error,
            "data": result.data
        }

    @classmethod
    def _error_to_json(cls, error: Error) -> Dict[str, object]:
        return {
            "type": error.type,
            "code": error.code,
            "text": error.text
        }

    def default(self, obj: object) -> object:
        if isinstance(obj, Result):
            return self._result_to_json(obj)
        if isinstance(obj, Error):
            return self._error_to_json(obj)
        if isinstance(obj, ErrorType):
            return str(obj)
        return super().default(obj)


class APIResponse(abc.ABC, Response):
    @abc.abstractmethod
    def __init__(self, result: Result, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data = self.serialize(result)

    @abc.abstractmethod
    def serialize(self, result: Result) -> str:
        pass


class JsonResponse(APIResponse):
    def __init__(self, *args, content_type="application/json", **kwargs):
        super().__init__(*args, **kwargs, content_type=content_type)

    def serialize(self, result: Result) -> str:
        return json.dumps(result, cls=ResultToJsonEncoder, separators=(",", ":"))


class XmlResponse(APIResponse):
    def __init__(self, *args, content_type="application/xml", **kwargs):
        super().__init__(*args, **kwargs, content_type=content_type)

    def serialize(self, result: Result) -> str:
        result_elem = result_to_xml(result, nsmap=xml_serialization.NS_MAP)
        etree.cleanup_namespaces(result_elem)
        return etree.tostring(result_elem, xml_declaration=True, encoding="utf-8")


class XmlResponseAlt(XmlResponse):
    def __init__(self, *args, content_type="text/xml", **kwargs):
        super().__init__(*args, **kwargs, content_type=content_type)


def result_to_xml(result: Result, **kwargs) -> etree.Element:
    result_elem = etree.Element("result", **kwargs)
    success_elem = etree.Element("success")
    success_elem.text = xml_serialization.boolean_to_xml(result.success)
    if result.error is None:
        error_elem = etree.Element("error")
    else:
        error_elem = error_to_xml(result.error)
    data_elem = etree.Element("data")
    if result.data is not None:
        for element in result_data_to_xml(result.data):
            data_elem.append(element)
    result_elem.append(success_elem)
    result_elem.append(error_elem)
    result_elem.append(data_elem)
    return result_elem


def error_to_xml(error: Error) -> etree.Element:
    error_elem = etree.Element("error")
    type_elem = etree.Element("type")
    type_elem.text = str(error.type)
    code_elem = etree.Element("code")
    code_elem.text = error.code
    text_elem = etree.Element("text")
    text_elem.text = error.text
    error_elem.append(type_elem)
    error_elem.append(code_elem)
    error_elem.append(text_elem)
    return error_elem


def result_data_to_xml(data: ResultData) -> Iterable[etree.Element]:
    # for xml we can just append multiple elements to the data element
    # so multiple elements will be handled the same as a single element
    if not isinstance(data, tuple):
        data = (data,)
    for obj in data:
        yield aas_object_to_xml(obj)


def aas_object_to_xml(obj: object) -> etree.Element:
    # TODO: a similar function should be implemented in the xml serialization
    if isinstance(obj, model.AssetAdministrationShell):
        return xml_serialization.asset_administration_shell_to_xml(obj)
    if isinstance(obj, model.Reference):
        return xml_serialization.reference_to_xml(obj)
    if isinstance(obj, model.View):
        return xml_serialization.view_to_xml(obj)
    if isinstance(obj, model.Submodel):
        return xml_serialization.submodel_to_xml(obj)
    # TODO: xml serialization needs a constraint_to_xml() function
    if isinstance(obj, model.Qualifier):
        return xml_serialization.qualifier_to_xml(obj)
    if isinstance(obj, model.SubmodelElement):
        return xml_serialization.submodel_element_to_xml(obj)
    raise TypeError(f"Serializing {type(obj).__name__} to XML is not supported!")


def get_response_type(request: Request) -> Type[APIResponse]:
    response_types: Dict[str, Type[APIResponse]] = {
        "application/json": JsonResponse,
        "application/xml": XmlResponse,
        "text/xml": XmlResponseAlt
    }
    if len(request.accept_mimetypes) == 0:
        return JsonResponse
    mime_type = request.accept_mimetypes.best_match(response_types)
    if mime_type is None:
        raise werkzeug.exceptions.NotAcceptable(f"This server supports the following content types: "
                                                + ", ".join(response_types.keys()))
    return response_types[mime_type]


def http_exception_to_response(exception: werkzeug.exceptions.HTTPException, response_type: Type[APIResponse]) \
        -> APIResponse:
    headers = exception.get_headers()
    location = exception.get_response().location
    if location is not None:
        headers.append(("Location", location))
    if exception.code and exception.code >= 400:
        error = Error(type(exception).__name__, exception.description if exception.description is not None else "",
                      ErrorType.ERROR)
        result = Result(error)
    else:
        result = Result(None)
    return response_type(result, status=exception.code, headers=headers)


T = TypeVar("T")


def parse_request_body(request: Request, expect_type: Type[T]) -> T:
    """
    TODO: werkzeug documentation recommends checking the content length before retrieving the body to prevent
          running out of memory. but it doesn't state how to check the content length
          also: what would be a reasonable maximum content length? the request body isn't limited by the xml/json schema
        In the meeting (25.11.2020) we discussed, this may refer to a reverse proxy in front of this WSGI app,
        which should limit the maximum content length.
    """
    type_constructables_map = {
        model.AASReference: XMLConstructables.AAS_REFERENCE,
        model.View: XMLConstructables.VIEW,
        model.Qualifier: XMLConstructables.QUALIFIER,
        model.SubmodelElement: XMLConstructables.SUBMODEL_ELEMENT
    }

    if expect_type not in type_constructables_map:
        raise TypeError(f"Parsing {expect_type} is not supported!")

    valid_content_types = ("application/json", "application/xml", "text/xml")

    if request.mimetype not in valid_content_types:
        raise werkzeug.exceptions.UnsupportedMediaType(f"Invalid content-type: {request.mimetype}! Supported types: "
                                                       + ", ".join(valid_content_types))

    try:
        if request.mimetype == "application/json":
            rv = json.loads(request.get_data(), cls=StrictStrippedAASFromJsonDecoder)
            # TODO: the following is ugly, but necessary because references aren't self-identified objects
            #  in the json schema
            # TODO: json deserialization will always create an AASReference[Submodel], xml deserialization determines
            #  that automatically
            if expect_type is model.AASReference:
                rv = StrictStrippedAASFromJsonDecoder._construct_aas_reference(rv, model.Submodel)
        else:
            try:
                xml_data = io.BytesIO(request.get_data())
                rv = read_aas_xml_element(xml_data, type_constructables_map[expect_type], stripped=True, failsafe=False)
            except (KeyError, ValueError) as e:
                # xml deserialization creates an error chain. since we only return one error, return the root cause
                f: BaseException = e
                while f.__cause__ is not None:
                    f = f.__cause__
                raise f from e
    except (KeyError, ValueError, TypeError, json.JSONDecodeError, etree.XMLSyntaxError, model.AASConstraintViolation) \
            as e:
        raise UnprocessableEntity(str(e)) from e

    if not isinstance(rv, expect_type):
        raise UnprocessableEntity(f"Object {rv!r} is not of type {expect_type.__name__}!")
    return rv


def identifier_uri_encode(id_: model.Identifier) -> str:
    return IDENTIFIER_TYPES[id_.id_type] + ":" + werkzeug.urls.url_quote(id_.id, safe="")


def identifier_uri_decode(id_str: str) -> model.Identifier:
    try:
        id_type_str, id_ = id_str.split(":", 1)
    except ValueError:
        raise ValueError(f"Identifier '{id_str}' is not of format 'ID_TYPE:ID'")
    id_type = IDENTIFIER_TYPES_INVERSE.get(id_type_str)
    if id_type is None:
        raise ValueError(f"IdentifierType '{id_type_str}' is invalid")
    return model.Identifier(werkzeug.urls.url_unquote(id_), id_type)


class IdentifierConverter(werkzeug.routing.UnicodeConverter):
    def to_url(self, value: model.Identifier) -> str:
        return super().to_url(identifier_uri_encode(value))

    def to_python(self, value: str) -> model.Identifier:
        try:
            return identifier_uri_decode(super().to_python(value))
        except ValueError as e:
            raise BadRequest(str(e)) from e


def validate_id_short(id_short: str) -> bool:
    try:
        model.MultiLanguageProperty(id_short)
    except ValueError:
        return False
    return True


class IdShortPathConverter(werkzeug.routing.PathConverter):
    id_short_prefix = "!"

    def to_url(self, value: List[str]) -> str:
        for id_short in value:
            if not validate_id_short(id_short):
                raise ValueError(f"{id_short} is not a valid id_short!")
        return "/".join([self.id_short_prefix + id_short for id_short in value])

    def to_python(self, value: str) -> List[str]:
        id_shorts = super().to_python(value).split("/")
        for idx, id_short in enumerate(id_shorts):
            if not id_short.startswith(self.id_short_prefix):
                raise werkzeug.routing.ValidationError
            id_short = id_short[1:]
            if not validate_id_short(id_short):
                raise BadRequest(f"{id_short} is not a valid id_short!")
            id_shorts[idx] = id_short
        return id_shorts


class WSGIApp:
    def __init__(self, object_store: model.AbstractObjectStore):
        self.object_store: model.AbstractObjectStore = object_store
        self.url_map = werkzeug.routing.Map([
            Submount("/api/v1", [
                Submount("/aas/<identifier:aas_id>", [
                    Rule("/", methods=["GET"], endpoint=self.get_aas),
                    Submount("/submodels", [
                        Rule("/", methods=["GET"], endpoint=self.get_aas_submodel_refs),
                        Rule("/", methods=["POST"], endpoint=self.post_aas_submodel_refs),
                        Rule("/<identifier:sm_id>/", methods=["GET"],
                             endpoint=self.get_aas_submodel_refs_specific),
                        Rule("/<identifier:sm_id>/", methods=["DELETE"],
                             endpoint=self.delete_aas_submodel_refs_specific)
                    ]),
                    Submount("/views", [
                        Rule("/", methods=["GET"], endpoint=self.get_aas_views),
                        Rule("/", methods=["POST"], endpoint=self.post_aas_views),
                        Rule("/<string:view_idshort>/", methods=["GET"],
                             endpoint=self.get_aas_views_specific),
                        Rule("/<string:view_idshort>/", methods=["PUT"],
                             endpoint=self.put_aas_views_specific),
                        Rule("/<string:view_idshort>/", methods=["DELETE"],
                             endpoint=self.delete_aas_views_specific)
                    ])
                ]),
                Submount("/submodels/<identifier:submodel_id>", [
                    Rule("/", methods=["GET"], endpoint=self.get_submodel),
                    Rule("/submodelElements/", methods=["GET"], endpoint=self.get_submodel_submodel_elements),
                    Rule("/submodelElements/", methods=["POST"], endpoint=self.post_submodel_submodel_elements),
                    Submount("/<id_short_path:id_shorts>", [
                        Rule("/", methods=["GET"],
                             endpoint=self.get_submodel_submodel_elements_specific_nested),
                        Rule("/", methods=["PUT"],
                             endpoint=self.put_submodel_submodel_elements_specific_nested),
                        Rule("/", methods=["DELETE"],
                             endpoint=self.delete_submodel_submodel_elements_specific_nested),
                        # TODO: remove the following type: ignore comments when mypy supports abstract types for Type[T]
                        # see https://github.com/python/mypy/issues/5374
                        Rule("/values/", methods=["GET"],
                             endpoint=self.factory_get_submodel_submodel_elements_nested_attr(
                                 model.SubmodelElementCollection, "value")),  # type: ignore
                        Rule("/values/", methods=["POST"],
                             endpoint=self.factory_post_submodel_submodel_elements_nested_attr(
                                 model.SubmodelElementCollection, "value")),  # type: ignore
                        Rule("/annotations/", methods=["GET"],
                             endpoint=self.factory_get_submodel_submodel_elements_nested_attr(
                                 model.AnnotatedRelationshipElement, "annotation")),
                        Rule("/annotations/", methods=["POST"],
                             endpoint=self.factory_post_submodel_submodel_elements_nested_attr(
                                 model.AnnotatedRelationshipElement, "annotation",
                                 request_body_type=model.DataElement)),  # type: ignore
                        Rule("/statements/", methods=["GET"],
                             endpoint=self.factory_get_submodel_submodel_elements_nested_attr(model.Entity,
                                                                                              "statement")),
                        Rule("/statements/", methods=["POST"],
                             endpoint=self.factory_post_submodel_submodel_elements_nested_attr(model.Entity,
                                                                                               "statement")),
                        Submount("/constraints", [
                            Rule("/", methods=["GET"], endpoint=self.get_submodel_submodel_element_constraints),
                            Rule("/", methods=["POST"], endpoint=self.post_submodel_submodel_element_constraints),
                            Rule("/<path:qualifier_type>/", methods=["GET"],
                                 endpoint=self.get_submodel_submodel_element_constraints),
                            Rule("/<path:qualifier_type>/", methods=["PUT"],
                                 endpoint=self.put_submodel_submodel_element_constraints),
                            Rule("/<path:qualifier_type>/", methods=["DELETE"],
                                 endpoint=self.delete_submodel_submodel_element_constraints),
                        ])
                    ]),
                    Submount("/constraints", [
                        Rule("/", methods=["GET"], endpoint=self.get_submodel_submodel_element_constraints),
                        Rule("/", methods=["POST"], endpoint=self.post_submodel_submodel_element_constraints),
                        Rule("/<path:qualifier_type>/", methods=["GET"],
                             endpoint=self.get_submodel_submodel_element_constraints),
                        Rule("/<path:qualifier_type>/", methods=["PUT"],
                             endpoint=self.put_submodel_submodel_element_constraints),
                        Rule("/<path:qualifier_type>/", methods=["DELETE"],
                             endpoint=self.delete_submodel_submodel_element_constraints),
                    ])
                ])
            ])
        ], converters={
            "identifier": IdentifierConverter,
            "id_short_path": IdShortPathConverter
        })

    def __call__(self, environ, start_response):
        response = self.handle_request(Request(environ))
        return response(environ, start_response)

    def _get_obj_ts(self, identifier: model.Identifier, type_: Type[model.provider._IT]) -> model.provider._IT:
        identifiable = self.object_store.get(identifier)
        if not isinstance(identifiable, type_):
            raise NotFound(f"No {type_.__name__} with {identifier} found!")
        return identifiable

    def _resolve_reference(self, reference: model.AASReference[model.base._RT]) -> model.base._RT:
        try:
            return reference.resolve(self.object_store)
        except (KeyError, TypeError, model.UnexpectedTypeError) as e:
            raise werkzeug.exceptions.InternalServerError(str(e)) from e

    @classmethod
    def _get_aas_submodel_reference_by_submodel_identifier(cls, aas: model.AssetAdministrationShell,
                                                           sm_identifier: model.Identifier) \
            -> model.AASReference[model.Submodel]:
        for sm_ref in aas.submodel:
            if sm_ref.get_identifier() == sm_identifier:
                return sm_ref
        raise NotFound(f"No reference to submodel with {sm_identifier} found!")

    @classmethod
    def _get_nested_submodel_element(cls, namespace: model.UniqueIdShortNamespace, id_shorts: List[str]) \
            -> model.SubmodelElement:
        current_namespace: Union[model.UniqueIdShortNamespace, model.SubmodelElement] = namespace
        for id_short in id_shorts:
            current_namespace = cls._expect_namespace(current_namespace, id_short)
            next_obj = cls._namespace_submodel_element_op(current_namespace, current_namespace.get_referable, id_short)
            if not isinstance(next_obj, model.SubmodelElement):
                raise werkzeug.exceptions.InternalServerError(f"{next_obj}, child of {current_namespace!r}, "
                                                              f"is not a submodel element!")
            current_namespace = next_obj
        if not isinstance(current_namespace, model.SubmodelElement):
            raise ValueError("No id_shorts specified!")
        return current_namespace

    @classmethod
    def _get_submodel_or_nested_submodel_element(cls, submodel: model.Submodel, id_shorts: List[str]) \
            -> Union[model.Submodel, model.SubmodelElement]:
        try:
            return cls._get_nested_submodel_element(submodel, id_shorts)
        except ValueError:
            return submodel

    @classmethod
    def _expect_namespace(cls, obj: object, needle: str) -> model.UniqueIdShortNamespace:
        if not isinstance(obj, model.UniqueIdShortNamespace):
            raise BadRequest(f"{obj!r} is not a namespace, can't locate {needle}!")
        return obj

    @classmethod
    def _namespace_submodel_element_op(cls, namespace: model.UniqueIdShortNamespace, op: Callable[[str], T], arg: str) \
            -> T:
        try:
            return op(arg)
        except KeyError as e:
            raise NotFound(f"Submodel element with id_short {arg} not found in {namespace!r}") from e

    def handle_request(self, request: Request):
        map_adapter: MapAdapter = self.url_map.bind_to_environ(request.environ)
        try:
            endpoint, values = map_adapter.match()
            if endpoint is None:
                raise werkzeug.exceptions.NotImplemented("This route is not yet implemented.")
            return endpoint(request, values, map_adapter=map_adapter)
        # any raised error that leaves this function will cause a 500 internal server error
        # so catch raised http exceptions and return them
        except werkzeug.exceptions.NotAcceptable as e:
            return e
        except werkzeug.exceptions.HTTPException as e:
            try:
                # get_response_type() may raise a NotAcceptable error, so we have to handle that
                return http_exception_to_response(e, get_response_type(request))
            except werkzeug.exceptions.NotAcceptable as e:
                return e

    # --------- AAS ROUTES ---------
    def get_aas(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        aas = self._get_obj_ts(url_args["aas_id"], model.AssetAdministrationShell)
        aas.update()
        return response_t(Result(aas))

    def get_aas_submodel_refs(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        aas = self._get_obj_ts(url_args["aas_id"], model.AssetAdministrationShell)
        aas.update()
        return response_t(Result(tuple(aas.submodel)))

    def post_aas_submodel_refs(self, request: Request, url_args: Dict, map_adapter: MapAdapter) -> Response:
        response_t = get_response_type(request)
        aas_identifier = url_args["aas_id"]
        aas = self._get_obj_ts(aas_identifier, model.AssetAdministrationShell)
        aas.update()
        sm_ref = parse_request_body(request, model.AASReference)
        # to give a location header in the response we have to be able to get the submodel identifier from the reference
        try:
            submodel_identifier = sm_ref.get_identifier()
        except ValueError as e:
            raise UnprocessableEntity(f"Can't resolve submodel identifier for given reference!") from e
        if sm_ref in aas.submodel:
            raise Conflict(f"{sm_ref!r} already exists!")
        aas.submodel.add(sm_ref)
        aas.commit()
        created_resource_url = map_adapter.build(self.get_aas_submodel_refs_specific, {
            "aas_id": aas_identifier,
            "sm_id": submodel_identifier
        }, force_external=True)
        return response_t(Result(sm_ref), status=201, headers={"Location": created_resource_url})

    def get_aas_submodel_refs_specific(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        aas = self._get_obj_ts(url_args["aas_id"], model.AssetAdministrationShell)
        aas.update()
        sm_ref = self._get_aas_submodel_reference_by_submodel_identifier(aas, url_args["sm_id"])
        return response_t(Result(sm_ref))

    def delete_aas_submodel_refs_specific(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        aas = self._get_obj_ts(url_args["aas_id"], model.AssetAdministrationShell)
        aas.update()
        sm_ref = self._get_aas_submodel_reference_by_submodel_identifier(aas, url_args["sm_id"])
        # use remove(sm_ref) because it raises a KeyError if sm_ref is not present
        # sm_ref must be present because _get_aas_submodel_reference_by_submodel_identifier() found it there
        # so if sm_ref is not in aas.submodel, this implementation is bugged and the raised KeyError will result
        # in an InternalServerError
        aas.submodel.remove(sm_ref)
        aas.commit()
        return response_t(Result(None))

    def get_aas_views(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        aas = self._get_obj_ts(url_args["aas_id"], model.AssetAdministrationShell)
        aas.update()
        return response_t(Result(tuple(aas.view)))

    def post_aas_views(self, request: Request, url_args: Dict, map_adapter: MapAdapter) -> Response:
        response_t = get_response_type(request)
        aas_identifier = url_args["aas_id"]
        aas = self._get_obj_ts(aas_identifier, model.AssetAdministrationShell)
        aas.update()
        view = parse_request_body(request, model.View)
        if ("id_short", view.id_short) in aas.view:
            raise Conflict(f"View with id_short {view.id_short} already exists!")
        aas.view.add(view)
        aas.commit()
        created_resource_url = map_adapter.build(self.get_aas_views_specific, {
            "aas_id": aas_identifier,
            "view_idshort": view.id_short
        }, force_external=True)
        return response_t(Result(view), status=201, headers={"Location": created_resource_url})

    def get_aas_views_specific(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        aas = self._get_obj_ts(url_args["aas_id"], model.AssetAdministrationShell)
        aas.update()
        view_idshort = url_args["view_idshort"]
        view = aas.view.get("id_short", view_idshort)
        if view is None:
            raise NotFound(f"No view with id_short {view_idshort} found!")
        return response_t(Result(view))

    def put_aas_views_specific(self, request: Request, url_args: Dict, map_adapter: MapAdapter) -> Response:
        response_t = get_response_type(request)
        aas_identifier = url_args["aas_id"]
        aas = self._get_obj_ts(aas_identifier, model.AssetAdministrationShell)
        aas.update()
        view_idshort = url_args["view_idshort"]
        view = aas.view.get("id_short", view_idshort)
        if view is None:
            raise NotFound(f"No view with id_short {view_idshort} found!")
        new_view = parse_request_body(request, model.View)
        # TODO: raise conflict if the following fails
        view.update_from(new_view)
        view.commit()
        if view_idshort.upper() != view.id_short.upper():
            created_resource_url = map_adapter.build(self.put_aas_views_specific, {
                "aas_id": aas_identifier,
                "view_idshort": view.id_short
            }, force_external=True)
            return response_t(Result(view), status=201, headers={"Location": created_resource_url})
        return response_t(Result(view))

    def delete_aas_views_specific(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        aas = self._get_obj_ts(url_args["aas_id"], model.AssetAdministrationShell)
        aas.update()
        view_idshort = url_args["view_idshort"]
        if ("id_short", view_idshort) not in aas.view:
            raise NotFound(f"No view with id_short {view_idshort} found!")
        aas.view.remove(view_idshort)
        return response_t(Result(None))

    # --------- SUBMODEL ROUTES ---------
    def get_submodel(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        submodel = self._get_obj_ts(url_args["submodel_id"], model.Submodel)
        submodel.update()
        return response_t(Result(submodel))

    def get_submodel_submodel_elements(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        submodel = self._get_obj_ts(url_args["submodel_id"], model.Submodel)
        submodel.update()
        return response_t(Result(tuple(submodel.submodel_element)))

    def post_submodel_submodel_elements(self, request: Request, url_args: Dict, map_adapter: MapAdapter) -> Response:
        response_t = get_response_type(request)
        submodel_identifier = url_args["submodel_id"]
        submodel = self._get_obj_ts(submodel_identifier, model.Submodel)
        submodel.update()
        # TODO: remove the following type: ignore comments when mypy supports abstract types for Type[T]
        # see https://github.com/python/mypy/issues/5374
        submodel_element = parse_request_body(request, model.SubmodelElement)  # type: ignore
        if ("id_short", submodel_element.id_short) in submodel.submodel_element:
            raise Conflict(f"Submodel element with id_short {submodel_element.id_short} already exists!")
        submodel.submodel_element.add(submodel_element)
        submodel.commit()
        created_resource_url = map_adapter.build(self.get_submodel_submodel_elements_specific_nested, {
            "submodel_id": submodel_identifier,
            "id_shorts": [submodel_element.id_short]
        }, force_external=True)
        return response_t(Result(submodel_element), status=201, headers={"Location": created_resource_url})

    def get_submodel_submodel_elements_specific_nested(self, request: Request, url_args: Dict, **_kwargs) -> Response:
        response_t = get_response_type(request)
        submodel = self._get_obj_ts(url_args["submodel_id"], model.Submodel)
        submodel.update()
        submodel_element = self._get_nested_submodel_element(submodel, url_args["id_shorts"])
        return response_t(Result(submodel_element))

    def put_submodel_submodel_elements_specific_nested(self, request: Request, url_args: Dict,
                                                       map_adapter: MapAdapter) -> Response:
        response_t = get_response_type(request)
        submodel_identifier = url_args["submodel_id"]
        submodel = self._get_obj_ts(submodel_identifier, model.Submodel)
        submodel.update()
        id_short_path = url_args["id_shorts"]
        submodel_element = self._get_nested_submodel_element(submodel, id_short_path)
        current_id_short = submodel_element.id_short
        # TODO: remove the following type: ignore comments when mypy supports abstract types for Type[T]
        # see https://github.com/python/mypy/issues/5374
        new_submodel_element = parse_request_body(request, model.SubmodelElement)  # type: ignore
        if type(submodel_element) is not type(new_submodel_element):
            raise UnprocessableEntity(f"Type of new submodel element {new_submodel_element} doesn't not match "
                                      f"the current submodel element {submodel_element}")
        # TODO: raise conflict if the following fails
        submodel_element.update_from(new_submodel_element)
        submodel_element.commit()
        if new_submodel_element.id_short.upper() != current_id_short.upper():
            created_resource_url = map_adapter.build(self.put_submodel_submodel_elements_specific_nested, {
                "submodel_id": submodel_identifier,
                "id_shorts": id_short_path[:-1] + [submodel_element.id_short]
            }, force_external=True)
            return response_t(Result(submodel_element), status=201, headers={"Location": created_resource_url})
        return response_t(Result(submodel_element))

    def delete_submodel_submodel_elements_specific_nested(self, request: Request, url_args: Dict, **_kwargs) \
            -> Response:
        response_t = get_response_type(request)
        submodel = self._get_obj_ts(url_args["submodel_id"], model.Submodel)
        submodel.update()
        id_shorts: List[str] = url_args["id_shorts"]
        parent: model.UniqueIdShortNamespace = submodel
        if len(id_shorts) > 1:
            parent = self._expect_namespace(
                self._get_nested_submodel_element(submodel, id_shorts[:-1]),
                id_shorts[-1]
            )
        self._namespace_submodel_element_op(parent, parent.remove_referable, id_shorts[-1])
        return response_t(Result(None))

    def get_submodel_submodel_element_constraints(self, request: Request, url_args: Dict, **_kwargs) \
            -> Response:
        response_t = get_response_type(request)
        submodel = self._get_obj_ts(url_args["submodel_id"], model.Submodel)
        submodel.update()
        sm_or_se = self._get_submodel_or_nested_submodel_element(submodel, url_args.get("id_shorts", []))
        qualifier_type = url_args.get("qualifier_type")
        if qualifier_type is None:
            return response_t(Result(tuple(sm_or_se.qualifier)))
        try:
            return response_t(Result(sm_or_se.get_qualifier_by_type(qualifier_type)))
        except KeyError:
            raise NotFound(f"No constraint with type {qualifier_type} found in {sm_or_se}")

    def post_submodel_submodel_element_constraints(self, request: Request, url_args: Dict, map_adapter: MapAdapter) \
            -> Response:
        response_t = get_response_type(request)
        submodel_identifier = url_args["submodel_id"]
        submodel = self._get_obj_ts(submodel_identifier, model.Submodel)
        submodel.update()
        id_shorts: List[str] = url_args.get("id_shorts", [])
        sm_or_se = self._get_submodel_or_nested_submodel_element(submodel, id_shorts)
        qualifier = parse_request_body(request, model.Qualifier)
        if ("type", qualifier.type) in sm_or_se.qualifier:
            raise Conflict(f"Qualifier with type {qualifier.type} already exists!")
        sm_or_se.qualifier.add(qualifier)
        sm_or_se.commit()
        created_resource_url = map_adapter.build(self.get_submodel_submodel_element_constraints, {
            "submodel_id": submodel_identifier,
            "id_shorts": id_shorts if len(id_shorts) != 0 else None,
            "qualifier_type": qualifier.type
        }, force_external=True)
        return response_t(Result(qualifier), status=201, headers={"Location": created_resource_url})

    def put_submodel_submodel_element_constraints(self, request: Request, url_args: Dict, map_adapter: MapAdapter) \
            -> Response:
        response_t = get_response_type(request)
        submodel_identifier = url_args["submodel_id"]
        submodel = self._get_obj_ts(submodel_identifier, model.Submodel)
        submodel.update()
        id_shorts: List[str] = url_args.get("id_shorts", [])
        sm_or_se = self._get_submodel_or_nested_submodel_element(submodel, id_shorts)
        new_qualifier = parse_request_body(request, model.Qualifier)
        qualifier_type = url_args["qualifier_type"]
        try:
            qualifier = sm_or_se.get_qualifier_by_type(qualifier_type)
        except KeyError:
            raise NotFound(f"No constraint with type {qualifier_type} found in {sm_or_se}")
        if type(qualifier) is not type(new_qualifier):
            raise UnprocessableEntity(f"Type of new qualifier {new_qualifier} doesn't not match "
                                      f"the current submodel element {qualifier}")
        qualifier_type_changed = qualifier_type != new_qualifier.type
        if qualifier_type_changed and ("type", new_qualifier.type) in sm_or_se.qualifier:
            raise Conflict(f"A qualifier of type {new_qualifier.type} already exists for {sm_or_se}")
        sm_or_se.remove_qualifier_by_type(qualifier.type)
        sm_or_se.qualifier.add(new_qualifier)
        sm_or_se.commit()
        if qualifier_type_changed:
            created_resource_url = map_adapter.build(self.get_submodel_submodel_element_constraints, {
                "submodel_id": submodel_identifier,
                "id_shorts": id_shorts if len(id_shorts) != 0 else None,
                "qualifier_type": new_qualifier.type
            }, force_external=True)
            return response_t(Result(new_qualifier), status=201, headers={"Location": created_resource_url})
        return response_t(Result(new_qualifier))

    def delete_submodel_submodel_element_constraints(self, request: Request, url_args: Dict, **_kwargs) \
            -> Response:
        response_t = get_response_type(request)
        submodel_identifier = url_args["submodel_id"]
        submodel = self._get_obj_ts(submodel_identifier, model.Submodel)
        submodel.update()
        id_shorts: List[str] = url_args.get("id_shorts", [])
        sm_or_se = self._get_submodel_or_nested_submodel_element(submodel, id_shorts)
        qualifier_type = url_args["qualifier_type"]
        try:
            sm_or_se.remove_qualifier_by_type(qualifier_type)
        except KeyError:
            raise NotFound(f"No constraint with type {qualifier_type} found in {sm_or_se}")
        sm_or_se.commit()
        return response_t(Result(None))

    # --------- SUBMODEL ROUTE FACTORIES ---------
    def factory_get_submodel_submodel_elements_nested_attr(self, type_: Type[model.Referable], attr: str) \
            -> Callable[[Request, Dict], Response]:
        def route(request: Request, url_args: Dict, **_kwargs) -> Response:
            response_t = get_response_type(request)
            submodel = self._get_obj_ts(url_args["submodel_id"], model.Submodel)
            submodel.update()
            submodel_element = self._get_nested_submodel_element(submodel, url_args["id_shorts"])
            if not isinstance(submodel_element, type_):
                raise UnprocessableEntity(f"Submodel element {submodel_element} is not a(n) {type_.__name__}!")
            return response_t(Result(tuple(getattr(submodel_element, attr))))
        return route

    def factory_post_submodel_submodel_elements_nested_attr(self, type_: Type[model.Referable], attr: str,
                                                            request_body_type: Type[model.SubmodelElement]
                                                            = model.SubmodelElement) \
            -> Callable[[Request, Dict, MapAdapter], Response]:
        def route(request: Request, url_args: Dict, map_adapter: MapAdapter) -> Response:
            response_t = get_response_type(request)
            submodel_identifier = url_args["submodel_id"]
            submodel = self._get_obj_ts(submodel_identifier, model.Submodel)
            submodel.update()
            id_shorts = url_args["id_shorts"]
            submodel_element = self._get_nested_submodel_element(submodel, id_shorts)
            if not isinstance(submodel_element, type_):
                raise UnprocessableEntity(f"Submodel element {submodel_element} is not a(n) {type_.__name__}!")
            new_submodel_element = parse_request_body(request, request_body_type)
            if ("id_short", new_submodel_element.id_short) in getattr(submodel_element, attr):
                raise Conflict(f"Submodel element with id_short {new_submodel_element.id_short} already exists!")
            getattr(submodel_element, attr).add(new_submodel_element)
            submodel_element.commit()
            created_resource_url = map_adapter.build(self.get_submodel_submodel_elements_specific_nested, {
                "submodel_id": submodel_identifier,
                "id_shorts": id_shorts + [new_submodel_element.id_short]
            }, force_external=True)
            return response_t(Result(new_submodel_element), status=201, headers={"Location": created_resource_url})
        return route


if __name__ == "__main__":
    from werkzeug.serving import run_simple
    # use example_aas_missing_attributes, because the AAS from example_aas has no views
    from aas.examples.data.example_aas_missing_attributes import create_full_example
    run_simple("localhost", 8080, WSGIApp(create_full_example()), use_debugger=True, use_reloader=True)
