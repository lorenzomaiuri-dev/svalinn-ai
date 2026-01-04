from pathlib import Path

import pytest
import yaml

from svalinn_ai.core.prompts import PromptManager


@pytest.fixture
def policy_config(tmp_path):
    # Create a temporary policies.yaml
    policies = {
        "policies": [
            {
                "id": "politics",
                "name": "No Politics",
                "description": "Block all political discussions.",
                "enabled": True,
            },
            {
                "id": "competitors",
                "name": "No Competitors",
                "description": "Block mentions of Rivals.",
                "enabled": False,  # Disabled
            },
        ]
    }

    p_file = tmp_path / "policies.yaml"
    with open(p_file, "w") as f:
        yaml.dump(policies, f)

    # Create dummy prompts.yaml that uses the placeholder
    prompts = {"input_guardian": {"raw": "System Rules:\n{active_policies}\nInput: {raw_input}"}}
    pr_file = tmp_path / "prompts.yaml"
    with open(pr_file, "w") as f:
        yaml.dump(prompts, f)

    return tmp_path


def test_policy_injection(policy_config):
    pm = PromptManager(policy_config)

    raw_prompt = pm.get_input_prompt("raw")

    # 1. Check enabled policy is present
    assert "No Politics" in raw_prompt
    assert "Block all political discussions" in raw_prompt

    # 2. Check disabled policy is ABSENT
    assert "No Competitors" not in raw_prompt

    # 3. Check formatting structure
    assert "   - No Politics:" in raw_prompt


def test_missing_policy_file():
    pm = PromptManager(Path("/non/existent"))
    # Should fallback gracefully
    assert "No specific business policies" in pm.active_policy_string
