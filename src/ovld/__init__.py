from typing import TYPE_CHECKING

from . import abc  # noqa: F401
from .codegen import Code, Def, Lambda, code_generator
from .core import (
    Ovld,
    OvldBase,
    OvldMC,
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
from .medley import (
    CodegenParameter,
    Medley,
)
from .mro import (
    TypeRelationship,
    subclasscheck,
    typeorder,
)
from .recode import (
    call_next,
    current_function,
    recurse,
    resolve,
)
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
    CodegenInProgress,
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
    "BOOTSTRAP",
    "MISSING",
    "Code",
    "CodegenInProgress",
    "CodegenParameter",
    "Dataclass",
    "Def",
    "Deferred",
    "Dependent",
    "DependentType",
    "Exactly",
    "Intersection",
    "Lambda",
    "Medley",
    "MultiTypeMap",
    "NameDatabase",
    "Named",
    "Ovld",
    "OvldBase",
    "OvldMC",
    "ParametrizedDependentType",
    "StrictSubclass",
    "TypeMap",
    "TypeRelationship",
    "__version__",
    "call_next",
    "class_check",
    "code_generator",
    "current_function",
    "dependent_check",
    "extend_super",
    "is_ovld",
    "keyword_decorator",
    "ovld",
    "parametrized_class_check",
    "recurse",
    "resolve",
    "subclasscheck",
    "typeorder",
]
