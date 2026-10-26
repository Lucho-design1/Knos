"""Claude agents working on Knos tasks, and Knos judging them: the Claude Agent SDK as a proposer with a guard
(agent_sdk.py) and Claude Managed Agents with Knos as the payer-side referee after the platform's own grader (managed.py).

Both need ANTHROPIC_API_KEY (or another credential the Anthropic SDKs resolve) to run; neither is called anywhere by
default. Their tests use recorded-shape fixtures labelled "synthetic".
"""
