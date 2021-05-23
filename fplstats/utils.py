import os
import json
from typing import Type, TypeVar
from pydantic import BaseModel


def read_file(file_path):
    """
    Reads a json file and returns the "raw" object, ie.
    a dict or a list.
    """
    obj = json.loads(open(os.path.join(file_path)).read())
    return obj


PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


def read_file_to_model(file_path, pydantic_model: Type[PydanticModel]) -> PydanticModel:
    """
    Reads a file and uses the loaded object to init and return
    an instance of the provided `pydantic_model`
    """
    obj = read_file(file_path)
    return pydantic_model.parse_obj(obj)
