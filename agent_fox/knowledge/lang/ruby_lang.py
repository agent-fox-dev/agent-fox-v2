"""Ruby language analyzer for the entity graph.

Implements LanguageAnalyzer for Ruby source files using tree-sitter-ruby.

Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import (
    ENTITY_EPOCH,
    child_by_type,
    child_text_by_type,
    field_text,
    make_entity,
    node_text,
)


class RubyAnalyzer:
    """Language analyzer for Ruby source files (.rb).

    Extracts FILE, MODULE, CLASS, and FUNCTION entities,
    together with CONTAINS, IMPORTS (require/require_relative), and EXTENDS edges.

    Requirements: 102-REQ-2.1, 102-REQ-3.1, 102-REQ-3.2, 102-REQ-3.3
    """

    @property
    def language_name(self) -> str:
        return "ruby"

    @property
    def file_extensions(self) -> set[str]:
        return {".rb"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Ruby."""
        import tree_sitter_ruby as tsrb  # type: ignore[import]
        from tree_sitter import Language, Parser

        return Parser(Language(tsrb.language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, MODULE, CLASS, and FUNCTION entities from a Ruby source file."""
        return _extract_ruby_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a Ruby source file."""
        return _extract_ruby_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a Ruby require path map.

        Maps require identifiers to repo-relative file paths.
        Handles the lib/ directory convention.

        Requirements: 102-REQ-3.2
        """
        return _build_ruby_module_map(repo_root, files)


# Aliases for backward compatibility with internal references.
_node_text = node_text
_field_text = field_text
_child_by_type = child_by_type
_child_text_by_type = child_text_by_type


# ---------------------------------------------------------------------------
# Ruby entity extraction
# ---------------------------------------------------------------------------


def _extract_ruby_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed Ruby source tree."""
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    root = tree.root_node
    _walk_ruby_entities(root.children, rel_path, entities, now, current_class=None)

    return entities


def _walk_ruby_entities(
    nodes,
    rel_path: str,
    entities: list[Entity],
    now: str,
    current_class: str | None,
) -> None:
    """Recursively extract entities from Ruby AST nodes."""
    for node in nodes:
        node_type = node.type

        if node_type == "module":
            # MODULE entity
            mod_name = _get_ruby_name(node)
            if mod_name:
                entities.append(make_entity(EntityType.MODULE, mod_name, rel_path, now=now))
            # Walk module body
            body = node.child_by_field_name("body") or _child_by_type(node, "body_statement")
            if body:
                _walk_ruby_entities(body.children, rel_path, entities, now, current_class=None)

        elif node_type == "class":
            # CLASS entity
            cls_name = _get_ruby_name(node)
            if cls_name:
                entities.append(make_entity(EntityType.CLASS, cls_name, rel_path, now=now))
            # Walk class body
            body = node.child_by_field_name("body") or _child_by_type(node, "body_statement")
            if body:
                _walk_ruby_entities(body.children, rel_path, entities, now, current_class=cls_name)

        elif node_type == "method":
            # FUNCTION entity (qualified if inside a class)
            method_name = _get_ruby_method_name(node)
            if method_name:
                qualified = f"{current_class}.{method_name}" if current_class else method_name
                entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))

        elif node_type == "singleton_method":
            # def self.method → FUNCTION
            method_name = _get_ruby_method_name(node)
            if method_name:
                qualified = f"{current_class}.{method_name}" if current_class else method_name
                entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))

        elif node_type == "body_statement":
            # body_statement wraps the contents of a module/class
            _walk_ruby_entities(node.children, rel_path, entities, now, current_class=current_class)

        elif node_type in ("begin", "rescue", "ensure"):
            # Walk into begin/rescue blocks
            _walk_ruby_entities(node.children, rel_path, entities, now, current_class=current_class)


def _get_ruby_name(node) -> str | None:
    """Get the name (constant) of a Ruby module or class node."""
    # Try the 'name' named field first
    name_node = node.child_by_field_name("name")
    if name_node and name_node.text:
        return name_node.text.decode("utf-8")
    # Fallback: first constant child
    for child in node.children:
        if child.type == "constant" and child.text:
            return child.text.decode("utf-8")
        # Scoped constant: Services::User
        if child.type == "scope_resolution" and child.text:
            return child.text.decode("utf-8")
    return None


def _get_ruby_method_name(node) -> str | None:
    """Get the name of a Ruby method node."""
    name_node = node.child_by_field_name("name")
    if name_node and name_node.text:
        return name_node.text.decode("utf-8")
    # Fallback: first identifier child
    for child in node.children:
        if child.type == "identifier" and child.text:
            return child.text.decode("utf-8")
    return None


def _get_ruby_superclass_name(class_node) -> str | None:
    """Get the superclass name from a Ruby class node."""
    # The superclass is accessible via the 'superclass' named field
    superclass = class_node.child_by_field_name("superclass")
    if superclass is None:
        # Fallback: look for superclass child node type
        for child in class_node.children:
            if child.type == "superclass":
                superclass = child
                break
    if superclass is None:
        return None

    # superclass node contains the class name (constant)
    for child in superclass.children:
        if child.type == "constant" and child.text:
            return child.text.decode("utf-8")
        if child.type == "scope_resolution" and child.text:
            # Fully qualified: Module::Base
            raw = child.text.decode("utf-8")
            return raw.split("::")[-1]

    return None


def _get_ruby_require_path(call_node) -> tuple[str | None, bool]:
    """Get require path and whether it's require_relative from a Ruby call node.

    Returns (path, is_relative) or (None, False) if not a require call.
    """
    # Get the method name
    method_node = call_node.child_by_field_name("method")
    if method_node is None:
        # Some grammar versions have the method as a direct identifier child
        method_node = _child_by_type(call_node, "identifier")
    if method_node is None:
        return None, False

    method_name = _node_text(method_node)
    if method_name not in ("require", "require_relative"):
        return None, False

    is_relative = method_name == "require_relative"

    # Get the arguments
    args = call_node.child_by_field_name("arguments")
    if args is None:
        args = _child_by_type(call_node, "argument_list")

    if args:
        for child in args.children:
            if child.type in ("string", "simple_string") and child.text:
                raw = child.text.decode("utf-8").strip()
                # Strip quotes: 'base' or "base"
                path = raw.strip("'\"")
                return path, is_relative
            if child.type == "string_content" and child.text:
                return child.text.decode("utf-8"), is_relative
    else:
        # require 'base' without argument_list (some grammar versions)
        for child in call_node.children:
            if child.type in ("string", "simple_string") and child.text:
                raw = child.text.decode("utf-8").strip().strip("'\"")
                return raw, is_relative

    return None, False


# ---------------------------------------------------------------------------
# Ruby edge extraction
# ---------------------------------------------------------------------------


def _extract_ruby_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS, IMPORTS, and EXTENDS edges from a parsed Ruby source tree."""
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name

    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}
    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node
    _walk_ruby_edges(
        root.children,
        rel_path,
        entity_by_name,
        file_entity,
        module_map,
        edges,
        current_class=None,
        current_parent=file_entity,
    )

    return edges


def _walk_ruby_edges(
    nodes,
    rel_path: str,
    entity_by_name: dict[str, Entity],
    file_entity: Entity,
    module_map: dict[str, str],
    edges: list[EntityEdge],
    current_class: str | None,
    current_parent: Entity,
) -> None:
    """Recursively extract edges from Ruby AST nodes."""
    for node in nodes:
        node_type = node.type

        if node_type == "module":
            mod_name = _get_ruby_name(node)
            if mod_name:
                mod_entity = entity_by_name.get(mod_name)
                if mod_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=mod_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )
                    body = node.child_by_field_name("body") or _child_by_type(node, "body_statement")
                    if body:
                        _walk_ruby_edges(
                            body.children,
                            rel_path,
                            entity_by_name,
                            file_entity,
                            module_map,
                            edges,
                            current_class=None,
                            current_parent=mod_entity,
                        )

        elif node_type == "class":
            cls_name = _get_ruby_name(node)
            if cls_name:
                cls_entity = entity_by_name.get(cls_name)
                if cls_entity:
                    # parent (file or module) → class CONTAINS
                    edges.append(
                        EntityEdge(
                            source_id=current_parent.id,
                            target_id=cls_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

                    # Superclass → EXTENDS edge
                    base_name = _get_ruby_superclass_name(node)
                    if base_name:
                        base_entity = entity_by_name.get(base_name)
                        target_id = base_entity.id if base_entity else f"class:{base_name}"
                        edges.append(
                            EntityEdge(
                                source_id=cls_entity.id,
                                target_id=target_id,
                                relationship=EdgeType.EXTENDS,
                            )
                        )

                    body = node.child_by_field_name("body") or _child_by_type(node, "body_statement")
                    if body:
                        _walk_ruby_edges(
                            body.children,
                            rel_path,
                            entity_by_name,
                            file_entity,
                            module_map,
                            edges,
                            current_class=cls_name,
                            current_parent=cls_entity,
                        )

        elif node_type in ("method", "singleton_method"):
            method_name = _get_ruby_method_name(node)
            if method_name:
                qualified = f"{current_class}.{method_name}" if current_class else method_name
                method_entity = entity_by_name.get(qualified)
                if method_entity:
                    edges.append(
                        EntityEdge(
                            source_id=current_parent.id,
                            target_id=method_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

        elif node_type == "call":
            # require / require_relative → IMPORTS edge
            require_path, is_relative = _get_ruby_require_path(node)
            if require_path:
                target_path = _resolve_ruby_require(require_path, rel_path, module_map, is_relative)
                if target_path:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=f"path:{target_path}",
                            relationship=EdgeType.IMPORTS,
                        )
                    )

        elif node_type == "body_statement":
            _walk_ruby_edges(
                node.children,
                rel_path,
                entity_by_name,
                file_entity,
                module_map,
                edges,
                current_class=current_class,
                current_parent=current_parent,
            )

        elif node_type in ("begin", "rescue", "ensure"):
            _walk_ruby_edges(
                node.children,
                rel_path,
                entity_by_name,
                file_entity,
                module_map,
                edges,
                current_class=current_class,
                current_parent=current_parent,
            )


def _resolve_ruby_require(
    require_path: str,
    current_rel_path: str,
    module_map: dict[str, str],
    is_relative: bool,
) -> str | None:
    """Resolve a Ruby require path to a repo-relative file path."""
    # Direct lookup in module_map (handles 'services/user' → 'lib/services/user.rb')
    if require_path in module_map:
        return module_map[require_path]

    # Try with .rb extension added
    with_rb = require_path + ".rb"
    if with_rb in module_map:
        return module_map[with_rb]

    # For require_relative, resolve relative to the current file's directory
    if is_relative:
        current_dir = str(Path(current_rel_path).parent).replace("\\", "/")
        if current_dir == ".":
            candidate = require_path + ".rb"
        else:
            candidate = f"{current_dir}/{require_path}.rb"
        if candidate in module_map:
            return module_map[candidate]
        # Also try without .rb
        candidate_no_ext = candidate[:-3] if candidate.endswith(".rb") else candidate
        if candidate_no_ext in module_map:
            return module_map[candidate_no_ext]

    # Try matching the last segment against module_map
    last_seg = require_path.split("/")[-1]
    for key, value in module_map.items():
        key_stem = key.rsplit(".", 1)[0] if "." in key.split("/")[-1] else key
        if key_stem.split("/")[-1] == last_seg:
            return value

    return None


# ---------------------------------------------------------------------------
# Ruby module map construction
# ---------------------------------------------------------------------------


def _build_ruby_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a Ruby require path map.

    For each .rb file, adds multiple entries:
    - The repo-relative path without extension (e.g., "lib/services/user")
    - With the lib/ prefix stripped (e.g., "services/user"), for files under lib/
    - The filename stem alone (e.g., "user")

    Requirements: 102-REQ-3.2
    """
    module_map: dict[str, str] = {}
    for f in files:
        try:
            rel_path = str(f.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue

        # Map the full path without extension
        path_no_ext = rel_path.rsplit(".", 1)[0] if "." in rel_path.rsplit("/", 1)[-1] else rel_path
        module_map[path_no_ext] = rel_path

        # Also map just the filename stem
        stem = f.stem
        if stem not in module_map:
            module_map[stem] = rel_path

        # Strip leading lib/ prefix (Ruby convention)
        if path_no_ext.startswith("lib/"):
            stripped = path_no_ext[4:]  # e.g., "services/user"
            if stripped not in module_map:
                module_map[stripped] = rel_path
            # Also add the stem of the stripped path
            stripped_stem = stripped.split("/")[-1]
            if stripped_stem not in module_map:
                module_map[stripped_stem] = rel_path

    return module_map
