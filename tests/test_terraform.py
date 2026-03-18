"""Tests for Terraform chain generation."""

import json
from pathlib import Path
from textwrap import dedent

from saboteur.deploy.terraform import TerraformRunner, _sanitize_block_name


class TestSanitizeBlockName:
    def test_simple(self):
        assert _sanitize_block_name("WEB-SSRF") == "web_ssrf"

    def test_multiple_hyphens(self):
        assert _sanitize_block_name("IAM-APPREG-SECRET") == "iam_appreg_secret"

    def test_already_lower(self):
        assert _sanitize_block_name("web-ssrf") == "web_ssrf"


class TestGenerateChainTf:
    def test_generates_file(self, tmp_path):
        runner = TerraformRunner(working_dir=tmp_path)
        chain = [
            {
                "module": "modules/web-ssrf",
                "module_id": "WEB-SSRF",
                "step": 0,
                "config": {"resource_prefix": "azs-webssrf-abc123"},
            },
        ]
        result = runner.generate_chain_tf(chain)
        assert result.exists()
        assert result.name == "chain.tf"

    def test_contains_module_block(self, tmp_path):
        runner = TerraformRunner(working_dir=tmp_path)
        chain = [
            {
                "module": "modules/web-ssrf",
                "module_id": "WEB-SSRF",
                "step": 0,
                "config": {"resource_prefix": "azs-webssrf-abc123"},
            },
        ]
        runner.generate_chain_tf(chain)
        content = (tmp_path / "chain.tf").read_text()
        assert 'module "step_0_web_ssrf"' in content
        assert 'source = "./modules/web-ssrf"' in content
        assert "var.chain[0].config.resource_prefix" in content
        assert 'var.flags["0"]' in content

    def test_multiple_steps(self, tmp_path):
        runner = TerraformRunner(working_dir=tmp_path)
        chain = [
            {
                "module": "modules/web-gitexpose",
                "module_id": "WEB-GITEXPOSE",
                "step": 0,
                "config": {"resource_prefix": "azs-webgit-111111"},
            },
            {
                "module": "modules/appreg-secret",
                "module_id": "IAM-APPREG-SECRET",
                "step": 1,
                "config": {"resource_prefix": "azs-appreg-222222"},
            },
            {
                "module": "modules/overperm-sp",
                "module_id": "IAM-OVERPERM-SP",
                "step": 2,
                "config": {"resource_prefix": "azs-overp-333333"},
            },
        ]
        runner.generate_chain_tf(chain)
        content = (tmp_path / "chain.tf").read_text()
        assert 'module "step_0_web_gitexpose"' in content
        assert 'module "step_1_iam_appreg_secret"' in content
        assert 'module "step_2_iam_overperm_sp"' in content

    def test_clean_chain_tf(self, tmp_path):
        runner = TerraformRunner(working_dir=tmp_path)
        chain = [
            {
                "module": "modules/web-ssrf",
                "module_id": "WEB-SSRF",
                "step": 0,
                "config": {"resource_prefix": "azs-test-000000"},
            },
        ]
        runner.generate_chain_tf(chain)
        assert (tmp_path / "chain.tf").exists()
        runner.clean_chain_tf()
        assert not (tmp_path / "chain.tf").exists()

    def test_clean_nonexistent_is_safe(self, tmp_path):
        runner = TerraformRunner(working_dir=tmp_path)
        runner.clean_chain_tf()  # Should not raise

    def test_integration_with_scenario_engine(self, tmp_path):
        """End-to-end: engine generates vars, runner generates chain.tf."""
        from saboteur.modules.catalog import load_catalog
        from saboteur.scenario.engine import ScenarioConfig, ScenarioEngine

        modules_dir = Path(__file__).resolve().parent.parent / "modules"
        catalog = load_catalog(modules_dir)
        engine = ScenarioEngine(catalog, seed=42)
        scenario = engine.generate(ScenarioConfig(chain_length=3, seed=42))

        tf_vars = scenario.to_terraform_vars()
        runner = TerraformRunner(working_dir=tmp_path)
        runner.write_var_file(tf_vars)
        runner.generate_chain_tf(tf_vars["chain"])

        chain_tf = (tmp_path / "chain.tf").read_text()
        tfvars = json.loads((tmp_path / "scenario.auto.tfvars.json").read_text())

        # Every chain step should have a corresponding module block
        for step in tfvars["chain"]:
            block_name = f"step_{step['step']}"
            assert block_name in chain_tf
            assert step["module"] in chain_tf
