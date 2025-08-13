"""Utilities to deal with function signatures."""

import inspect
import itertools
import typing
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from functools import cached_property
from types import GenericAlias

from .types import normalize_type
from .utils import MISSING, subtler_type


class LazySignature(inspect.Signature):
    def __init__(self, ovld):
        super().__init__([])
        self.ovld = ovld

    def replace(
        self, *, parameters=inspect._void, return_annotation=inspect._void
    ):  # pragma: no cover
        if parameters is inspect._void:
            parameters = self.parameters.values()

        if return_annotation is inspect._void:
            return_annotation = self._return_annotation

        return inspect.Signature(parameters, return_annotation=return_annotation)

    @property
    def parameters(self):
        anal = self.ovld.argument_analysis
        parameters = []
        if anal.is_method:
            parameters.append(
                inspect.Parameter(
                    name="self",
                    kind=inspect._POSITIONAL_ONLY,
                )
            )
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._POSITIONAL_ONLY,
            )
            for p in anal.strict_positional_required
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._POSITIONAL_ONLY,
                default=MISSING,
            )
            for p in anal.strict_positional_optional
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._POSITIONAL_OR_KEYWORD,
            )
            for p in anal.positional_required
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._POSITIONAL_OR_KEYWORD,
                default=MISSING,
            )
            for p in anal.positional_optional
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._KEYWORD_ONLY,
            )
            for p in anal.keyword_required
        ]
        parameters += [
            inspect.Parameter(
                name=p,
                kind=inspect._KEYWORD_ONLY,
                default=MISSING,
            )
            for p in anal.keyword_optional
        ]
        return OrderedDict({p.name: p for p in parameters})


@dataclass(frozen=True)
class Arginfo:
    position: typing.Optional[int]
    name: typing.Optional[str]
    required: bool
    ann: type

    @cached_property
    def is_complex(self):
        return isinstance(self.ann, GenericAlias)

    @cached_property
    def canonical(self):
        return self.name if self.position is None else self.position


@dataclass(frozen=True)
class Signature:
    types: tuple
    return_type: type
    req_pos: int
    max_pos: int
    req_names: frozenset
    vararg: bool
    priority: float
    tiebreak: int = 0
    is_method: bool = False
    arginfo: list[Arginfo] = field(default_factory=list, hash=False, compare=False)

    @classmethod
    def extract(cls, fn, lcl={}):
        typelist = []
        sig = inspect.signature(fn)
        max_pos = 0
        req_pos = 0
        req_names = set()
        is_method = False

        arginfo = []
        for i, (name, param) in enumerate(sig.parameters.items()):
            if name == "self" or (name == "cls" and getattr(fn, "specializer", False)):
                if i != 0:  # pragma: no cover
                    raise Exception(
                        f"Argument name '{name}' marks a method and must always be in the first position."
                    )
                is_method = True
                continue
            pos = nm = None
            ann = normalize_type(param.annotation, fn, lcl)
            if param.kind is inspect._POSITIONAL_ONLY:
                pos = i - is_method
                typelist.append(ann)
                req_pos += param.default is inspect._empty
                max_pos += 1
            elif param.kind is inspect._POSITIONAL_OR_KEYWORD:
                pos = i - is_method
                nm = param.name
                typelist.append(ann)
                req_pos += param.default is inspect._empty
                max_pos += 1
            elif param.kind is inspect._KEYWORD_ONLY:
                nm = param.name
                typelist.append((param.name, ann))
                if param.default is inspect._empty:
                    req_names.add(param.name)
            elif param.kind is inspect._VAR_POSITIONAL:
                raise TypeError("ovld does not support *args")
            elif param.kind is inspect._VAR_KEYWORD:
                raise TypeError("ovld does not support **kwargs")
            arginfo.append(
                Arginfo(
                    position=pos,
                    name=nm,
                    required=param.default is inspect._empty,
                    ann=ann,
                )
            )

        return cls(
            types=tuple(typelist),
            return_type=normalize_type(sig.return_annotation, fn),
            req_pos=req_pos,
            max_pos=max_pos,
            req_names=frozenset(req_names),
            vararg=False,
            is_method=is_method,
            priority=None,
            arginfo=arginfo,
        )


class ArgumentAnalyzer:
    def __init__(self):
        self.name_to_positions = defaultdict(set)
        self.position_to_names = defaultdict(set)
        self.counts = defaultdict(lambda: [0, 0])
        self.complex_transforms = set()
        self.total = 0
        self.is_method = None
        self.done = False

    def add(self, sig):
        self.done = False
        self.complex_transforms.update(arg.canonical for arg in sig.arginfo if arg.is_complex)
        for arg in sig.arginfo:
            if arg.position is not None:
                self.position_to_names[arg.position].add(arg.name)
            if arg.name is not None:
                self.name_to_positions[arg.name].add(arg.canonical)

            cnt = self.counts[arg.canonical]
            cnt[0] += arg.required
            cnt[1] += 1

        self.total += 1

        if self.is_method is None:
            self.is_method = sig.is_method
        elif self.is_method != sig.is_method:  # pragma: no cover
            raise TypeError(
                "Some, but not all registered methods define `self`. It should be all or none."
            )

    def compile(self):
        if self.done:
            return
        for name, pos in self.name_to_positions.items():
            if len(pos) != 1:
                if all(isinstance(p, int) for p in pos):
                    raise TypeError(
                        f"Argument '{name}' is declared in different positions by different methods. The same argument name should always be in the same position unless it is strictly positional."
                    )
                else:
                    raise TypeError(
                        f"Argument '{name}' is declared in a positional and keyword setting by different methods. It should be either."
                    )

        p_to_n = [list(names) for _, names in sorted(self.position_to_names.items())]

        positional = list(
            itertools.takewhile(
                lambda names: len(names) == 1 and isinstance(names[0], str),
                reversed(p_to_n),
            )
        )
        positional.reverse()
        strict_positional = p_to_n[: len(p_to_n) - len(positional)]

        assert strict_positional + positional == p_to_n

        self.strict_positional_required = [
            f"ARG{pos + 1}"
            for pos, _ in enumerate(strict_positional)
            if self.counts[pos][0] == self.total
        ]
        self.strict_positional_optional = [
            f"ARG{pos + 1}"
            for pos, _ in enumerate(strict_positional)
            if self.counts[pos][0] != self.total
        ]

        self.positional_required = [
            names[0]
            for pos, names in enumerate(positional)
            if self.counts[pos + len(strict_positional)][0] == self.total
        ]
        self.positional_optional = [
            names[0]
            for pos, names in enumerate(positional)
            if self.counts[pos + len(strict_positional)][0] != self.total
        ]

        keywords = [
            name for _, (name,) in self.name_to_positions.items() if not isinstance(name, int)
        ]
        self.keyword_required = [
            name for name in keywords if self.counts[name][0] == self.total
        ]
        self.keyword_optional = [
            name for name in keywords if self.counts[name][0] != self.total
        ]
        self.done = True

    def lookup_for(self, key):
        return subtler_type if key in self.complex_transforms else type
