"""Assemble the default agent tool belt."""

from __future__ import annotations

from nexcoder.agent.core.tools.base import ToolBelt
from nexcoder.agent.core.tools.files import register_file_tools
from nexcoder.agent.core.tools.memory_tool import register_memory_tool
from nexcoder.agent.core.tools.search import register_search_tools
from nexcoder.agent.core.tools.shell import register_shell_tool
from nexcoder.agent.core.tools.skill import register_skill_tool
from nexcoder.agent.core.tools.todo import register_todo_tool


def build_default_belt() -> ToolBelt:
    belt = ToolBelt()
    register_file_tools(belt)
    register_search_tools(belt)
    register_shell_tool(belt)
    register_todo_tool(belt)
    register_skill_tool(belt)
    register_memory_tool(belt)
    return belt
