"""Test helpers built on the fake API."""
from agent_kit.agent import Agent
from agent_kit.demo_app import ChatStore, build_registry
from agent_kit.fake_api import FakeAPI, message, text, tool_turn, tool_use  # noqa: F401
from agent_kit.policy import Policy
from agent_kit.tools import ToolContext


def make_world(replies, *, role="member", policy=None, registry=None, **agent_kw):
    """A store with two users' data, a fake API, an agent and a context for user 1."""
    store = ChatStore()
    mine = store.add(1, "Egg production", ["Eggs dropped 12% last week"])
    other = store.add(2, "Private chat", ["Secret plans"])
    api = FakeAPI(replies)
    agent = Agent(
        api.client, model="claude-sonnet-5-5", registry=registry or build_registry(),
        policy=policy or Policy(), system="You manage chats.", **agent_kw,
    )
    ctx = ToolContext(user_id=1, role=role, services=store)
    return store, mine, other, api, agent, ctx


def ask(agent, ctx, words="hello"):
    return agent.start([{"role": "user", "content": words}], ctx)
