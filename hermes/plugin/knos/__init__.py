"""Knos as a Hermes Agent directory plugin (copy this folder to the plugins folder of your Hermes home, as `knos`).

The tools live in the knos package (knos.hermes_plugin), which this imports; the same function is the pip entry
point `knos = "knos.hermes_plugin:register"` in the group `hermes_agent.plugins`, so either way loads the same code.
Install the package first: the knos package from PyPI, version 0.3.29.
"""

from knos.hermes_plugin import register  # noqa: F401 - Hermes calls register(ctx)
