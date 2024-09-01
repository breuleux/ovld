from typing import TYPE_CHECKING

from .core import (
    Ovld,
    OvldBase,
    OvldCall,
    OvldMC,
    extend_super,
    is_ovld,
    ovld,
)
from .dependent import (
    Dependent,
    DependentType,
    SingleParameterDependentType,
    dependent_check,
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
    StrictSubclass,
    class_check,
    parametrized_class_check,
)
from .utils import (
    BOOTSTRAP,
    MISSING,
    Named,
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
    "OvldCall",
    "OvldMC",
    "TypeMap",
    "extend_super",
    "is_ovld",
    "ovld",
    "Dependent",
    "SingleParameterDependentType",
    "DependentType",
    "dependent_check",
    "BOOTSTRAP",
    "MISSING",
    "Dataclass",
    "Named",
    "Deferred",
    "Exactly",
    "StrictSubclass",
    "class_check",
    "parametrized_class_check",
    "keyword_decorator",
    "call_next",
    "recurse",
]
