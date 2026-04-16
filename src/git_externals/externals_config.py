import os
from typing import TYPE_CHECKING

from .VCS import VCS

if TYPE_CHECKING:
    import typing
    try:
        from _typeshed import StrPath #, StrOrBytesPath
    except ImportError:
        StrPath: typing.TypeAlias = typing.Union[str,os.PathLike[str]]
    try:
        from typing import TypedDict
    except ImportError:
        pass
    else:
        class ExternalsConfig(TypedDict, total=False, extra_items=str):
            path: StrPath
            branch: str
            url: str
            vcs: VCS
            symlink: str
            cloneArgs: str
            updateArgs: str
