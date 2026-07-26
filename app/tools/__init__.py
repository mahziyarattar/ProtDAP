"""Tool implementations wrapped as LangChain tools for the ReAct agent.

Each module here is a plain, independently testable Python module; the
LangChain `@tool` wrapping happens in app/agent/graph.py so the underlying
logic (app/tools/*.py) can be unit-tested without spinning up an agent.
"""
