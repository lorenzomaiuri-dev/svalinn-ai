import yaml

from svalinn_ai.core.prompts import PromptManager


def test_defaults_load_correctly():
    pm = PromptManager()
    assert "security shield" in pm.get_input_prompt("raw")
    formatted = pm.format_honeypot_prompt("test input")
    assert "test input" in formatted


def test_custom_config(tmp_path):
    # Create fake config
    custom_prompts = {"input_guardian": {"raw": "Custom Raw Prompt"}}
    f = tmp_path / "prompts.yaml"
    with open(f, "w") as file:
        yaml.dump(custom_prompts, file)

    pm = PromptManager(tmp_path)

    # Should use custom
    assert pm.get_input_prompt("raw") == "Custom Raw Prompt"
    # Should fall back to default for others
    assert "security shield" in pm.get_input_prompt("normalized")
