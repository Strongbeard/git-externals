from .VCS import VCS

class ExternalsConfig:
    def __init__(self):
        path: str
        branch: str
        url: str
        vcs: VCS
        symlink: str
        cloneArgs: str
        updateArgs: str
