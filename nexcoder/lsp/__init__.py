"""Language Server Protocol integration.

``client.py`` speaks JSON-RPC over stdio to one language server;
``manager.py`` owns server lifecycles per language and translates
between editor coordinates and LSP structures.
"""
