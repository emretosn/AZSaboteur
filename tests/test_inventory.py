"""Tests for the dynamic Ansible inventory generator."""

from __future__ import annotations

import yaml

from saboteur.deploy.inventory import generate_inventory, _ansible_group_name


class TestAnsibleGroupName:
    def test_simple_role(self):
        assert _ansible_group_name("roles/vulnerable-flask-app") == "vulnerable_flask_app"

    def test_no_prefix(self):
        assert _ansible_group_name("keyvault-lax") == "keyvault_lax"

    def test_nested_path(self):
        assert _ansible_group_name("some/deep/roles/nsg-open") == "nsg_open"


class TestGenerateInventory:
    """Test inventory generation from mock Terraform outputs."""

    MOCK_TF_OUTPUTS = {
        "kali_public_ip": {"value": "20.0.0.1"},
        "kali_admin_username": {"value": "kali"},
        "resource_group_name": {"value": "rg-AZSaboteur-test"},
        "chain_outputs": {
            "value": {
                "0": {"private_ip": "10.13.37.20", "vm_id": "/sub/.../vm0"},
                "1": {"key_vault_name": "kv-test", "key_vault_uri": "https://kv-test.vault.azure.net/"},
                "2": {"private_ip": "10.13.37.21", "vm_id": "/sub/.../vm2"},
            },
            "sensitive": True,
        },
    }

    MOCK_CHAIN = [
        {"step": 0, "module_id": "WEB-SSRF", "ansible_role": "roles/vulnerable-flask-app"},
        {"step": 1, "module_id": "STR-KEYVAULT-POLICY", "ansible_role": "roles/keyvault-lax"},
        {"step": 2, "module_id": "NET-MGMT-EXPOSED", "ansible_role": "roles/mgmt-exposed"},
    ]

    MOCK_CREDS = {
        "step_0_username": "svc_deploy",
        "step_0_password": "P@ss1234!",
        "step_1_username": "kv_reader",
        "step_1_password": "KvP@ss!",
        "step_2_username": "webadmin",
        "step_2_password": "W3b@dmin!",
    }

    MOCK_FLAGS = {
        "0": "AZS_F{aaa111}",
        "1": "AZS_F{bbb222}",
        "2": "AZS_F{ccc333}",
    }

    def test_generates_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("saboteur.deploy.inventory.ANSIBLE_DIR", tmp_path)
        path = generate_inventory(
            self.MOCK_TF_OUTPUTS, self.MOCK_CHAIN,
            self.MOCK_CREDS, self.MOCK_FLAGS, "kalipass",
        )
        assert path.exists()
        assert path.name == "hosts.yml"

    def test_vm_host_has_ssh_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr("saboteur.deploy.inventory.ANSIBLE_DIR", tmp_path)
        path = generate_inventory(
            self.MOCK_TF_OUTPUTS, self.MOCK_CHAIN,
            self.MOCK_CREDS, self.MOCK_FLAGS, "kalipass",
        )
        inv = yaml.safe_load(path.read_text())
        host = inv["all"]["children"]["vulnerable_flask_app"]["hosts"]["step_0"]
        assert host["ansible_host"] == "10.13.37.20"
        assert host["ansible_user"] == "svc_deploy"
        assert host["ansible_ssh_pass"] == "P@ss1234!"
        assert "ProxyCommand" in host["ansible_ssh_common_args"]
        assert "20.0.0.1" in host["ansible_ssh_common_args"]
        assert "sshpass -f" in host["ansible_ssh_common_args"]

    def test_non_vm_host_uses_local_connection(self, tmp_path, monkeypatch):
        monkeypatch.setattr("saboteur.deploy.inventory.ANSIBLE_DIR", tmp_path)
        path = generate_inventory(
            self.MOCK_TF_OUTPUTS, self.MOCK_CHAIN,
            self.MOCK_CREDS, self.MOCK_FLAGS, "kalipass",
        )
        inv = yaml.safe_load(path.read_text())
        host = inv["all"]["children"]["keyvault_lax"]["hosts"]["step_1"]
        assert host["ansible_connection"] == "local"
        assert "ansible_host" not in host

    def test_flags_assigned_correctly(self, tmp_path, monkeypatch):
        monkeypatch.setattr("saboteur.deploy.inventory.ANSIBLE_DIR", tmp_path)
        path = generate_inventory(
            self.MOCK_TF_OUTPUTS, self.MOCK_CHAIN,
            self.MOCK_CREDS, self.MOCK_FLAGS, "kalipass",
        )
        inv = yaml.safe_load(path.read_text())
        step0 = inv["all"]["children"]["vulnerable_flask_app"]["hosts"]["step_0"]
        step2 = inv["all"]["children"]["mgmt_exposed"]["hosts"]["step_2"]
        assert step0["flag"] == "AZS_F{aaa111}"
        assert step2["flag"] == "AZS_F{ccc333}"

    def test_extra_outputs_merged(self, tmp_path, monkeypatch):
        monkeypatch.setattr("saboteur.deploy.inventory.ANSIBLE_DIR", tmp_path)
        path = generate_inventory(
            self.MOCK_TF_OUTPUTS, self.MOCK_CHAIN,
            self.MOCK_CREDS, self.MOCK_FLAGS, "kalipass",
        )
        inv = yaml.safe_load(path.read_text())
        kv_host = inv["all"]["children"]["keyvault_lax"]["hosts"]["step_1"]
        assert kv_host["key_vault_name"] == "kv-test"
        assert kv_host["key_vault_uri"] == "https://kv-test.vault.azure.net/"

    def test_all_groups_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr("saboteur.deploy.inventory.ANSIBLE_DIR", tmp_path)
        path = generate_inventory(
            self.MOCK_TF_OUTPUTS, self.MOCK_CHAIN,
            self.MOCK_CREDS, self.MOCK_FLAGS, "kalipass",
        )
        inv = yaml.safe_load(path.read_text())
        groups = set(inv["all"]["children"].keys())
        assert groups == {"vulnerable_flask_app", "keyvault_lax", "mgmt_exposed"}

    def test_empty_chain(self, tmp_path, monkeypatch):
        monkeypatch.setattr("saboteur.deploy.inventory.ANSIBLE_DIR", tmp_path)
        path = generate_inventory(
            self.MOCK_TF_OUTPUTS, [], {}, {}, "kalipass",
        )
        inv = yaml.safe_load(path.read_text())
        assert inv["all"]["children"] == {}
