""" Implementation of the tsrc Workspace: a collection of git repositories
"""

from typing import Iterable, List, Tuple, Optional

import cli_ui as ui
from path import Path
import ruamel.yaml

import tsrc
import tsrc.executor
import tsrc.git

from .cloner import Cloner
from .copier import FileCopier
from .syncer import Syncer
from .remote_setter import RemoteSetter
from .local_manifest import LocalManifest
from .config import WorkspaceConfig


def copy_cfg_path_if_needed(root_path: Path) -> None:
    """ Backward compatibility layer with tsrc < 1.0 """
    old_path = root_path / ".tsrc/manifest.yml"
    new_path = root_path / ".tsrc/config.yml"
    if old_path.exists() and not new_path.exists():
        ui.info("Migrating config to new path:", new_path)
        yaml = ruamel.yaml.YAML(typ="rt")
        old_dict = yaml.load(old_path.text())
        new_config = WorkspaceConfig(
            manifest_branch=old_dict.get("branch"),
            manifest_url=old_dict["url"],
            repo_groups=old_dict.get("groups"),
            shallow_clones=old_dict.get("shallow"),
        )
        new_config.save_to_file(new_path)


class Workspace:
    def __init__(self, root_path: Path) -> None:
        self.root_path = root_path
        self.local_manifest = LocalManifest(root_path / ".tsrc" / "manifest")
        copy_cfg_path_if_needed(root_path)
        self.config = WorkspaceConfig.from_file(root_path / ".tsrc" / "config.yml")

    def get_repos(self) -> List[tsrc.Repo]:
        repo_groups = self.config.repo_groups
        manifest = self.get_manifest()
        return manifest.get_repos(groups=repo_groups)

    def get_manifest(self) -> tsrc.Manifest:
        return self.local_manifest.get_manifest()

    def get_github_enterprise_url(self) -> Optional[str]:
        manifest = self.local_manifest.get_manifest()
        return manifest.github_enterprise_url

    def get_gitlab_url(self) -> Optional[str]:
        manifest = self.local_manifest.get_manifest()
        return manifest.gitlab_url

    def update_manifest(self) -> None:
        manifest_url = self.config.manifest_url
        manifest_branch = self.config.manifest_branch
        self.local_manifest.update(url=manifest_url, branch=manifest_branch)

    def clone_missing(self) -> None:
        to_clone = []
        for repo in self.get_repos():
            repo_path = self.root_path / repo.src
            if not repo_path.exists():
                to_clone.append(repo)
        cloner = Cloner(self.root_path, shallow=self.config.shallow_clones)
        tsrc.executor.run_sequence(to_clone, cloner)

    def set_remotes(self) -> None:
        remote_setter = RemoteSetter(self.root_path)
        tsrc.executor.run_sequence(self.get_repos(), remote_setter)

    def copy_files(self) -> None:
        file_copier = FileCopier(self.root_path)
        manifest = self.local_manifest.get_manifest()
        copyfiles = manifest.copyfiles
        tsrc.executor.run_sequence(copyfiles, file_copier)

    def sync(self, *, force: bool = False) -> None:
        syncer = Syncer(self.root_path, force=force)
        try:
            tsrc.executor.run_sequence(self.get_repos(), syncer)
        finally:
            syncer.display_bad_branches()

    def enumerate_repos(self) -> Iterable[Tuple[int, tsrc.Repo, Path]]:
        """ Yield (index, repo, full_path) for all the repos """
        for i, repo in enumerate(self.get_repos()):
            full_path = self.root_path / repo.src
            yield (i, repo, full_path)
