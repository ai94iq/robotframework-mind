"""The folder tree for a folder that holds several repos: untick a repo to leave it out of the search."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator

PATH = Qt.ItemDataRole.UserRole


class FolderTree(QTreeWidget):
    """One row per repo, under rows for the folders that group them; long names are cut in the middle."""

    def __init__(self):
        super().__init__()
        self.setObjectName("folders")
        self.setHeaderHidden(True)
        self.setIndentation(14)
        self.setRootIsDecorated(True)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setHidden(True)

    def set_repos(self, repos: list[str]):
        self.clear()
        groups: dict[str, QTreeWidgetItem] = {}
        for repo in repos:
            parent, parts = None, repo.split("/")
            for depth, part in enumerate(parts):
                key = "/".join(parts[: depth + 1])
                if key not in groups:
                    groups[key] = self._item(parent, part, key if depth == len(parts) - 1 else None)
                parent = groups[key]
        self.expandAll()

    def _item(self, parent, text, path):
        item = QTreeWidgetItem([text])
        item.setToolTip(0, path or text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
        item.setCheckState(0, Qt.CheckState.Checked)
        item.setData(0, PATH, path)
        (parent.addChild if parent else self.addTopLevelItem)(item)
        return item

    def scope(self) -> list[str] | None:
        """The ticked repos, or None when every repo is ticked (search everything, loose files included)."""
        repos, ticked = [], []
        it = QTreeWidgetItemIterator(self)
        while it.value():
            item = it.value()
            if item.data(0, PATH):
                repos.append(item.data(0, PATH))
                if item.checkState(0) == Qt.CheckState.Checked:
                    ticked.append(item.data(0, PATH))
            it += 1
        return None if len(ticked) == len(repos) else ticked
