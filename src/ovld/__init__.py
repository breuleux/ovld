from typing import TYPE_CHECKING

from . import abc  # noqa: F401
from .codegen import CodeGen, code_generator
from .core import (
    Ovld,
    OvldBase,
    OvldMC,
    OvldPerInstanceBase,
    OvldPerInstanceMC,
    extend_super,
    is_ovld,
    ovld,
)
from .dependent import (
    Dependent,
    DependentType,
    ParametrizedDependentType,
    dependent_check,
)
from .mro import (
    TypeRelationship,
    subclasscheck,
    typeorder,
)
from .recode import call_next, recurse
from .typemap import (
    MultiTypeMap,
    TypeMap,
)
from .types import (
    Dataclass,
    Deferred,
    Exactly,
    Intersection,
    StrictSubclass,
    class_check,
    parametrized_class_check,
)
from .utils import (
    BOOTSTRAP,
    MISSING,
    Named,
    NameDatabase,
    keyword_decorator,
)
from .version import version as __version__

if TYPE_CHECKING:  # pragma: no cover
    # Pretend that @ovld is @typing.overload.
    # I can't believe this works.
    from typing import overload as ovld


__all__ = [
    "MultiTypeMap",
    "Ovld",
    "OvldBase",
    "OvldMC",
    "OvldPerInstanceMC",
    "OvldPerInstanceBase",
    "TypeMap",
    "extend_super",
    "is_ovld",
    "ovld",
    "CodeGen",
    "code_generator",
    "Dependent",
    "ParametrizedDependentType",
    "DependentType",
    "dependent_check",
    "BOOTSTRAP",
    "MISSING",
    "Dataclass",
    "Named",
    "NameDatabase",
    "Deferred",
    "Exactly",
    "Intersection",
    "StrictSubclass",
    "class_check",
    "subclasscheck",
    "typeorder",
    "TypeRelationship",
    "parametrized_class_check",
    "keyword_decorator",
    "call_next",
    "recurse",
    "__version__",
]
