"""Kotlin language analyzer for the entity graph.

Implements LanguageAnalyzer for Kotlin source files using tree-sitter-kotlin.

Tree-sitter Kotlin grammar notes:
- `package_header` contains the package name as `qualified_identifier`.
- Classes are `class_declaration` (covers regular class, interface, data class, enum class).
- Objects are `object_declaration`.
- Companion objects are `companion_object` nodes inside a `class_body`.
- Functions are `function_declaration` at file top-level or inside `class_body`.
- Imports are `import` nodes containing a `qualified_identifier`.
- Inheritance/interface implementation: `delegation_specifiers` →
  `delegation_specifier` → either `constructor_invocation` (class) or
  `user_type` (interface).

Grammar quirk: tree-sitter-kotlin 1.x incorrectly sets `has_error=True` for
class bodies where members appear on the same line as the opening brace
(e.g., `class Foo { fun bar() {} }`). The `_KotlinParser` wrapper normalizes
source code to multi-line class bodies before parsing to avoid this false
positive.

Requirements: 107-REQ-3.1, 107-REQ-3.2, 107-REQ-3.3, 107-REQ-3.4,
              107-REQ-3.5, 107-REQ-3.E1, 107-REQ-3.E2
"""

from __future__ import annotations

import re
from pathlib import Path

from agent_fox.knowledge.entities import EdgeType, Entity, EntityEdge, EntityType
from agent_fox.knowledge.lang._ts_helpers import (
    ENTITY_EPOCH,
    make_entity,
    node_text,
)

# Module-level import so the name can be patched in tests (TS-107-E9).
try:
    from tree_sitter_kotlin import language  # type: ignore[import]  # noqa: F401
except ImportError:
    language = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Parser wrapper: works around tree-sitter-kotlin 1.x inline-class-body bug
# ---------------------------------------------------------------------------

_INLINE_OPEN_RE = re.compile(rb"\{ ")
_INLINE_CLOSE_RE = re.compile(rb" \}")


def _normalize_kotlin_source(source: bytes) -> bytes:
    """Normalize Kotlin source to avoid false-positive has_error.

    tree-sitter-kotlin 1.x sets has_error=True when class body members appear
    on the same line as the opening brace (e.g. `class Foo { fun bar() {} }`).
    Replacing `{ ` with `{\\n` and ` }` with `\\n}` converts inline class
    bodies to multi-line format that the grammar handles correctly.
    This transformation is safe: it only affects files with inline blocks,
    and does not change the AST structure — only whitespace.
    """
    result = _INLINE_OPEN_RE.sub(b"{\n", source)
    result = _INLINE_CLOSE_RE.sub(b"\n}", result)
    return result


class _KotlinParser:
    """Wrapper around tree-sitter Parser that normalizes Kotlin source code.

    Works around tree-sitter-kotlin 1.x bug where inline class bodies
    (e.g., `class Foo { fun bar() {} }`) produce false-positive has_error.
    """

    def __init__(self, parser) -> None:
        self._parser = parser

    def parse(self, source: bytes | None = None, **kwargs):
        """Normalize source and delegate to the underlying parser."""
        if source is not None:
            source = _normalize_kotlin_source(source)
        return self._parser.parse(source, **kwargs)

    def __getattr__(self, name: str):
        """Delegate all other attribute access to the wrapped parser."""
        return getattr(self._parser, name)


# ---------------------------------------------------------------------------
# KotlinAnalyzer
# ---------------------------------------------------------------------------


class KotlinAnalyzer:
    """Language analyzer for Kotlin source files (.kt, .kts).

    Extracts FILE, MODULE (package), CLASS (class/interface/object/enum class/data class),
    and FUNCTION (fun declarations, qualified as ClassName.functionName for methods).
    Produces CONTAINS, IMPORTS, and EXTENDS edges.

    Requirements: 107-REQ-3.1, 107-REQ-3.2, 107-REQ-3.3, 107-REQ-3.4, 107-REQ-3.5
    """

    @property
    def language_name(self) -> str:
        return "kotlin"

    @property
    def file_extensions(self) -> set[str]:
        return {".kt", ".kts"}

    def make_parser(self):  # type: ignore[return]
        """Create a tree-sitter Parser for Kotlin.

        Returns a _KotlinParser wrapper that normalizes source code before
        parsing to work around a false-positive has_error bug in tree-sitter-kotlin
        1.x for inline class bodies.
        """
        if language is None:
            raise ImportError("tree-sitter-kotlin is not installed")
        from tree_sitter import Language, Parser

        return _KotlinParser(Parser(Language(language())))

    def extract_entities(self, tree, rel_path: str) -> list[Entity]:
        """Extract FILE, MODULE, CLASS, and FUNCTION entities from a Kotlin tree."""
        return _extract_kotlin_entities(tree, rel_path)

    def extract_edges(
        self,
        tree,
        rel_path: str,
        entities: list[Entity],
        module_map: dict[str, str],
    ) -> list[EntityEdge]:
        """Extract CONTAINS, IMPORTS, and EXTENDS edges from a Kotlin tree."""
        return _extract_kotlin_edges(tree, rel_path, entities, module_map)

    def build_module_map(
        self,
        repo_root: Path,
        files: list[Path],
    ) -> dict[str, str]:
        """Build a Kotlin package.ClassName → repo-relative file path mapping.

        Requirements: 107-REQ-3.5
        """
        return _build_kotlin_module_map(repo_root, files)


# ---------------------------------------------------------------------------
# Helper: qualified_identifier text
# ---------------------------------------------------------------------------


def _qualified_identifier_text(node) -> str | None:
    """Extract the full dotted text from a qualified_identifier node."""
    if node is None:
        return None
    text = node_text(node)
    return text


# ---------------------------------------------------------------------------
# Kotlin entity extraction
# ---------------------------------------------------------------------------


def _extract_kotlin_entities(tree, rel_path: str) -> list[Entity]:
    """Extract all entities from a parsed Kotlin source tree.

    Requirements: 107-REQ-3.3, 107-REQ-3.E1
    """
    now = ENTITY_EPOCH
    file_name = Path(rel_path).name
    entities: list[Entity] = []

    # FILE entity — always present.
    entities.append(make_entity(EntityType.FILE, file_name, rel_path, now=now))

    root = tree.root_node

    # Package/MODULE entity
    pkg_name: str | None = None
    for child in root.children:
        if child.type == "package_header":
            qi = _find_child_by_type(child, "qualified_identifier")
            if qi is not None:
                pkg_name = node_text(qi)
                if pkg_name:
                    entities.append(make_entity(EntityType.MODULE, pkg_name, rel_path, now=now))
            break

    # Walk top-level declarations for classes and functions.
    for child in root.children:
        if child.type == "class_declaration":
            _collect_kotlin_class_entities(child, rel_path, entities, now)
        elif child.type == "object_declaration":
            _collect_kotlin_object_entities(child, rel_path, entities, now)
        elif child.type == "function_declaration":
            # Top-level function (no class qualifier)
            func_name = _get_identifier(child)
            if func_name:
                entities.append(make_entity(EntityType.FUNCTION, func_name, rel_path, now=now))

    return entities


def _collect_kotlin_class_entities(
    class_node,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect CLASS and FUNCTION entities from a class_declaration node.

    Handles regular class, interface, data class, enum class, and sealed class.
    """
    class_name = _get_identifier(class_node)
    if class_name is None:
        return

    entities.append(make_entity(EntityType.CLASS, class_name, rel_path, now=now))

    # Walk class_body for methods and companion objects.
    for child in class_node.children:
        if child.type == "class_body":
            _collect_kotlin_class_body_entities(child, class_name, rel_path, entities, now)


def _collect_kotlin_object_entities(
    obj_node,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect CLASS and FUNCTION entities from an object_declaration node.

    object declarations are treated as CLASS entities.
    """
    obj_name = _get_identifier(obj_node)
    if obj_name is None:
        return

    entities.append(make_entity(EntityType.CLASS, obj_name, rel_path, now=now))

    # Walk class_body for methods.
    for child in obj_node.children:
        if child.type == "class_body":
            _collect_kotlin_class_body_entities(child, obj_name, rel_path, entities, now)


def _collect_kotlin_class_body_entities(
    body_node,
    class_name: str,
    rel_path: str,
    entities: list[Entity],
    now: str,
) -> None:
    """Collect FUNCTION entities from a class_body node.

    Methods are qualified as 'ClassName.functionName'.
    Companion object methods are qualified as 'ClassName.functionName'
    (not 'ClassName.Companion.functionName') per REQ-3.E1.
    """
    for child in body_node.children:
        if child.type == "function_declaration":
            func_name = _get_identifier(child)
            if func_name:
                qualified = f"{class_name}.{func_name}"
                entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))

        elif child.type == "companion_object":
            # Companion object: methods are qualified as ClassName.methodName (REQ-3.E1).
            for co_child in child.children:
                if co_child.type == "class_body":
                    for body_child in co_child.children:
                        if body_child.type == "function_declaration":
                            func_name = _get_identifier(body_child)
                            if func_name:
                                qualified = f"{class_name}.{func_name}"
                                entities.append(make_entity(EntityType.FUNCTION, qualified, rel_path, now=now))


# ---------------------------------------------------------------------------
# Kotlin edge extraction
# ---------------------------------------------------------------------------


def _extract_kotlin_edges(
    tree,
    rel_path: str,
    entities: list[Entity],
    module_map: dict[str, str],
) -> list[EntityEdge]:
    """Extract CONTAINS, IMPORTS, and EXTENDS edges from a parsed Kotlin source tree.

    Requirements: 107-REQ-3.4, 107-REQ-3.E2
    """
    edges: list[EntityEdge] = []
    file_name = Path(rel_path).name
    entity_by_name: dict[str, Entity] = {e.entity_name: e for e in entities}

    file_entity = entity_by_name.get(file_name)
    if file_entity is None:
        return edges

    root = tree.root_node

    for child in root.children:
        if child.type == "import":
            # IMPORTS edges from import statements.
            qi = _find_child_by_type(child, "qualified_identifier")
            if qi is not None:
                import_name = node_text(qi)
                if import_name:
                    target_path = module_map.get(import_name)
                    if target_path is not None:
                        edges.append(
                            EntityEdge(
                                source_id=file_entity.id,
                                target_id=f"path:{target_path}",
                                relationship=EdgeType.IMPORTS,
                            )
                        )
                    # Not in module_map → external dep → skip silently (REQ-3.E2)

        elif child.type == "class_declaration":
            class_edges = _extract_kotlin_class_edges(child, file_entity, entity_by_name)
            edges.extend(class_edges)

        elif child.type == "object_declaration":
            obj_edges = _extract_kotlin_object_edges(child, file_entity, entity_by_name)
            edges.extend(obj_edges)

        elif child.type == "function_declaration":
            # Top-level function: file -> function CONTAINS edge.
            func_name = _get_identifier(child)
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


def _extract_kotlin_class_edges(
    class_node,
    file_entity: Entity,
    entity_by_name: dict[str, Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS and EXTENDS edges for a class_declaration."""
    edges: list[EntityEdge] = []

    class_name = _get_identifier(class_node)
    if class_name is None:
        return edges

    class_entity = entity_by_name.get(class_name)

    # CONTAINS: file -> class
    if class_entity:
        edges.append(
            EntityEdge(
                source_id=file_entity.id,
                target_id=class_entity.id,
                relationship=EdgeType.CONTAINS,
            )
        )

    for child in class_node.children:
        if child.type == "delegation_specifiers":
            # EXTENDS edges from inheritance / interface implementation.
            if class_entity:
                for spec in child.children:
                    if spec.type == "delegation_specifier":
                        base_name = _get_delegation_specifier_name(spec)
                        if base_name:
                            base_entity = entity_by_name.get(base_name)
                            edges.append(
                                EntityEdge(
                                    source_id=class_entity.id,
                                    target_id=base_entity.id if base_entity else f"class:{base_name}",
                                    relationship=EdgeType.EXTENDS,
                                )
                            )

        elif child.type == "class_body":
            # CONTAINS: class -> methods and companion methods.
            if class_entity:
                body_edges = _extract_kotlin_body_edges(child, class_name, class_entity, entity_by_name)
                edges.extend(body_edges)

    return edges


def _extract_kotlin_object_edges(
    obj_node,
    file_entity: Entity,
    entity_by_name: dict[str, Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS edges for an object_declaration."""
    edges: list[EntityEdge] = []

    obj_name = _get_identifier(obj_node)
    if obj_name is None:
        return edges

    obj_entity = entity_by_name.get(obj_name)

    # CONTAINS: file -> object
    if obj_entity:
        edges.append(
            EntityEdge(
                source_id=file_entity.id,
                target_id=obj_entity.id,
                relationship=EdgeType.CONTAINS,
            )
        )

    # CONTAINS: object -> methods
    for child in obj_node.children:
        if child.type == "class_body" and obj_entity:
            body_edges = _extract_kotlin_body_edges(child, obj_name, obj_entity, entity_by_name)
            edges.extend(body_edges)

    return edges


def _extract_kotlin_body_edges(
    body_node,
    class_name: str,
    class_entity: Entity,
    entity_by_name: dict[str, Entity],
) -> list[EntityEdge]:
    """Extract CONTAINS edges for methods inside a class_body.

    Companion object methods are qualified as 'ClassName.methodName'.
    """
    edges: list[EntityEdge] = []

    for child in body_node.children:
        if child.type == "function_declaration":
            func_name = _get_identifier(child)
            if func_name:
                qualified = f"{class_name}.{func_name}"
                func_entity = entity_by_name.get(qualified)
                if func_entity:
                    edges.append(
                        EntityEdge(
                            source_id=class_entity.id,
                            target_id=func_entity.id,
                            relationship=EdgeType.CONTAINS,
                        )
                    )

        elif child.type == "companion_object":
            # Companion object methods: qualified as ClassName.methodName (REQ-3.E1).
            for co_child in child.children:
                if co_child.type == "class_body":
                    for body_child in co_child.children:
                        if body_child.type == "function_declaration":
                            func_name = _get_identifier(body_child)
                            if func_name:
                                qualified = f"{class_name}.{func_name}"
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
# Kotlin module map construction
# ---------------------------------------------------------------------------

_KT_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)", re.MULTILINE)
_KT_CLASS_RE = re.compile(
    r"(?:^|(?<=\s))(?:(?:data|sealed|enum|abstract|open|inner|value)\s+)*"
    r"(?:class|interface|object)\s+(\w+)",
    re.MULTILINE,
)


def _build_kotlin_module_map(repo_root: Path, files: list[Path]) -> dict[str, str]:
    """Build a mapping from Kotlin package-qualified class names to repo-relative file paths.

    Maps "com.example.models.User" → repo-relative POSIX path.
    All values are POSIX-style repo-relative paths (no backslashes, no leading /).

    Requirements: 107-REQ-3.5
    """
    module_map: dict[str, str] = {}
    for kt_file in files:
        try:
            content = kt_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel_path = str(kt_file.relative_to(repo_root)).replace("\\", "/")

        pkg_match = _KT_PACKAGE_RE.search(content)
        package = pkg_match.group(1) if pkg_match else None

        class_names = _KT_CLASS_RE.findall(content)

        for cls in class_names:
            if package:
                fqn = f"{package}.{cls}"
            else:
                fqn = cls
            module_map[fqn] = rel_path

    return module_map


# ---------------------------------------------------------------------------
# Tree-sitter node helpers (Kotlin-specific)
# ---------------------------------------------------------------------------


def _find_child_by_type(node, *types: str):
    """Return the first direct child whose type is in *types*, or None."""
    for child in node.children:
        if child.type in types:
            return child
    return None


def _get_identifier(node) -> str | None:
    """Get the text of the first 'identifier' child of *node*."""
    for child in node.children:
        if child.type == "identifier":
            return node_text(child)
    return None


def _get_delegation_specifier_name(spec_node) -> str | None:
    """Extract the class/interface name from a delegation_specifier node.

    Handles:
    - constructor_invocation → user_type → identifier (class)
    - user_type → identifier (interface)
    """
    for child in spec_node.children:
        if child.type == "constructor_invocation":
            # Class constructor: find user_type → identifier
            for ci_child in child.children:
                if ci_child.type == "user_type":
                    return _get_user_type_name(ci_child)
        elif child.type == "user_type":
            return _get_user_type_name(child)
    return None


def _get_user_type_name(user_type_node) -> str | None:
    """Extract the simple name from a user_type node."""
    # user_type can be qualified: e.g. com.example.Foo → but the identifier
    # we want is the last one. For simplicity, return the full text.
    text = node_text(user_type_node)
    if text:
        # Return just the simple name (last segment) since that's what
        # the entity was registered with (e.g., "BaseModel" not "com.example.BaseModel").
        return text.split(".")[-1]
    return None
