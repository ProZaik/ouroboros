"""Cycle #92 pin: the always-visible ``knowledge_read`` tool description teaches
per-project routing up front, so a task does not have to spend an ACCESS_DENIED
round-trip to discover that a project room's knowledge store is reachable only
through the knowledge tools.

The enforcement half already exists: ``ouroboros/project_facts.py``'s
``project_store_access_block`` emits a typed ``ACCESS_DENIED`` naming
``knowledge_read`` / ``knowledge_write`` when a generic data tool targets a
project store. This pin covers the *teaching* surface — the description the
model always sees at ``knowledge_read`` registration.

Non-vacuity (neuter/restore protocol): editing the guidance clause out of the
``knowledge_read`` description in ``ouroboros/tools/knowledge.py`` turns
``test_knowledge_read_description_names_per_project_routing`` red; restoring it
turns it green.

Out of scope, deliberately: a test cannot assert that an LLM *chooses*
``knowledge_read`` (that is a prose classifier over behavior, BIBLE P5). It can
only pin the guidance text that steers the choice.
"""

from ouroboros.tools.knowledge import get_tools


def _knowledge_read_description() -> str:
    entries = [e for e in get_tools() if e.name == "knowledge_read"]
    assert entries, "knowledge_read is not registered"
    return entries[0].schema["description"]


def test_knowledge_read_description_names_per_project_routing():
    desc = _knowledge_read_description()
    # The per-project scope grammar, verbatim as the scope parameter documents it.
    assert "project:<exact project id>" in desc
    # The denial of generic data tools for project stores is stated.
    assert "denied" in desc.lower()
    # The remedy is named: the knowledge tools themselves.
    assert "knowledge tools" in desc.lower()


def test_knowledge_read_description_still_documents_its_core_contract():
    desc = _knowledge_read_description()
    # The original contract must survive the additive clause.
    assert "canonical address" in desc
    assert "source revision" in desc
