"""Dart language analyzer for the entity graph.

Implements LanguageAnalyzer for Dart source files using tree-sitter-dart-orchard.

Tree-sitter Dart grammar notes (tree-sitter-dart-orchard):
- `library_name` contains the library directive (library my_lib;).
  - dotted_identifier_list → identifier children give the name.
- `import_or_export` contains import statements.
  - library_import → import_specification → configurable_uri → uri → string_literal.
  - Strip surrounding quotes to get the import path string.
- `class_definition` covers regular class declarations.
  - identifier (class name), superclass (extends/with), interfaces (implements), class_body.
- `mixin_declaration` covers mixin declarations.
  - mixin → identifier (mixin name), class_body.
- `enum_declaration` covers enum declarations.
  - identifier (enum name), enum_body.
- `extension_declaration` covers extension declarations.
  - identifier (extension name), extension_body.
- `function_signature` + `function_body` at root level = top-level function.
- Inside class_body/extension_body: method_signature + function_body.
  - method_signature → function_signature → identifier = method name.
  - method_signature → getter_signature → identifier = getter name.
- `superclass` node: type_identifier (base class) + mixins → type_identifier (with).
- `interfaces` node: type_identifier children (implements).

Requirements: 107-REQ-4.1, 107-REQ-4.2, 107-REQ-4.3, 107-REQ-4.4,
              107-REQ-4.5, 107-REQ-4.E1, 107-REQ-4.E2
"""

from __future__ import annotations

from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import (
    ENTITY_EPOCH,
    make_entity,
    node_text,
)

# Module-level import so the name can be patched in tests (TS-107-E9).
try:
    from tree_sitter_dart_orchard import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# DartAnalyzer
# ---------------------------------------------------------------------------


class DartAnalyzer:
    """Language analyzer for Dart source files (.dart).

    Extracts FILE, MODULE (library directive only), CLASS (class/mixin/enum/extension),
    and FUNCTION (top-level functions and methods, qualified as ClassName.methodName).
    Produces CONTAINS, IMPORTS, and EXTENDS edges.

    Requirements: 107-REQ-4.1, 107-REQ-4.2, 107-REQ-4.3, 107-REQ-4.4, 107-REQ-4.5
    """

    @property
    def language_name(self) -> str:
        return "dart"

    @property
    def file_extensions(self) -> set[str]:
        return {".dart"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Dart.

        Requirements: 107-REQ-4.2
        """
        if language is None:
            raise ImportError("tree-sitter-dart-orchard is not installed")
        from tree_sitter import Language, Parser

        return Parser(Language(language()))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, MODULE, CLASS, and FUNCTION entities from a Dart tree.

        Requirements: 107-REQ-4.3, 107-REQ-4.E2
        """
        return _extract_dart_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a Dart tree.

        Requirements: 107-REQ-4.4, 107-REQ-4.E1
        """
        return _extract_dart_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a Dart import path → repo-relative file path mapping.

        Requirements: 107-REQ-4.5
        """
        return _build_dart_module_map(repo_root, files)


# ---------------------------------------------------------------------------
# Dart entity extraction
# ---------------------------------------------------------------------------


def _extract_dart_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed Dart source tree.

    Requirements: 107-REQ-4.3, 107-REQ-4.E2
    """
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    # FILE entity — always present.
    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    root = tree.root_node

    for child in root.children:
        if child.type == "library_name":
            # MODULE entity — only when explicit library directive is present (REQ-4.E2).
            lib_name = _get_library_name(child)
            if lib_name:
                entities.append(make_entity(EntityType.MODULE, lib_name, rel_path, now=now))

        elif child.type == "class_definition":
            _collect_dart_class_entities(child, rel_path, entities, now)

        elif child.type == "mixin_declaration":
            _collect_dart_mixin_entities(child, rel_path, entities, now)

        elif child.type == "enum_declaration":
            enum_name = _get_identifier(child)
            if enum_name:
                entities.append(make_entity(EntityType.CLASS, enum_name, rel_path, now=now))

        elif child.type == "extension_declaration":
            _collect_dart_extension_entities(child, rel_path, entities, now)

        elif child.type == "function_signature":
            # Top-level function — function_signature and function_body are siblings.
            func_name = _get_function_signature_name(child)
            if func_name:
                entities.append(make_entity(EntityType.FUNCTION, func_name, rel_path, now=now))

    return entities


def _collect_dart_class_entities(
    class_node,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect CLASS and FUNCTION entities from a class_definition node."""
    class_name = _get_identifier(class_node)
    if class_name is None:
        return

    entities.append(make_entity(EntityType.CLASS, class_name, rel_path, now=now))

    # Walk class_body for methods.
    for child in class_node.children:
        if child.type == "class_body":
            _collect_body_method_entities(child, class_name, rel_path, entities, now)


def _collect_dart_mixin_entities(
    mixin_node,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect CLASS and FUNCTION entities from a mixin_declaration node."""
    mixin_name = _get_identifier(mixin_node)
    if mixin_name is None:
        return

    entities.append(make_entity(EntityType.CLASS, mixin_name, rel_path, now=now))

    for child in mixin_node.children:
        if child.type == "class_body":
            _collect_body_method_entities(child, mixin_name, rel_path, entities, now)


def _collect_dart_extension_entities(
    ext_node,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect CLASS and FUNCTION entities from an extension_declaration node."""
    ext_name = _get_identifier(ext_node)
    if ext_name is None:
        return

    entities.append(make_entity(EntityType.CLASS, ext_name, rel_path, now=now))

    for child in ext_node.children:
        if child.type == "extension_body":
            _collect_body_method_entities(child, ext_name, rel_path, entities, now)


def _collect_body_method_entities(
    body_node,
    class_name: str,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect FUNCTION entities from class_body or extension_body.

    Methods are qualified as 'ClassName.methodName'.
    """
    for child in body_node.children:
        if child.type == "method_signature":
            method_name = _get_method_signature_name(child)
            if method_name:
                qualified = f"{class_name}.{method_name}"
                entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))


# ---------------------------------------------------------------------------
# Dart edge extraction
# ---------------------------------------------------------------------------


def _extract_dart_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS, IMPORTS, and EXTENDS edges from a parsed Dart source tree.

    Requirements: 107-REQ-4.4, 107-REQ-4.E1
    """
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name
    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}

    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node

    for child in root.children:
        if child.type == "import_or_export":
            # IMPORTS edges from import statements (REQ-4.4, REQ-4.E1).
            import_path = _extract_import_path(child)
            if import_path is not None:
                # Skip dart: SDK imports and package: external imports (REQ-4.E1).
                if import_path.startswith("dart:") or import_path.startswith("package:"):
                    continue
                target_path = module_map.get(import_path)
                if target_path is not None:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=f"path:{target_path}",
                            relationship=EdgeType.IMPORTS,
                        )
                    )
                # Not in module_map → external dep → skip silently

        elif child.type == "class_definition":
            class_edges = _extract_dart_class_edges(child, file_entity, entity_by_name)
            edges.extend(class_edges)

        elif child.type == "mixin_declaration":
            mixin_edges = _extract_dart_mixin_edges(child, file_entity, entity_by_name)
            edges.extend(mixin_edges)

        elif child.type == "enum_declaration":
            enum_name = _get_identifier(child)
            if enum_name:
                enum_entity = entity_by_name.get(enum_name)
                if enum_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=enum_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

        elif child.type == "extension_declaration":
            ext_edges = _extract_dart_extension_edges(child, file_entity, entity_by_name)
            edges.extend(ext_edges)

        elif child.type == "function_signature":
            # Top-level function: file → function CONTAINS edge.
            func_name = _get_function_signature_name(child)
            if func_name:
                func_entity = entity_by_name.get(func_name)
                if func_entity:
                    edges.append(
                        EntityEdge(
                            source_id=file_entity.id,
                            target_id=func_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

    return edges


def _extract_dart_class_edges(
    class_node,
    file_entity: Entity,
    entity_by_name: dict[str, Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS and EXTENDS edges for a class_definition."""
    edges: list[EntityEdge] = []

    class_name = _get_identifier(class_node)
    if class_name is None:
        return edges

    class_entity = entity_by_name.get(class_name)

    # CONTAINS: file → class.
    if class_entity:
        edges.append(
            EntityEdge(
                source_id=file_entity.id,
                target_id=class_entity.id,
                relationship=EdgeType.CONTAINS,
            )
        )

    for child in class_node.children:
        if child.type == "superclass":
            # EXTENDS from extends and with clauses.
            if class_entity:
                extend_targets = _extract_superclass_targets(child)
                for target_name in extend_targets:
                    target_entity = entity_by_name.get(target_name)
                    edges.append(
                        EntityEdge(
                            source_id=class_entity.id,
                            target_id=target_entity.id if target_entity else f"class:{target_name}",
                            relationship=EdgeType.EXTENDS,
                        )
                    )

        elif child.type == "interfaces":
            # EXTENDS from implements clause.
            if class_entity:
                for iface_child in child.children:
                    if iface_child.type == "type_identifier":
                        iface_name = node_text(iface_child)
                        if iface_name:
                            iface_entity = entity_by_name.get(iface_name)
                            edges.append(
                                EntityEdge(
                                    source_id=class_entity.id,
                                    target_id=iface_entity.id if iface_entity else f"class:{iface_name}",
                                    relationship=EdgeType.EXTENDS,
                                )
                            )

        elif child.type == "class_body" and class_entity:
            # CONTAINS: class → methods.
            body_edges = _extract_dart_body_edges(child, class_name, class_entity, entity_by_name)
            edges.extend(body_edges)

    return edges


def _extract_dart_mixin_edges(
    mixin_node,
    file_entity: Entity,
    entity_by_name: dict[str, Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS edges for a mixin_declaration."""
    edges: list[EntityEdge] = []

    mixin_name = _get_identifier(mixin_node)
    if mixin_name is None:
        return edges

    mixin_entity = entity_by_name.get(mixin_name)

    # CONTAINS: file → mixin.
    if mixin_entity:
        edges.append(
            EntityEdge(
                source_id=file_entity.id,
                target_id=mixin_entity.id,
                relationship=EdgeType.CONTAINS,
            )
        )

    # CONTAINS: mixin → methods.
    for child in mixin_node.children:
        if child.type == "class_body" and mixin_entity:
            body_edges = _extract_dart_body_edges(child, mixin_name, mixin_entity, entity_by_name)
            edges.extend(body_edges)

    return edges


def _extract_dart_extension_edges(
    ext_node,
    file_entity: Entity,
    entity_by_name: dict[str, Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS edges for an extension_declaration."""
    edges: list[EntityEdge] = []

    ext_name = _get_identifier(ext_node)
    if ext_name is None:
        return edges

    ext_entity = entity_by_name.get(ext_name)

    # CONTAINS: file → extension.
    if ext_entity:
        edges.append(
            EntityEdge(
                source_id=file_entity.id,
                target_id=ext_entity.id,
                relationship=EdgeType.CONTAINS,
            )
        )

    # CONTAINS: extension → methods.
    for child in ext_node.children:
        if child.type == "extension_body" and ext_entity:
            body_edges = _extract_dart_body_edges(child, ext_name, ext_entity, entity_by_name)
            edges.extend(body_edges)

    return edges


def _extract_dart_body_edges(
    body_node,
    class_name: str,
    class_entity: Entity,
    entity_by_name: dict[str, Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS edges for methods inside a class_body or extension_body."""
    edges: list[EntityEdge] = []

    for child in body_node.children:
        if child.type == "method_signature":
            method_name = _get_method_signature_name(child)
            if method_name:
                qualified = f"{class_name}.{method_name}"
                func_entity = entity_by_name.get(qualified)
                if func_entity:
                    edges.append(
                        EntityEdge(
                            source_id=class_entity.id,
                            target_id=func_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

    return edges


# ---------------------------------------------------------------------------
# Dart module map construction
# ---------------------------------------------------------------------------


def _build_dart_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a mapping from Dart import path strings to repo-relative file paths.

    Maps repo-relative file path (and lib/-stripped variant) → repo-relative POSIX path.
    This allows both `import 'lib/models/user.dart'` and `import 'models/user.dart'`
    to resolve when the file is at lib/models/user.dart.

    All values are POSIX-style repo-relative paths (no backslashes, no leading /).

    Requirements: 107-REQ-4.5
    """
    module_map: dict[str, str] = {}
    for dart_file in files:
        try:
            rel_path = str(dart_file.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            continue

        # Map the full repo-relative path.
        module_map[rel_path] = rel_path

        # If file is under lib/, also map the lib/-stripped version.
        # Dart convention: files under lib/ are imported without the lib/ prefix.
        if rel_path.startswith("lib/"):
            stripped = rel_path[4:]  # Remove "lib/" prefix.
            module_map[stripped] = rel_path

    return module_map


# ---------------------------------------------------------------------------
# Tree-sitter node helpers (Dart-specific)
# ---------------------------------------------------------------------------


def _find_child_by_type(node, *types: str):
    """Return the first direct child whose type is in *types*, or None."""
    for child in node.children:
        if child.type in types:
            return child
    return None


def _get_identifier(node) -> str | None:
    """Get the text of the first 'identifier' direct child of *node*."""
    for child in node.children:
        if child.type == "identifier":
            return node_text(child)
    return None


def _get_library_name(library_name_node) -> str | None:
    """Extract the library name from a library_name node.

    library_name → dotted_identifier_list → identifier children.
    The library name is the text of dotted_identifier_list (joined by dots),
    or simply the identifier text for single-segment names.
    """
    dotted = _find_child_by_type(library_name_node, "dotted_identifier_list")
    if dotted is not None:
        # For dotted names like my_app.accounts, get the full text.
        text = node_text(dotted)
        if text:
            return text
    # Fallback: plain identifier.
    return _get_identifier(library_name_node)


def _get_function_signature_name(function_sig_node) -> str | None:
    """Get the function name from a function_signature node.

    function_signature → identifier (the function name).
    """
    return _get_identifier(function_sig_node)


def _get_method_signature_name(method_sig_node) -> str | None:
    """Get the method name from a method_signature node.

    method_signature may contain:
    - function_signature → identifier (regular method)
    - getter_signature → identifier (getter)
    - setter_signature → identifier (setter)
    """
    for child in method_sig_node.children:
        if child.type in ("function_signature", "getter_signature", "setter_signature"):
            return _get_identifier(child)
    return None


def _extract_import_path(import_or_export_node) -> str | None:
    """Extract the import path string from an import_or_export node.

    Navigates: import_or_export → library_import → import_specification
               → configurable_uri → uri → string_literal → strip quotes.

    Returns None if this is not an import (e.g., an export).
    """
    library_import = _find_child_by_type(import_or_export_node, "library_import")
    if library_import is None:
        return None
    import_spec = _find_child_by_type(library_import, "import_specification")
    if import_spec is None:
        return None
    config_uri = _find_child_by_type(import_spec, "configurable_uri")
    if config_uri is None:
        return None
    uri = _find_child_by_type(config_uri, "uri")
    if uri is None:
        return None
    string_lit = _find_child_by_type(uri, "string_literal")
    if string_lit is None:
        return None
    text = node_text(string_lit)
    if text is None or len(text) < 2:
        return None
    # Strip surrounding single or double quotes.
    return text[1:-1]


def _extract_superclass_targets(superclass_node) -> list[str]:
    """Extract base class and mixin names from a superclass node.

    superclass → type_identifier (extends target)
    superclass → mixins → type_identifier (with targets)
    """
    targets: list[str] = []
    for child in superclass_node.children:
        if child.type == "type_identifier":
            text = node_text(child)
            if text:
                targets.append(text)
        elif child.type == "mixins":
            for mixin_child in child.children:
                if mixin_child.type == "type_identifier":
                    text = node_text(mixin_child)
                    if text:
                        targets.append(text)
    return targets
